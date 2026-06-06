import json
from types import SimpleNamespace

import pytest

from app.bot import kis_api
from app.bot.kis_api import KISClient


class FakeResponse:
    status_code = 200

    def json(self):
        return {"rt_cd": "0", "output": {"ODNO": "TEST-ORDER"}}


def make_kis_client(trade_mode: str = "MOCK") -> KISClient:
    return KISClient(
        SimpleNamespace(
            user_id=1,
            trade_mode=trade_mode,
            kis_app_key="valid-app-key",
            kis_app_secret="valid-secret",
            kis_account_no="87654321-01",
        )
    )


def capture_order_request(
    monkeypatch,
    method_name: str,
    session: str,
    trade_mode: str,
) -> dict:
    client = make_kis_client(trade_mode)
    client.get_access_token = lambda: "test-token"
    client.get_hashkey = lambda body: "test-hash"
    client._get_exchange_code = lambda ticker: "NASD"

    captured = {}

    def fake_post(url, headers, data, timeout):
        captured["body"] = json.loads(data)
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(kis_api.requests, "post", fake_post)

    method = getattr(client, method_name)
    result = method("AAPL", 3, price=123.45, session=session)

    assert result["rt_cd"] == "0"
    return captured


@pytest.mark.parametrize(
    ("method_name", "session", "trade_mode", "expected_order_division", "expected_tr_id"),
    [
        ("buy_overseas_order", "PRE_MARKET", "REAL", "32", "TTTT1002U"),
        ("buy_overseas_order", "REGULAR_MARKET", "REAL", "00", "TTTT1002U"),
        ("buy_overseas_order", "AFTER_HOURS", "REAL", "34", "TTTT1002U"),
        ("sell_overseas_order", "PRE_MARKET", "REAL", "32", "TTTT1006U"),
        ("sell_overseas_order", "REGULAR_MARKET", "REAL", "00", "TTTT1006U"),
        ("sell_overseas_order", "AFTER_HOURS", "REAL", "34", "TTTT1006U"),
        ("buy_overseas_order", "PRE_MARKET", "MOCK", "00", "VTTT1002U"),
        ("sell_overseas_order", "AFTER_HOURS", "MOCK", "00", "VTTT1006U"),
    ],
)
def test_kis_overseas_orders_use_market_session_order_division(
    monkeypatch,
    method_name: str,
    session: str,
    trade_mode: str,
    expected_order_division: str,
    expected_tr_id: str,
):
    captured = capture_order_request(monkeypatch, method_name, session, trade_mode)
    body = captured["body"]

    assert body["PDNO"] == "AAPL"
    assert body["ORD_QTY"] == "3"
    assert body["ORD_DVSN"] == expected_order_division
    assert captured["headers"]["tr_id"] == expected_tr_id
