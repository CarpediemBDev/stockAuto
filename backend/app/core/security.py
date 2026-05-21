import os
from datetime import datetime, timedelta
from typing import Union, Any
import jwt
import bcrypt

# JWT 설정
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "stockauto_super_secret_key_2026_change_me_in_production")
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
