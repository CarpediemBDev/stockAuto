from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from app.core.database import get_db
from app.core.models import User, UserSettings, RefreshToken, utc_now_aware
from app.core.config import get_allowed_origins, settings
from app.core.logging import logger
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_password_hash,
    hash_refresh_token,
    verify_password,
)
from app.core.dependencies import get_current_user
from datetime import timedelta

from app.core.response import SuccessResponseRoute
router = APIRouter(route_class=SuccessResponseRoute)
REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"
LEGACY_REFRESH_COOKIE_PATHS = ("/",)
REFRESH_COOKIE_MAX_AGE = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
BCRYPT_MAX_PASSWORD_BYTES = 72


def _delete_refresh_cookie_at_path(response: Response, path: str) -> None:
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        path=path,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
        domain=settings.REFRESH_COOKIE_DOMAIN,
    )


def _set_refresh_cookie(response: Response, token: str) -> None:
    for legacy_path in LEGACY_REFRESH_COOKIE_PATHS:
        if legacy_path != REFRESH_COOKIE_PATH:
            _delete_refresh_cookie_at_path(response, legacy_path)

    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=REFRESH_COOKIE_MAX_AGE,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
        secure=settings.REFRESH_COOKIE_SECURE,
        path=REFRESH_COOKIE_PATH,
        domain=settings.REFRESH_COOKIE_DOMAIN,
    )


def _delete_refresh_cookie(response: Response) -> None:
    cookie_paths = {REFRESH_COOKIE_PATH, *LEGACY_REFRESH_COOKIE_PATHS}
    for path in cookie_paths:
        _delete_refresh_cookie_at_path(response, path)


def _validate_cookie_request_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin not in get_allowed_origins():
        logger.warning("[Security] Rejected auth cookie request from untrusted origin: %s", origin)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="허용되지 않은 요청 출처입니다.")


def _find_refresh_token(db: Session, token: str) -> RefreshToken | None:
    token_hash = hash_refresh_token(token)
    db_token = db.query(RefreshToken).filter(RefreshToken.token == token_hash).first()
    if db_token:
        return db_token

    # 기존 평문 저장 세션은 첫 사용 시 회전되도록 한시적으로 호환합니다.
    return db.query(RefreshToken).filter(RefreshToken.token == token).first()


def _get_refresh_cookie_candidates(request: Request) -> list[str]:
    candidates: list[str] = []

    # 쿠키 Path가 변경되면 브라우저가 같은 이름의 쿠키를 여러 개 보낼 수 있습니다.
    for cookie_header in request.headers.getlist("cookie"):
        for cookie_pair in cookie_header.split(";"):
            name, separator, value = cookie_pair.strip().partition("=")
            if separator and name == REFRESH_COOKIE_NAME and value:
                candidates.append(value)

    mapped_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if mapped_token:
        candidates.append(mapped_token)

    return list(dict.fromkeys(candidates))


def _find_valid_refresh_cookie(
    request: Request,
    db: Session,
) -> tuple[str, RefreshToken, str] | None:
    now = utc_now_aware()

    for token in _get_refresh_cookie_candidates(request):
        token_user_id = decode_refresh_token(token)
        if not token_user_id:
            continue

        db_token = _find_refresh_token(db, token)
        if (
            db_token
            and not db_token.is_revoked
            and db_token.expires_at >= now
            and str(db_token.user_id) == token_user_id
        ):
            return token, db_token, token_user_id

    return None


