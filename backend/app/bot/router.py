from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.models import BotStatus
from datetime import datetime
from app.core.config import settings

router = APIRouter()

@router.get("/status")
def get_bot_status(db: Session = Depends(get_db)):
    status = db.query(BotStatus).first()
    if not status:
        status = BotStatus(is_running=False)
        db.add(status)
        db.commit()
        db.refresh(status)
    return {
        "is_running": status.is_running, 
        "is_real_enabled": status.is_real_enabled,
        "updated_at": status.updated_at,
        "trade_mode": settings.TRADE_MODE,
        "is_real": settings.IS_REAL
    }

@router.post("/toggle-real")
def toggle_real_enabled(db: Session = Depends(get_db)):
    status = db.query(BotStatus).first()
    if not status:
        status = BotStatus(is_running=False, is_real_enabled=True)
        db.add(status)
    else:
        status.is_real_enabled = not status.is_real_enabled
        status.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Real trading enabled toggled", "is_real_enabled": status.is_real_enabled}

@router.post("/start")
def start_bot(db: Session = Depends(get_db)):
    status = db.query(BotStatus).first()
    if not status:
        status = BotStatus(is_running=True)
        db.add(status)
    else:
        status.is_running = True
        status.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Bot started", "is_running": True}

@router.post("/stop")
def stop_bot(db: Session = Depends(get_db)):
    status = db.query(BotStatus).first()
    if not status:
        status = BotStatus(is_running=False)
        db.add(status)
    else:
        status.is_running = False
        status.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Bot stopped", "is_running": False}
