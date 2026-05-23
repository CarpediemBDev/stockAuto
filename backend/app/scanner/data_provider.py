import yfinance as yf
import pandas as pd
import asyncio

async def fetch_ohlcv(ticker: str, interval: str = "1h", period: str = "5d") -> pd.DataFrame:
    """
    지정한 단일 종목의 OHLCV 데이터를 비동기로 안전하게 가져오고 MultiIndex 컬럼을 단일화합니다.
    """
    try:
        data = await asyncio.to_thread(yf.download, ticker, period=period, interval=interval, progress=False)
        if data.empty:
            return pd.DataFrame()
            
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
            
        return data
    except Exception as e:
        print(f"[DataProvider] Error fetching {ticker} ({interval}): {e}")
        return pd.DataFrame()

async def get_multi_timeframe_data(ticker: str) -> tuple:
    """
    15분봉(추세용)과 1분봉(실행용) 데이터를 동시에 비동기 병렬로 가져옵니다.
    """
    task_15m = fetch_ohlcv(ticker, interval="15m", period="7d")
    task_1m = fetch_ohlcv(ticker, interval="1m", period="2d")
    return await asyncio.gather(task_15m, task_1m)

async def fetch_index_data(market_index: str = "QQQ") -> pd.DataFrame:
    """
    나스닥 지수(QQQ) 데이터를 가져옵니다.
    """
    return await fetch_ohlcv(market_index, interval="15m", period="2d")

async def fetch_bulk_ohlcv(tickers: list, interval: str, period: str, group_by: str = "ticker") -> pd.DataFrame:
    """
    여러 종목의 OHLCV 데이터를 벌크(대량)로 다운로드합니다.
    """
    if not tickers:
        return pd.DataFrame()
    try:
        data = await asyncio.to_thread(
            yf.download, 
            tickers, 
            period=period, 
            interval=interval, 
            group_by=group_by, 
            progress=False
        )
        return data
    except Exception as e:
        print(f"[DataProvider] Error in bulk download for {len(tickers)} tickers ({interval}): {e}")
        return pd.DataFrame()

# ⭐ v2.0 Ticker 연관 모든 API 캡슐화 추가 (완벽한 벤더 격리)

async def fetch_ticker_news(ticker: str) -> list:
    """
    종목의 실시간 최신 뉴스 목록을 비동기 스레드로 안전하게 수집합니다.
    """
    try:
        ticker_obj = yf.Ticker(ticker)
        news = await asyncio.to_thread(lambda: ticker_obj.news)
        return news if news else []
    except Exception as e:
        print(f"[DataProvider] Error fetching news for {ticker}: {e}")
        return []

async def fetch_ticker_info(ticker: str) -> dict:
    """
    종목의 실시간 재무/기본정보(info)를 비동기 스레드로 안전하게 수집합니다.
    """
    try:
        ticker_obj = yf.Ticker(ticker)
        info = await asyncio.to_thread(lambda: ticker_obj.info)
        return info if info else {}
    except Exception as e:
        print(f"[DataProvider] Error fetching info for {ticker}: {e}")
        return {}

def fetch_ticker_fast_info(ticker: str):
    """
    종목의 빠른 지표(fast_info)를 동기식으로 수집합니다. (동기 API용)
    """
    try:
        ticker_obj = yf.Ticker(ticker)
        return ticker_obj.fast_info
    except Exception as e:
        print(f"[DataProvider] Error fetching fast_info for {ticker}: {e}")
        return None

def fetch_bulk_ohlcv_sync(tickers: list, interval: str, period: str, group_by: str = "ticker") -> pd.DataFrame:
    """
    여러 종목의 OHLCV 데이터를 동기식으로 다운로드합니다. (동기 API/메서드용)
    """
    if not tickers:
        return pd.DataFrame()
    try:
        data = yf.download(
            tickers, 
            period=period, 
            interval=interval, 
            group_by=group_by, 
            progress=False
        )
        return data
    except Exception as e:
        print(f"[DataProvider] Error in sync bulk download for {len(tickers)} tickers ({interval}): {e}")
        return pd.DataFrame()

def fetch_ticker_info_sync(ticker: str) -> dict:
    """
    종목의 실시간 재무/기본정보(info)를 동기식으로 안전하게 수집합니다. (동기 API용)
    """
    try:
        ticker_obj = yf.Ticker(ticker)
        return ticker_obj.info if ticker_obj.info else {}
    except Exception as e:
        print(f"[DataProvider] Error fetching sync info for {ticker}: {e}")
        return {}

def fetch_ohlcv_sync(ticker: str, interval: str = "1h", period: str = "5d") -> pd.DataFrame:
    """
    단일 종목의 OHLCV 데이터를 동기식으로 안전하게 가져오고 MultiIndex 컬럼을 단일화합니다. (동기 API/메서드용)
    """
    try:
        data = yf.download(ticker, period=period, interval=interval, progress=False)
        if data.empty:
            return pd.DataFrame()
            
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
            
        return data
    except Exception as e:
        print(f"[DataProvider] Error sync fetching {ticker} ({interval}): {e}")
        return pd.DataFrame()


