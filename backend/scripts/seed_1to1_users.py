import sys
import os

# Add backend directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import SessionLocal
from app.core.models import User, UserSettings, Strategy

def main():
    db = SessionLocal()
    try:
        # Get all valid strategies
        strategies = db.query(Strategy).all()
        valid_strategy_types = {s.strategy_type for s in strategies}
        
        print(f"Total valid strategies: {len(valid_strategy_types)}")

        # Get all users and their settings
        users = db.query(User).all()
        
        # Get admin user's password hash to use as default for new users
        admin_user = db.query(User).filter(User.username == "admin").first()
        default_hash = admin_user.hashed_password if admin_user else "hashed_pw_placeholder"

        mapped_strategies = set()
        users_to_delete = []

        # Check existing users for fake mappings
        for user in users:
            if not user.settings:
                print(f"User {user.username} has no settings. Creating default...")
                settings = UserSettings(user_id=user.id, strategy_type="regime_switching")
                db.add(settings)
                db.commit()
                db.refresh(user)
            
            s_type = user.settings.strategy_type
            if s_type not in valid_strategy_types:
                print(f"User {user.username} mapped to fake strategy '{s_type}'. Marking for deletion or remap.")
                users_to_delete.append(user)
            elif s_type in mapped_strategies:
                print(f"User {user.username} mapped to duplicate strategy '{s_type}'. Marking for deletion or remap.")
                users_to_delete.append(user)
            else:
                mapped_strategies.add(s_type)
        
        # Handle duplicates/fakes by deleting them (to ensure strict 1:1)
        for u in users_to_delete:
            print(f"Deleting user {u.username} to prevent fake/duplicate mapping.")
            db.delete(u)
        
        db.commit()

        # Find unmapped strategies
        unmapped_strategies = valid_strategy_types - mapped_strategies
        print(f"Unmapped strategies count: {len(unmapped_strategies)}")

        # Create new users for unmapped strategies
        for s_type in unmapped_strategies:
            username = f"user_{s_type}"
            new_user = User(
                username=username,
                hashed_password=default_hash,
                role="USER"
            )
            db.add(new_user)
            db.commit()
            db.refresh(new_user)

            new_settings = UserSettings(
                user_id=new_user.id,
                strategy_type=s_type,
                trade_mode="SIMULATED"
            )
            db.add(new_settings)
            db.commit()
            print(f"Created user {username} mapped to {s_type}")

        print("1:1 mapping completed successfully.")

    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()
