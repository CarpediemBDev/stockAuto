import sqlite3
import os

def main():
    db_path = "backend/stockauto.db"
    if not os.path.exists(db_path):
        db_path = "stockauto.db"
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    c.execute("SELECT id, level, message, created_at FROM action_logs ORDER BY created_at DESC LIMIT 30")
    logs = c.fetchall()
    print("=== LATEST 30 ACTION LOGS ===")
    for log in logs:
        print(f"[{log[1]}] {log[2]} | {log[3]}")
        
    conn.close()

if __name__ == "__main__":
    main()
