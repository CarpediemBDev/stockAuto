import asyncio

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.trades.router_market as market_router_module


def create_market_app() -> FastAPI:
    app = FastAPI()
    app.include_router(market_router_module.router, prefix="/api/v1/market")
    return app


def test_market_overview_returns_partial_data_when_source_times_out(monkeypatch):
    async def fake_sentiment():
        return "BULLISH"

    async def fake_ticker_summary(ticker_symbol: str):
        if ticker_symbol == "^IXIC":
            return {
                "symbol": ticker_symbol,
                "current": 100.0,
                "change": 1.0,
                "change_pct": 1.0,
            }

        await asyncio.sleep(0.05)
        return {
            "symbol": ticker_symbol,
            "current": 1300.0,
            "change": 0.5,
            "change_pct": 0.04,
        }

    monkeypatch.setattr(market_router_module, "MARKET_OVERVIEW_TASK_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(market_router_module, "check_market_sentiment", fake_sentiment)
    monkeypatch.setattr(market_router_module, "get_ticker_summary", fake_ticker_summary)

    with TestClient(create_market_app()) as client:
        response = client.get("/api/v1/market/overview")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["sentiment"] == "BULLISH"
    assert payload["nasdaq"]["symbol"] == "^IXIC"
    assert payload["exchange_rate"] is None
    assert "timestamp" in payload


@pytest.mark.asyncio
async def test_ticker_summary_requires_previous_close(monkeypatch):
    async def fake_fetch_ohlcv(ticker_symbol: str, interval: str, period: str):
        return pd.DataFrame({"Close": [100.0]})

    monkeypatch.setattr(market_router_module, "fetch_ohlcv", fake_fetch_ohlcv)

    assert await market_router_module.get_ticker_summary("TEST") is None
