import asyncio
import threading

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
            "source": ["MARKET"],
            "details": {},
        }
    ]

    async def fake_scan_overseas_market():
        return signals

    async def fake_analyze_single_ticker(ticker, bypass_fundamental=False):
        assert ticker == "AAPL"
        assert bypass_fundamental is True
        return {
            "ticker": "AAPL",
            "name": "Apple",
            "price": 200.0,
            "signal_score": 77,
            "source": ["WATCHLIST"],
            "details": {},
        }

    scanner_router_module.scheduler_mod.latest_scanned_signals = []
    scanner_router_module.scheduler_mod.latest_watchlist_signals = {}
    app, db, engine = create_authenticated_scanner_app()
    scan_session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
    monkeypatch.setattr(scanner_router_module.scheduler_mod, "scan_overseas_market", fake_scan_overseas_market)
    monkeypatch.setattr(scanner_router_module.scheduler_mod, "analyze_single_ticker", fake_analyze_single_ticker)
    monkeypatch.setattr(scanner_router_module.scheduler_mod, "SessionLocal", scan_session_factory)
    monkeypatch.setattr(scanner_router_module.scheduler_mod, "get_market_session", lambda: "CLOSED")

    try:
        with TestClient(app) as client:
            scan_response = client.post("/api/v1/scanner/overseas")
            latest_response = client.get("/api/v1/scanner/latest")

        assert scan_response.status_code == 200
        assert scan_response.json()["message"] == "해외 마켓 스캔이 백그라운드에서 시작되었습니다."
        assert latest_response.status_code == 200
        assert latest_response.json()["data"] == {
            "is_scanning": False,
            "signals": [
                signals[0],
                {
                    "ticker": "AAPL",
                    "name": "Apple",
                    "price": 200.0,
                    "signal_score": 77,
                    "source": ["WATCHLIST"],
                    "details": {},
                },
            ],
        }
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_latest_signals_requires_authentication():
    app = create_scanner_app()

    def override_get_db():
        yield None

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        response = client.get("/api/v1/scanner/latest")

    assert response.status_code == 401


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
    refresh_done = threading.Event()

    async def fake_refresh_swing_prediction_cache(cache_key, db_arg=None, refresh_reserved=False):
        assert "GLOBAL_SWING_POOL" in cache_key
        snapshot = swing_cache_module.write_swing_prediction_snapshot(db, cache_key, ["AAPL"], expected, swing_cache_module.SWING_SYNC_FRESH)
        response = swing_cache_module.snapshot_to_swing_response(snapshot)
        swing_cache_module.write_swing_prediction_cache(cache_key, response["candidates"], response["sync_status"], response["updated_at"])
        swing_cache_module.release_swing_prediction_refresh(cache_key)
        refresh_done.set()
        return response

    swing_cache_module.clear_swing_prediction_cache()
    app, db, engine = create_authenticated_scanner_app()
    monkeypatch.setattr(scanner_router_module, "refresh_swing_prediction_cache", fake_refresh_swing_prediction_cache)
    try:
        with TestClient(app) as client:
            refresh_response = client.post("/api/v1/scanner/swing-predict/refresh")
            assert refresh_done.wait(timeout=2.0)
            cached_response = client.get("/api/v1/scanner/swing-predict")

        assert refresh_response.status_code == 200
        refresh_payload = refresh_response.json()["data"]
        assert refresh_payload["candidates"] == []
        assert refresh_payload["sync_status"] == "refreshing"
        assert refresh_payload["updated_at"] is None
        assert cached_response.status_code == 200
        cached_payload = cached_response.json()["data"]
        assert cached_payload["candidates"] == expected
        assert cached_payload["sync_status"] == "fresh"
        assert cached_payload["updated_at"] is not None
        assert db.query(SwingPredictionSnapshot).count() == 1
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        swing_cache_module.clear_swing_prediction_cache()


def test_swing_prediction_refreshing_status_survives_next_poll(monkeypatch):
    expected = [{"ticker": "AAPL", "score": 77.0}]

    async def keep_refresh_reserved(cache_key, db_arg=None, refresh_reserved=False):
        return None

    swing_cache_module.clear_swing_prediction_cache()
    app, db, engine = create_authenticated_scanner_app()
    monkeypatch.setattr(scanner_router_module, "refresh_swing_prediction_cache", keep_refresh_reserved)
    try:
        cache_key = swing_cache_module.get_swing_cache_key()
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
            refresh_response = client.post("/api/v1/scanner/swing-predict/refresh")
            polling_response = client.get("/api/v1/scanner/swing-predict")

        assert refresh_response.status_code == 200
        assert refresh_response.json()["data"]["sync_status"] == "refreshing"
        assert polling_response.status_code == 200
        polling_payload = polling_response.json()["data"]
        assert polling_payload["candidates"] == expected
        assert polling_payload["sync_status"] == "refreshing"
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
        cache_key = swing_cache_module.get_swing_cache_key()
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


