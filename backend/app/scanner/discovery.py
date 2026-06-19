import asyncio

import httpx

from app.core.logging import logger
from app.scanner.toss_scraper_runner import fetch_toss_market_scanners

# 모든 외부 소스가 실패해도 종목 발굴이 0건이 되지 않도록 보장하는 기본 안전망입니다.
SAFETY_TECH_LIST = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META", "AMD", "NFLX", "TSM"]


async def fetch_yahoo_market_scanners() -> dict[str, list[str]]:
    """Yahoo Finance API에서 주요 미국 시장 스캐너 종목을 가져옵니다."""
    scanners = {
        "YAHOO_ACTIVE": "most_actives",
        "YAHOO_GAINER": "day_gainers",
        "YAHOO_LOSER": "day_losers",
        "YAHOO_TECH": "growth_technology_stocks",
    }

    results = {key: [] for key in scanners}
    headers = {"User-Agent": "Mozilla/5.0"}

    async def fetch_single_scanner(client: httpx.AsyncClient, tag: str, scanner_id: str) -> None:
        url = (
            "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
            f"?formatted=false&scrIds={scanner_id}&count=100"
        )
        try:
            response = await client.get(url, headers=headers, timeout=5.0)
            if response.status_code != 200:
                logger.warning("[Discovery] %s returned status %s.", tag, response.status_code)
                return
            data = response.json()
            quotes = data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
            tickers = [quote.get("symbol") for quote in quotes if quote.get("symbol")]
            if tickers:
                results[tag] = tickers
        except Exception as exc:
            logger.warning("[Discovery] Yahoo Screener (%s) failed: %s", tag, exc)

    try:
        async with httpx.AsyncClient() as client:
            tasks = [fetch_single_scanner(client, tag, scanner_id) for tag, scanner_id in scanners.items()]
            await asyncio.gather(*tasks)
    except Exception as exc:
        logger.warning("[Discovery] Yahoo scanners execution failed: %s", exc)

    return results


async def fetch_naver_market_scanners() -> dict[str, list[str]]:
    """Naver crawler 결과를 공용 discovery source map 형태로 정규화합니다."""
    try:
        from app.scanner.naver_scraper_runner import fetch_naver_us_rankings
    except Exception as exc:
        logger.warning("[Discovery] Naver scraper unavailable: %s", exc)
        return {}

    try:
        results = await fetch_naver_us_rankings()
        cleaned_results = {}
        for tag, tickers in results.items():
            cleaned = [t for t in tickers if t]
            if cleaned:
                cleaned_results[tag] = cleaned
        return cleaned_results
    except Exception as exc:
        logger.warning("[Discovery] Naver scraper failed: %s", exc)
        return {}


def count_source_results(results: dict[str, list[str]]) -> dict[str, int]:
    return {tag: len(tickers) for tag, tickers in sorted(results.items()) if tickers}


from datetime import datetime

LATEST_DISCOVERY_STATS = {
    "last_run": None,
    "status": "IDLE", # IDLE, RUNNING, COMPLETED, ERROR
    "toss": {"count": 0, "status": "PENDING", "error": None},
    "yahoo": {"count": 0, "status": "PENDING", "error": None},
    "naver": {"count": 0, "status": "PENDING", "error": None},
    "total_universe": 0,
}

