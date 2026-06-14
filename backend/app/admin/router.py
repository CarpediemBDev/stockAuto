from datetime import date
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.bot.order_reconciler import disable_auto_resume_for_user, has_unresolved_orders
from app.core.credentials import CredentialCryptoError, decrypt_credential, encrypt_credential
from app.core.database import get_db
from app.core.dependencies import get_current_user, get_current_admin_user
from app.core.logging import logger
from app.core.models import ActionLog, User, UserSettings, BrokerCredential, utc_now_aware

router = APIRouter()

class SettingsUpdateSchema(BaseModel):
    trade_mode: str
    broker_provider: str
    telegram_chat_id: Optional[str] = None
    telegram_enabled: Optional[bool] = False

class CredentialSchema(BaseModel):
    trade_mode: str
    broker_name: str
    app_key: str
    app_secret: str
    account_no: str

class VerifyCurrentSchema(BaseModel):
    trade_mode: Optional[str] = None
    broker_name: str

VALID_TRADE_MODES = {"SIMULATED", "MOCK", "REAL"}
BACKTEST_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
BACKTEST_TICKER_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9.-]{0,14}$")
PLACEHOLDER_VALUES = {
    "YOUR_APP_KEY_HERE",
    "your_virtual_app_key_here",
    "your_real_app_key_here",
    "your_app_key_here",
    "your_toss_app_key_here",
    "00000000-01",
    "12345678-01",
    "00000000",
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


def _parse_backtest_date(value: Optional[str], field_name: str) -> date:
    if not value or not BACKTEST_DATE_PATTERN.fullmatch(value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name}은 YYYY-MM-DD 형식이어야 합니다.",
        )
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name}에 유효한 날짜를 입력하세요.",
        ) from exc


def _parse_backtest_tickers(tickers: Optional[str]) -> list[str] | None:
    if not tickers:
        return None

    parsed = []
    seen = set()
    for raw_ticker in tickers.split(","):
        ticker = raw_ticker.strip().upper()
        if not ticker:
            continue
        if not BACKTEST_TICKER_PATTERN.fullmatch(ticker):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"지원하지 않는 티커 형식입니다: {ticker}",
            )
        if ticker not in seen:
            parsed.append(ticker)
            seen.add(ticker)

    if not parsed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="백테스트할 티커를 하나 이상 입력하세요.",
        )
    if len(parsed) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="백테스트 티커는 최대 100개까지 입력할 수 있습니다.",
        )
    return parsed

def _is_missing_or_placeholder(value: Optional[str]) -> bool:
    normalized = (value or "").strip()
    return not normalized or normalized in PLACEHOLDER_VALUES

def _mask_plain_value(value: Optional[str], visible_prefix: int = 4, visible_suffix: int = 3) -> Optional[str]:
    normalized = (value or "").strip()
    if not normalized:
        return None
    if len(normalized) <= visible_prefix + visible_suffix:
        return "*" * len(normalized)
    return f"{normalized[:visible_prefix]}...{normalized[-visible_suffix:]}"

def _credential_values(cred: BrokerCredential) -> tuple[Optional[str], Optional[str], Optional[str]]:
    return (
        decrypt_credential(getattr(cred, "app_key", None)),
        decrypt_credential(getattr(cred, "app_secret", None)),
        decrypt_credential(getattr(cred, "account_no", None)),
    )

def _credential_meta(cred: BrokerCredential) -> dict:
    crypto_error = None
    account_no = None
    try:
        app_key, app_secret, account_no = _credential_values(cred)
    except CredentialCryptoError:
        app_key = None
        app_secret = None
        crypto_error = f"{cred.broker_name} 인증정보 복호화에 실패했습니다."

    has_credentials = (
        crypto_error is None
        and not any(_is_missing_or_placeholder(value) for value in (app_key, app_secret, account_no))
    )
    verification_status = cred.verification_status or "unverified"
    if crypto_error:
        verification_status = "crypto_error"

    return {
        "broker_name": cred.broker_name,
        "has_credentials": has_credentials,
        "account_no_masked": _mask_plain_value(account_no),
        "verification_status": verification_status,
        "verified_trade_mode": cred.verified_trade_mode,
        "verified_at": cred.verified_at,
        "credential_error": crypto_error,
    }

