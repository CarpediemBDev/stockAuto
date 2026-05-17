from fastapi import APIRouter
import app.bot.scheduler as scheduler_mod
from app.core.exceptions import StockAutoException
from app.core.response import success_response
from app.scanner.scanner import scan_overseas_market

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
