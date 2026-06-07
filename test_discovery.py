import asyncio
import sys
import os

# add backend to path
sys.path.insert(0, os.path.abspath('backend'))

from app.scanner.discovery import get_seed_tickers

async def main():
    tickers, source_map = await get_seed_tickers()
    print("\n--- TEST RESULT ---")
    
    tags = {}
    for t, sources in source_map.items():
        for s in sources:
            tags[s] = tags.get(s, 0) + 1
            
    for k, v in tags.items():
        print(f"Tag: {k} -> {v} tickers")
        
    print(f"Total Unique Tickers: {len(tickers)}")

asyncio.run(main())
