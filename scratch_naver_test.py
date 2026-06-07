import httpx
import asyncio

async def test_naver():
    url = "https://m.stock.naver.com/api/stocks/ranking/usa?page=1&pageSize=100&type=tradeAmount"
    # m.stock.naver.com api for ranking
    url2 = "https://m.stock.naver.com/api/stocks/marketValue/USA?page=1&pageSize=50"
    headers = {"User-Agent": "Mozilla/5.0"}
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(url, headers=headers)
            print("URL 1:", res.status_code, res.text[:200])
        except Exception as e:
            print("URL 1 fail:", e)
            
        try:
            res2 = await client.get(url2, headers=headers)
            print("URL 2:", res2.status_code, res2.text[:200])
        except Exception as e:
            print("URL 2 fail:", e)

asyncio.run(test_naver())
