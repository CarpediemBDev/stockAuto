from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.credentials import CredentialCryptoError, decrypt_credential, encrypt_credential
from app.core.database import get_db
from app.core.dependencies import get_current_user, get_current_admin_user
from app.core.models import ActionLog, User, UserSettings, utc_now_naive

router = APIRouter()


class SettingsUpdateSchema(BaseModel):
    trade_mode: str
    broker_provider: str
    telegram_chat_id: Optional[str] = None
    telegram_enabled: Optional[bool] = False


class KisCredentialsSchema(BaseModel):
    trade_mode: str
    kis_app_key: str
    kis_app_secret: str
    kis_account_no: str


class KisVerifyCurrentSchema(BaseModel):
    trade_mode: Optional[str] = None


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
            detail="지원하지 않는 트레이딩 모드입니다. SIMULATED, MOCK, REAL 중 하나를 선택하세요.",
        )
    return normalized


def _is_missing_or_placeholder(value: Optional[str]) -> bool:
    normalized = (value or "").strip()
    return not normalized or normalized in PLACEHOLDER_KIS_VALUES


def _mask_plain_value(value: Optional[str], visible_prefix: int = 4, visible_suffix: int = 3) -> Optional[str]:
    normalized = (value or "").strip()
    if not normalized:
        return None
    if len(normalized) <= visible_prefix + visible_suffix:
        return "*" * len(normalized)
    return f"{normalized[:visible_prefix]}...{normalized[-visible_suffix:]}"


def _credential_values(db_settings: UserSettings) -> tuple[Optional[str], Optional[str], Optional[str]]:
    return (
        decrypt_credential(getattr(db_settings, "kis_app_key", None)),
        decrypt_credential(getattr(db_settings, "kis_app_secret", None)),
        decrypt_credential(getattr(db_settings, "kis_account_no", None)),
    )


def _has_usable_kis_credentials(db_settings: Optional[UserSettings]) -> bool:
    if not db_settings:
        return False
    try:
        app_key, app_secret, account_no = _credential_values(db_settings)
    except CredentialCryptoError:
        return False
    return not any(_is_missing_or_placeholder(value) for value in (app_key, app_secret, account_no))


def _credential_meta(db_settings: UserSettings) -> dict:
    crypto_error = None
    account_no = None
    try:
        app_key, app_secret, account_no = _credential_values(db_settings)
    except CredentialCryptoError:
        app_key = None
        app_secret = None
        crypto_error = "KIS 인증정보 복호화에 실패했습니다. 서버 암호화 키 설정을 확인하세요."

    has_credentials = (
        crypto_error is None
        and not any(_is_missing_or_placeholder(value) for value in (app_key, app_secret, account_no))
    )
    verification_status = getattr(db_settings, "kis_verification_status", None) or "unverified"
    if crypto_error:
        verification_status = "crypto_error"

    return {
        "has_kis_credentials": has_credentials,
        "kis_account_no_masked": _mask_plain_value(account_no),
        "kis_verification_status": verification_status,
        "kis_verified_trade_mode": getattr(db_settings, "kis_verified_trade_mode", None),
        "kis_verified_at": getattr(db_settings, "kis_verified_at", None),
        "kis_credential_error": crypto_error,
    }


def _settings_response(db_settings: UserSettings) -> dict:
    import os

    return {
        "id": getattr(db_settings, "id", None),
        "user_id": getattr(db_settings, "user_id", None),
        "trade_mode": getattr(db_settings, "trade_mode", None) or "SIMULATED",
        "broker_provider": getattr(db_settings, "broker_provider", None) or "KIS",
        "telegram_chat_id": getattr(db_settings, "telegram_chat_id", None),
        "telegram_enabled": bool(getattr(db_settings, "telegram_enabled", False)),
        "is_running": bool(getattr(db_settings, "is_running", False)),
        "is_real_enabled": bool(getattr(db_settings, "is_real_enabled", False)),
        "global_bot_username": os.getenv("TELEGRAM_BOT_USERNAME", "stockauto_official_bot"),
        **_credential_meta(db_settings),
    }


def _ensure_db_settings(current_user: User, db: Session) -> UserSettings:
    db_settings = current_user.settings
    if not db_settings:
        db_settings = UserSettings(user_id=current_user.id)
        db.add(db_settings)
        try:
            current_user.settings = db_settings
        except Exception:
            pass
    return db_settings


def _raise_crypto_http_error() -> None:
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="서버 KIS 암호화 키가 설정되지 않았거나 올바르지 않아 인증정보를 처리할 수 없습니다.",
    )


