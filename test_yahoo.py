import httpx
import asyncio

async def test():
    urls = [
        "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=false&scrIds=day_gainers&count=20",
        "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=false&scrIds=day_losers&count=20",
        "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=false&scrIds=most_actives&count=20"
    ]
    headers = {"User-Agent": "Mozilla/5.0"}
    async with httpx.AsyncClient() as client:
        for u in urls:
            try:
                res = await client.get(u, headers=headers)
                print(f"{u} -> {res.status_code}")
                if res.status_code == 200:
                    data = res.json()
                    quotes = data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
                    print(u.split("=")[-2].split("&")[0], ":", ", ".join([q.get('symbol', '') for q in quotes[:5]]))
            except Exception as e:
                pass

asyncio.run(test())
