import re
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.models import TradeLog, ActionLog, User
from app.core.dependencies import get_current_user

from app.core.response import SuccessResponseRoute
router = APIRouter(route_class=SuccessResponseRoute)

# 증권사 응답의 거래소 접두("NAS_AAPL")를 떼어내는 정규식.
# DB(holdings·trade_logs)의 티커는 접두 없는 형태가 단일 기준이고, 프런트도 카드에서
# 같은 규칙으로 잘라 쓴다(PortfolioView의 cleanTicker). 필터 입력만 관대하게 받아
# 어느 쪽 표기로 물어봐도 같은 원장을 가리키게 한다.
_BROKER_PREFIX = re.compile(r"^[A-Z0-9]+_")


def normalize_ticker(raw: str) -> str:
    """조회용 티커 정규화. 대문자로 올리고 거래소 접두를 제거한다."""
    return _BROKER_PREFIX.sub("", raw.strip().upper())


@router.get("")
def get_trade_logs(
    skip: int = 0,
    limit: int = 100,
    # Annotated로 다는 이유는 기본값을 진짜 None으로 남기기 위함이다. Query(default=None)을
    # 기본값 자리에 두면 함수를 직접 호출하는 경로(테스트·내부 재사용)에서 Query 객체가
    # 그대로 들어와 문자열로 다뤄지다 터진다.
    ticker: Annotated[
        str | None,
        Query(description="특정 종목의 체결 이력만 조회. 접두 유무는 무관하다(AAPL == NAS_AAPL)"),
    ] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(TradeLog).filter(TradeLog.user_id == current_user.id)
    if ticker:
        # 빈 문자열·공백만 들어오면 필터를 걸지 않는다(전체 조회와 동일). 정규화 결과가
        # 비면 어떤 행과도 매칭되지 않아 "이력 없음"으로 오인될 수 있기 때문이다.
        normalized = normalize_ticker(ticker)
        if normalized:
            query = query.filter(TradeLog.ticker == normalized)

    logs = query.order_by(TradeLog.executed_at.desc())\
                .offset(skip)\
                .limit(limit)\
                .all()
    return logs

@router.get("/actions")
def get_action_logs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """현재 사용자의 봇 활동 로그를 최신순으로 20개 반환합니다."""
    return db.query(ActionLog)\
             .filter(ActionLog.user_id == current_user.id)\
             .order_by(ActionLog.created_at.desc())\
             .limit(20)\
             .all()