def _verify_kis_values(
    trade_mode: str,
    kis_app_key: Optional[str],
    kis_app_secret: Optional[str],
    kis_account_no: Optional[str],
    user_id: int,
) -> tuple[bool, str]:
    mode = _normalize_trade_mode(trade_mode)
    if mode == "SIMULATED":
        return True, "SIMULATED 모드는 KIS 통신 검증이 필요하지 않습니다."

    missing_fields = []
    if _is_missing_or_placeholder(kis_app_key):
        missing_fields.append("APP KEY")
    if _is_missing_or_placeholder(kis_app_secret):
        missing_fields.append("APP SECRET")
    if _is_missing_or_placeholder(kis_account_no):
        missing_fields.append("ACCOUNT NO")

    if missing_fields:
        return False, f"KIS 연동 정보가 누락되었거나 기본값입니다: {', '.join(missing_fields)}"

    class TempUserSettings:
        def __init__(self) -> None:
            self.user_id = user_id
            self.kis_app_key = kis_app_key
            self.kis_app_secret = kis_app_secret
            self.kis_account_no = kis_account_no
            self.trade_mode = mode

    try:
        from app.bot.kis_api import KISClient

        client = KISClient(db_settings=TempUserSettings())
        token = client.get_access_token()
        if not token:
            return False, "KIS Access Token 발급에 실패했습니다. APP KEY 또는 APP SECRET을 확인하세요."

        balance = client.get_account_balance()
        provider = balance.get("provider")

        if provider in ["KIS Mock", "KIS Live"]:
            return True, f"KIS API 통신이 성공적으로 검증되었습니다. 서버 유형: {provider}"
        return False, "KIS 서버 통신은 되었으나 잔고 조회에 실패했습니다. 계좌번호를 확인하세요."
    except Exception as exc:
        return False, f"검증 중 알 수 없는 오류가 발생했습니다: {str(exc)}"


@router.get("/")
def get_user_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """현재 로그인한 사용자의 안전한 개인 설정을 반환합니다."""
    db_settings = current_user.settings
    if not db_settings:
        db_settings = UserSettings(user_id=current_user.id)
        db.add(db_settings)
        db.commit()
        db.refresh(db_settings)

    return _settings_response(db_settings)


@router.post("/verify-kis")
def verify_kis_settings(
    payload: KisCredentialsSchema,
    current_user: User = Depends(get_current_user),
):
    """제공된 KIS 인증정보의 실시간 통신 유효성을 검증합니다. 값을 저장하지 않습니다."""
    success, message = _verify_kis_values(
        payload.trade_mode,
        payload.kis_app_key,
        payload.kis_app_secret,
        payload.kis_account_no,
        current_user.id,
    )
    return {"success": success, "message": message}


@router.post("/kis-credentials/verify-and-save")
def save_kis_credentials(
    payload: KisCredentialsSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """KIS 인증정보를 검증한 뒤 암호화하여 저장합니다. 원문은 응답하지 않습니다."""
    trade_mode = _normalize_trade_mode(payload.trade_mode)
    if trade_mode == "SIMULATED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SIMULATED 모드는 KIS 인증정보 저장이 필요하지 않습니다.",
        )

    success, message = _verify_kis_values(
        trade_mode,
        payload.kis_app_key,
        payload.kis_app_secret,
        payload.kis_account_no,
        current_user.id,
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    db_settings = _ensure_db_settings(current_user, db)
    try:
        db_settings.kis_app_key = encrypt_credential(payload.kis_app_key)
        db_settings.kis_app_secret = encrypt_credential(payload.kis_app_secret)
        db_settings.kis_account_no = encrypt_credential(payload.kis_account_no)
    except CredentialCryptoError:
        _raise_crypto_http_error()

    db_settings.broker_provider = "KIS"
    db_settings.kis_verification_status = "verified"
    db_settings.kis_verified_trade_mode = trade_mode
    db_settings.kis_verified_at = utc_now_naive()

    db.commit()
    db.refresh(db_settings)

    return {
        "success": True,
        "message": message,
        "settings": _settings_response(db_settings),
    }


@router.post("/kis-credentials/verify-current")
def verify_current_kis_credentials(
    payload: KisVerifyCurrentSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """저장된 KIS 인증정보를 복호화하여 현재 서버와 다시 검증합니다."""
    db_settings = current_user.settings
    if not db_settings:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="저장된 KIS 인증정보가 없습니다.")

    trade_mode = _normalize_trade_mode(
        payload.trade_mode
        or getattr(db_settings, "kis_verified_trade_mode", None)
        or db_settings.trade_mode
    )
    if trade_mode == "SIMULATED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SIMULATED 모드는 KIS 인증정보 검증이 필요하지 않습니다.",
        )

    try:
        app_key, app_secret, account_no = _credential_values(db_settings)
    except CredentialCryptoError:
        _raise_crypto_http_error()

    if any(_is_missing_or_placeholder(value) for value in (app_key, app_secret, account_no)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="저장된 KIS 인증정보가 없습니다.")

    success, message = _verify_kis_values(trade_mode, app_key, app_secret, account_no, current_user.id)
    if success:
        db_settings.kis_verification_status = "verified"
        db_settings.kis_verified_trade_mode = trade_mode
        db_settings.kis_verified_at = utc_now_naive()
    else:
        db_settings.kis_verification_status = "failed"
        db_settings.kis_verified_trade_mode = trade_mode
        db_settings.kis_verified_at = None

    db.commit()
    db.refresh(db_settings)

    return {
        "success": success,
        "message": message,
        "settings": _settings_response(db_settings),
    }


