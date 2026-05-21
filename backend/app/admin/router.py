from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.models import SystemSettings
from app.core.config import settings

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
def get_system_settings(db: Session = Depends(get_db)):
    """현재 시스템 설정(어드민)을 반환합니다. DB에 없으면 초기값을 생성합니다."""
    db_settings = db.query(SystemSettings).first()
    if not db_settings:
        db_settings = SystemSettings(
            trade_mode=settings.TRADE_MODE,
            broker_provider=settings.BROKER_PROVIDER,
            kis_app_key=settings.KIS_APP_KEY,
            kis_app_secret=settings.KIS_APP_SECRET,
            kis_account_no=settings.KIS_ACCOUNT_NO,
            telegram_bot_token=settings.TELEGRAM_BOT_TOKEN,
            telegram_chat_id=settings.TELEGRAM_CHAT_ID,
            telegram_enabled=settings.TELEGRAM_ENABLED,
        )
        db.add(db_settings)
        db.commit()
        db.refresh(db_settings)
        
    return db_settings

@router.post("/")
def update_system_settings(payload: SettingsUpdateSchema, db: Session = Depends(get_db)):
    """시스템 설정을 DB에 저장하고, 서버 런타임에 핫 리로드합니다."""
    db_settings = db.query(SystemSettings).first()
    if not db_settings:
        db_settings = SystemSettings()
        db.add(db_settings)
        
    db_settings.trade_mode = payload.trade_mode
    db_settings.broker_provider = payload.broker_provider
    db_settings.kis_app_key = payload.kis_app_key
    db_settings.kis_app_secret = payload.kis_app_secret
    db_settings.kis_account_no = payload.kis_account_no
    
    # Telegram settings (Phase 11)
    db_settings.telegram_bot_token = payload.telegram_bot_token
    db_settings.telegram_chat_id = payload.telegram_chat_id
    db_settings.telegram_enabled = payload.telegram_enabled
    
    db.commit()
    db.refresh(db_settings)
    
    # [핫 리로드] 메모리 설정 즉시 업데이트
    settings.TRADE_MODE = payload.trade_mode
    settings.IS_SIMULATED = payload.trade_mode == "SIMULATED"
    settings.IS_MOCK = payload.trade_mode == "MOCK"
    settings.IS_REAL = payload.trade_mode == "REAL"
    settings.BROKER_PROVIDER = payload.broker_provider
    
    settings.KIS_APP_KEY = payload.kis_app_key
    settings.KIS_APP_SECRET = payload.kis_app_secret
    settings.KIS_ACCOUNT_NO = payload.kis_account_no
    
    # Telegram Memory settings
    settings.TELEGRAM_BOT_TOKEN = payload.telegram_bot_token
    settings.TELEGRAM_CHAT_ID = payload.telegram_chat_id
    settings.TELEGRAM_ENABLED = payload.telegram_enabled
    
    # 3-Mode에 따른 TR_ID 및 Base URL 동적 업데이트
    if settings.IS_REAL:
        settings.KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"
        settings.TR_ID_BALANCE = "TTTC8434R"
        settings.TR_ID_BUY_OVERSEAS = "JTTT1002U"
        settings.TR_ID_SELL_OVERSEAS = "JTTT1001U"
        settings.TR_ID_OVERSEAS_BALANCE = "CTRP6504R"
        settings.TR_ID_ORDER_HISTORY = "JTTT3010R"
    else:
        settings.KIS_BASE_URL = "https://vts-openapi.koreainvestment.com:29443"
        settings.TR_ID_BALANCE = "VTTC8434R"
        settings.TR_ID_BUY_OVERSEAS = "VTTT1002U"
        settings.TR_ID_SELL_OVERSEAS = "VTTT1001U"
        settings.TR_ID_OVERSEAS_BALANCE = "VTRP6504R"
        settings.TR_ID_ORDER_HISTORY = "VTTS3010R"
        
    print(f"[*] Admin Settings Hot Reloaded: Mode={settings.TRADE_MODE}, Provider={settings.BROKER_PROVIDER} | Telegram={settings.TELEGRAM_ENABLED}")
    
    # 💡 텔레그램 데몬 실시간 재부팅 (토큰 갱신 시 대응)
    from app.core.telegram import stop_telegram_bot, start_telegram_bot
    print("[*] Hot reloading Telegram Polling thread...")
    stop_telegram_bot()
    start_telegram_bot()
    
    return db_settings
