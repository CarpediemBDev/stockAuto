from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional
from app.core.database import get_db
from app.core.models import User, UserSettings, RefreshToken, utc_now_aware
from app.core.config import settings
from app.core.logging import logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_password_hash,
    verify_password,
)
from app.core.dependencies import get_current_user
from datetime import timedelta

router = APIRouter()
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="refresh_token",
        value=token,
        httponly=True,
        max_age=14 * 24 * 60 * 60,
        samesite="lax",
        secure=settings.IS_PROD,
        path=REFRESH_COOKIE_PATH,
    )


def _delete_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        "refresh_token",
        path=REFRESH_COOKIE_PATH,
        secure=settings.IS_PROD,
        samesite="lax",
    )

# --- Pydantic Schemas ---
class UserAuthSchema(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="로그인 아이디")
    password: str = Field(..., min_length=4, description="비밀번호")

class TokenResponseSchema(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    refresh_token: Optional[str] = None

class RefreshRequestSchema(BaseModel):
    refresh_token: str

class LogoutRequestSchema(BaseModel):
    refresh_token: Optional[str] = None

class UserProfileSchema(BaseModel):
    id: int
    username: str
    trade_mode: str
    broker_provider: Optional[str] = None
    telegram_enabled: bool

class ChangePasswordSchema(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=4)

# --- Routes ---

@router.post("/signup", response_model=TokenResponseSchema, status_code=status.HTTP_201_CREATED)
def signup(payload: UserAuthSchema, response: Response, db: Session = Depends(get_db)):
    """
    신규 사용자 회원가입 및 초기 설정 레코드 동시 생성 API (트랜잭션 원자성 강화)
    """
    # 아이디 중복 체크
    existing_user = db.query(User).filter(User.username == payload.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 존재하는 아이디입니다."
        )

    try:
        # 1. 비밀번호 단방향 암호화 및 유저 추가
        hashed = get_password_hash(payload.password)
        new_user = User(username=payload.username, hashed_password=hashed)
        db.add(new_user)
        db.flush()  # 신규 유저 ID 할당을 위한 메모리 동기화

        # 2. 신규 사용자의 전용 트레이딩 설정 레코드 자동 생성
        new_settings = UserSettings(user_id=new_user.id)
        db.add(new_settings)

        # 3. 회원가입 완료 후 즉시 사용 가능한 JWT 토큰 발급
        access_token = create_access_token(subject=new_user.id)
        refresh_token = create_refresh_token(subject=new_user.id)

        # 4. Refresh Token DB 저장
        db_rt = RefreshToken(
            user_id=new_user.id,
            token=refresh_token,
            expires_at=utc_now_aware() + timedelta(days=14)
        )
        db.add(db_rt)
        
        # 변경사항 전체 일괄 커밋
        db.commit()
        logger.info(f"[Auth] New user registered successfully: {new_user.username}")
    except Exception as e:
        db.rollback()
        logger.error(f"[Auth] Signup transaction failed, rolled back: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="회원가입 처리 중 내부 오류가 발생했습니다."
        )

    # HttpOnly 쿠키에 Refresh Token 설정 (쿠키 호환성 유지)
    _set_refresh_cookie(response, refresh_token)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": new_user.username,
        "refresh_token": refresh_token
    }

