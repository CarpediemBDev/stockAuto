import sqlite3
import os

# backend 디렉터리에 있는 stockauto.db를 가리킵니다.
db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "stockauto.db")
print("Target DB path:", db_path)
print("File exists:", os.path.exists(db_path))

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 테이블 목록 조회
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [t[0] for t in cursor.fetchall()]
print("Tables in DB:", tables)

if "user_settings" in tables:
    cursor.execute("SELECT user_id, telegram_bot_token, telegram_chat_id, telegram_enabled, broker_provider, trade_mode FROM user_settings")
    rows = cursor.fetchall()
    print("\n--- user_settings Rows ---")
    for r in rows:
        print(f"User ID: {r[0]}")
        print(f"Telegram Bot Token: {r[1]}")
        print(f"Telegram Chat ID: {r[2]}")
        print(f"Telegram Enabled: {r[3]}")
        print(f"Broker: {r[4]} | Mode: {r[5]}")
        print("-" * 30)
else:
    print("user_settings table NOT found!")

conn.close()
