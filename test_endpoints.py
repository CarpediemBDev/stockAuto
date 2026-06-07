import httpx
import asyncio

async def test():
    u = "https://api.stock.naver.com/stock/exchange/NASDAQ/marketValue?page=1&pageSize=5"
    headers = {"User-Agent": "Mozilla/5.0"}
    async with httpx.AsyncClient() as client:
        res = await client.get(u, headers=headers)
        data = res.json()
        stocks = data.get("stocks", [])
        for s in stocks:
            print(f"Name: {s.get('stockName')}, Symbol: {s.get('symbolCode')}, Reuter: {s.get('reutersCode')}")

asyncio.run(test())
