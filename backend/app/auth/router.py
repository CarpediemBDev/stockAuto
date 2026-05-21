from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from app.core.database import get_db
from app.core.models import User, UserSettings
from app.core.security import get_password_hash, verify_password, create_access_token
from app.core.dependencies import get_current_user

router = APIRouter()

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

# --- Routes ---

@router.post("/signup", response_model=TokenResponseSchema, status_code=status.HTTP_201_CREATED)
def signup(payload: UserAuthSchema, db: Session = Depends(get_db)):
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
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": new_user.username
    }

@router.post("/login", response_model=TokenResponseSchema)
def login(payload: UserAuthSchema, db: Session = Depends(get_db)):
    """
    사용자 로그인 및 JWT 발급 API
    """
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다."
        )
        
    access_token = create_access_token(subject=user.id)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user.username
    }

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
