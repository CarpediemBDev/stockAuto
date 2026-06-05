import json
from types import SimpleNamespace

import pytest

from app.bot import kis_api
from app.bot.kis_api import KISClient


class FakeResponse:
    status_code = 200

    def json(self):
        return {"rt_cd": "0", "output": {"ODNO": "TEST-ORDER"}}


def make_kis_client() -> KISClient:
    return KISClient(
        SimpleNamespace(
            user_id=1,
            trade_mode="MOCK",
            kis_app_key="valid-app-key",
            kis_app_secret="valid-secret",
            kis_account_no="87654321-01",
        )
    )


def capture_order_body(monkeypatch, method_name: str, session: str) -> dict:
    client = make_kis_client()
    client.get_access_token = lambda: "test-token"
    client.get_hashkey = lambda body: "test-hash"
    client._get_exchange_code = lambda ticker: "NASD"

    captured = {}

    def fake_post(url, headers, data, timeout):
        captured["body"] = json.loads(data)
        return FakeResponse()

    monkeypatch.setattr(kis_api.requests, "post", fake_post)

    method = getattr(client, method_name)
    result = method("AAPL", 3, price=123.45, session=session)

    assert result["rt_cd"] == "0"
    return captured["body"]


@pytest.mark.parametrize(
    ("method_name", "session", "expected_order_division"),
    [
        ("buy_overseas_order", "PRE_MARKET", "32"),
        ("buy_overseas_order", "REGULAR_MARKET", "00"),
        ("buy_overseas_order", "AFTER_HOURS", "34"),
        ("sell_overseas_order", "PRE_MARKET", "32"),
        ("sell_overseas_order", "REGULAR_MARKET", "00"),
        ("sell_overseas_order", "AFTER_HOURS", "34"),
    ],
)
def test_kis_overseas_orders_use_market_session_order_division(
    monkeypatch,
    method_name: str,
    session: str,
    expected_order_division: str,
):
    body = capture_order_body(monkeypatch, method_name, session)

    assert body["PDNO"] == "AAPL"
    assert body["ORD_QTY"] == "3"
    assert body["ORD_DVSN"] == expected_order_division
