from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.models import User, UserSettings, ActionLog
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

VALID_TRADE_MODES = {"SIMULATED", "MOCK", "REAL"}
PLACEHOLDER_KIS_VALUES = {
    "YOUR_APP_KEY_HERE",
    "your_virtual_app_key_here",
    "your_real_app_key_here",
    "your_app_key_here",
    "00000000-01",
    "12345678-01",
    "your_account_no_here",
}

def _normalize_trade_mode(mode: str) -> str:
    normalized = (mode or "").upper().strip()
    if normalized not in VALID_TRADE_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="지원하지 않는 트레이딩 모드입니다. SIMULATED, MOCK, REAL 중 하나를 선택하세요."
        )
    return normalized

def _is_missing_or_placeholder(value: Optional[str]) -> bool:
    normalized = (value or "").strip()
    return not normalized or normalized in PLACEHOLDER_KIS_VALUES

def _verify_kis_payload(payload: SettingsUpdateSchema, current_user: User) -> tuple[bool, str]:
    mode = _normalize_trade_mode(payload.trade_mode)
    if mode == "SIMULATED":
        return True, "SIMULATED 모드는 통신 검증이 필요하지 않습니다."

    missing_fields = []
    if _is_missing_or_placeholder(payload.kis_app_key):
        missing_fields.append("APP KEY")
    if _is_missing_or_placeholder(payload.kis_app_secret):
        missing_fields.append("APP SECRET")
    if _is_missing_or_placeholder(payload.kis_account_no):
        missing_fields.append("ACCOUNT NO")

    if missing_fields:
        return False, f"KIS 연동 정보가 누락되었거나 기본값입니다: {', '.join(missing_fields)}"

    class TempUserSettings:
        def __init__(self, p: SettingsUpdateSchema, user_id: int):
            self.user_id = user_id
            self.kis_app_key = p.kis_app_key
            self.kis_app_secret = p.kis_app_secret
            self.kis_account_no = p.kis_account_no
            self.trade_mode = mode

    try:
        from app.bot.kis_api import KISClient
        client = KISClient(db_settings=TempUserSettings(payload, current_user.id))

        token = client.get_access_token()
        if not token:
            return False, "KIS Access Token 발급에 실패했습니다. APP KEY 또는 APP SECRET을 확인하세요."

        balance = client.get_account_balance()
        provider = balance.get("provider")

        if provider in ["KIS Mock", "KIS Live"]:
            return True, f"KIS API 통신이 성공적으로 검증되었습니다. (서버 유형: {provider})"
        return False, "KIS 서버 통신은 되었으나 잔고 조회에 실패했습니다. 계좌번호를 확인하세요."
    except Exception as e:
        return False, f"검증 중 알 수 없는 에러가 발생했습니다: {str(e)}"

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
    success, message = _verify_kis_payload(payload, current_user)
    return {"success": success, "message": message}

@router.post("/")
def update_user_settings(
    payload: SettingsUpdateSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """현재 로그인한 사용자의 트레이딩 설정을 DB에 저장하고 해당 사용자의 서비스를 핫 리로드합니다."""
    trade_mode = _normalize_trade_mode(payload.trade_mode)
    if trade_mode in {"MOCK", "REAL"}:
        success, message = _verify_kis_payload(payload, current_user)
        if not success:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    db_settings = current_user.settings
    if not db_settings:
        db_settings = UserSettings(user_id=current_user.id)
        db.add(db_settings)
        
    db_settings.trade_mode = trade_mode
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

@router.get("/system-logs")
def get_system_logs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """[슈퍼어드민 전용] 모든 사용자 봇의 최신 100개 디버깅 로그 조회"""
    if current_user.username != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        
    return db.query(ActionLog).order_by(ActionLog.created_at.desc()).limit(100).all()

@router.get("/backtest/tournament")
async def get_backtest_tournament_results(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """[슈퍼어드민 전용] 지정된 특정 기간(start_date ~ end_date)의 5대 전략 토너먼트 대항전 백테스트를 동적 실행 및 캐시 서빙합니다."""
    if current_user.username != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        
    # 날짜 파라미터가 없으면 기존의 1년치 기본 캐시 파일 로드하여 고속 서빙
    if not start_date or not end_date:
        import json
        import os
        results_path = r"C:\Users\Im\.gemini\antigravity\brain\3a7f1012-f111-46d8-8da9-7971ca6063b4\scratch\tournament_results.json"
        if not os.path.exists(results_path):
            return []
        try:
            with open(results_path, "r", encoding="utf-8") as f_in:
                return json.load(f_in)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
            
    # 날짜 파라미터가 있을 시 동적 토너먼트 가상 샌드박스 가동
    try:
        from app.admin.backtest_runner import run_dynamic_tournament
        data = await run_dynamic_tournament(start_date, end_date)
        return data
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"동적 백테스트 실행 중 에러가 발생했습니다: {str(e)}"
        )
