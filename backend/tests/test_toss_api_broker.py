from types import SimpleNamespace
import pytest
import requests
from app.bot.toss_api import TossClient
from app.bot.toss_broker import TossBroker
from app.core.exceptions import StockAutoException

class MockDbCredential:
    def __init__(self, user_id, app_key, app_secret, account_no):
        self.user_id = user_id
        self.app_key = app_key
        self.app_secret = app_secret
        self.account_no = account_no

@pytest.fixture
def mock_decrypt(mocker):
    return mocker.patch("app.bot.toss_api.decrypt_credential", side_effect=lambda x: x)

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
                "accountSeq": "seq_12345",
                "accountNo": "1000-2000",
                "status": "ACTIVE"
            }
        ]
    }
    mocker.patch("requests.get", return_value=mock_response)

    seq = client.get_account_sequence()
    assert seq == "seq_12345"

def test_toss_broker_get_holdings(mock_decrypt, mocker):
    cred = MockDbCredential(1, "valid_key", "valid_secret", "12345678")
    settings = SimpleNamespace(trade_mode="REAL")
    broker = TossBroker(db_settings=settings, db_credential=cred)

    # Mock token & accountSeq
    mocker.patch.object(broker.client, "get_access_token", return_value="mock_token")
    mocker.patch.object(broker.client, "get_account_sequence", return_value="mock_seq")

    # Mock get_assets to return dummy list
    mocker.patch.object(broker.client, "get_assets", return_value=[
        {
            "symbol": "AAPL",
            "name": "애플",
            "quantity": "10",
            "purchasePrice": "180.5"
        },
        {
            "symbol": "TSLA",
            "name": "테슬라",
            "quantity": "0",  # 수량이 0인 종목은 걸러져야 함
            "purchasePrice": "200.0"
        }
    ])

    holdings = broker.get_holdings()
    assert len(holdings) == 1
    assert holdings[0]["ticker"] == "AAPL"
    assert holdings[0]["quantity"] == 10
    assert holdings[0]["avg_price"] == 180.5

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

def test_toss_broker_check_order_status(mock_decrypt, mocker):
    cred = MockDbCredential(1, "valid_key", "valid_secret", "12345678")
    settings = SimpleNamespace(trade_mode="REAL")
    broker = TossBroker(db_settings=settings, db_credential=cred)

    # Mock get_order_status
    mocker.patch.object(broker.client, "get_order_status", return_value={
        "orderId": "toss-ord-123",
        "symbol": "AAPL",
        "quantity": "5",
        "filledQuantity": "5",
        "filledPrice": "186.2",
        "status": "FILLED"
    })

    status_res = broker.check_order_status("toss-ord-123")
    assert status_res["status"] == "FILLED"
    assert status_res["filled_qty"] == 5
    assert status_res["filled_price"] == 186.2
    assert status_res["order_no"] == "toss-ord-123"
