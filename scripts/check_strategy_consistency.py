# -*- coding: utf-8 -*-
import sys
from pathlib import Path
import sqlite3
import re

def get_factory_keys(root: Path) -> set[str]:
    factory_path = root / "backend" / "app" / "strategies" / "strategy_factory.py"
    if not factory_path.exists():
        return set()
    content = factory_path.read_text(encoding="utf-8")
    
    keys = set()
    for match in re.finditer(r'strategy_type\s*==\s*"([^"]+)"', content):
        keys.add(match.group(1))
    
    for match in re.finditer(r'strategy_type\s*in\s*\[(.*?)\]', content):
        list_str = match.group(1)
        for string_match in re.finditer(r'"([^"]+)"', list_str):
            keys.add(string_match.group(1))
            
    return keys

def check_consistency(root: Path) -> int:
    db_path = root / "backend" / "stockauto.db"
    if not db_path.exists():
        print(f"  [WARN] DB not found at {db_path}, skipping consistency check.")
        return 0
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT strategy_type FROM strategies WHERE is_active=1")
        db_keys = {row[0] for row in cursor.fetchall()}
    except sqlite3.OperationalError:
        print("  [WARN] strategies table not found or error reading, skipping consistency check.")
        return 0
    finally:
        conn.close()
    
    factory_keys = get_factory_keys(root)
    multi_slot_keys = {"multi_slot", "multi_slot_3", "three_slot", "core_satellite"}
    code_keys = factory_keys | multi_slot_keys
    
    phantom_keys = db_keys - code_keys
    missing_in_db = code_keys - db_keys
    
    status = 0
    if phantom_keys:
        print(f"  [FAIL] DB contains phantom strategies not recognized by code: {phantom_keys}")
        status = 1
    
    if missing_in_db:
        print(f"  [WARN] Code contains strategies missing in DB (likely aliases): {missing_in_db}")
        
    if status == 0:
        print(f"  [OK] Strategy catalog consistency check passed. DB keys: {len(db_keys)}, Code keys: {len(code_keys)}")
        
    return status

if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    sys.exit(check_consistency(root))
