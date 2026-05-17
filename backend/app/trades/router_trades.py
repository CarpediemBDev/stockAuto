from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.models import TradeLog, ActionLog

router = APIRouter()

@router.get("/")
def get_trade_logs(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    logs = db.query(TradeLog).order_by(TradeLog.executed_at.desc()).offset(skip).limit(limit).all()
    return logs

@router.get("/actions")
def get_action_logs(db: Session = Depends(get_db)):
    """봇의 실시간 활동 로그를 최신순으로 20개 반환합니다."""
    return db.query(ActionLog).order_by(ActionLog.created_at.desc()).limit(20).all()
