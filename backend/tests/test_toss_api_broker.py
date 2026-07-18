from types import SimpleNamespace
import pytest
import requests
from app.brokers.toss_api import TossClient
from app.brokers.toss_broker import TossBroker
from app.core.exceptions import StockAutoException

class MockDbCredential:
    def __init__(self, user_id, app_key, app_secret, account_no):
        self.user_id = user_id
        self.app_key = app_key
        self.app_secret = app_secret
        self.account_no = account_no

@pytest.fixture
def mock_decrypt(mocker):
    return mocker.patch("app.brokers.toss_api.decrypt_credential", side_effect=lambda x: x)

def test_toss_client_initialization_no_credential():
    with pytest.raises(StockAutoException) as excinfo:
        TossClient(db_credential=None, trade_mode="SIMULATED")
    assert excinfo.value.code == "INVALID_TOSS_CREDENTIALS"

def test_toss_client_initialization_invalid_credential(mock_decrypt):
    cred = MockDbCredential(1, "YOUR_APP_KEY_HERE", "secret", "account")
    with pytest.raises(StockAutoException) as excinfo:
        TossClient(db_credential=cred, trade_mode="REAL")
    assert excinfo.value.code == "INVALID_TOSS_CREDENTIALS"

def test_toss_client_token_request_success(mock_decrypt, mocker):
    cred = MockDbCredential(1, "valid_key", "valid_secret", "12345678")
    client = TossClient(db_credential=cred, trade_mode="REAL")

    # Mock requests.post for token endpoint
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "TOSS_JWT_TEST_TOKEN",
        "token_type": "Bearer",
        "expires_in": 86400
    }
    mocker.patch("requests.post", return_value=mock_response)

    token = client.get_access_token()
    assert token == "TOSS_JWT_TEST_TOKEN"
    assert client.token == "TOSS_JWT_TEST_TOKEN"

def test_toss_client_token_request_failed(mock_decrypt, mocker):
    cred = MockDbCredential(1, "valid_key", "valid_secret", "12345678")
    client = TossClient(db_credential=cred, trade_mode="REAL")

    mock_response = mocker.Mock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request"
    mocker.patch("requests.post", return_value=mock_response)

    token = client.get_access_token()
    assert token is None

def test_toss_client_get_accounts(mock_decrypt, mocker):
    cred = MockDbCredential(1, "valid_key", "valid_secret", "12345678")
    client = TossClient(db_credential=cred, trade_mode="REAL")

    # Mock token
    mocker.patch.object(client, "get_access_token", return_value="mock_token")

    # Mock requests.get for accounts list
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "result": [
            {
                "accountSeq": 12345,
                "accountNo": "1000-2000",
                "accountType": "BROKERAGE",
            }
        ]
    }
    mocker.patch("requests.get", return_value=mock_response)

    seq = client.get_account_sequence()
    assert seq == 12345

def test_toss_client_get_account_balance_uses_official_holdings_and_buying_power(mock_decrypt, mocker):
    cred = MockDbCredential(1, "valid_key", "valid_secret", "12345678")
    client = TossClient(db_credential=cred, trade_mode="REAL")
    mocker.patch.object(client, "get_access_token", return_value="mock_token")
    mocker.patch.object(client, "get_account_sequence", return_value=12345)

    holdings_response = mocker.Mock()
    holdings_response.status_code = 200
    holdings_response.json.return_value = {
        "result": {
            "marketValue": {
                "amount": {"krw": "100000", "usd": "200"},
            },
            "profitLoss": {
                "amount": {"krw": "10000", "usd": "20"},
                "rate": "0.10",
            },
            "items": [],
        }
    }
    krw_buying_power = mocker.Mock()
    krw_buying_power.status_code = 200
    krw_buying_power.json.return_value = {
        "result": {"currency": "KRW", "cashBuyingPower": "50000"}
    }
    usd_buying_power = mocker.Mock()
    usd_buying_power.status_code = 200
    usd_buying_power.json.return_value = {
        "result": {"currency": "USD", "cashBuyingPower": "10"}
    }
    get_mock = mocker.patch(
        "requests.get",
        side_effect=[holdings_response, krw_buying_power, usd_buying_power],
    )

    balance = client.get_account_balance(exchange_rate=1300)

    assert get_mock.call_args_list[0].args[0].endswith("/api/v1/holdings")
    assert get_mock.call_args_list[1].kwargs["params"] == {"currency": "KRW"}
    assert get_mock.call_args_list[2].kwargs["params"] == {"currency": "USD"}
    assert balance["stock_balance"] == 360000
    assert balance["cash_balance"] == 63000
    assert balance["total_asset"] == 423000
    assert balance["profit_loss"] == 36000
    assert balance["profit_rate"] == 10.0

