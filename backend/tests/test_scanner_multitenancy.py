from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.bot.scheduler as scheduler
import app.scanner.scanner as scanner_module
import app.trades.router_account as account_router_module
import app.watchlist.router as watchlist_router_module
from app.auth.router import router as auth_router
from app.bot.fx_cache import FXRateCache
from app.core.database import Base, get_db
from app.scanner.router import router as scanner_router
from app.scanner.swing_prediction_cache import (
    clear_swing_prediction_cache,
    get_swing_cache_key,
    normalize_swing_candidate,
    write_swing_prediction_cache,
)
from app.trades.router_account import router as account_router
from app.watchlist.router import router as watchlist_router


class FakeBroker:
    def get_account_balance(self):
        return {
            "cash_balance": 10_000_000.0,
            "stock_value": 0.0,
            "total_asset": 10_000_000.0,
        }


def unwrap_success(response):
    payload = response.json()
    assert payload["code"] == "SUCCESS"
    return payload["data"]


def create_multitenant_app(session_factory) -> FastAPI:
    app = FastAPI()

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.include_router(auth_router, prefix="/api/v1/auth")
    app.include_router(watchlist_router, prefix="/api/v1/watchlist")
    app.include_router(scanner_router, prefix="/api/v1/scanner")
    app.include_router(account_router, prefix="/api/v1/account")
    return app


def signup(client: TestClient, username: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/signup",
        json={"username": username, "password": "strongpassword123"},
    )
    assert response.status_code == 201
    token = unwrap_success(response)["access_token"]
    return {"Authorization": f"Bearer {token}"}


def tickers_from_latest(response) -> dict[str, dict]:
    signals = unwrap_success(response)["signals"]
    return {signal["ticker"]: signal for signal in signals}


def test_scanner_and_account_radar_isolate_two_users_and_follow_deletion(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    app = create_multitenant_app(session_factory)

    async def fake_fetch_ohlcv(_ticker, interval="1d", period="1d"):
        return SimpleNamespace(empty=False)

    async def fake_market_sentiment():
        return "BULLISH"

    monkeypatch.setattr(watchlist_router_module, "fetch_ohlcv", fake_fetch_ohlcv)
    monkeypatch.setattr(scanner_module, "check_market_sentiment", fake_market_sentiment)
    monkeypatch.setattr(account_router_module, "get_broker_client", lambda _settings: FakeBroker())
    monkeypatch.setattr(FXRateCache, "get_rate", classmethod(lambda _cls: 1_400.0))

    scheduler.latest_scanned_signals = [
        {
            "ticker": "NVDA",
            "name": "NVIDIA",
            "price": 150.0,
            "signal_score": 90,
            "source": ["MARKET"],
            "details": {"rvol": 3.0, "risk": "LOW"},
        }
    ]
    scheduler.latest_watchlist_signals = {
        "AAPL": {
            "ticker": "AAPL",
            "name": "Apple",
            "price": 200.0,
            "signal_score": 75,
            "details": {},
        },
        "MSFT": {
            "ticker": "MSFT",
            "name": "Microsoft",
            "price": 500.0,
            "signal_score": 74,
            "details": {},
        },
    }

    try:
        with TestClient(app) as client:
            user_a_headers = signup(client, "tenant_a")
            user_b_headers = signup(client, "tenant_b")

            assert client.post(
                "/api/v1/watchlist",
                json={"ticker": "AAPL", "ticker_name": "Apple"},
                headers=user_a_headers,
            ).status_code == 200
            assert client.post(
                "/api/v1/watchlist",
                json={"ticker": "MSFT", "ticker_name": "Microsoft"},
                headers=user_b_headers,
            ).status_code == 200

            user_a_latest = tickers_from_latest(
                client.get("/api/v1/scanner/latest", headers=user_a_headers)
            )
            user_b_latest = tickers_from_latest(
                client.get("/api/v1/scanner/latest", headers=user_b_headers)
            )

            assert set(user_a_latest) == {"NVDA", "AAPL"}
            assert user_a_latest["AAPL"]["source"] == ["WATCHLIST"]
            assert "MSFT" not in user_a_latest
            assert set(user_b_latest) == {"NVDA", "MSFT"}
            assert user_b_latest["MSFT"]["source"] == ["WATCHLIST"]
            assert "AAPL" not in user_b_latest

            user_a_balance = unwrap_success(
                client.get("/api/v1/account/balance", headers=user_a_headers)
            )
            user_b_balance = unwrap_success(
                client.get("/api/v1/account/balance", headers=user_b_headers)
            )
            assert user_a_balance["focused_radar_tickers"] == ["AAPL", "NVDA"]
            assert user_b_balance["focused_radar_tickers"] == ["MSFT", "NVDA"]

            delete_response = client.delete(
                "/api/v1/watchlist/AAPL",
                headers=user_a_headers,
            )
            assert delete_response.status_code == 200

            user_a_latest_after_delete = tickers_from_latest(
                client.get("/api/v1/scanner/latest", headers=user_a_headers)
            )
            user_a_balance_after_delete = unwrap_success(
                client.get("/api/v1/account/balance", headers=user_a_headers)
            )
            assert set(user_a_latest_after_delete) == {"NVDA"}
            assert user_a_balance_after_delete["focused_radar_tickers"] == ["NVDA"]
    finally:
        scheduler.latest_scanned_signals = []
        scheduler.latest_watchlist_signals = {}
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_swing_prediction_is_authenticated_global_market_data():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    app = create_multitenant_app(session_factory)
    cache_key = get_swing_cache_key()
    expected_candidates = [normalize_swing_candidate({"ticker": "NVDA", "score": 88.0})]
    clear_swing_prediction_cache()
    write_swing_prediction_cache(
        cache_key,
        expected_candidates,
        "fresh",
        "2026-06-23T00:00:00+00:00",
    )

    try:
        with TestClient(app) as client:
            unauthenticated = client.get("/api/v1/scanner/swing-predict")
            user_a_headers = signup(client, "swing_tenant_a")
            user_b_headers = signup(client, "swing_tenant_b")
            user_a_response = client.get(
                "/api/v1/scanner/swing-predict",
                headers=user_a_headers,
            )
            user_b_response = client.get(
                "/api/v1/scanner/swing-predict",
                headers=user_b_headers,
            )

        assert unauthenticated.status_code == 401
        assert user_a_response.status_code == 200
        assert user_b_response.status_code == 200
        assert unwrap_success(user_a_response) == unwrap_success(user_b_response)
        assert unwrap_success(user_a_response) == {
            "candidates": expected_candidates,
            "scope": "global",
            "sync_status": "fresh",
            "updated_at": "2026-06-23T00:00:00+00:00",
        }
    finally:
        clear_swing_prediction_cache()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