async def get_seed_tickers() -> tuple[list[str], dict[str, list[str]]]:
    """
    Toss, Yahoo Finance, Naver 후보군을 병렬 수집해 하나의 종목 유니버스로 병합합니다.

    하나의 소스라도 성공하면 해당 종목으로 분석을 진행하며, 모든 외부 소스가 실패해도
    SAFETY_TECH_LIST를 추가해 종목 발굴이 0건이 되지 않도록 보장합니다.
    """
    logger.info("[Discovery] Starting parallel ticker discovery process...")
    LATEST_DISCOVERY_STATS["status"] = "RUNNING"
    LATEST_DISCOVERY_STATS["last_run"] = datetime.now().isoformat()

    source_map: dict[str, set[str]] = {}

    toss_results, yahoo_results, naver_results = await asyncio.gather(
        fetch_toss_market_scanners(),
        fetch_yahoo_market_scanners(),
        fetch_naver_market_scanners(),
        return_exceptions=True,
    )

    scanners_results: dict[str, list[str]] = {}
    
    # Toss Stats
    if isinstance(toss_results, Exception):
        logger.warning("[Discovery] Toss scanners failed: %s", toss_results)
        LATEST_DISCOVERY_STATS["toss"] = {"count": 0, "status": "ERROR", "error": str(toss_results)}
    else:
        source_counts = count_source_results(toss_results)
        if source_counts:
            logger.info("[Discovery] Toss source counts: %s", source_counts)
            scanners_results.update(toss_results)
        else:
            logger.warning("[Discovery] Toss returned no tickers.")
        LATEST_DISCOVERY_STATS["toss"] = {"count": sum(len(v) for v in toss_results.values()), "status": "SUCCESS", "error": None}

    # Yahoo Stats
    if isinstance(yahoo_results, Exception):
        logger.warning("[Discovery] Yahoo scanners failed: %s", yahoo_results)
        LATEST_DISCOVERY_STATS["yahoo"] = {"count": 0, "status": "ERROR", "error": str(yahoo_results)}
    else:
        source_counts = count_source_results(yahoo_results)
        if source_counts:
            logger.info("[Discovery] Yahoo source counts: %s", source_counts)
            scanners_results.update(yahoo_results)
        else:
            logger.warning("[Discovery] Yahoo returned no tickers.")
        LATEST_DISCOVERY_STATS["yahoo"] = {"count": sum(len(v) for v in yahoo_results.values()), "status": "SUCCESS", "error": None}

    # Naver Stats
    if isinstance(naver_results, Exception):
        logger.warning("[Discovery] Naver scanners failed: %s", naver_results)
        LATEST_DISCOVERY_STATS["naver"] = {"count": 0, "status": "ERROR", "error": str(naver_results)}
    else:
        source_counts = count_source_results(naver_results)
        if source_counts:
            logger.info("[Discovery] Naver source counts: %s", source_counts)
            scanners_results.update(naver_results)
        else:
            logger.warning("[Discovery] Naver returned no tickers.")
        LATEST_DISCOVERY_STATS["naver"] = {"count": sum(len(v) for v in naver_results.values()), "status": "SUCCESS", "error": None}

    if not scanners_results or not any(scanners_results.values()):
        logger.warning("[Discovery] Toss, Yahoo, and Naver sources failed. Using safety tech list only.")
        LATEST_DISCOVERY_STATS["status"] = "ERROR"

    for tag, tickers in scanners_results.items():
        for ticker in tickers:
            source_map.setdefault(ticker, set()).add(tag)
            source_map[ticker].add("MARKET")

    for ticker in SAFETY_TECH_LIST:
        source_map.setdefault(ticker, set()).add("SAFETY_NET")
        source_map[ticker].add("MARKET")

    final_universe = list(source_map.keys())

    if not final_universe:
        logger.warning("[Discovery] All sources failed. Using safety tech list.")
        fallback_map = {ticker: ["MARKET"] for ticker in SAFETY_TECH_LIST}
        LATEST_DISCOVERY_STATS["total_universe"] = len(SAFETY_TECH_LIST)
        LATEST_DISCOVERY_STATS["status"] = "COMPLETED"
        return list(SAFETY_TECH_LIST), fallback_map

    final_source_map = {ticker: sorted(sources) for ticker, sources in source_map.items()}
    total_market = sum(len(tickers) for tickers in scanners_results.values())
    
    LATEST_DISCOVERY_STATS["total_universe"] = len(final_universe)
    if LATEST_DISCOVERY_STATS["status"] != "ERROR":
        LATEST_DISCOVERY_STATS["status"] = "COMPLETED"

    logger.info(
        "[Discovery] Process complete. Final universe size: %s | Market Scanner Total: %s | Safety: %s",
        len(final_universe),
        total_market,
        len(SAFETY_TECH_LIST),
    )

    return final_universe, final_source_map
