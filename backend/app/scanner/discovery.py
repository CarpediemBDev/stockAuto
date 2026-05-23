import requests
import asyncio
from app.bot.kis_api import KISClient
from app.core.database import SessionLocal
from app.core.models import WatchList

# KIS API 클라이언트 초기화
kis_client = KISClient()

def fetch_db_watchlist() -> list:
    """DB에서 사용자의 관심종목 리스트를 가져옵니다."""
    db = SessionLocal()
    try:
        watchlist = db.query(WatchList).all()
        tickers = [item.ticker for item in watchlist if item.ticker]
        if tickers: print(f"[Discovery] Found {len(tickers)} tickers from DB Watchlist.")
        return tickers
    except Exception as e:
        print(f"[Discovery] DB fetch failed: {e}")
        return []
    finally:
        db.close()

async def fetch_kis_rankings() -> list:
    """KIS API를 통해 실시간 순위 종목을 가져옵니다."""
    tickers = []
    try:
        exchanges = ["NAS", "NYS"]
        rank_types = ["2", "3"] # 2: 거래대금, 3: 등락률
        for ex in exchanges:
            for rt in rank_types:
                res = await asyncio.to_thread(kis_client.get_overseas_ranking, ex, rt)
                if res:
                    tickers.extend([item.get("symb") for item in res if item.get("symb")])
        if tickers: print(f"[Discovery] Found {len(tickers)} tickers via KIS API.")
        return list(set(tickers))
    except Exception as e:
        print(f"[Discovery] KIS API failed: {e}")
        return []

async def fetch_yahoo_most_active() -> list:
    """Yahoo Finance API를 통해 실시간 활성 종목을 가져옵니다."""
    try:
        url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=false&scrIds=most_actives&count=100"
        headers = {"User-Agent": "Mozilla/5.0"}
        # HTTP 요청을 비동기 스레드에서 실행하여 블로킹 방지
        res = await asyncio.to_thread(requests.get, url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            quotes = data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
            tickers = [q.get("symbol") for q in quotes if q.get("symbol")]
            if tickers: print(f"[Discovery] Found {len(tickers)} tickers via Yahoo Finance.")
            return tickers
    except Exception as e:
        print(f"[Discovery] Yahoo Screener failed: {e}")
    return []

async def get_seed_tickers():
    """
    여러 소스에서 분석 대상 종목(Seed Tickers)을 병렬로 수집하고 병합합니다.
    """
    print("\n[Discovery] Starting parallel ticker discovery process...")
    
    # 1. 병렬 수집 예약 (KIS + Yahoo)
    kis_task = fetch_kis_rankings()
    yahoo_task = fetch_yahoo_most_active()
    
    # 2. DB 관심종목 수집 (동기)
    db_list = fetch_db_watchlist()
    
    # 3. 모든 소스 결과 대기 및 병합
    kis_list, yahoo_list = await asyncio.gather(kis_task, yahoo_task)
    final_universe = list(set(kis_list + db_list + yahoo_list))
    
    if not final_universe:
        print("[Discovery] All sources failed. Using safety tech list.")
        return ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META", "AMD", "NFLX", "TSM"]
    
    print(f"[Discovery] Process complete. Final universe size: {len(final_universe)}")
    print(f" - KIS: {len(kis_list)} | Yahoo: {len(yahoo_list)} | Watchlist: {len(db_list)}")
    
    return final_universe
