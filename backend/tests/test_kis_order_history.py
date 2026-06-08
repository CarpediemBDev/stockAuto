from types import SimpleNamespace

from app.bot import kis_api
from app.bot.kis_api import KISClient


class FakeResponse:
    status_code = 200

    def __init__(self, body, tr_cont=""):
        self._body = body
        self.headers = {"tr_cont": tr_cont}
        self.text = ""

    def json(self):
        return self._body


def make_client():
    client = KISClient(
        SimpleNamespace(
            user_id=1,
            trade_mode="REAL",
            app_key="valid-app-key",
            app_secret="valid-secret",
            account_no="87654321-01",
        ),
        trade_mode="REAL"
    )
    client.get_access_token = lambda: "token"
    return client


def test_list_order_history_uses_official_contract_and_paginates(monkeypatch):
    client = make_client()
    calls = []
    responses = iter([
        FakeResponse(
            {
                "rt_cd": "0",
                "output": [{
                    "ord_dt": "20260605",
                    "ord_tmd": "101500",
                    "odno": "ORDER-1",
                    "sll_buy_dvsn_cd": "02",
                    "pdno": "AAPL",
                    "ovrs_excg_cd": "NASD",
                    "ft_ord_qty": "3",
                    "ft_ord_unpr3": "200.00",
                    "ft_ccld_qty": "1",
                    "ft_ccld_unpr3": "199.50",
                    "nccs_qty": "2",
                }],
                "ctx_area_nk200": "NEXT-NK",
                "ctx_area_fk200": "NEXT-FK",
            },
            tr_cont="M",
        ),
        FakeResponse(
            {
                "rt_cd": "0",
                "output": [{
                    "ord_dt": "20260605",
                    "ord_tmd": "101600",
                    "odno": "ORDER-2",
                    "sll_buy_dvsn_cd": "01",
                    "pdno": "MSFT",
                    "ovrs_excg_cd": "NASD",
                    "ft_ord_qty": "2",
                    "ft_ord_unpr3": "400.00",
                    "ft_ccld_qty": "2",
                    "ft_ccld_unpr3": "401.00",
                    "nccs_qty": "0",
                }],
                "ctx_area_nk200": "",
                "ctx_area_fk200": "",
            }
        ),
    ])

    def fake_get(url, headers, params, timeout):
        calls.append((headers, params))
        return next(responses)

    monkeypatch.setattr(kis_api.requests, "get", fake_get)

    orders = client.list_order_history("20260605", "20260605")

    assert [order["order_no"] for order in orders] == ["ORDER-1", "ORDER-2"]
    assert orders[0]["status"] == "PARTIAL"
    assert orders[0]["side"] == "BUY"
    assert orders[1]["status"] == "FILLED"
    assert orders[1]["side"] == "SELL"
    assert calls[0][0]["tr_id"] == "TTTS3035R"
    assert calls[0][1]["ODNO"] == ""
    assert calls[0][1]["CCLD_NCCS_DVSN"] == "00"
    assert calls[1][0]["tr_cont"] == "N"
    assert calls[1][1]["CTX_AREA_NK200"] == "NEXT-NK"
    assert calls[1][1]["CTX_AREA_FK200"] == "NEXT-FK"
