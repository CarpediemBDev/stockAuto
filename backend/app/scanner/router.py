from fastapi import APIRouter, Depends, BackgroundTasks
import app.bot.scheduler as scheduler_mod
from app.core.exceptions import StockAutoException
from app.core.logging import logger
from app.core import models
from app.core.dependencies import get_current_user
from app.core.database import get_db
from sqlalchemy.orm import Session
from app.scanner.swing_prediction_cache import (
    get_swing_cache_key,
    read_swing_prediction_cache,
    refresh_swing_prediction_cache,
    refreshing_swing_response,
    release_swing_prediction_refresh,
    reserve_swing_prediction_refresh,
)
import asyncio
import threading

from app.core.response import SuccessResponseRoute
router = APIRouter(route_class=SuccessResponseRoute)

@router.get("/latest")
async def get_latest_signals(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """공용 상위 신호와 로그인 사용자의 관심종목 신호를 반환합니다."""
    if not hasattr(scheduler_mod, 'latest_scanned_signals'):
        raise StockAutoException(code="SCHEDULER_NOT_READY", message="스캐너 엔진이 아직 준비되지 않았습니다.", status_code=503)

    market_signals = scheduler_mod.latest_scanned_signals
    watchlists_by_user = scheduler_mod.load_watchlist_tickers_by_user(
        db,
        [current_user.id],
    )
    _, user_signals = scheduler_mod.build_user_signal_context(
        current_user.id,
        market_signals,
        watchlists_by_user,
        scheduler_mod.latest_watchlist_signals,
    )

    top_market_tickers = {
        signal.get("ticker")
        for signal in sorted(
            market_signals,
            key=lambda item: item.get("signal_score", 0),
            reverse=True,
        )[:10]
    }
    result = [
        signal
        for signal in sorted(
            user_signals,
            key=lambda item: item.get("signal_score", 0),
            reverse=True,
        )
        if signal.get("ticker") in top_market_tickers
        or "WATCHLIST" in signal.get("source", [])
    ]
    is_scanning = (
        getattr(scheduler_mod, "is_manual_scanning", False)
        or scheduler_mod.is_scanner_refresh_in_progress()
    )
    return {"is_scanning": is_scanning, "signals": result}

async def background_scan_overseas():
    """예약 스캔과 동일한 단일 실행 가드로 수동 스캔을 수행합니다."""
    scheduler_mod.is_manual_scanning = True
    try:
        await scheduler_mod.refresh_scanner_cache(force=True)
    except Exception as e:
        logger.error(f"[ManualScan] 백그라운드 스캔 중 오류 발생: {e}", exc_info=True)
    finally:
        scheduler_mod.is_manual_scanning = False


def background_refresh_swing_prediction(cache_key: tuple[str, ...]) -> None:
    """HTTP 응답 루프와 분리된 스레드에서 스윙 예측 캐시를 갱신합니다."""
    try:
        asyncio.run(refresh_swing_prediction_cache(cache_key, None, True))
    except Exception:
        release_swing_prediction_refresh(cache_key)
        logger.exception("[SwingPrediction] Background refresh thread failed unexpectedly")

@router.post("/overseas")
async def trigger_overseas_scan(
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user)
):
    """수동으로 해외 마켓 스캔을 트리거합니다. (비동기 처리)"""
    background_tasks.add_task(background_scan_overseas)
    return {"message": "해외 마켓 스캔이 백그라운드에서 시작되었습니다."}

@router.get("/swing-predict")
async def get_swing_prediction(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """캐시된 스윙 예측 후보를 즉시 반환합니다."""
    return read_swing_prediction_cache(get_swing_cache_key(), db)


@router.post("/swing-predict/refresh")
async def refresh_swing_prediction(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """내일 세력돌파 및 스윙 상승 가능성이 있는 TOP 5 종목군을 수동 갱신합니다."""
    cache_key = get_swing_cache_key()
    if reserve_swing_prediction_refresh(cache_key):
        refreshing_swing_response(cache_key, db)
        threading.Thread(
            target=background_refresh_swing_prediction,
            args=(cache_key,),
            daemon=True,
        ).start()
    return {
        "data": refreshing_swing_response(cache_key, db),
        "message": "스윙 예측 갱신이 백그라운드에서 시작되었습니다.",
    }
