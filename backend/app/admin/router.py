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
    telegram_chat_id: Optional[str] = None
    telegram_enabled: Optional[bool] = False

@router.get("/")
def get_user_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """현재 로그인한 사용자의 트레이딩 및 텔레그램 개인 설정을 반환합니다."""
    db_settings = current_user.settings
    if not db_settings:
        db_settings = UserSettings(user_id=current_user.id)
        db.add(db_settings)
        db.commit()
        db.refresh(db_settings)
        
    import os
    return {
        "id": db_settings.id,
        "user_id": db_settings.user_id,
        "trade_mode": db_settings.trade_mode,
        "broker_provider": db_settings.broker_provider,
        "kis_app_key": db_settings.kis_app_key,
        "kis_app_secret": db_settings.kis_app_secret,
        "kis_account_no": db_settings.kis_account_no,
        "telegram_chat_id": db_settings.telegram_chat_id,
        "telegram_enabled": db_settings.telegram_enabled,
        "is_running": db_settings.is_running,
        "is_real_enabled": db_settings.is_real_enabled,
        "global_bot_username": os.getenv("TELEGRAM_BOT_USERNAME", "stockauto_official_bot")
    }

@router.post("/verify-kis")
def verify_kis_settings(
    payload: SettingsUpdateSchema,
    current_user: User = Depends(get_current_user)
):
    """제공된 KIS 설정의 실시간 통신 유효성을 검증합니다."""
    if payload.trade_mode == "SIMULATED":
        return {"success": True, "message": "SIMULATED 모드는 통신 검증이 필요하지 않습니다."}
        
    # KISClient를 위한 임시 settings 객체 래핑
    class TempUserSettings:
        def __init__(self, p, user_id):
            self.user_id = user_id
            self.kis_app_key = p.kis_app_key
            self.kis_app_secret = p.kis_app_secret
            self.kis_account_no = p.kis_account_no
            self.trade_mode = p.trade_mode

    temp_settings = TempUserSettings(payload, current_user.id)
    
    from app.bot.kis_api import KISClient
    client = KISClient(user_settings=temp_settings)
    
    # 1단계: 토큰 발급 테스트
    token = client.get_access_token()
    if not token:
        return {
            "success": False,
            "message": "KIS Access Token 발급에 실패했습니다. APP KEY 또는 APP SECRET을 확인하세요."
        }
        
    # 2단계: 실제 해외주식 잔고조회 테스트
    try:
        balance = client.get_account_balance()
        provider = balance.get("provider")
        
        if provider == "Simulated":
            return {
                "success": False,
                "message": "유효한 API Key가 없어 Simulated(모의) 데이터로 우회 동작 중입니다. 연동 키 값을 다시 확인하세요."
            }
        elif provider in ["KIS Mock", "KIS Live"]:
            return {
                "success": True,
                "message": f"KIS API 통신이 성공적으로 검증되었습니다. (서버 유형: {provider})"
            }
        else:
            # 잔고조회 API 자체 실패로 기본 딕셔너리 리턴 시 (provider 없음)
            return {
                "success": False,
                "message": "KIS 서버 통신은 되었으나 잔고 조회에 실패했습니다. 계좌번호를 확인하세요."
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"검증 중 알 수 없는 에러가 발생했습니다: {str(e)}"
        }

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
    db_settings.telegram_chat_id = payload.telegram_chat_id
    db_settings.telegram_enabled = payload.telegram_enabled
    
    db.commit()
    db.refresh(db_settings)
    
    # 💡 글로벌 단일 봇 아키텍처에서는 별도의 유저 스레드 재기동 없이 DB 반영만으로 실시간 처리됩니다.
    print(f"[*] Telegram settings updated dynamically for User ID: {current_user.id} (Global Bot Architecture)")
    
    return db_settings

@router.get("/users")
def list_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """[슈퍼어드민 전용] 모든 가입자 리스트 및 봇 가동 유무 조회"""
    if current_user.username != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    
    users = db.query(User).all()
    result = []
    for u in users:
        s = u.settings
        result.append({
            "id": u.id,
            "username": u.username,
            "created_at": u.created_at,
            "trade_mode": s.trade_mode if s else "SIMULATED",
            "telegram_enabled": s.telegram_enabled if s else False,
            "is_running": s.is_running if s else False,
        })
    return result

@router.post("/users/{user_id}/toggle-bot")
def toggle_user_bot(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """[슈퍼어드민 전용] 타 사용자의 자동매매 봇 원격 기동/일시정지 제어"""
    if current_user.username != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    
    target_settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if not target_settings:
        raise HTTPException(status_code=404, detail="사용자 설정을 찾을 수 없습니다.")
        
    target_settings.is_running = not target_settings.is_running
    db.commit()
    db.refresh(target_settings)
    
    action = "started" if target_settings.is_running else "stopped"
    return {"message": f"Successfully {action} bot for user {user_id}", "is_running": target_settings.is_running}

@router.post("/users/{user_id}/delete")
def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """[슈퍼어드민 전용] 특정 가입자 계정 영구 삭제 (연동 텔레그램 스레드 즉각 중지)"""
    if current_user.username != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="자기 자신은 삭제할 수 없습니다.")
        
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
        
    # 💡 글로벌 단일 봇 아키텍처에서는 계정 삭제 시 관련 설정도 캐스케이드(Cascade) 삭제되어 자동으로 연동 해제됩니다.
    
    db.delete(target_user)
    db.commit()
    return {"message": f"Successfully deleted user {user_id}"}