def test_swing_prediction_refresh_failure_persists_failed_status(monkeypatch):
    async def fail_scan_next_day_candidates(tickers):
        raise RuntimeError("upstream failed")

    monkeypatch.setattr(swing_cache_module, "scan_next_day_candidates", fail_scan_next_day_candidates)
    swing_cache_module.clear_swing_prediction_cache()
    app, db, engine = create_authenticated_scanner_app()
    try:
        cache_key = swing_cache_module.get_swing_cache_key()
        response = asyncio.run(swing_cache_module.refresh_swing_prediction_cache(cache_key, db))
        cached = swing_cache_module.read_swing_prediction_cache(cache_key, db)

        assert response["sync_status"] == "failed"
        assert cached == {
            "candidates": [],
            "sync_status": "failed",
            "updated_at": None,
        }
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        swing_cache_module.clear_swing_prediction_cache()


def test_swing_prediction_refresh_failure_persists_stale_status(monkeypatch):
    expected = [{"ticker": "AAPL", "score": 77.0}]

    async def fail_scan_next_day_candidates(tickers):
        raise RuntimeError("upstream failed")

    monkeypatch.setattr(swing_cache_module, "scan_next_day_candidates", fail_scan_next_day_candidates)
    swing_cache_module.clear_swing_prediction_cache()
    app, db, engine = create_authenticated_scanner_app()
    try:
        cache_key = swing_cache_module.get_swing_cache_key()
        db.add(
            SwingPredictionSnapshot(
                cache_key=swing_cache_module.serialize_swing_cache_key(cache_key),
                ticker_universe='["AAPL"]',
                candidates_json='[{"ticker": "AAPL", "score": 77.0}]',
                sync_status="fresh",
            )
        )
        db.commit()

        response = asyncio.run(swing_cache_module.refresh_swing_prediction_cache(cache_key, db))
        cached = swing_cache_module.read_swing_prediction_cache(cache_key, db)

        assert response["candidates"] == expected
        assert response["sync_status"] == "stale"
        assert cached["candidates"] == expected
        assert cached["sync_status"] == "stale"
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        swing_cache_module.clear_swing_prediction_cache()


def test_swing_prediction_refresh_uses_discovery_seed_tickers(monkeypatch):
    expected = [{"ticker": "AAPL", "score": 81.0}]
    scanned_tickers = []

    async def fake_get_seed_tickers():
        return ["AAPL", "NVDA"], {"AAPL": ["YAHOO_ACTIVE"], "NVDA": ["NAVER_US_RANKING"]}

    async def fake_scan_next_day_candidates(tickers):
        scanned_tickers.extend(tickers)
        return expected

    monkeypatch.setattr("app.scanner.discovery.get_seed_tickers", fake_get_seed_tickers)
    monkeypatch.setattr(swing_cache_module, "scan_next_day_candidates", fake_scan_next_day_candidates)
    swing_cache_module.clear_swing_prediction_cache()
    app, db, engine = create_authenticated_scanner_app()
    try:
        cache_key = swing_cache_module.get_swing_cache_key()
        response = asyncio.run(swing_cache_module.refresh_swing_prediction_cache(cache_key, db))
        cached = swing_cache_module.read_swing_prediction_cache(cache_key, db)

        assert scanned_tickers == ["AAPL", "NVDA"]
        assert response["candidates"] == expected
        assert response["sync_status"] == "fresh"
        assert cached["candidates"] == expected
        assert cached["sync_status"] == "fresh"
        assert db.query(SwingPredictionSnapshot).count() == 1
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        swing_cache_module.clear_swing_prediction_cache()


def test_swing_prediction_refresh_failure_returns_stale_snapshot(monkeypatch):
    expected = [{"ticker": "AAPL", "score": 77.0}]
    refresh_done = threading.Event()

    async def fail_refresh_swing_prediction_cache(cache_key, db_arg=None, refresh_reserved=False):
        cached = swing_cache_module.read_swing_prediction_cache(cache_key, db)
        cached["sync_status"] = swing_cache_module.SWING_SYNC_STALE
        swing_cache_module.write_swing_prediction_cache(
            cache_key,
            cached["candidates"],
            cached["sync_status"],
            cached["updated_at"],
        )
        swing_cache_module.release_swing_prediction_refresh(cache_key)
        refresh_done.set()
        return cached

    swing_cache_module.clear_swing_prediction_cache()
    app, db, engine = create_authenticated_scanner_app()
    monkeypatch.setattr(scanner_router_module, "refresh_swing_prediction_cache", fail_refresh_swing_prediction_cache)
    try:
        cache_key = swing_cache_module.get_swing_cache_key()
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
            response = client.post("/api/v1/scanner/swing-predict/refresh")
            assert refresh_done.wait(timeout=2.0)
            cached_response = client.get("/api/v1/scanner/swing-predict")

        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["candidates"] == expected
        assert payload["sync_status"] == "refreshing"
        assert cached_response.status_code == 200
        assert cached_response.json()["data"]["sync_status"] == "stale"
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        swing_cache_module.clear_swing_prediction_cache()
