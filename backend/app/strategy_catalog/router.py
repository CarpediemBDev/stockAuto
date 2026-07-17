from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.models import Strategy
from typing import List, Dict, Any
from app.core.response import SuccessResponseRoute

router = APIRouter(route_class=SuccessResponseRoute)

@router.get("/catalog", summary="Get Selectable Strategy Catalog")
async def get_strategies(
    db: Session = Depends(get_db)
):
    """
    사용자가 선택할 수 있는 전략 카탈로그 목록을 반환합니다.
    (is_active=True 이면서 is_selectable=True 인 전략들만 반환, sort_order 오름차순 정렬)
    응답 포맷은 app.core.response_formatter.SuccessResponseRoute 에 의해 자동 포장됩니다.
    """
    strategies = (
        db.query(Strategy)
        .filter(Strategy.is_active == True, Strategy.is_selectable == True)
        .order_by(Strategy.sort_order.asc())
        .all()
    )
    
    result = []
    for s in strategies:
        result.append({
            "id": s.strategy_type,
            "name": s.name_ko,
            "name_en": s.name_en,
            "description": s.description,
            "tier": s.tier,
            "regime": s.regime,
            "summary_ko": s.summary_ko,
            "sort_order": s.sort_order
        })
        
    return result
