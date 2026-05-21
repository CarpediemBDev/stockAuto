from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.models import User, UserSettings
from datetime import datetime
from app.core.dependencies import get_current_user

router = APIRouter()

@router.get("/status")
def get_bot_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    settings = current_user.settings
    if not settings:
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
        
    return {
        "is_running": settings.is_running, 
        "is_real_enabled": settings.is_real_enabled,
        "updated_at": settings.updated_at,
        "trade_mode": settings.trade_mode,
        "is_real": settings.trade_mode == "REAL"
    }

@router.post("/toggle-real")
def toggle_real_enabled(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    settings = current_user.settings
    if not settings:
        settings = UserSettings(user_id=current_user.id, is_real_enabled=True)
        db.add(settings)
    else:
        settings.is_real_enabled = not settings.is_real_enabled
        settings.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Real trading enabled toggled", "is_real_enabled": settings.is_real_enabled}

@router.post("/start")
def start_bot(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    settings = current_user.settings
    if not settings:
        settings = UserSettings(user_id=current_user.id, is_running=True)
        db.add(settings)
    else:
        settings.is_running = True
        settings.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Bot started", "is_running": True}

@router.post("/stop")
def stop_bot(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    settings = current_user.settings
    if not settings:
        settings = UserSettings(user_id=current_user.id, is_running=False)
        db.add(settings)
    else:
        settings.is_running = False
        settings.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Bot stopped", "is_running": False}
