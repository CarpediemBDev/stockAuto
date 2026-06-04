from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.scanner.router as scanner_router_module
import app.scanner.swing_prediction_cache as swing_cache_module
from app.core.database import Base, get_db
from app.core.dependencies import get_current_user
from app.core.models import SwingPredictionSnapshot, User, WatchList


def create_scanner_app() -> FastAPI:
    app = FastAPI()
    app.include_router(scanner_router_module.router, prefix="/api/v1/scanner")
    return app


def create_authenticated_scanner_app():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionFactory()
    user = User(username="tester", hashed_password="hash")
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(WatchList(user_id=user.id, ticker="AAPL", ticker_name="Apple"))
    db.commit()

    app = create_scanner_app()

    def override_get_db():
        try:
            yield db
        finally:
            pass

    def override_get_current_user():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    return app, db, engine


def test_manual_overseas_scan_updates_latest_signal_cache(monkeypatch):
    signals = [
        {
            "ticker": "NVDA",
            "name": "NVIDIA",
            "price": 100.0,
            "signal_score": 88,
            "signal_type": "STRONG_BUY",
            "details": {},
        }
    ]

    async def fake_scan_overseas_market():
        return signals

    monkeypatch.setattr(scanner_router_module, "scan_overseas_market", fake_scan_overseas_market)
    scanner_router_module.scheduler_mod.latest_scanned_signals = []

    with TestClient(create_scanner_app()) as client:
        scan_response = client.get("/api/v1/scanner/overseas")
        latest_response = client.get("/api/v1/scanner/latest")

    assert scan_response.status_code == 200
    assert scan_response.json()["data"] == signals
    assert latest_response.status_code == 200
    assert latest_response.json()["data"] == signals


def test_swing_prediction_cache_read_does_not_run_heavy_scan(monkeypatch):
    async def fail_scan_next_day_candidates(tickers):
        raise AssertionError("cached read must not run swing scan")

    monkeypatch.setattr(swing_cache_module, "scan_next_day_candidates", fail_scan_next_day_candidates)
    swing_cache_module.clear_swing_prediction_cache()
    app, db, engine = create_authenticated_scanner_app()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/scanner/swing-predict")

        assert response.status_code == 200
        assert response.json()["data"] == {
            "candidates": [],
            "sync_status": "empty",
            "updated_at": None,
        }
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        swing_cache_module.clear_swing_prediction_cache()


def test_swing_prediction_refresh_updates_cached_response(monkeypatch):
    expected = [{"ticker": "AAPL", "score": 77.0}]

    async def fake_scan_next_day_candidates(tickers):
        assert "AAPL" in tickers
        return expected

    monkeypatch.setattr(swing_cache_module, "scan_next_day_candidates", fake_scan_next_day_candidates)
    swing_cache_module.clear_swing_prediction_cache()
    app, db, engine = create_authenticated_scanner_app()
    try:
        with TestClient(app) as client:
            refresh_response = client.get("/api/v1/scanner/swing-predict/refresh")
            cached_response = client.get("/api/v1/scanner/swing-predict")

        assert refresh_response.status_code == 200
        refresh_payload = refresh_response.json()["data"]
        assert refresh_payload["candidates"] == expected
        assert refresh_payload["sync_status"] == "fresh"
        assert refresh_payload["updated_at"] is not None
        assert cached_response.status_code == 200
        assert cached_response.json()["data"] == refresh_payload
        assert db.query(SwingPredictionSnapshot).count() == 1
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        swing_cache_module.clear_swing_prediction_cache()


def test_swing_prediction_read_falls_back_to_persisted_snapshot():
    expected = [{"ticker": "AAPL", "score": 77.0}]

    swing_cache_module.clear_swing_prediction_cache()
    app, db, engine = create_authenticated_scanner_app()
    try:
        cache_key = swing_cache_module.get_swing_cache_key(["AAPL"])
        db.add(
            SwingPredictionSnapshot(
                cache_key=swing_cache_module.serialize_swing_cache_key(cache_key),
                ticker_universe='["AAPL"]',
                candidates_json='[{"ticker": "AAPL", "score": 77.0}]',
                sync_status="fresh",
            )
        )
        db.commit()

        with TestClient(app) as client:
            response = client.get("/api/v1/scanner/swing-predict")

        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["candidates"] == expected
        assert payload["sync_status"] == "stale"
        assert payload["updated_at"] is not None
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        swing_cache_module.clear_swing_prediction_cache()


def test_swing_prediction_refresh_failure_returns_stale_snapshot(monkeypatch):
    expected = [{"ticker": "AAPL", "score": 77.0}]

    async def fail_scan_next_day_candidates(tickers):
        raise RuntimeError("upstream failed")

    monkeypatch.setattr(swing_cache_module, "scan_next_day_candidates", fail_scan_next_day_candidates)
    swing_cache_module.clear_swing_prediction_cache()
    app, db, engine = create_authenticated_scanner_app()
    try:
        cache_key = swing_cache_module.get_swing_cache_key(["AAPL"])
        db.add(
            SwingPredictionSnapshot(
                cache_key=swing_cache_module.serialize_swing_cache_key(cache_key),
                ticker_universe='["AAPL"]',
                candidates_json='[{"ticker": "AAPL", "score": 77.0}]',
                sync_status="fresh",
            )
        )
        db.commit()

        with TestClient(app) as client:
            response = client.get("/api/v1/scanner/swing-predict/refresh")

        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["candidates"] == expected
        assert payload["sync_status"] == "stale"
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        swing_cache_module.clear_swing_prediction_cache()
