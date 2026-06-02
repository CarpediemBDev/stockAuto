import os
from datetime import datetime, timedelta
from typing import Union, Any
import jwt
import bcrypt

# JWT 설정 및 보안 유효성 검사 (Phase 26 하네스 가드 장착)
from app.core.config import settings
from app.core.logging import logger

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
INSECURE_DEFAULT_KEYS = {
    "stockauto_super_secret_key_2026_change_me_in_production",
    "change_me_to_a_long_random_local_secret",
    "change_me_to_a_long_random_dev_secret",
    "change_me_to_a_long_random_production_secret",
}

if not JWT_SECRET_KEY or JWT_SECRET_KEY in INSECURE_DEFAULT_KEYS:
    warning_msg = (
        "[⚠️ SECURITY CRITICAL] JWT_SECRET_KEY가 설정되지 않았거나 취약한 디폴트 키를 사용 중입니다! "
        "보안을 위해 .env 파일에 안전한 JWT_SECRET_KEY를 생성해 주십시오."
    )
    
    # 실거래 모드 또는 프로덕션 프로필인 경우 시스템 기동을 중단하여 자산 완벽 보호
    if settings.IS_REAL or settings.PROFILE == "prod":
        logger.error(f"[🔥 BLOCKING STARTUP] {warning_msg}")
        raise RuntimeError("실거래(REAL) 모드에서는 안전한 JWT_SECRET_KEY 설정이 필수적입니다. 서버 구동을 차단합니다.")
    else:
        # 로컬/시뮬레이션 개발 환경에서는 경고 노출 후 임시 키 적용 허용
        logger.warning(warning_msg)
        JWT_SECRET_KEY = "stockauto_super_secret_key_2026_change_me_in_production"

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30 # 30일 동안 유효한 토큰 발급


def get_password_hash(password: str) -> str:
    """비밀번호 단방향 bcrypt 해싱"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """단방향 해시 비밀번호 매칭 검증"""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def create_access_token(subject: Union[str, Any], expires_delta: timedelta = None) -> str:
    """Access JWT 토큰 발행"""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {
        "exp": expire,
        "sub": str(subject)
    }
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Union[str, None]:
    """Access JWT 토큰 해독 및 검증"""
    try:
        decoded_token = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return decoded_token["sub"]
    except jwt.PyJWTError:
        return None