def _new_refresh_token(user: User, db: Session) -> str:
    token = create_refresh_token(subject=user.id)
    db.add(
        RefreshToken(
            user_id=user.id,
            token=hash_refresh_token(token),
            expires_at=utc_now_aware() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    return token


def _token_response(user: User, access_token: str) -> dict:
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user.username,
        "role": user.role,
    }


def _validate_bcrypt_password_length(password: str) -> str:
    if len(password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError("비밀번호는 UTF-8 기준 72바이트 이하여야 합니다.")
    return password


# --- Pydantic Schemas ---
class LoginSchema(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="로그인 아이디")
    password: str = Field(..., min_length=1, max_length=128, description="비밀번호")


class SignupSchema(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="로그인 아이디")
    password: str = Field(..., min_length=12, max_length=128, description="비밀번호")

    _validate_password_bytes = field_validator("password")(_validate_bcrypt_password_length)


class TokenResponseSchema(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str

class UserProfileSchema(BaseModel):
    id: int
    username: str
    role: str
    trade_mode: str
    broker_provider: Optional[str] = None
    telegram_enabled: bool

class ChangePasswordSchema(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=12, max_length=128)

    _validate_password_bytes = field_validator("new_password")(_validate_bcrypt_password_length)

# --- Routes ---

@router.post("/signup", response_model=TokenResponseSchema, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupSchema, response: Response, db: Session = Depends(get_db)):
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
        access_token = create_access_token(
            subject=new_user.id,
            token_version=new_user.token_version,
        )
        refresh_token = _new_refresh_token(new_user, db)

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

    return _token_response(new_user, access_token)

@router.post("/login", response_model=TokenResponseSchema)
def login(payload: LoginSchema, response: Response, db: Session = Depends(get_db)):
    """
    사용자 로그인 및 JWT 발급 API (브루트포스 방어 및 타이밍 공격 방어 포함)
    """
    user = db.query(User).filter(User.username == payload.username).first()

    # 타이밍 공격 방어: 유저가 존재하지 않더라도 더미 bcrypt 연산을 돌려 응답 소요 시간 대칭화
    if user:
        is_password_correct = verify_password(payload.password, user.hashed_password)
    else:
        # 동일한 부하가 걸리도록 더미 bcrypt 연산 실행
        verify_password(payload.password, DUMMY_PASSWORD_HASH)
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

    access_token = create_access_token(
        subject=user.id,
        token_version=user.token_version,
    )
    refresh_token = _new_refresh_token(user, db)
    db.commit()

    _set_refresh_cookie(response, refresh_token)

    return _token_response(user, access_token)

@router.post("/refresh", response_model=TokenResponseSchema)
def refresh_token(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    HttpOnly 쿠키의 Refresh Token을 회전하고 새 Access Token을 발급합니다.
    """
    _validate_cookie_request_origin(request)
    cookie_candidates = _get_refresh_cookie_candidates(request)

    if not cookie_candidates:
        raise HTTPException(status_code=401, detail="Refresh token missing")

    valid_cookie = _find_valid_refresh_cookie(request, db)
    if not valid_cookie:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    _, db_token, _ = valid_cookie

    # 유저 조회
    user = db.query(User).filter(User.id == db_token.user_id).first()
    if not user:
        _delete_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="User not found")

    db_token.is_revoked = True
    rotated_refresh_token = _new_refresh_token(user, db)
    access_token = create_access_token(
        subject=user.id,
        token_version=user.token_version,
    )
    db.commit()
    _set_refresh_cookie(response, rotated_refresh_token)
    return _token_response(user, access_token)

@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    로그아웃 (Refresh Token 파기 및 쿠키 삭제)
    """
    _validate_cookie_request_origin(request)
    cookie_candidates = _get_refresh_cookie_candidates(request)
    revoked_token_ids: set[int] = set()

    for token in cookie_candidates:
        db_token = _find_refresh_token(db, token)
        if db_token and db_token.id not in revoked_token_ids:
            db_token.is_revoked = True
            revoked_token_ids.add(db_token.id)

    if revoked_token_ids:
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
    current_user.token_version += 1

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
        "role": current_user.role,
        "trade_mode": current_user.settings.trade_mode if current_user.settings else "SIMULATED",
        "broker_provider": current_user.settings.broker_provider if current_user.settings else None,
        "telegram_enabled": current_user.settings.telegram_enabled if current_user.settings else False
    }
