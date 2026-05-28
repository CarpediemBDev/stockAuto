from fastapi import APIRouter, Depends
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
    return success_response(data=signals)

@router.get("/swing-predict")
async def get_swing_prediction(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """내일 세력돌파 및 스윙 상승 가능성이 있는 TOP 5 종목군을 진단합니다."""
    # 1. 유저 관심종목 수집
    watchlist_items = db.query(models.WatchList).filter(models.WatchList.user_id == current_user.id).all()
    user_tickers = [item.ticker for item in watchlist_items]
    
    # 2. 시장 주도 우량주 기본 수령 풀과 결합하여 감시 리스트 셋업 (De-duplication)
    default_pool = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "NFLX", "AMD", "PLTR", "SMCI"]
    combined_tickers = list(set(user_tickers + default_pool))
    
    # 3. 누적 일봉 스윙 예측 모듈 기동
    candidates = await scan_next_day_candidates(combined_tickers)
    
    return success_response(data=candidates)

