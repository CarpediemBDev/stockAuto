import asyncio
import json
import threading
import time

from sqlalchemy.orm import Session

from app.core import models
from app.core.database import SessionLocal
from app.core.logging import logger
from app.scanner.swing_predictor import scan_next_day_candidates

SWING_SYNC_EMPTY = "empty"
SWING_SYNC_FAILED = "failed"
SWING_SYNC_FRESH = "fresh"
SWING_SYNC_REFRESHING = "refreshing"
SWING_SYNC_STALE = "stale"

DEFAULT_SWING_POOL = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "NFLX", "AMD",
    "PLTR", "SMCI", "ARM", "QCOM", "MU", "INTC", "ASML", "TSM", "LRCX", "AMAT",
    "COIN", "MSTR", "MARA", "RIOT", "HOOD", "SQ", "PYPL", "SOFI", "AFRM", "UPST",
    "CRWD", "PANW", "ZS", "NET", "SNOW", "DDOG", "NOW", "CRM", "ADBE", "INTU",
    "LLY", "NVO", "V", "MA", "JPM", "WMT", "COST", "HD", "UBER", "ABNB",
    "RIVN", "LCID", "CVNA", "ROKU", "DOCU", "ZM", "GME", "AMC", "DKNG", "PENN",
    # Penny / Small-cap / Meme stocks (1$ 미만/소형주)
    "AKAN", "WNW", "ASTC", "SDA", "HUBC", "MNTS", "ITP", "SES", "AEHL", "ODYS", 
    "PRFX", "FFIE", "GWAV", "CRKN", "HOLO", "KOSS", "PEGY", "SINT", "LUNR"
]

_swing_prediction_cache_lock = threading.RLock()
_swing_prediction_cache: dict[tuple[str, ...], dict] = {}
_swing_prediction_refresh_lock = threading.Lock()
_swing_prediction_refreshing: set[tuple[str, ...]] = set()


def get_swing_cache_key(user_tickers: list[str]) -> tuple[str, ...]:
    return tuple(sorted(set(user_tickers + DEFAULT_SWING_POOL)))


def serialize_swing_cache_key(cache_key: tuple[str, ...]) -> str:
    return "|".join(cache_key)


def empty_swing_response(sync_status: str = SWING_SYNC_EMPTY) -> dict:
    return {
        "candidates": [],
        "sync_status": sync_status,
        "updated_at": None,
    }


def get_latest_swing_snapshot(db: Session, cache_key: tuple[str, ...]) -> models.SwingPredictionSnapshot | None:
    return (
        db.query(models.SwingPredictionSnapshot)
        .filter(models.SwingPredictionSnapshot.cache_key == serialize_swing_cache_key(cache_key))
        .order_by(models.SwingPredictionSnapshot.created_at.desc(), models.SwingPredictionSnapshot.id.desc())
        .first()
    )


def snapshot_to_swing_response(snapshot: models.SwingPredictionSnapshot, sync_status: str | None = None) -> dict:
    try:
        candidates = json.loads(snapshot.candidates_json)
    except json.JSONDecodeError:
        candidates = []
    return {
        "candidates": candidates,
        "sync_status": sync_status or snapshot.sync_status,
        "updated_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
    }


def read_swing_prediction_cache(cache_key: tuple[str, ...], db: Session) -> dict:
    with _swing_prediction_cache_lock:
        cached = _swing_prediction_cache.get(cache_key)
        if cached:
            response = {
                "candidates": list(cached["candidates"]),
                "sync_status": cached["sync_status"],
                "updated_at": cached["updated_at"],
            }
            if is_swing_prediction_refreshing(cache_key):
                response["sync_status"] = SWING_SYNC_REFRESHING
            return response

    snapshot = get_latest_swing_snapshot(db, cache_key)
    if not snapshot:
        response = empty_swing_response()
        if is_swing_prediction_refreshing(cache_key):
            response["sync_status"] = SWING_SYNC_REFRESHING
            write_swing_prediction_cache(cache_key, response["candidates"], response["sync_status"], response["updated_at"])
        return response

    response = snapshot_to_swing_response(snapshot, SWING_SYNC_STALE)
    if is_swing_prediction_refreshing(cache_key):
        response["sync_status"] = SWING_SYNC_REFRESHING
    write_swing_prediction_cache(cache_key, response["candidates"], response["sync_status"], response["updated_at"])
    return response


