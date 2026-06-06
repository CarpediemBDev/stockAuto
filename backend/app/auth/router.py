from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from app.core.database import get_db
from app.core.models import User, UserSettings, RefreshToken, utc_now_naive
from app.core.config import settings
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

class UserProfileSchema(BaseModel):
    id: int
    username: str
    trade_mode: str
    broker_provider: str
    telegram_enabled: bool

class ChangePasswordSchema(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=4)

# --- Routes ---

@router.post("/signup", response_model=TokenResponseSchema, status_code=status.HTTP_201_CREATED)
def signup(payload: UserAuthSchema, response: Response, db: Session = Depends(get_db)):
    """
    신규 사용자 회원가입 및 초기 설정 레코드 동시 생성 API
    """
    # 아이디 중복 체크
    existing_user = db.query(User).filter(User.username == payload.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 존재하는 아이디입니다."
        )

    # 비밀번호 단방향 암호화 및 유저 추가
    hashed = get_password_hash(payload.password)
    new_user = User(username=payload.username, hashed_password=hashed)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # 신규 사용자의 전용 트레이딩 설정 레코드 자동 생성
    new_settings = UserSettings(user_id=new_user.id)
    db.add(new_settings)
    db.commit()

    # 회원가입 완료 후 즉시 사용 가능한 JWT 토큰 발급
    access_token = create_access_token(subject=new_user.id)
    refresh_token = create_refresh_token(subject=new_user.id)

    # Refresh Token DB 저장
    db_rt = RefreshToken(
        user_id=new_user.id,
        token=refresh_token,
        expires_at=utc_now_naive() + timedelta(days=14)
    )
    db.add(db_rt)
    db.commit()

    # HttpOnly 쿠키에 Refresh Token 설정
    _set_refresh_cookie(response, refresh_token)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": new_user.username
    }

@router.post("/login", response_model=TokenResponseSchema)
def login(payload: UserAuthSchema, response: Response, db: Session = Depends(get_db)):
    """
    사용자 로그인 및 JWT 발급 API (브루트포스 방어 포함)
    """
    user = db.query(User).filter(User.username == payload.username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다."
        )

    # 잠금 상태 체크
    if user.locked_until and user.locked_until > utc_now_naive():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="로그인 실패 5회 초과로 계정이 잠겼습니다. 잠시 후 다시 시도해주세요."
        )

    if not verify_password(payload.password, user.hashed_password):
        # 실패 횟수 증가
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= 5:
            user.locked_until = utc_now_naive() + timedelta(minutes=15)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다."
        )

    # 성공 시 상태 초기화
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()

    access_token = create_access_token(subject=user.id)
    refresh_token = create_refresh_token(subject=user.id)

    # Refresh Token DB 저장
    db_rt = RefreshToken(
        user_id=user.id,
        token=refresh_token,
        expires_at=utc_now_naive() + timedelta(days=14)
    )
    db.add(db_rt)
    db.commit()

    _set_refresh_cookie(response, refresh_token)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user.username
    }

@router.post("/refresh", response_model=TokenResponseSchema)
def refresh_token(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    HttpOnly 쿠키의 Refresh Token을 사용해 새 Access Token을 발급합니다.
    """
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="Refresh token missing")
    token_user_id = decode_refresh_token(token)
    if not token_user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    # DB 토큰 검증
    db_token = db.query(RefreshToken).filter(RefreshToken.token == token).first()
    if not db_token or db_token.is_revoked or db_token.expires_at < utc_now_naive():
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
        "username": user.username
    }

@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    로그아웃 (Refresh Token 파기 및 쿠키 삭제)
    """
    token = request.cookies.get("refresh_token")
    if token:
        db_token = db.query(RefreshToken).filter(RefreshToken.token == token).first()
        if db_token:
            db_token.is_revoked = True
            db.commit()

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
        "broker_provider": current_user.settings.broker_provider if current_user.settings else "KIS",
        "telegram_enabled": current_user.settings.telegram_enabled if current_user.settings else False
    }
