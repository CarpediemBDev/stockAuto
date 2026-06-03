from fastapi import APIRouter, Depends
import json
import threading
import time
import app.bot.scheduler as scheduler_mod
from app.core.exceptions import StockAutoException
from app.core.response import success_response
from app.scanner.scanner import scan_overseas_market
from app.core import models
from app.core.dependencies import get_current_user
from app.core.database import get_db
from sqlalchemy.orm import Session
from app.scanner.swing_predictor import scan_next_day_candidates

router = APIRouter()
_swing_prediction_cache_lock = threading.RLock()
_swing_prediction_cache: dict[tuple[str, ...], dict] = {}
_swing_prediction_refresh_lock = threading.Lock()
_swing_prediction_refreshing: set[tuple[str, ...]] = set()

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
]


def _get_swing_cache_key(user_tickers: list[str]) -> tuple[str, ...]:
    return tuple(sorted(set(user_tickers + DEFAULT_SWING_POOL)))


def _serialize_swing_cache_key(cache_key: tuple[str, ...]) -> str:
    return "|".join(cache_key)


def _empty_swing_response(sync_status: str = SWING_SYNC_EMPTY) -> dict:
    return {
        "candidates": [],
        "sync_status": sync_status,
        "updated_at": None,
    }


def _get_latest_swing_snapshot(db: Session, cache_key: tuple[str, ...]) -> models.SwingPredictionSnapshot | None:
    return (
        db.query(models.SwingPredictionSnapshot)
        .filter(models.SwingPredictionSnapshot.cache_key == _serialize_swing_cache_key(cache_key))
        .order_by(models.SwingPredictionSnapshot.created_at.desc(), models.SwingPredictionSnapshot.id.desc())
        .first()
    )


def _snapshot_to_swing_response(snapshot: models.SwingPredictionSnapshot, sync_status: str | None = None) -> dict:
    try:
        candidates = json.loads(snapshot.candidates_json)
    except json.JSONDecodeError:
        candidates = []
    return {
        "candidates": candidates,
        "sync_status": sync_status or snapshot.sync_status,
        "updated_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
    }


def _read_swing_prediction_cache(cache_key: tuple[str, ...], db: Session) -> dict:
    with _swing_prediction_cache_lock:
        cached = _swing_prediction_cache.get(cache_key)
        if cached:
            return {
                "candidates": list(cached["candidates"]),
                "sync_status": cached["sync_status"],
                "updated_at": cached["updated_at"],
            }

    snapshot = _get_latest_swing_snapshot(db, cache_key)
    if not snapshot:
        return _empty_swing_response()

    response = _snapshot_to_swing_response(snapshot, SWING_SYNC_STALE)
    _write_swing_prediction_cache(cache_key, response["candidates"], response["sync_status"], response["updated_at"])
    return response


def _write_swing_prediction_cache(cache_key: tuple[str, ...], candidates: list, sync_status: str, updated_at: str | None) -> None:
    with _swing_prediction_cache_lock:
        _swing_prediction_cache[cache_key] = {
            "candidates": list(candidates),
            "sync_status": sync_status,
            "updated_at": updated_at,
            "timestamp": time.time(),
        }


def _write_swing_prediction_snapshot(db: Session, cache_key: tuple[str, ...], candidates: list, sync_status: str) -> models.SwingPredictionSnapshot:
    snapshot = models.SwingPredictionSnapshot(
        cache_key=_serialize_swing_cache_key(cache_key),
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

@router.get("/latest")
async def get_latest_signals():
    """봇이 마지막으로 스캔한 상위 시그널 리스트를 반환합니다."""
    if not hasattr(scheduler_mod, 'latest_scanned_signals'):
        raise StockAutoException(code="SCHEDULER_NOT_READY", message="스캐너 엔진이 아직 준비되지 않았습니다.", status_code=503)
    
    signals = scheduler_mod.latest_scanned_signals
    if not signals:
        return success_response(data=[])
    
    # 점수 높은 순 정렬 (데이터가 있을 때만)
    result = sorted(signals, key=lambda x: x.get('signal_score', 0), reverse=True)[:10]
    return success_response(data=result)

@router.get("/overseas")
async def get_overseas_scan():
    """수동으로 해외 마켓 스캔을 트리거합니다. (디버깅용)"""
    signals = await scan_overseas_market()
    scheduler_mod.latest_scanned_signals = signals
    return success_response(data=signals)

@router.get("/swing-predict")
async def get_swing_prediction(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """캐시된 스윙 예측 후보를 즉시 반환합니다."""
    watchlist_items = db.query(models.WatchList).filter(models.WatchList.user_id == current_user.id).all()
    user_tickers = [item.ticker for item in watchlist_items]
    return success_response(data=_read_swing_prediction_cache(_get_swing_cache_key(user_tickers), db))


@router.get("/swing-predict/refresh")
async def refresh_swing_prediction(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """내일 세력돌파 및 스윙 상승 가능성이 있는 TOP 5 종목군을 수동 갱신합니다."""
    watchlist_items = db.query(models.WatchList).filter(models.WatchList.user_id == current_user.id).all()
    user_tickers = [item.ticker for item in watchlist_items]
    cache_key = _get_swing_cache_key(user_tickers)
    with _swing_prediction_refresh_lock:
        if cache_key in _swing_prediction_refreshing:
            cached = _read_swing_prediction_cache(cache_key, db)
            cached["sync_status"] = SWING_SYNC_REFRESHING
            return success_response(data=cached)
        _swing_prediction_refreshing.add(cache_key)

    try:
        candidates = await scan_next_day_candidates(list(cache_key))
        snapshot = _write_swing_prediction_snapshot(db, cache_key, candidates, SWING_SYNC_FRESH)
        response = _snapshot_to_swing_response(snapshot)
        _write_swing_prediction_cache(cache_key, response["candidates"], response["sync_status"], response["updated_at"])
        return success_response(data=response)
    except Exception:
        db.rollback()
        cached = _read_swing_prediction_cache(cache_key, db)
        if cached["candidates"]:
            cached["sync_status"] = SWING_SYNC_STALE
            return success_response(data=cached)
        return success_response(data=_empty_swing_response(SWING_SYNC_FAILED))
    finally:
        with _swing_prediction_refresh_lock:
            _swing_prediction_refreshing.discard(cache_key)
