import time
import yfinance as yf
import pandas as pd

class FXRateCache:
    """
    실시간 원/달러 환율(USDKRW=X)을 위한 메모리 캐싱 헬퍼 클래스.
    10초 주기 폴링 등 잦은 호출로 인한 API 지연 및 Yahoo Finance Rate Limit(HTTP 429)을 방지합니다.
    """
    _cached_rate = 1350.0
    _last_fetched = 0.0
    _cache_duration = 600.0  # 10분 (600초)

    @classmethod
    def get_rate(cls) -> float:
        now = time.time()
        if now - cls._last_fetched > cls._cache_duration:
            try:
                # 10분 이상 지났을 때만 실제 Yahoo Finance에서 환율 조회
                df_fx = yf.download("USDKRW=X", period="1d", progress=False)
                if not df_fx.empty:
                    if isinstance(df_fx.columns, pd.MultiIndex):
                        df_fx.columns = df_fx.columns.get_level_values(0)
                    cls._cached_rate = float(df_fx['Close'].iloc[-1])
                    cls._last_fetched = now
                    print(f"[FXCache] Updated live rate successfully: {cls._cached_rate}")
            except Exception as e:
                print(f"[FXCache] Failed to download live rate, using cached value {cls._cached_rate}: {e}")
                # 실패 시에는 다음 호출 때 바로 재시도하는 것을 막기 위해 임시 캐시 유효 시간 연장 (1분 뒤 재시도)
                cls._last_fetched = now - (cls._cache_duration - 60.0)
        return cls._cached_rate
