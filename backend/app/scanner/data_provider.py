import yfinance as yf
import pandas as pd
import asyncio
import time
import threading
from app.core.logging import logger

# yfinance는 프로세스 전체 singleton session/crumb를 공유한다.
# 병렬 호출 시 Yahoo crumb가 흔들릴 수 있어 모든 Yahoo 호출을 이 게이트로 직렬화한다.
_yf_lock = threading.RLock()
_yf_last_call = 0.0
_yf_min_interval = 0.25

_cache_lock = threading.RLock()

# 전역 캐시 장치
_ohlcv_cache = {}
_ticker_info_cache = {}      # Key: ticker, Value: (timestamp, dict)
_ticker_news_cache = {}      # Key: ticker, Value: (timestamp, list)
_ticker_fast_info_cache = {}  # Key: ticker, Value: (timestamp, fast_info_obj)
_bulk_ohlcv_cache = {}        # Key: (sorted_tickers, interval, period, group_by), Value: (timestamp, df)

OHLCV_CACHE_TTL = 45.0
BULK_OHLCV_CACHE_TTL = 60.0
TICKER_INFO_CACHE_TTL = 86400.0
TICKER_NEWS_CACHE_TTL = 600.0
TICKER_FAST_INFO_CACHE_TTL = 86400.0

def _clone_cached(value):
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if isinstance(value, dict):
        return value.copy()
    if isinstance(value, list):
        return value.copy()
    return value

def _read_cache(cache: dict, cache_key, ttl: float):
    now = time.time()
    with _cache_lock:
        cached = cache.get(cache_key)
        if not cached:
            return None
        cached_time, cached_value = cached
        if now - cached_time < ttl:
            return _clone_cached(cached_value)
    return None

def _write_cache(cache: dict, cache_key, value):
    with _cache_lock:
        cache[cache_key] = (time.time(), _clone_cached(value))

def _normalize_ohlcv(data: pd.DataFrame) -> pd.DataFrame:
    if data is None:
        return pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        data = data.copy()
        data.columns = data.columns.get_level_values(0)
    return data

def _run_yfinance_cached(cache: dict, cache_key, ttl: float, fetcher):
    cached = _read_cache(cache, cache_key, ttl)
    if cached is not None:
        return cached

    global _yf_last_call
    with _yf_lock:
        cached = _read_cache(cache, cache_key, ttl)
        if cached is not None:
            return cached

        now = time.time()
        wait_seconds = _yf_min_interval - (now - _yf_last_call)
        if wait_seconds > 0:
            time.sleep(wait_seconds)

        try:
            value = fetcher()
        finally:
            _yf_last_call = time.time()

        _write_cache(cache, cache_key, value)
        return _clone_cached(value)

async def fetch_ohlcv(ticker: str, interval: str = "1h", period: str = "5d") -> pd.DataFrame:
    """
    지정한 단일 종목의 OHLCV 데이터를 비동기로 안전하게 가져오고 MultiIndex 컬럼을 단일화합니다.
    (💡 10초 전역 캐싱 적용 - 중복 요출 원천 차단)
    """
    cache_key = (ticker, interval, period)
    try:
        data = await asyncio.to_thread(
            _run_yfinance_cached,
            _ohlcv_cache,
            cache_key,
            OHLCV_CACHE_TTL,
            lambda: _normalize_ohlcv(
                yf.download(ticker, period=period, interval=interval, progress=False, threads=False)
            )
        )
        return data if not data.empty else pd.DataFrame()
    except Exception as e:
        logger.warning(f"[DataProvider] Error fetching {ticker} ({interval}): {e}")
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
    return await fetch_ohlcv(market_index, interval="15m", period="10d")

async def fetch_bulk_ohlcv(tickers: list, interval: str, period: str, group_by: str = "ticker") -> pd.DataFrame:
    """
    여러 종목의 OHLCV 데이터를 벌크(대량)로 다운로드합니다.
    (💡 10초 전역 캐싱 적용)
    """
    if not tickers:
        return pd.DataFrame()
    cache_key = (tuple(sorted(tickers)), interval, period, group_by)
    try:
        data = await asyncio.to_thread(
            _run_yfinance_cached,
            _bulk_ohlcv_cache,
            cache_key,
            BULK_OHLCV_CACHE_TTL,
            lambda: yf.download(
                tickers,
                period=period,
                interval=interval,
                group_by=group_by,
                progress=False,
                threads=False
            )
        )
        return data
    except Exception as e:
        logger.warning(f"[DataProvider] Error in bulk download for {len(tickers)} tickers ({interval}): {e}")
        return pd.DataFrame()

