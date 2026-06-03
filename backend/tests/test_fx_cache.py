from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pandas as pd

import app.bot.fx_cache as fx_cache
from app.bot.fx_cache import FXRateCache


def reset_fx_cache(rate: float = 1350.0, last_fetched: float = 0.0, duration: float = 600.0) -> None:
    FXRateCache._cached_rate = rate
    FXRateCache._last_fetched = last_fetched
    FXRateCache._cache_duration = duration
    FXRateCache._lock = threading.RLock()


def test_get_rate_fetches_once_for_concurrent_cache_miss(monkeypatch):
    reset_fx_cache()
    call_count = 0
    call_count_lock = threading.Lock()
    start_gate = threading.Barrier(10)

    def fake_fetch_ohlcv_sync(ticker: str, period: str):
        nonlocal call_count
        assert ticker == "USDKRW=X"
        assert period == "1d"
        with call_count_lock:
            call_count += 1
        time.sleep(0.02)
        return pd.DataFrame({"Close": [1517.56]})

    monkeypatch.setattr(fx_cache, "fetch_ohlcv_sync", fake_fetch_ohlcv_sync)

    def read_rate() -> float:
        start_gate.wait(timeout=5)
        return FXRateCache.get_rate()

    with ThreadPoolExecutor(max_workers=10) as executor:
        rates = list(executor.map(lambda _: read_rate(), range(10)))

    assert rates == [1517.56] * 10
    assert call_count == 1

    assert FXRateCache.get_rate() == 1517.56
    assert call_count == 1


def test_get_rate_uses_cached_value_inside_ttl(monkeypatch):
    reset_fx_cache(rate=1400.0, last_fetched=time.time(), duration=600.0)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("cached FX rate should not fetch live data inside TTL")

    monkeypatch.setattr(fx_cache, "fetch_ohlcv_sync", fail_if_called)

    assert FXRateCache.get_rate() == 1400.0
