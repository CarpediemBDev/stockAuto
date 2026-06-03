from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.scanner.router as scanner_router_module


def create_scanner_app() -> FastAPI:
    app = FastAPI()
    app.include_router(scanner_router_module.router, prefix="/api/v1/scanner")
    return app


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
