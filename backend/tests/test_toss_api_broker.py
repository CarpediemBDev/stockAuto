from types import SimpleNamespace
import pytest
from app.bot.toss_api import TossClient
from app.bot.toss_broker import TossBroker
from app.core.exceptions import StockAutoException

class MockDbCredential:
    def __init__(self, user_id, app_key, app_secret, account_no):
        self.user_id = user_id
        # In a real scenario, these would be encrypted strings.
        # But for test mocking where decrypt_credential is not mocked, 
        # wait, TossClient decrypts these inside __init__.
        # So we should mock decrypt_credential.
        self.app_key = app_key
        self.app_secret = app_secret
        self.account_no = account_no

def test_toss_client_initialization_no_credential():
    with pytest.raises(StockAutoException) as excinfo:
        TossClient(db_credential=None, trade_mode="SIMULATED")
    assert excinfo.value.code == "INVALID_TOSS_CREDENTIALS"

def test_toss_client_initialization_invalid_credential(mocker):
    mocker.patch("app.bot.toss_api.decrypt_credential", side_effect=lambda x: x)
    cred = MockDbCredential(1, "YOUR_APP_KEY_HERE", "secret", "account")
    
    with pytest.raises(StockAutoException) as excinfo:
        TossClient(db_credential=cred, trade_mode="REAL")
    assert excinfo.value.code == "INVALID_TOSS_CREDENTIALS"

def test_toss_client_initialization_valid_credential(mocker):
    mocker.patch("app.bot.toss_api.decrypt_credential", side_effect=lambda x: x)
    cred = MockDbCredential(1, "valid_key", "valid_secret", "12345678")
    
    client = TossClient(db_credential=cred, trade_mode="REAL")
    assert client.trade_mode == "REAL"
    assert client.is_real is True
    assert client.app_key == "valid_key"

def test_toss_broker_methods(mocker):
    mocker.patch("app.bot.toss_api.decrypt_credential", side_effect=lambda x: x)
    cred = MockDbCredential(1, "valid_key", "valid_secret", "12345678")
    settings = SimpleNamespace(trade_mode="REAL")
    
    broker = TossBroker(db_settings=settings, db_credential=cred)
    
    # Test balance
    balance = broker.get_account_balance()
    assert balance["provider"] == "TOSS"
    assert "is_mock" in balance
    assert balance["total_asset"] == 0

    # Test buy order
    buy_res = broker.buy_order("AAPL", 1, 150.0)
    assert buy_res["success"] is True
    assert buy_res["order_no"].startswith("TOSS-BUY-")

    # Test sell order
    sell_res = broker.sell_order("AAPL", 1, 150.0)
    assert sell_res["success"] is True
    assert sell_res["order_no"].startswith("TOSS-SELL-")
