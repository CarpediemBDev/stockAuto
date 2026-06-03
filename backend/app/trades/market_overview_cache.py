import asyncio
import threading
from app.core.models import utc_now_naive

from sqlalchemy.orm import Session

from app.core import models
from app.core.database import SessionLocal
from app.core.logging import logger
from app.scanner.data_provider import fetch_ohlcv
from app.scanner.scanner import check_market_sentiment

MARKET_OVERVIEW_TASK_TIMEOUT_SECONDS = 8.0
SYNC_STATUS_FRESH = "fresh"
SYNC_STATUS_STALE = "stale"
SYNC_STATUS_FAILED = "failed"

_market_overview_cache_lock = threading.RLock()
_market_overview_cache: dict | None = None
_market_overview_refresh_lock = threading.Lock()
_market_overview_refresh_in_progress = False


async def _fetch_with_timeout(coro, label: str):
    try:
        return await asyncio.wait_for(coro, timeout=MARKET_OVERVIEW_TASK_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.warning(
            "[Market] %s fetch timed out after %.1fs",
            label,
            MARKET_OVERVIEW_TASK_TIMEOUT_SECONDS,
        )
        return None
    except Exception as exc:
        logger.warning("[Market] %s fetch failed: %s", label, exc)
        return None


async def get_ticker_summary(ticker_symbol: str):
    """특정 티커의 현재가와 전일 대비 등락 정보를 가져옵니다."""
    try:
        df = await fetch_ohlcv(ticker_symbol, interval="1d", period="10d")
        if df.empty or len(df) < 2:
            return None

        current = float(df["Close"].iloc[-1])
        prev = float(df["Close"].iloc[-2])
        change = current - prev
        change_pct = (change / prev) * 100 if prev else 0.0

        return {
            "symbol": ticker_symbol,
            "current": round(current, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
        }
    except Exception as exc:
        logger.warning("[Market] Error fetching %s summary: %s", ticker_symbol, exc)
        return None


def _get_latest_snapshot(db: Session) -> models.MarketOverviewSnapshot | None:
    return (
        db.query(models.MarketOverviewSnapshot)
        .order_by(models.MarketOverviewSnapshot.created_at.desc(), models.MarketOverviewSnapshot.id.desc())
        .first()
    )


def _ticker_from_snapshot(snapshot: models.MarketOverviewSnapshot, prefix: str) -> dict | None:
    current = getattr(snapshot, f"{prefix}_current")
    if current is None:
        return None
    return {
        "symbol": getattr(snapshot, f"{prefix}_symbol"),
        "current": current,
        "change": getattr(snapshot, f"{prefix}_change"),
        "change_pct": getattr(snapshot, f"{prefix}_change_pct"),
        "sync_status": getattr(snapshot, f"{prefix}_sync_status"),
    }


def _snapshot_to_response(snapshot: models.MarketOverviewSnapshot) -> dict:
    return {
        "market_condition": snapshot.market_condition,
        "sentiment": snapshot.market_condition,
        "market_condition_sync_status": snapshot.market_condition_sync_status,
        "nasdaq": _ticker_from_snapshot(snapshot, "nasdaq"),
        "exchange_rate": _ticker_from_snapshot(snapshot, "exchange_rate"),
        "timestamp": snapshot.created_at.isoformat() if snapshot.created_at else utc_now_naive().isoformat(),
    }


def _default_response() -> dict:
    return {
        "market_condition": "NEUTRAL",
        "sentiment": "NEUTRAL",
        "market_condition_sync_status": SYNC_STATUS_FAILED,
        "nasdaq": None,
        "exchange_rate": None,
        "timestamp": utc_now_naive().isoformat(),
    }


def _set_memory_cache(data: dict) -> None:
    global _market_overview_cache
    with _market_overview_cache_lock:
        _market_overview_cache = data.copy()


def clear_market_overview_memory_cache() -> None:
    global _market_overview_cache
    with _market_overview_cache_lock:
        _market_overview_cache = None


def get_cached_market_overview(db: Session | None = None) -> dict:
    with _market_overview_cache_lock:
        if _market_overview_cache is not None:
            return _market_overview_cache.copy()

    owns_session = db is None
    session = db or SessionLocal()
    try:
        snapshot = _get_latest_snapshot(session)
        if snapshot is None:
            data = _default_response()
        else:
            data = _snapshot_to_response(snapshot)
        _set_memory_cache(data)
        return data
    finally:
        if owns_session:
            session.close()


def _resolved_market_condition(value: str | None, previous: models.MarketOverviewSnapshot | None) -> tuple[str, str]:
    if value:
        return value, SYNC_STATUS_FRESH
    if previous:
        return previous.market_condition, SYNC_STATUS_STALE
    return "NEUTRAL", SYNC_STATUS_FAILED


def _resolved_ticker(value: dict | None, previous: models.MarketOverviewSnapshot | None, prefix: str) -> tuple[dict | None, str]:
    if value:
        return value, SYNC_STATUS_FRESH
    if previous:
        previous_value = _ticker_from_snapshot(previous, prefix)
        if previous_value:
            previous_value["sync_status"] = SYNC_STATUS_STALE
            return previous_value, SYNC_STATUS_STALE
    return None, SYNC_STATUS_FAILED


def _ticker_columns(ticker: dict | None, prefix: str, sync_status: str) -> dict:
    return {
        f"{prefix}_symbol": ticker["symbol"] if ticker else "^IXIC" if prefix == "nasdaq" else "USDKRW=X",
        f"{prefix}_current": ticker["current"] if ticker else None,
        f"{prefix}_change": ticker["change"] if ticker else None,
        f"{prefix}_change_pct": ticker["change_pct"] if ticker else None,
        f"{prefix}_sync_status": sync_status,
    }


async def refresh_market_overview_snapshot(db: Session | None = None) -> dict:
    global _market_overview_refresh_in_progress
    with _market_overview_refresh_lock:
        if _market_overview_refresh_in_progress:
            logger.info("[Market] Previous overview refresh still running. Skipping duplicate refresh.")
            return get_cached_market_overview(db)
        _market_overview_refresh_in_progress = True

    owns_session = db is None
    session = db or SessionLocal()
    try:
        previous = _get_latest_snapshot(session)
        market_condition_raw, nasdaq_raw, exchange_rate_raw = await asyncio.gather(
            _fetch_with_timeout(check_market_sentiment(), "market condition"),
            _fetch_with_timeout(get_ticker_summary("^IXIC"), "NASDAQ"),
            _fetch_with_timeout(get_ticker_summary("USDKRW=X"), "USD/KRW"),
        )

        market_condition, market_condition_sync_status = _resolved_market_condition(
            market_condition_raw,
            previous,
        )
        nasdaq, nasdaq_sync_status = _resolved_ticker(nasdaq_raw, previous, "nasdaq")
        exchange_rate, exchange_rate_sync_status = _resolved_ticker(
            exchange_rate_raw,
            previous,
            "exchange_rate",
        )

        snapshot = models.MarketOverviewSnapshot(
            market_condition=market_condition,
            market_condition_sync_status=market_condition_sync_status,
            **_ticker_columns(nasdaq, "nasdaq", nasdaq_sync_status),
            **_ticker_columns(exchange_rate, "exchange_rate", exchange_rate_sync_status),
        )
        session.add(snapshot)
        session.commit()
        session.refresh(snapshot)

        data = _snapshot_to_response(snapshot)
        _set_memory_cache(data)
        return data
    except Exception:
        session.rollback()
        logger.exception("[Market] Failed to refresh market overview snapshot")
        return get_cached_market_overview(session)
    finally:
        if owns_session:
            session.close()
        with _market_overview_refresh_lock:
            _market_overview_refresh_in_progress = False


def market_overview_cache_wrapper() -> None:
    try:
        asyncio.run(refresh_market_overview_snapshot())
    except RuntimeError:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(refresh_market_overview_snapshot())
        else:
            loop.run_until_complete(refresh_market_overview_snapshot())