def write_swing_prediction_cache(cache_key: tuple[str, ...], candidates: list, sync_status: str, updated_at: str | None) -> None:
    with _swing_prediction_cache_lock:
        _swing_prediction_cache[cache_key] = {
            "candidates": list(candidates),
            "sync_status": sync_status,
            "updated_at": updated_at,
            "timestamp": time.time(),
        }


def write_swing_prediction_snapshot(db: Session, cache_key: tuple[str, ...], candidates: list, sync_status: str) -> models.SwingPredictionSnapshot:
    snapshot = models.SwingPredictionSnapshot(
        cache_key=serialize_swing_cache_key(cache_key),
        ticker_universe=json.dumps(list(cache_key), ensure_ascii=False),
        candidates_json=json.dumps(candidates, ensure_ascii=False),
        sync_status=sync_status,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def clear_swing_prediction_cache() -> None:
    with _swing_prediction_cache_lock:
        _swing_prediction_cache.clear()
    with _swing_prediction_refresh_lock:
        _swing_prediction_refreshing.clear()


def reserve_swing_prediction_refresh(cache_key: tuple[str, ...]) -> bool:
    with _swing_prediction_refresh_lock:
        if cache_key in _swing_prediction_refreshing:
            return False
        _swing_prediction_refreshing.add(cache_key)
        return True


def release_swing_prediction_refresh(cache_key: tuple[str, ...]) -> None:
    with _swing_prediction_refresh_lock:
        _swing_prediction_refreshing.discard(cache_key)


def is_swing_prediction_refreshing(cache_key: tuple[str, ...]) -> bool:
    with _swing_prediction_refresh_lock:
        return cache_key in _swing_prediction_refreshing


def refreshing_swing_response(cache_key: tuple[str, ...], db: Session) -> dict:
    cached = read_swing_prediction_cache(cache_key, db)
    cached["sync_status"] = SWING_SYNC_REFRESHING
    write_swing_prediction_cache(cache_key, cached["candidates"], cached["sync_status"], cached["updated_at"])
    return cached


async def refresh_swing_prediction_cache(
    cache_key: tuple[str, ...],
    db: Session | None = None,
    refresh_reserved: bool = False,
) -> dict:
    owns_session = db is None
    session = db or SessionLocal()
    if not refresh_reserved and not reserve_swing_prediction_refresh(cache_key):
        try:
            return refreshing_swing_response(cache_key, session)
        finally:
            if owns_session:
                session.close()
    refreshing_swing_response(cache_key, session)

    try:
        candidates = await scan_next_day_candidates(list(cache_key))
        snapshot = write_swing_prediction_snapshot(session, cache_key, candidates, SWING_SYNC_FRESH)
        response = snapshot_to_swing_response(snapshot)
        write_swing_prediction_cache(cache_key, response["candidates"], response["sync_status"], response["updated_at"])
        logger.info("[SwingPrediction] Refresh complete. Cached %s candidates.", len(candidates))
        return response
    except Exception:
        session.rollback()
        logger.exception("[SwingPrediction] Failed to refresh swing prediction cache")
        cached = read_swing_prediction_cache(cache_key, session)
        if cached["candidates"]:
            cached["sync_status"] = SWING_SYNC_STALE
            write_swing_prediction_cache(cache_key, cached["candidates"], cached["sync_status"], cached["updated_at"])
            return cached
        failed_response = empty_swing_response(SWING_SYNC_FAILED)
        write_swing_prediction_cache(cache_key, failed_response["candidates"], failed_response["sync_status"], failed_response["updated_at"])
        return failed_response
    finally:
        release_swing_prediction_refresh(cache_key)
        if owns_session:
            session.close()


def swing_prediction_cache_wrapper() -> None:
    try:
        asyncio.run(refresh_swing_prediction_cache(get_swing_cache_key([])))
    except RuntimeError:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(refresh_swing_prediction_cache(get_swing_cache_key([])))
        else:
            loop.run_until_complete(refresh_swing_prediction_cache(get_swing_cache_key([])))