def test_toss_broker_get_holdings(mock_decrypt, mocker):
    cred = MockDbCredential(1, "valid_key", "valid_secret", "12345678")
    settings = SimpleNamespace(trade_mode="REAL")
    broker = TossBroker(db_settings=settings, db_credential=cred)

    # Mock token & accountSeq
    mocker.patch.object(broker.client, "get_access_token", return_value="mock_token")
    mocker.patch.object(broker.client, "get_account_sequence", return_value="mock_seq")

    mocker.patch.object(broker.client, "get_assets", return_value=[
        {
            "symbol": "AAPL",
            "name": "애플",
            "quantity": "10",
            "averagePurchasePrice": "180.5",
            "lastPrice": "190.25",
        },
        {
            "symbol": "TSLA",
            "name": "테슬라",
            "quantity": "0",  # 수량이 0인 종목은 걸러져야 함
            "averagePurchasePrice": "200.0",
        }
    ])

    holdings = broker.get_holdings()
    assert len(holdings) == 1
    assert holdings[0]["ticker"] == "AAPL"
    assert holdings[0]["quantity"] == 10
    assert holdings[0]["avg_price"] == 180.5
    assert holdings[0]["current_price"] == 190.25

def test_toss_broker_buy_sell_order(mock_decrypt, mocker):
    cred = MockDbCredential(1, "valid_key", "valid_secret", "12345678")
    settings = SimpleNamespace(trade_mode="REAL")
    broker = TossBroker(db_settings=settings, db_credential=cred)

    # Mock token & accountSeq
    mocker.patch.object(broker.client, "get_access_token", return_value="mock_token")
    mocker.patch.object(broker.client, "get_account_sequence", return_value="mock_seq")

    # Mock requests.post for order
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "code": "SUCCESS",
        "result": {
            "orderId": "toss-ord-123"
        }
    }
    mocker.patch("requests.post", return_value=mock_response)

    buy_res = broker.buy_order("AAPL", 5, 185.0)
    assert buy_res["success"] is True
    assert buy_res["order_no"] == "toss-ord-123"
    assert buy_res["status"] == "PENDING"

    sell_res = broker.sell_order("AAPL", 5, 185.0)
    assert sell_res["success"] is True
    assert sell_res["order_no"] == "toss-ord-123"
    first_order_body = requests.post.call_args_list[0].kwargs["json"]
    assert first_order_body["orderType"] == "LIMIT"
    assert first_order_body["timeInForce"] == "DAY"
    assert first_order_body["price"] == "185.00"

def test_toss_broker_check_order_status(mock_decrypt, mocker):
    cred = MockDbCredential(1, "valid_key", "valid_secret", "12345678")
    settings = SimpleNamespace(trade_mode="REAL")
    broker = TossBroker(db_settings=settings, db_credential=cred)

    # Mock get_order_status
    mocker.patch.object(broker.client, "get_order_status", return_value={
        "orderId": "toss-ord-123",
        "symbol": "AAPL",
        "quantity": "5",
        "execution": {
            "filledQuantity": "5",
            "averageFilledPrice": "186.2",
        },
        "status": "FILLED",
    })

    status_res = broker.check_order_status("toss-ord-123")
    assert status_res["status"] == "FILLED"
    assert status_res["filled_qty"] == 5
    assert status_res["filled_price"] == 186.2
    assert status_res["order_no"] == "toss-ord-123"

def test_toss_broker_list_order_history_reads_official_execution_fields(mock_decrypt, mocker):
    cred = MockDbCredential(1, "valid_key", "valid_secret", "12345678")
    settings = SimpleNamespace(trade_mode="REAL")
    broker = TossBroker(db_settings=settings, db_credential=cred)
    mocker.patch.object(
        broker.client,
        "get_order_history",
        side_effect=[
            [
                {
                    "orderId": "open-1",
                    "symbol": "AAPL",
                    "side": "BUY",
                    "status": "PENDING",
                    "quantity": "3",
                    "price": "180.00",
                    "orderedAt": "2026-07-02T10:11:12+09:00",
                    "execution": {"filledQuantity": "0", "averageFilledPrice": None},
                }
            ],
            [
                {
                    "orderId": "closed-1",
                    "symbol": "MSFT",
                    "side": "SELL",
                    "status": "PARTIAL_FILLED",
                    "quantity": "4",
                    "price": "300.00",
                    "orderedAt": "2026-07-02T10:12:13+09:00",
                    "execution": {"filledQuantity": "2", "averageFilledPrice": "301.50"},
                }
            ],
        ],
    )

    history = broker.list_order_history("2026-07-02", "2026-07-03")

    assert len(history) == 2
    assert history[0]["status"] == "UNFILLED"
    assert history[0]["order_time"] == "101112"
    assert history[1]["status"] == "PARTIAL"
    assert history[1]["filled_qty"] == 2
    assert history[1]["filled_price"] == 301.5