# ⭐ v2.0 Ticker 연관 모든 API 캡슐화 추가 (완벽한 벤더 격리)

async def fetch_ticker_news(ticker: str) -> list:
    """
    종목의 실시간 최신 뉴스 목록을 비동기 스레드로 안전하게 수집합니다.
    (💡 10초 전역 캐싱 적용)
    """
    try:
        news_data = await asyncio.to_thread(
            _run_yfinance_cached,
            _ticker_news_cache,
            ticker,
            TICKER_NEWS_CACHE_TTL,
            lambda: yf.Ticker(ticker).news or []
        )
        return news_data
    except Exception as e:
        logger.warning(f"[DataProvider] Error fetching news for {ticker}: {e}")
        return []

async def fetch_ticker_info(ticker: str) -> dict:
    """
    종목의 실시간 재무/기본정보(info)를 비동기 스레드로 안전하게 수집합니다.
    (💡 10초 전역 캐싱 적용)
    """
    try:
        info_data = await asyncio.to_thread(
            _run_yfinance_cached,
            _ticker_info_cache,
            ticker,
            TICKER_INFO_CACHE_TTL,
            lambda: yf.Ticker(ticker).info or {}
        )
        return info_data
    except Exception as e:
        logger.warning(f"[DataProvider] Error fetching info for {ticker}: {e}")
        return {}

def fetch_ticker_fast_info(ticker: str):
    """
    종목의 빠른 지표(fast_info)를 동기식으로 수집합니다. (동기 API용)
    (💡 10초 전역 캐싱 적용)
    """
    try:
        return _run_yfinance_cached(
            _ticker_fast_info_cache,
            ticker,
            TICKER_FAST_INFO_CACHE_TTL,
            lambda: yf.Ticker(ticker).fast_info
        )
    except Exception as e:
        logger.warning(f"[DataProvider] Error fetching fast_info for {ticker}: {e}")
        return None

def fetch_bulk_ohlcv_sync(tickers: list, interval: str, period: str, group_by: str = "ticker") -> pd.DataFrame:
    """
    여러 종목의 OHLCV 데이터를 동기식으로 다운로드합니다. (동기 API/메서드용)
    (💡 10초 전역 캐싱 적용)
    """
    if not tickers:
        return pd.DataFrame()
    cache_key = (tuple(sorted(tickers)), interval, period, group_by)
    try:
        data = _run_yfinance_cached(
            _bulk_ohlcv_cache,
            cache_key,
            BULK_OHLCV_CACHE_TTL,
            lambda: yf.download(
                tickers,
                period=period,
                interval=interval,
                group_by=group_by,
                progress=False,
                threads=False
            )
        )
        return data
    except Exception as e:
        logger.warning(f"[DataProvider] Error in sync bulk download for {len(tickers)} tickers ({interval}): {e}")
        return pd.DataFrame()

def fetch_ticker_info_sync(ticker: str) -> dict:
    """
    종목의 실시간 재무/기본정보(info)를 동기식으로 안전하게 수집합니다. (동기 API용)
    (💡 10초 전역 캐싱 적용)
    """
    try:
        return _run_yfinance_cached(
            _ticker_info_cache,
            ticker,
            TICKER_INFO_CACHE_TTL,
            lambda: yf.Ticker(ticker).info or {}
        )
    except Exception as e:
        logger.warning(f"[DataProvider] Error fetching sync info for {ticker}: {e}")
        return {}

def fetch_ohlcv_sync(ticker: str, interval: str = "1h", period: str = "5d") -> pd.DataFrame:
    """
    단일 종목의 OHLCV 데이터를 동기식으로 안전하게 가져오고 MultiIndex 컨럼을 단일화합니다. (동기 API/메서드용)
    (💡 10초 전역 캐싱 적용 - 비동기 fetch_ohlcv와 캐시 공유)
    """
    cache_key = (ticker, interval, period)
    try:
        data = _run_yfinance_cached(
            _ohlcv_cache,
            cache_key,
            OHLCV_CACHE_TTL,
            lambda: _normalize_ohlcv(
                yf.download(ticker, period=period, interval=interval, progress=False, threads=False)
            )
        )
        return data if not data.empty else pd.DataFrame()
    except Exception as e:
        logger.warning(f"[DataProvider] Error sync fetching {ticker} ({interval}): {e}")
        return pd.DataFrame()

