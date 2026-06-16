import asyncio
import json
import os

from app.core.logging import logger


async def fetch_naver_us_rankings() -> list[str]:
    """Run the Naver Node/Puppeteer scraper and return normalized ticker symbols."""
    logger.info("[NaverScraperRunner] Fetching US ranking data from Naver via Node.js Puppeteer...")
    script_path = os.path.join(os.path.dirname(__file__), "naver_scraper.js")

    try:
        process = await asyncio.create_subprocess_exec(
            "node",
            script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.path.dirname(__file__),
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=45.0)
        stderr_text = stderr.decode("utf-8", errors="replace").strip()

        if process.returncode != 0:
            logger.error("[NaverScraperRunner] Node script failed: %s", stderr_text)
            return []

        output = stdout.decode("utf-8", errors="replace").strip()
        lines = [line for line in output.splitlines() if line.strip()]
        if not lines:
            return []

        tickers = json.loads(lines[-1])
        if not isinstance(tickers, list):
            logger.error("[NaverScraperRunner] Unexpected scraper output type: %s", type(tickers).__name__)
            return []

        normalized = []
        for ticker in tickers:
            if isinstance(ticker, str) and ticker:
                normalized.append(ticker)

        deduped = list(dict.fromkeys(normalized))
        if stderr_text:
            logger.warning("[NaverScraperRunner] Scraper completed with stderr: %s", stderr_text)
        logger.info("[NaverScraperRunner] Successfully extracted %s tickers.", len(deduped))
        return deduped

    except asyncio.TimeoutError:
        logger.error("[NaverScraperRunner] Scraper runner timed out after 45 seconds.")
        return []
    except Exception as exc:
        logger.error("[NaverScraperRunner] Unexpected error during scraping: %s", exc)
        return []
