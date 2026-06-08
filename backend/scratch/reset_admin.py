import os
import sys

# 프로젝트 루트를 python path에 추가하여 app 패키지를 찾을 수 있도록 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.append(backend_dir)

from app.core.database import SessionLocal
from app.core.models import User
from app.core.security import get_password_hash
from app.core.logging import logger

def reset_admin_passwords():
    db = SessionLocal()
    try:
        # 'admin' 평문 비밀번호의 해시값 계산
        hashed_password = get_password_hash("admin")
        
        # admin 및 admin2 ~ admin10 계정 목록
        target_usernames = ["admin"] + [f"admin{i}" for i in range(2, 11)]
        
        logger.info(f"[*] Resetting passwords for: {', '.join(target_usernames)}")
        
        updated_count = 0
        for username in target_usernames:
            user = db.query(User).filter(User.username == username).first()
            if user:
                user.hashed_password = hashed_password
                # 로그인 실패 횟수 및 잠금 초기화
                user.failed_login_attempts = 0
                user.locked_until = None
                updated_count += 1
                logger.info(f"    [+] {username} 계정 비밀번호가 'admin'으로 재설정되고 잠금이 해제되었습니다.")
            else:
                logger.warning(f"    [-] {username} 계정을 데이터베이스에서 찾을 수 없습니다. (생성되지 않았음)")
                
        if updated_count > 0:
            db.commit()
            logger.info(f"[+] 총 {updated_count}개 계정의 비밀번호 초기화 및 잠금 해제가 완료되었습니다.")
        else:
            logger.warning("[!] 업데이트할 계정이 존재하지 않습니다.")
            
    except Exception as e:
        db.rollback()
        logger.error(f"[!] 비밀번호 리셋 중 오류 발생: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    reset_admin_passwords()
