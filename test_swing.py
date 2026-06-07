import asyncio
import sys
import os

# 백엔드 루트 경로 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

from app.scanner.swing_prediction_cache import refresh_swing_prediction_cache, get_swing_cache_key

async def main():
    print("Testing swing prediction cache refresh...")
    try:
        cache_key = get_swing_cache_key()
        result = await refresh_swing_prediction_cache(cache_key)
        print("Refresh successful!")
        print("Sync Status:", result.get("sync_status"))
        print("Candidates count:", len(result.get("candidates", [])))
    except Exception as e:
        print(f"Runtime Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
