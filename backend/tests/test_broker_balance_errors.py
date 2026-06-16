from types import SimpleNamespace

import pytest

import app.bot.kis_api as kis_api_module
import app.bot.toss_api as toss_api_module
from app.bot.kis_api import KISClient
from app.bot.toss_api import TossClient
from app.core.exceptions import StockAutoException


def test_kis_balance_rejects_success_response_without_asset_data(monkeypatch):
    client = object.__new__(KISClient)
    client.account_no = "12345678-01"
    client.base_url = "https://example.test"
    client.is_real = False
    client.get_access_token = lambda: "token"
    client._get_default_headers = lambda _tr_id: {}

    monkeypatch.setattr(
        kis_api_module.requests,
        "get",
        lambda *args, **kwargs: SimpleNamespace(
            status_code=200,
            json=lambda: {"output2": {}},
            text="",
        ),
    )

    with pytest.raises(StockAutoException) as exc_info:
        client.get_account_balance(exchange_rate=1_350.0)

    assert exc_info.value.code == "KIS_BALANCE_UNAVAILABLE"


def test_toss_balance_rejects_success_response_without_asset_data(monkeypatch):
    client = object.__new__(TossClient)
    client.base_url = "https://example.test"
    client.is_real = False
    client.get_access_token = lambda: "token"
    client.get_account_sequence = lambda: "account"

    monkeypatch.setattr(
        toss_api_module.requests,
        "get",
        lambda *args, **kwargs: SimpleNamespace(
            status_code=200,
            json=lambda: {"result": {"summary": {}}},
            text="",
        ),
    )

    with pytest.raises(StockAutoException) as exc_info:
        client.get_account_balance(exchange_rate=1_350.0)

    assert exc_info.value.code == "TOSS_BALANCE_UNAVAILABLE"