@router.post("/login", response_model=TokenResponseSchema)
def login(payload: UserAuthSchema, response: Response, db: Session = Depends(get_db)):
    """
    사용자 로그인 및 JWT 발급 API (브루트포스 방어 및 타이밍 공격 방어 포함)
    """
    user = db.query(User).filter(User.username == payload.username).first()

    # 타이밍 공격 방어: 유저가 존재하지 않더라도 더미 bcrypt 연산을 돌려 응답 소요 시간 대칭화
    if user:
        is_password_correct = verify_password(payload.password, user.hashed_password)
    else:
        # 동일한 부하가 걸리도록 더미 bcrypt 연산 실행
        verify_password(payload.password, "$2b$12$DUMMYHASHFORSECURITYPURPOSESONLYDONTUSETHISONE")
        is_password_correct = False

    # 잠금 상태 체크 (유저가 존재할 때만 실행)
    if user and user.locked_until:
        if user.locked_until > utc_now_aware():
            logger.warning(f"[Security] Blocked login attempt on locked account: {payload.username}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="로그인 실패 5회 초과로 계정이 잠겼습니다. 잠시 후 다시 시도해주세요."
            )
        else:
            # 잠금 시간 15분이 지나고 다시 로그인을 시도한 경우, 실패 횟수를 0으로 클리어
            user.failed_login_attempts = 0
            user.locked_until = None
            db.commit()

    if not user or not is_password_correct:
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.locked_until = utc_now_aware() + timedelta(minutes=15)
                logger.error(f"[Security] Account {user.username} locked due to 5 consecutive failures.")
            db.commit()
            logger.warning(f"[Auth] Failed login attempt for user: {payload.username} (Failed attempts: {user.failed_login_attempts})")
        else:
            logger.warning(f"[Auth] Failed login attempt for non-existent user: {payload.username}")

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다."
        )

    # 성공 시 상태 초기화
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()
    logger.info(f"[Auth] User logged in successfully: {user.username}")

    access_token = create_access_token(subject=user.id)
    refresh_token = create_refresh_token(subject=user.id)

    # Refresh Token DB 저장
    db_rt = RefreshToken(
        user_id=user.id,
        token=refresh_token,
        expires_at=utc_now_aware() + timedelta(days=14)
    )
    db.add(db_rt)
    db.commit()

    _set_refresh_cookie(response, refresh_token)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user.username,
        "refresh_token": refresh_token
    }

@router.post("/refresh", response_model=TokenResponseSchema)
def refresh_token(
    payload: Optional[RefreshRequestSchema] = None,
    request: Request = None,
    response: Response = None,
    db: Session = Depends(get_db)
):
    """
    JSON 바디 또는 HttpOnly 쿠키의 Refresh Token을 사용해 새 Access Token을 발급합니다.
    """
    token = None
    if payload:
        token = payload.refresh_token
    if not token and request:
        token = request.cookies.get("refresh_token")

    if not token:
        raise HTTPException(status_code=401, detail="Refresh token missing")
    token_user_id = decode_refresh_token(token)
    if not token_user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    # DB 토큰 검증
    db_token = db.query(RefreshToken).filter(RefreshToken.token == token).first()
    if not db_token or db_token.is_revoked or db_token.expires_at < utc_now_aware():
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    if str(db_token.user_id) != token_user_id:
        raise HTTPException(status_code=401, detail="Refresh token subject mismatch")

    # 유저 조회
    user = db.query(User).filter(User.id == db_token.user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    access_token = create_access_token(subject=user.id)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user.username,
        "refresh_token": token
    }

@router.post("/logout")
def logout(
    payload: Optional[LogoutRequestSchema] = None,
    request: Request = None,
    response: Response = None,
    db: Session = Depends(get_db)
):
    """
    로그아웃 (Refresh Token 파기 및 쿠키 삭제)
    """
    token = None
    if payload:
        token = payload.refresh_token
    if not token and request:
        token = request.cookies.get("refresh_token")

    if token:
        db_token = db.query(RefreshToken).filter(RefreshToken.token == token).first()
        if db_token:
            db_token.is_revoked = True
            db.commit()

    if response:
        _delete_refresh_cookie(response)
    return {"success": True, "message": "Successfully logged out"}

@router.post("/change-password")
def change_password(
    payload: ChangePasswordSchema,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    비밀번호 변경 및 강제 로그아웃 (모든 기기 세션 만료)
    """
    if not verify_password(payload.old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="기존 비밀번호가 일치하지 않습니다.")

    current_user.hashed_password = get_password_hash(payload.new_password)

    # 기존 모든 Refresh Token 무효화
    db.query(RefreshToken).filter(RefreshToken.user_id == current_user.id).update({"is_revoked": True})
    db.commit()

    # 현재 기기 쿠키 삭제
    _delete_refresh_cookie(response)

    return {"success": True, "message": "비밀번호가 성공적으로 변경되었습니다. 다시 로그인해주세요."}

@router.get("/me", response_model=UserProfileSchema)
def get_me(current_user: User = Depends(get_current_user)):
    """
    현재 로그인된 사용자의 기본 정보와 설정 상태를 가져옵니다.
    """
    return {
        "id": current_user.id,
        "username": current_user.username,
        "trade_mode": current_user.settings.trade_mode if current_user.settings else "SIMULATED",
        "broker_provider": current_user.settings.broker_provider if current_user.settings else None,
        "telegram_enabled": current_user.settings.telegram_enabled if current_user.settings else False
    }