def _settings_response(db_settings: UserSettings) -> dict:
    import os
    credentials = db_settings.credentials if db_settings else []
    return {
        "id": getattr(db_settings, "id", None) if db_settings else None,
        "user_id": getattr(db_settings, "user_id", None) if db_settings else None,
        "trade_mode": getattr(db_settings, "trade_mode", None) or "SIMULATED",
        "broker_provider": getattr(db_settings, "broker_provider", None),
        "telegram_chat_id": getattr(db_settings, "telegram_chat_id", None) if db_settings else None,
        "telegram_enabled": bool(getattr(db_settings, "telegram_enabled", False)) if db_settings else False,
        "is_running": bool(getattr(db_settings, "is_running", False)) if db_settings else False,
        "global_bot_username": os.getenv("TELEGRAM_BOT_USERNAME", "stockauto_official_bot"),
        "credentials": [_credential_meta(c) for c in credentials],
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
        detail="서버 암호화 키가 설정되지 않았거나 올바르지 않아 인증정보를 처리할 수 없습니다.",
    )

def _verify_credential_values(
    trade_mode: str,
    broker_name: str,
    app_key: Optional[str],
    app_secret: Optional[str],
    account_no: Optional[str],
    user_id: int,
) -> tuple[bool, str]:
    mode = _normalize_trade_mode(trade_mode)
    if mode == "SIMULATED":
        return True, f"SIMULATED 모드는 {broker_name} 통신 검증이 필요하지 않습니다."

    missing_fields = []
    if _is_missing_or_placeholder(app_key): missing_fields.append("APP KEY")
    if _is_missing_or_placeholder(app_secret): missing_fields.append("APP SECRET")
    if _is_missing_or_placeholder(account_no): missing_fields.append("ACCOUNT NO")

    if missing_fields:
        return False, f"{broker_name} 연동 정보가 누락되었거나 기본값입니다: {', '.join(missing_fields)}"

    # Create dummy credential to inject into factory/client
    class TempCred:
        def __init__(self):
            self.user_id = user_id
            self.broker_name = broker_name
            self.app_key = app_key
            self.app_secret = app_secret
            self.account_no = account_no

    try:
        if broker_name == "KIS":
            from app.bot.kis_api import KISClient
            client = KISClient(db_credential=TempCred(), trade_mode=mode)
        elif broker_name == "TOSS":
            from app.bot.toss_api import TossClient
            client = TossClient(db_credential=TempCred(), trade_mode=mode)
        else:
            return False, f"지원하지 않는 증권사입니다: {broker_name}"

        token = client.get_access_token()
        if not token:
            return False, f"{broker_name} Access Token 발급에 실패했습니다. 키를 확인하세요."

        balance = client.get_account_balance()
        provider = balance.get("provider", "Unknown")
        return True, f"{broker_name} API 통신이 성공적으로 검증되었습니다. 서버 유형: {provider}"
    except Exception as exc:
        return False, f"검증 중 알 수 없는 오류가 발생했습니다: {str(exc)}"


@router.get("/")
def get_user_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db_settings = current_user.settings
    if not db_settings:
        db_settings = UserSettings(user_id=current_user.id)
        db.add(db_settings)
        db.commit()
        db.refresh(db_settings)
    return _settings_response(db_settings)

