import httpx
import asyncio
from app.core.database import SessionLocal
from app.core.models import WatchList

# 고정 미국 주요 종목군 (모든 외부 소스 실패 시 최후의 안전망)
SAFETY_TECH_LIST = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META", "AMD", "NFLX", "TSM"]

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

async def fetch_yahoo_most_active() -> list:
    """Yahoo Finance API를 통해 실시간 활성 종목을 가져옵니다."""
    try:
        url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=false&scrIds=most_actives&count=100"
        headers = {"User-Agent": "Mozilla/5.0"}
        async with httpx.AsyncClient() as client:
            res = await client.get(url, headers=headers, timeout=5.0)
            if res.status_code == 200:
                data = res.json()
                quotes = data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
                tickers = [q.get("symbol") for q in quotes if q.get("symbol")]
                if tickers: print(f"[Discovery] Found {len(tickers)} tickers via Yahoo Finance.")
                return tickers
    except Exception as e:
        print(f"[Discovery] Yahoo Screener failed: {e}")
    return []

async def get_seed_tickers() -> tuple[list, dict[str, list[str]]]:
    """
    여러 소스에서 분석 대상 종목(Seed Tickers)을 병렬로 수집하고 병합합니다.
    Returns: (tickers, source_map)
      - tickers: 중복 제거된 전체 종목 리스트
      - source_map: {ticker: ["MARKET"|"WATCHLIST", ...]} 출처 꼬리표 맵
    """
    print("\n[Discovery] Starting parallel ticker discovery process...")

    source_map: dict[str, set[str]] = {}

    # 1. 병렬 수집 예약 (Yahoo Finance)
    yahoo_task = fetch_yahoo_most_active()

    # 2. DB 관심종목 수집 (동기)
    db_list = fetch_db_watchlist()

    # 3. 모든 소스 결과 대기
    yahoo_list = await yahoo_task

    # 4. 출처 꼬리표(Source Tag) 부착
    for t in yahoo_list:
        source_map.setdefault(t, set()).add("MARKET")
    for t in SAFETY_TECH_LIST:
        source_map.setdefault(t, set()).add("MARKET")
    for t in db_list:
        source_map.setdefault(t, set()).add("WATCHLIST")

    final_universe = list(source_map.keys())

    if not final_universe:
        print("[Discovery] All sources failed. Using safety tech list.")
        fallback_map = {t: ["MARKET"] for t in SAFETY_TECH_LIST}
        return list(SAFETY_TECH_LIST), fallback_map

    # set → sorted list 변환 (JSON 직렬화 호환)
    final_source_map = {t: sorted(s) for t, s in source_map.items()}

    print(f"[Discovery] Process complete. Final universe size: {len(final_universe)}")
    print(f" - Yahoo: {len(yahoo_list)} | Watchlist: {len(db_list)} | Safety: {len(SAFETY_TECH_LIST)}")

    return final_universe, final_source_map
