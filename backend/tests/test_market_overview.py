import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.trades.market_overview_cache as cache_module
import app.trades.router_market as market_router_module
from app.core.database import Base
from app.core.models import MarketOverviewSnapshot, utc_now_aware


@pytest.fixture
def market_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionFactory()
    cache_module.clear_market_overview_memory_cache()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        cache_module.clear_market_overview_memory_cache()


def create_market_app() -> FastAPI:
    app = FastAPI()
    app.include_router(market_router_module.router, prefix="/api/v1/market")
    return app


def test_market_overview_route_returns_cached_data(monkeypatch):
    expected = {
        "market_condition": "BULLISH",
        "sentiment": "BULLISH",
        "market_condition_sync_status": "fresh",
        "nasdaq": None,
        "exchange_rate": None,
        "timestamp": utc_now_aware().isoformat(),
    }

    monkeypatch.setattr(market_router_module, "get_cached_market_overview", lambda: expected)

    with TestClient(create_market_app()) as client:
        response = client.get("/api/v1/market/overview")

    assert response.status_code == 200
    assert response.json()["data"] == expected


@pytest.mark.asyncio
async def test_refresh_market_overview_snapshot_persists_and_caches(monkeypatch, market_session):
    async def fake_market_condition():
        return "BULLISH"

    async def fake_ticker_summary(ticker_symbol: str):
        return {
            "symbol": ticker_symbol,
            "current": 100.0,
            "change": 1.5,
            "change_pct": 1.52,
        }

    monkeypatch.setattr(cache_module, "check_market_sentiment", fake_market_condition)
    monkeypatch.setattr(cache_module, "get_ticker_summary", fake_ticker_summary)

    data = await cache_module.refresh_market_overview_snapshot(market_session)

    assert data["market_condition"] == "BULLISH"
    assert data["sentiment"] == "BULLISH"
    assert data["market_condition_sync_status"] == "fresh"
    assert data["nasdaq"]["sync_status"] == "fresh"
    assert data["exchange_rate"]["sync_status"] == "fresh"
    assert market_session.query(MarketOverviewSnapshot).count() == 1
    assert cache_module.get_cached_market_overview(market_session) == data


@pytest.mark.asyncio
async def test_refresh_market_overview_snapshot_uses_stale_previous_values(monkeypatch, market_session):
    previous = MarketOverviewSnapshot(
        market_condition="BEARISH",
        market_condition_sync_status="fresh",
        nasdaq_symbol="^IXIC",
        nasdaq_current=123.0,
        nasdaq_change=-2.0,
        nasdaq_change_pct=-1.6,
        nasdaq_sync_status="fresh",
        exchange_rate_symbol="USDKRW=X",
        exchange_rate_current=1300.0,
        exchange_rate_change=3.0,
        exchange_rate_change_pct=0.2,
        exchange_rate_sync_status="fresh",
    )
    market_session.add(previous)
    market_session.commit()
    cache_module.clear_market_overview_memory_cache()

    async def fake_market_condition():
        return None

    async def fake_ticker_summary(ticker_symbol: str):
        return None

    monkeypatch.setattr(cache_module, "check_market_sentiment", fake_market_condition)
    monkeypatch.setattr(cache_module, "get_ticker_summary", fake_ticker_summary)

    data = await cache_module.refresh_market_overview_snapshot(market_session)

    assert data["market_condition"] == "BEARISH"
    assert data["market_condition_sync_status"] == "stale"
    assert data["nasdaq"]["current"] == 123.0
    assert data["nasdaq"]["sync_status"] == "stale"
    assert data["exchange_rate"]["current"] == 1300.0
    assert data["exchange_rate"]["sync_status"] == "stale"
    assert market_session.query(MarketOverviewSnapshot).count() == 2