@router.post("/")
def update_user_settings(
    payload: SettingsUpdateSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    trade_mode = _normalize_trade_mode(payload.trade_mode)
    db_settings = _ensure_db_settings(current_user, db)

    if trade_mode != (db_settings.trade_mode or "SIMULATED").upper() and has_unresolved_orders(db, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="미해결 주문 재조정 중에는 거래 모드를 변경할 수 없습니다.",
        )

    # Validate if switching to MOCK/REAL that the selected broker_provider is verified
    if trade_mode in {"MOCK", "REAL"}:
        provider = payload.broker_provider
        cred = db.query(BrokerCredential).filter_by(user_id=current_user.id, broker_name=provider).first()
        if not cred or cred.verification_status != "verified" or cred.verified_trade_mode != trade_mode:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{trade_mode} 모드로 변경하려면 {provider} 인증정보가 사전에 검증(verified)되어 있어야 합니다.",
            )

    db_settings.trade_mode = trade_mode
    db_settings.broker_provider = payload.broker_provider
    db_settings.telegram_chat_id = payload.telegram_chat_id
    db_settings.telegram_enabled = payload.telegram_enabled

    db.commit()
    db.refresh(db_settings)
    return _settings_response(db_settings)

@router.post("/credentials/verify")
def verify_credential(
    payload: CredentialSchema,
    current_user: User = Depends(get_current_user),
):
    success, message = _verify_credential_values(
        payload.trade_mode,
        payload.broker_name,
        payload.app_key,
        payload.app_secret,
        payload.account_no,
        current_user.id,
    )
    return {"success": success, "message": message}

@router.post("/credentials/verify-and-save")
def save_credential(
    payload: CredentialSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if has_unresolved_orders(db, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="미해결 주문 재조정 중에는 인증정보를 변경할 수 없습니다.",
        )
    trade_mode = _normalize_trade_mode(payload.trade_mode)
    if trade_mode == "SIMULATED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SIMULATED 모드는 인증정보 저장이 필요하지 않습니다.",
        )

    success, message = _verify_credential_values(
        trade_mode,
        payload.broker_name,
        payload.app_key,
        payload.app_secret,
        payload.account_no,
        current_user.id,
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    db_settings = _ensure_db_settings(current_user, db)
    cred = db.query(BrokerCredential).filter_by(user_id=current_user.id, broker_name=payload.broker_name).first()
    if not cred:
        cred = BrokerCredential(user_id=current_user.id, broker_name=payload.broker_name)
        db.add(cred)

    try:
        cred.app_key = encrypt_credential(payload.app_key)
        cred.app_secret = encrypt_credential(payload.app_secret)
        cred.account_no = encrypt_credential(payload.account_no)
    except CredentialCryptoError:
        _raise_crypto_http_error()

    cred.verification_status = "verified"
    cred.verified_trade_mode = trade_mode
    cred.verified_at = utc_now_aware()

    # Automatically set as default provider if it's the first one
    if not db_settings.broker_provider:
        db_settings.broker_provider = payload.broker_name

    db.commit()
    db.refresh(db_settings)

    return {
        "success": True,
        "message": message,
        "settings": _settings_response(db_settings),
    }

@router.post("/credentials/verify-current")
def verify_current_credential(
    payload: VerifyCurrentSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db_settings = current_user.settings
    if not db_settings:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="저장된 설정이 없습니다.")

    cred = db.query(BrokerCredential).filter_by(user_id=current_user.id, broker_name=payload.broker_name).first()
    if not cred:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"저장된 {payload.broker_name} 인증정보가 없습니다.")

    trade_mode = _normalize_trade_mode(
        payload.trade_mode or cred.verified_trade_mode or db_settings.trade_mode
    )
    if trade_mode == "SIMULATED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SIMULATED 모드는 인증정보 검증이 필요하지 않습니다.",
        )

    try:
        app_key, app_secret, account_no = _credential_values(cred)
    except CredentialCryptoError:
        _raise_crypto_http_error()

    if any(_is_missing_or_placeholder(value) for value in (app_key, app_secret, account_no)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="저장된 인증정보가 불안정합니다.")

    success, message = _verify_credential_values(trade_mode, payload.broker_name, app_key, app_secret, account_no, current_user.id)
    if success:
        cred.verification_status = "verified"
        cred.verified_trade_mode = trade_mode
        cred.verified_at = utc_now_aware()
    else:
        cred.verification_status = "failed"
        cred.verified_trade_mode = trade_mode
        cred.verified_at = None

    db.commit()
    db.refresh(db_settings)

    return {
        "success": success,
        "message": message,
        "settings": _settings_response(db_settings),
    }

