import time
import pandas as pd
import threading
from app.scanner.data_provider import fetch_ohlcv_sync
from app.core.logging import logger

class FXRateCache:
    """
    사용자와 무관하게 공유되는 프로세스 전역 원/달러 환율 캐시.
    스케줄러는 한 자동매매 사이클마다 이 값을 한 번만 읽어 모든 사용자 계산에 주입합니다.
    """
    _cached_rate = 1350.0
    _last_fetched = 0.0
    _cache_duration = 600.0  # 10분 (600초)
    _lock = threading.RLock()

    @classmethod
    def get_rate(cls) -> float:
        now = time.time()
        if now - cls._last_fetched <= cls._cache_duration:
            return cls._cached_rate

        with cls._lock:
            now = time.time()
            if now - cls._last_fetched <= cls._cache_duration:
                return cls._cached_rate

            try:
                # 10분 이상 지났을 때만 실제 Yahoo Finance에서 환율 조회
                df_fx = fetch_ohlcv_sync("USDKRW=X", period="1d")
                if not df_fx.empty:
                    if isinstance(df_fx.columns, pd.MultiIndex):
                        df_fx.columns = df_fx.columns.get_level_values(0)
                    cls._cached_rate = float(df_fx["Close"].iloc[-1])
                    logger.info(f"[FXCache] Updated live rate successfully: {cls._cached_rate}")
                else:
                    logger.warning(f"[FXCache] Empty live rate response, using cached value {cls._cached_rate}")
                cls._last_fetched = time.time()
            except Exception as e:
                logger.warning(f"[FXCache] Failed to download live rate, using cached value {cls._cached_rate}: {e}")
                # 실패 시에는 다음 호출 때 바로 재시도하는 것을 막기 위해 임시 캐시 유효 시간 연장 (1분 뒤 재시도)
                cls._last_fetched = now - (cls._cache_duration - 60.0)
        return cls._cached_rate
