import asyncio
import json
import os

from app.core.logging import logger


def normalize_naver_rankings_payload(payload) -> dict[str, list[str]]:
    if isinstance(payload, list):
        unique_tickers = list(dict.fromkeys(ticker for ticker in payload if ticker))
        return {"NAVER_US_RANKING": unique_tickers} if unique_tickers else {}

    if not isinstance(payload, dict):
        logger.error("[NaverScraperRunner] Unexpected scraper output type: %s", type(payload).__name__)
        return {}

    results: dict[str, list[str]] = {}
    for tag, tickers in payload.items():
        if not isinstance(tag, str) or not isinstance(tickers, list):
            continue
        cleaned = list(dict.fromkeys(ticker for ticker in tickers if ticker))
        if cleaned:
            results[tag] = cleaned
    return results


async def fetch_naver_us_rankings() -> dict[str, list[str]]:
    """Run the Naver Node/Puppeteer scraper and return normalized scanner results."""
    logger.info("[NaverScraperRunner] Fetching Top ranking data from Naver via Node.js Puppeteer...")
    script_path = os.path.join(os.path.dirname(__file__), "naver_scraper.js")

    try:
        process = await asyncio.create_subprocess_exec(
            "node",
            script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.path.dirname(__file__),
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=45.0)
        finally:
            if process.returncode is None:
                try:
                    process.kill()
                except Exception:
                    pass
                    
        stderr_text = stderr.decode("utf-8", errors="replace").strip()

        if process.returncode != 0:
            logger.error("[NaverScraperRunner] Node script failed: %s", stderr_text)
            return {}

        output = stdout.decode("utf-8", errors="replace").strip()
        lines = [line for line in output.splitlines() if line.strip()]
        if not lines:
            return {}

        results = normalize_naver_rankings_payload(json.loads(lines[-1]))

        total_found = sum(len(tickers) for tickers in results.values())
        if total_found == 0:
            if stderr_text:
                logger.error("[NaverScraperRunner] Empty result with scraper stderr: %s", stderr_text)
            else:
                logger.warning("[NaverScraperRunner] Empty result from Naver scraper.")
            return {}

        if stderr_text:
            logger.warning("[NaverScraperRunner] Scraper completed with stderr: %s", stderr_text)
        logger.info("[NaverScraperRunner] Successfully extracted %s tickers across 5 tabs.", total_found)
        return results

    except asyncio.TimeoutError:
        logger.error("[NaverScraperRunner] Scraper runner timed out after 45 seconds.")
        return {}
    except Exception as exc:
        logger.error("[NaverScraperRunner] Unexpected error during scraping: %s", exc)
        return {}
