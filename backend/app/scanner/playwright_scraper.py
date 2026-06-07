import asyncio
import logging
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

async def fetch_naver_us_rankings() -> list[str]:
    """
    Playwright를 사용하여 네이버 증권(해외주식) 화면에 접속해 랭킹(거래대금 등) 종목을 추출합니다.
    (API 차단 우회 및 높은 생존력 보장)
    """
    tickers = set()
    logger.info("[Playwright] Starting headless browser for Naver Finance scraping...")

    try:
        async with async_playwright() as p:
            # 헤드리스 모드로 실행 (실제 브라우저 구동)
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            # 응답 가로채기 (네이버 내부 API JSON 추출 방식 - DOM 파싱보다 훨씬 안정적)
            async def handle_response(response):
                if "api/stocks/marketValue/USA" in response.url or "api/stocks/ranking/usa" in response.url:
                    try:
                        if response.status == 200:
                            json_data = await response.json()
                            stocks = json_data.get('stocks', []) if 'stocks' in json_data else json_data
                            for stock in stocks:
                                symbol = stock.get('symbolCode')
                                if symbol:
                                    tickers.add(symbol.split('.')[0]) # e.g. AAPL.O -> AAPL
                    except Exception as e:
                        logger.error(f"[Playwright] Failed to parse intercepted JSON: {e}")

            page.on("response", handle_response)

            # 네이버 증권 해외 시가총액 페이지 접속
            await page.goto("https://m.stock.naver.com/worldstock/menu/marketValue/USA", wait_until="networkidle")
            await asyncio.sleep(2) # 추가 대기

            # 거래대금/급등 페이지도 접속하여 합집합 구성 (원한다면)
            # await page.goto("https://m.stock.naver.com/worldstock/menu/volume/USA", wait_until="networkidle")
            # await asyncio.sleep(2)

            await browser.close()
            
    except Exception as e:
        logger.error(f"[Playwright] Browser scraping failed: {e}")

    final_tickers = list(tickers)
    logger.info(f"[Playwright] Successfully extracted {len(final_tickers)} tickers.")
    return final_tickers

if __name__ == "__main__":
    # 단독 테스트 실행용
    logging.basicConfig(level=logging.INFO)
    res = asyncio.run(fetch_naver_us_rankings())
    print("Extracted Tickers:", res)
