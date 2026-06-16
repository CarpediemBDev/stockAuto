import json
import os
import asyncio
from app.core.logging import logger

async def fetch_toss_market_scanners() -> dict[str, list[str]]:
    """
    토스증권 실시간 차트 랭킹 데이터를 가져옵니다.
    의존성: Node.js 및 Puppeteer (toss_scraper.js 활용)
    """
    logger.info("[TossCrawler] Fetching Top 100 ranking data from Toss Securities via Node.js Puppeteer...")
    
    script_path = os.path.join(os.path.dirname(__file__), "toss_scraper.js")
    
    try:
        # Run node script as an external process
        process = await asyncio.create_subprocess_exec(
            "node", script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.path.dirname(__file__)
        )
        
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=45.0)
        
        stderr_text = stderr.decode("utf-8", errors="replace").strip()

        if process.returncode != 0:
            logger.error(f"[TossCrawler] Node script failed: {stderr_text}")
            return {}
            
        output = stdout.decode("utf-8").strip()
        # Find the JSON output from the last line
        lines = [line for line in output.split('\n') if line.strip()]
        if not lines:
            return {}
            
        json_output = lines[-1]
        results = json.loads(json_output)
        
        total_found = sum(len(tickers) for tickers in results.values())
        if total_found == 0:
            if stderr_text:
                logger.error(f"[TossCrawler] Empty result with scraper stderr: {stderr_text}")
            else:
                logger.warning("[TossCrawler] Empty result from Toss scraper.")
            return {}

        if stderr_text:
            logger.warning(f"[TossCrawler] Scraper completed with stderr: {stderr_text}")
        logger.info(f"[TossCrawler] Successfully extracted {total_found} tickers across 6 tabs.")
        
        return results
        
    except asyncio.TimeoutError:
        logger.error("[TossCrawler] Crawler timed out after 45 seconds.")
        return {}
    except Exception as e:
        logger.error(f"[TossCrawler] Unexpected error during crawling: {e}")
        return {}
