import pytest
import pandas as pd

import app.scanner.scanner as scanner_module
from app.bot.fx_cache import FXRateCache


def make_ohlcv(index, close_values, volume_values):
    close = pd.Series(close_values, index=index, dtype=float)
    return pd.DataFrame(
        {
            "Open": close * 0.99,
            "High": close * 1.02,
            "Low": close * 0.98,
            "Close": close,
            "Volume": pd.Series(volume_values, index=index, dtype=float),
        },
        index=index,
    )


@pytest.mark.asyncio
async def test_scan_market_expert_maps_realtime_strategy_fields(monkeypatch):
    yesterday = pd.date_range("2026-06-01 09:30", periods=20, freq="15min")
    today = pd.date_range("2026-06-02 09:30", periods=10, freq="15min")
    intraday_index = yesterday.append(today)
    close_15m = list(range(100, 120)) + list(range(125, 135))
    volume_15m = [1000] * 28 + [5000, 5200]
    df_15m = make_ohlcv(intraday_index, close_15m, volume_15m)

    one_minute_index = pd.date_range("2026-06-02 09:30", periods=20, freq="5min")
    df_5m = make_ohlcv(one_minute_index, list(range(120, 140)), [4000] * 20)

    daily_index = pd.date_range("2025-06-02", periods=252, freq="B")
    df_daily = make_ohlcv(daily_index, [100 + (i * 0.15) for i in range(252)], [1000000] * 252)
    df_daily.loc[df_daily.index[-1], "High"] = 141.0

    qqq_index = pd.date_range("2026-05-20 09:30", periods=60, freq="15min")
    df_qqq = make_ohlcv(qqq_index, [100 + (i * 0.1) for i in range(60)], [1000000] * 60)

    async def fake_get_seed_tickers():
        return ["NVDA"], {"NVDA": ["MARKET"]}

    async def fake_check_market_sentiment():
        return "BULLISH"

    async def fake_fetch_index_data(ticker):
        return df_qqq

    async def fake_fetch_bulk_ohlcv(tickers, interval, period, group_by="ticker"):
        if interval == "15m":
            return df_15m
        if interval == "5m":
            return df_5m
        if interval == "1d":
            return df_daily
        raise AssertionError(f"unexpected interval: {interval}")

    async def fake_fetch_ticker_news(ticker):
        return []

    async def fake_check_fundamental_health(ticker):
        return True

    monkeypatch.setattr(scanner_module, "get_seed_tickers", fake_get_seed_tickers)
    monkeypatch.setattr(scanner_module, "check_market_sentiment", fake_check_market_sentiment)
    monkeypatch.setattr(scanner_module, "fetch_index_data", fake_fetch_index_data)
    monkeypatch.setattr(scanner_module, "fetch_bulk_ohlcv", fake_fetch_bulk_ohlcv)
    monkeypatch.setattr(scanner_module, "fetch_ticker_news", fake_fetch_ticker_news)
    monkeypatch.setattr(scanner_module, "check_fundamental_health", fake_check_fundamental_health)
    monkeypatch.setattr(FXRateCache, "get_rate", classmethod(lambda cls: 1350.0))

    results = await scanner_module.scan_market_expert()

    assert len(results) == 1
    result = results[0]
    assert result["ticker"] == "NVDA"
    assert result["signal_score"] == 100.0
    assert result["signal_type"] == "STRONG_BUY"
    assert result["details"]["rvol"] > 1.0
    assert result["details"]["ema_aligned"] is True
    assert result["details"]["gap"] > 0
    assert result["details"]["is_near_52w_high"] is True
