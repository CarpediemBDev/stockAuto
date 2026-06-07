import httpx
import asyncio

async def test():
    urls = [
        "https://api.stock.naver.com/stock/exchange/NASDAQ/tradeAmount?page=1&pageSize=10",
        "https://api.stock.naver.com/stock/exchange/NASDAQ/volume?page=1&pageSize=10",
        "https://api.stock.naver.com/stock/exchange/NASDAQ/upRate?page=1&pageSize=10",
        "https://api.stock.naver.com/stock/exchange/NASDAQ/fluctuation?page=1&pageSize=10",
        "https://api.stock.naver.com/ranking/stock/usa/tradeAmount?page=1&pageSize=10",
        "https://api.stock.naver.com/ranking/stock/local/tradeAmount?page=1&pageSize=10"
    ]
    headers = {"User-Agent": "Mozilla/5.0"}
    async with httpx.AsyncClient() as client:
        for u in urls:
            try:
                res = await client.get(u, headers=headers)
                print(f"{u} -> {res.status_code}")
                if res.status_code == 200:
                    data = res.json()
                    stocks = data.get("stocks", [])
                    print(", ".join([s.get('symbolCode', '') for s in stocks[:5]]))
            except Exception as e:
                pass

asyncio.run(test())
