import os
import sys

# 백엔드 모듈 경로 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.core.database import SessionLocal
from app.core.models import UserSettings

def enable_all_bots():
    db = SessionLocal()
    try:
        updated_count = db.query(UserSettings).filter(UserSettings.is_running == False).update(
            {UserSettings.is_running: True},
            synchronize_session=False
        )
        db.commit()
        print(f"SUCCESS: Updated {updated_count} user(s) to is_running=True.")
        
        total_running = db.query(UserSettings).filter(UserSettings.is_running == True).count()
        total_users = db.query(UserSettings).count()
        print(f"INFO: Total user_settings count: {total_users}, Currently running bots: {total_running}")
    except Exception as e:
        db.rollback()
        print(f"ERROR: Failed to update bot status - {e}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    enable_all_bots()
