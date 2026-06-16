import httpx
import asyncio

from app.scanner.toss_crawler import fetch_toss_market_scanners

# 고정 미국 주요 종목군 (모든 외부 소스 실패 시 최후의 안전망)
SAFETY_TECH_LIST = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META", "AMD", "NFLX", "TSM"]

async def fetch_yahoo_market_scanners() -> dict[str, list[str]]:
    """Yahoo Finance API를 통해 4가지 핵심 스캐너 지표를 병렬로 가져옵니다."""
    scanners = {
        "YAHOO_ACTIVE": "most_actives",
        "YAHOO_GAINER": "day_gainers",
        "YAHOO_LOSER": "day_losers",
        "YAHOO_TECH": "growth_technology_stocks"
    }
    
    results = {k: [] for k in scanners.keys()}
    headers = {"User-Agent": "Mozilla/5.0"}
    
    async def fetch_single_scanner(client, tag, scr_id):
        url = f"https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=false&scrIds={scr_id}&count=100"
        try:
            res = await client.get(url, headers=headers, timeout=5.0)
            if res.status_code == 200:
                data = res.json()
                quotes = data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
                tickers = [q.get("symbol") for q in quotes if q.get("symbol")]
                if tickers: 
                    results[tag] = tickers
                    print(f"[Discovery] {tag} found {len(tickers)} tickers.")
        except Exception as e:
            print(f"[Discovery] Yahoo Screener ({tag}) failed: {e}")

    try:
        async with httpx.AsyncClient() as client:
            tasks = [fetch_single_scanner(client, tag, scr_id) for tag, scr_id in scanners.items()]
            await asyncio.gather(*tasks)
    except Exception as e:
        print(f"[Discovery] Yahoo scanners execution failed: {e}")
        
    return results

async def get_seed_tickers() -> tuple[list, dict[str, list[str]]]:
    """
    여러 소스에서 분석 대상 종목(Seed Tickers)을 병렬로 수집하고 병합합니다.
    Returns: (tickers, source_map)
      - tickers: 중복 제거된 전체 종목 리스트
      - source_map: {ticker: ["YAHOO_*"|"SAFETY_NET", ...]} 공용 시장 출처 꼬리표 맵
    """
    print("\n[Discovery] Starting parallel ticker discovery process...")

    source_map: dict[str, set[str]] = {}

    toss_results, yahoo_results = await asyncio.gather(
        fetch_toss_market_scanners(),
        fetch_yahoo_market_scanners(),
        return_exceptions=True,
    )

    scanners_results: dict[str, list[str]] = {}
    for source_name, result in (("Toss", toss_results), ("Yahoo", yahoo_results)):
        if isinstance(result, Exception):
            print(f"[Discovery] {source_name} scanners failed: {result}")
            continue
        if result:
            scanners_results.update(result)

    if not scanners_results or not any(scanners_results.values()):
        print("[Discovery] Toss and Yahoo sources failed. Using safety tech list only.")

    # 출처 꼬리표(Source Tag) 부착
    for tag, tickers in scanners_results.items():
        for t in tickers:
            source_map.setdefault(t, set()).add(tag)
            source_map[t].add("MARKET")
            
    for t in SAFETY_TECH_LIST:
        source_map.setdefault(t, set()).add("SAFETY_NET")
        source_map[t].add("MARKET")

    final_universe = list(source_map.keys())

    if not final_universe:
        print("[Discovery] All sources failed. Using safety tech list.")
        fallback_map = {t: ["MARKET"] for t in SAFETY_TECH_LIST}
        return list(SAFETY_TECH_LIST), fallback_map

    # set → sorted list 변환 (JSON 직렬화 호환)
    final_source_map = {t: sorted(s) for t, s in source_map.items()}

    print(f"[Discovery] Process complete. Final universe size: {len(final_universe)}")
    total_market = sum(len(v) for v in scanners_results.values())
    print(f" - Market Scanner Total: {total_market} | Safety: {len(SAFETY_TECH_LIST)}")

    return final_universe, final_source_map
