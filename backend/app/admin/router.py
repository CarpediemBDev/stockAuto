from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.models import User, UserSettings
from app.core.dependencies import get_current_user

router = APIRouter()

class SettingsUpdateSchema(BaseModel):
    trade_mode: str
    broker_provider: str
    kis_app_key: Optional[str] = None
    kis_app_secret: Optional[str] = None
    kis_account_no: Optional[str] = None
    
    # Telegram Bot Settings (Phase 11)
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    telegram_enabled: Optional[bool] = False

@router.get("/")
def get_user_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """현재 로그인한 사용자의 트레이딩 및 텔레그램 개인 설정을 반환합니다."""
    # 만약 settings 레코드가 없으면 초기값 생성
    db_settings = current_user.settings
    if not db_settings:
        db_settings = UserSettings(user_id=current_user.id)
        db.add(db_settings)
        db.commit()
        db.refresh(db_settings)
        
    return db_settings

@router.post("/")
def update_user_settings(
    payload: SettingsUpdateSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """현재 로그인한 사용자의 트레이딩 설정을 DB에 저장하고 해당 사용자의 서비스를 핫 리로드합니다."""
    db_settings = current_user.settings
    if not db_settings:
        db_settings = UserSettings(user_id=current_user.id)
        db.add(db_settings)
        
    db_settings.trade_mode = payload.trade_mode
    db_settings.broker_provider = payload.broker_provider
    db_settings.kis_app_key = payload.kis_app_key
    db_settings.kis_app_secret = payload.kis_app_secret
    db_settings.kis_account_no = payload.kis_account_no
    
    # Telegram settings
    db_settings.telegram_bot_token = payload.telegram_bot_token
    db_settings.telegram_chat_id = payload.telegram_chat_id
    db_settings.telegram_enabled = payload.telegram_enabled
    
    db.commit()
    db.refresh(db_settings)
    
    # 💡 텔레그램 봇 데몬 실시간 재부팅 (현재 유저 개별 데몬 스레드 리로드)
    from app.core.telegram import stop_telegram_bot_for_user, start_telegram_bot_for_user
    print(f"[*] Hot reloading Telegram Polling thread for User ID: {current_user.id}...")
    stop_telegram_bot_for_user(current_user.id)
    if db_settings.telegram_enabled:
        start_telegram_bot_for_user(current_user.id, db_settings.telegram_bot_token, db_settings.telegram_chat_id)
    
    return db_settings