@router.delete("/kis-credentials")
def delete_kis_credentials(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """저장된 KIS 인증정보와 검증 메타데이터를 삭제합니다."""
    db_settings = current_user.settings
    if not db_settings:
        db_settings = UserSettings(user_id=current_user.id)
        db.add(db_settings)

    db_settings.kis_app_key = None
    db_settings.kis_app_secret = None
    db_settings.kis_account_no = None
    db_settings.kis_verification_status = "unverified"
    db_settings.kis_verified_trade_mode = None
    db_settings.kis_verified_at = None

    db.commit()
    db.refresh(db_settings)

    return {
        "success": True,
        "message": "KIS 인증정보가 삭제되었습니다.",
        "settings": _settings_response(db_settings),
    }


@router.post("/")
def update_user_settings(
    payload: SettingsUpdateSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """현재 로그인한 사용자의 일반 설정을 저장합니다. KIS 원문 인증정보는 처리하지 않습니다."""
    trade_mode = _normalize_trade_mode(payload.trade_mode)
    if trade_mode in {"MOCK", "REAL"}:
        current_settings = current_user.settings
        if not _has_usable_kis_credentials(current_settings):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="MOCK/REAL 모드를 사용하려면 KIS 인증정보를 먼저 검증 및 저장하세요.",
            )
        if getattr(current_settings, "kis_verification_status", None) != "verified":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="KIS 인증정보 검증 상태가 verified가 아닙니다. 다시 검증하세요.",
            )
        if getattr(current_settings, "kis_verified_trade_mode", None) != trade_mode:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{trade_mode} 모드용 KIS 인증정보 검증이 필요합니다.",
            )

    db_settings = _ensure_db_settings(current_user, db)
    db_settings.trade_mode = trade_mode
    db_settings.broker_provider = payload.broker_provider
    db_settings.telegram_chat_id = payload.telegram_chat_id
    db_settings.telegram_enabled = payload.telegram_enabled

    db.commit()
    db.refresh(db_settings)

    print(f"[*] Telegram settings updated dynamically for User ID: {current_user.id} (Global Bot Architecture)")

    return _settings_response(db_settings)


@router.get("/users")
def list_users(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """관리자용 가입자 목록과 봇 상태 조회."""
    users = db.query(User).all()
    result = []
    for user in users:
        settings = user.settings
        result.append(
            {
                "id": user.id,
                "username": user.username,
                "created_at": user.created_at,
                "trade_mode": settings.trade_mode if settings else "SIMULATED",
                "telegram_enabled": settings.telegram_enabled if settings else False,
                "is_running": settings.is_running if settings else False,
            }
        )
    return result


@router.post("/users/{user_id}/toggle-bot")
def toggle_user_bot(
    user_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """관리자용 사용자 봇 기동/중지 제어."""
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
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """관리자용 사용자 계정 삭제."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="자기 자신은 삭제할 수 없습니다.")

    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    db.delete(target_user)
    db.commit()
    return {"message": f"Successfully deleted user {user_id}"}


@router.get("/system-logs")
def get_system_logs(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """관리자용 최신 시스템 로그 조회."""
    return db.query(ActionLog).order_by(ActionLog.created_at.desc()).limit(100).all()


@router.get("/backtest/tournament")
async def get_backtest_tournament_results(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: User = Depends(get_current_admin_user),
):
    """지정 기간의 백테스트 토너먼트 결과를 조회합니다."""
    if not start_date or not end_date:
        import json
        import os

        results_path = (
            r"C:\Users\Im\.gemini\antigravity\brain\3a7f1012-f111-46d8-8da9-7971ca6063b4"
            r"\scratch\tournament_results.json"
        )
        if not os.path.exists(results_path):
            return []
        try:
            with open(results_path, "r", encoding="utf-8") as f_in:
                return json.load(f_in)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        from app.admin.backtest_runner import run_dynamic_tournament

        return await run_dynamic_tournament(start_date, end_date)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"동적 백테스트 실행 중 오류가 발생했습니다: {str(exc)}",
        ) from exc
