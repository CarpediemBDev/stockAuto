import asyncio

import pandas as pd

from app.bot.backtest_engine import BacktestSimulator
from app.scanner import data_provider
from app.scanner.indicators import calculate_vwap


def test_backtest_range_includes_full_end_date():
    index = pd.DatetimeIndex(
        [
            "2025-01-01 09:30:00",
            "2025-01-02 16:00:00",
            "2025-01-03 09:30:00",
        ]
    )
    frame = pd.DataFrame({"Close": [100.0, 101.0, 102.0]}, index=index)

    sliced = BacktestSimulator._slice_requested_range(
        frame,
        start_date="2025-01-01",
        end_date="2025-01-02",
    )

    assert list(sliced.index) == list(index[:2])


def test_fetch_ohlcv_uses_explicit_dates_without_period(monkeypatch):
    captured = {}
    expected = pd.DataFrame(
        {"Close": [100.0]},
        index=pd.DatetimeIndex(["2025-01-02"]),
    )

    def fake_download(ticker, **kwargs):
        captured["ticker"] = ticker
        captured["kwargs"] = kwargs
        return expected

    data_provider._ohlcv_cache.clear()
    monkeypatch.setattr(data_provider.yf, "download", fake_download)

    result = asyncio.run(
        data_provider.fetch_ohlcv(
            "AAPL",
            interval="1h",
            period="5d",
            start="2025-01-01",
            end="2025-02-01",
        )
    )

    assert not result.empty
    assert captured["ticker"] == "AAPL"
    assert captured["kwargs"]["start"] == "2025-01-01"
    assert captured["kwargs"]["end"] == "2025-02-01"
    assert "period" not in captured["kwargs"]


def test_fetch_ohlcv_keeps_period_mode_for_live_calls(monkeypatch):
    captured = {}
    expected = pd.DataFrame(
        {"Close": [100.0]},
        index=pd.DatetimeIndex(["2025-01-02"]),
    )

    def fake_download(ticker, **kwargs):
        captured["ticker"] = ticker
        captured["kwargs"] = kwargs
        return expected

    data_provider._ohlcv_cache.clear()
    monkeypatch.setattr(data_provider.yf, "download", fake_download)

    asyncio.run(data_provider.fetch_ohlcv("AAPL", interval="1d", period="10d"))

    assert captured["kwargs"]["period"] == "10d"
    assert "start" not in captured["kwargs"]
    assert "end" not in captured["kwargs"]


def test_vwap_accepts_date_named_index():
    index = pd.DatetimeIndex(
        [
            "2025-01-02 09:30:00",
            "2025-01-02 10:30:00",
        ],
        name="Date",
    )
    frame = pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.0],
            "Close": [101.0, 102.0],
            "Volume": [1000.0, 2000.0],
        },
        index=index,
    )

    result = calculate_vwap(frame)

    assert len(result) == 2
    assert result.index.equals(index)
