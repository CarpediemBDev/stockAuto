from fastapi import APIRouter, Depends, BackgroundTasks
import app.bot.scheduler as scheduler_mod
from app.core.exceptions import StockAutoException
from app.core.response import success_response
from app.core.logging import logger
from app.scanner.scanner import scan_overseas_market
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

router = APIRouter()

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

async def background_scan_overseas():
    """백그라운드에서 스캔을 수행하고 전역 캐시를 업데이트합니다."""
    signals = await scan_overseas_market()
    scheduler_mod.latest_scanned_signals = signals


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
    return success_response(message="해외 마켓 스캔이 백그라운드에서 시작되었습니다.")

@router.get("/swing-predict")
async def get_swing_prediction(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """캐시된 스윙 예측 후보를 즉시 반환합니다."""
    watchlist_items = db.query(models.WatchList).filter(models.WatchList.user_id == current_user.id).all()
    user_tickers = [item.ticker for item in watchlist_items]
    return success_response(data=read_swing_prediction_cache(get_swing_cache_key(user_tickers), db))


@router.post("/swing-predict/refresh")
async def refresh_swing_prediction(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """내일 세력돌파 및 스윙 상승 가능성이 있는 TOP 5 종목군을 수동 갱신합니다."""
    watchlist_items = db.query(models.WatchList).filter(models.WatchList.user_id == current_user.id).all()
    user_tickers = [item.ticker for item in watchlist_items]
    cache_key = get_swing_cache_key(user_tickers)
    if reserve_swing_prediction_refresh(cache_key):
        refreshing_swing_response(cache_key, db)
        threading.Thread(
            target=background_refresh_swing_prediction,
            args=(cache_key,),
            daemon=True,
        ).start()
    return success_response(
        data=refreshing_swing_response(cache_key, db),
        message="스윙 예측 갱신이 백그라운드에서 시작되었습니다.",
    )
