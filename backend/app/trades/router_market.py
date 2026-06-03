from fastapi import APIRouter
from app.core.response import success_response
from app.trades.market_overview_cache import get_cached_market_overview

router = APIRouter(tags=["Market"])

@router.get("/overview")
async def get_market_overview():
    """캐시된 나스닥, 환율, 시장 상태를 즉시 반환합니다."""
    return success_response(data=get_cached_market_overview())
