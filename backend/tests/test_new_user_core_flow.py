from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.bot.scheduler as scheduler
import app.watchlist.router as watchlist_router_module
from app.auth.router import router as auth_router
from app.bot.order_reconciler import (
    begin_order_submission,
    create_order_intent,
    finalize_order_submission,
)
from app.bot.router import router as bot_router
from app.core.database import Base, get_db
from app.core.models import UserSettings
from app.scanner.router import router as scanner_router
from app.watchlist.router import router as watchlist_router


def unwrap_success(response):
    payload = response.json()
    assert payload["code"] == "SUCCESS"
    return payload["data"]


def test_new_user_watchlist_scan_and_multiple_order_resume_flow(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    async def fake_fetch_ohlcv(ticker, interval="1d", period="1d"):
        return SimpleNamespace(empty=False)

    app = FastAPI()
    app.dependency_overrides[get_db] = override_get_db
    app.include_router(auth_router, prefix="/api/v1/auth")
    app.include_router(bot_router, prefix="/api/v1/bot")
    app.include_router(watchlist_router, prefix="/api/v1/watchlist")
    app.include_router(scanner_router, prefix="/api/v1/scanner")

    monkeypatch.setattr(watchlist_router_module, "fetch_ohlcv", fake_fetch_ohlcv)
    scheduler.latest_scanned_signals = [
        {
            "ticker": "NVDA",
            "name": "NVIDIA",
            "price": 150.0,
            "signal_score": 90,
            "source": ["MARKET"],
        }
    ]
    scheduler.latest_watchlist_signals = {
        "AAPL": {
            "ticker": "AAPL",
            "name": "Apple",
            "price": 200.0,
            "signal_score": 75,
        }
    }

    try:
        with TestClient(app) as client:
            signup_response = client.post(
                "/api/v1/auth/signup",
                json={"username": "new_trader", "password": "strongpassword123"},
            )
            token = unwrap_success(signup_response)["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            watchlist_response = client.post(
                "/api/v1/watchlist/",
                json={"ticker": "AAPL", "ticker_name": "Apple"},
                headers=headers,
            )
            assert watchlist_response.status_code == 200

            start_response = client.post("/api/v1/bot/start", headers=headers)
            assert start_response.status_code == 200
            assert unwrap_success(start_response)["is_running"] is True

            latest_response = client.get("/api/v1/scanner/latest", headers=headers)
            assert latest_response.status_code == 200
            latest_signals = unwrap_success(latest_response)["signals"]
            signal_by_ticker = {signal["ticker"]: signal for signal in latest_signals}
            assert set(signal_by_ticker) == {"NVDA", "AAPL"}
            assert signal_by_ticker["AAPL"]["source"] == ["WATCHLIST"]

        db = session_factory()
        try:
            db_settings = db.query(UserSettings).one()
            db_settings.trade_mode = "MOCK"
            db_settings.broker_provider = "KIS"
            db.commit()

            orders = []
            for ticker in ("AAPL", "MSFT"):
                order = create_order_intent(
                    db,
                    db_settings,
                    side="BUY",
                    ticker=ticker,
                    prefixed_ticker=ticker,
                    ticker_name=ticker,
                    requested_qty=1,
                    submitted_price=100.0,
                    exchange_code="NASD",
                    order_division="00",
                )
                begin_order_submission(db, order, db_settings)
                orders.append(order)

            for index, order in enumerate(orders, start=1):
                finalize_order_submission(
                    db,
                    order,
                    db_settings,
                    {
                        "success": True,
                        "order_submitted": True,
                        "fill_confirmed": True,
                        "status": "FILLED",
                        "order_no": f"ORDER-{index}",
                        "filled_qty": 1,
                        "filled_price": 100.0,
                    },
                )

            db.refresh(db_settings)
            assert db_settings.is_running is True
        finally:
            db.close()
    finally:
        scheduler.latest_scanned_signals = []
        scheduler.latest_watchlist_signals = {}
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
