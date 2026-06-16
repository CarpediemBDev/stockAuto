import asyncio
import json
import os

from app.core.logging import logger


async def fetch_toss_market_scanners() -> dict[str, list[str]]:
    """Run the Toss Node/Puppeteer scraper and return normalized scanner results."""
    logger.info("[TossScraperRunner] Fetching Top 100 ranking data from Toss Securities via Node.js Puppeteer...")
    script_path = os.path.join(os.path.dirname(__file__), "toss_scraper.js")

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
            logger.error("[TossScraperRunner] Node script failed: %s", stderr_text)
            return {}

        output = stdout.decode("utf-8", errors="replace").strip()
        lines = [line for line in output.splitlines() if line.strip()]
        if not lines:
            return {}

        results = json.loads(lines[-1])
        total_found = sum(len(tickers) for tickers in results.values())
        if total_found == 0:
            if stderr_text:
                logger.error("[TossScraperRunner] Empty result with scraper stderr: %s", stderr_text)
            else:
                logger.warning("[TossScraperRunner] Empty result from Toss scraper.")
            return {}

        if stderr_text:
            logger.warning("[TossScraperRunner] Scraper completed with stderr: %s", stderr_text)
        logger.info("[TossScraperRunner] Successfully extracted %s tickers across 6 tabs.", total_found)
        return results

    except asyncio.TimeoutError:
        logger.error("[TossScraperRunner] Scraper runner timed out after 45 seconds.")
        return {}
    except Exception as exc:
        logger.error("[TossScraperRunner] Unexpected error during scraping: %s", exc)
        return {}
