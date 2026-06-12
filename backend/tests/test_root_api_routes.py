import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.trades.router_trades import router as trades_router
from app.translations.router import router as translations_router
from app.watchlist.router import router as watchlist_router


@pytest.mark.parametrize(
    ("prefix", "router"),
    [
        ("/api/v1/trades", trades_router),
        ("/api/v1/translations", translations_router),
        ("/api/v1/watchlist", watchlist_router),
    ],
)
def test_authenticated_root_api_routes_do_not_redirect(prefix, router):
    app = FastAPI()
    app.include_router(router, prefix=prefix)

    with TestClient(app) as client:
        response = client.get(
            prefix,
            headers={"Authorization": "Bearer invalid-token"},
            follow_redirects=False,
        )

    assert response.status_code == 401
    assert "location" not in response.headers
