# -*- coding: utf-8 -*-
import httpx
import asyncio

async def probe():
    endpoints = [
        "https://api.stock.naver.com/stock/exchange/NASDAQ/marketValue?page=1&pageSize=3",
        "https://api.stock.naver.com/stock/exchange/NASDAQ/tradeAmount?page=1&pageSize=3",
        "https://api.stock.naver.com/stock/exchange/NASDAQ/volume?page=1&pageSize=3",
        "https://api.stock.naver.com/stock/exchange/NASDAQ/rise?page=1&pageSize=3",
        "https://api.stock.naver.com/stock/exchange/NASDAQ/fall?page=1&pageSize=3",
        "https://m.stock.naver.com/api/stocks/ranking/usa?page=1&pageSize=3&type=tradeAmount",
        "https://m.stock.naver.com/front-api/v1/worldStock/ranking/tradeAmount/USA?page=1&pageSize=3",
        "https://m.stock.naver.com/front-api/v1/worldStock/ranking/volume/USA?page=1&pageSize=3",
        "https://m.stock.naver.com/front-api/v1/worldStock/ranking/upRate/USA?page=1&pageSize=3",
        "https://m.stock.naver.com/front-api/v1/worldStock/ranking/marketValue/USA?page=1&pageSize=3"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://m.stock.naver.com/worldstock/menu/volume/USA"
    }
    
    async with httpx.AsyncClient() as client:
        for u in endpoints:
            try:
                res = await client.get(u, headers=headers, timeout=5.0)
                status = res.status_code
                print(f"[STATUS {status}] {u}")
                if status == 200:
                    data = res.json()
                    print(f"   => Success! Extracted keys: {list(data.keys())[:5] if isinstance(data, dict) else 'List'}")
            except Exception as e:
                print(f"[ERROR] {u} -> {e}")

asyncio.run(probe())