@router.delete("/credentials/{broker_name}")
def delete_credential(
    broker_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if has_unresolved_orders(db, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="미해결 주문 재조정 중에는 인증정보를 삭제할 수 없습니다.",
        )
    
    cred = db.query(BrokerCredential).filter_by(user_id=current_user.id, broker_name=broker_name).first()
    if cred:
        db.delete(cred)
        db.commit()

    db_settings = _ensure_db_settings(current_user, db)
    return {
        "success": True,
        "message": f"{broker_name} 인증정보가 삭제되었습니다.",
        "settings": _settings_response(db_settings),
    }

@router.get("/users")
def list_users(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    users = db.query(User).all()
    result = []
    for user in users:
        settings = user.settings
        
        profit_rate = 0.0
        if settings:
            try:
                is_simulated = settings.trade_mode == "SIMULATED"
                has_verified_cred = False
                
                if not is_simulated and settings.broker_provider:
                    for cred in settings.credentials:
                        if cred.broker_name == settings.broker_provider and cred.verification_status == "verified":
                            has_verified_cred = True
                            break
                
                if is_simulated or has_verified_cred:
                    from app.bot.broker_factory import get_broker_client
                    broker = get_broker_client(settings)
                    balance = broker.get_account_balance()
                    profit_rate = balance.get("profit_rate", 0.0)
            except Exception as e:
                # API 호출 에러 발생 시 안전하게 0.0%로 폴백하여 어드민 대시보드 마비 차단
                print(f"[Admin User List] Failed to fetch balance for user {user.username}: {e}")
                profit_rate = 0.0

        from app.bot.multi_strategy_manager import MultiStrategyManager
        strategy_type = settings.strategy_type if settings else "regime_switching"
        strategy_name = MultiStrategyManager()._get_name_for_strategy(strategy_type)

        result.append(
            {
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "created_at": user.created_at,
                "trade_mode": settings.trade_mode if settings else "SIMULATED",
                "broker_provider": settings.broker_provider if settings else None,
                "telegram_enabled": settings.telegram_enabled if settings else False,
                "telegram_chat_id": settings.telegram_chat_id if settings else None,
                "is_running": settings.is_running if settings else False,
                "profit_rate": profit_rate,
                "strategy_type": strategy_type,
                "strategy_name": strategy_name,
                "credentials": [_credential_meta(c) for c in settings.credentials] if settings else [],
            }
        )
    return result


@router.post("/users/{user_id}/toggle-bot")
def toggle_user_bot(
    user_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    target_settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if not target_settings:
        raise HTTPException(status_code=404, detail="사용자 설정을 찾을 수 없습니다.")

    if not target_settings.is_running and has_unresolved_orders(db, user_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="미해결 증권사 주문이 있어 봇을 시작할 수 없습니다.",
        )
    if target_settings.is_running:
        disable_auto_resume_for_user(db, user_id)
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
    return db.query(ActionLog).order_by(ActionLog.created_at.desc()).limit(100).all()

@router.get("/backtest/tournament")
async def get_backtest_tournament_results(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    tickers: Optional[str] = None,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    parsed_start_date = _parse_backtest_date(start_date, "시작일(start_date)")
    parsed_end_date = _parse_backtest_date(end_date, "종료일(end_date)")
    if parsed_start_date > parsed_end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="시작일은 종료일보다 늦을 수 없습니다.",
        )
    parsed_tickers = _parse_backtest_tickers(tickers)

    try:
        from app.admin.backtest_runner import run_dynamic_tournament
        return await run_dynamic_tournament(
            parsed_start_date.isoformat(),
            parsed_end_date.isoformat(),
            tickers_list=parsed_tickers,
            db=db,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[Backtest Tournament] Dynamic tournament execution failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="동적 백테스트 실행 중 오류가 발생했습니다.",
        ) from exc
