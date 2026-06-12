from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.models import TradeLog, ActionLog, User
from app.core.dependencies import get_current_user

router = APIRouter()

@router.get("")
def get_trade_logs(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    logs = db.query(TradeLog)\
             .filter(TradeLog.user_id == current_user.id)\
             .order_by(TradeLog.executed_at.desc())\
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
