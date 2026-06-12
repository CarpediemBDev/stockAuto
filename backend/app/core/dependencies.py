from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.models import User
from app.core.security import decode_access_token_claims

security_scheme = HTTPBearer()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    HTTP Bearer JWT 토큰 검증 및 현재 요청 중인 사용자 객체 추출 의존성 주입 함수.
    """
    token = credentials.credentials
    claims = decode_access_token_claims(token)
    user_id_str = claims.get("sub") if claims else None

    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않거나 만료된 토큰입니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = int(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰 서식이 올바르지 않습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_version = claims.get("ver", 0)
    if not isinstance(token_version, int) or token_version != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="폐기된 로그인 세션입니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """
    현재 사용자가 관리자(ADMIN) 역할을 가지고 있는지 검증하는 의존성 주입 함수.
    """
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 권한이 필요합니다.",
        )
    return current_user


class RequireRole:
    """
    Role-based access control (RBAC) 팩토리 의존성.
    사용법: Depends(RequireRole("ADMIN")) 또는 Depends(RequireRole("SUPERADMIN"))
    """
    def __init__(self, required_role: str):
        self.required_role = required_role

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        if current_user.role != self.required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"{self.required_role} 권한이 필요합니다.",
            )
        return current_user
