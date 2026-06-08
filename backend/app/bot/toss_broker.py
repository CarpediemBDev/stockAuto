from app.bot.base_broker import BaseBroker
from app.bot.toss_api import TossClient
import time
import uuid

class TossBroker(BaseBroker):
    def __init__(self, db_settings=None, db_credential=None):
        super().__init__(db_settings, db_credential)
        self.client = TossClient(db_credential, db_settings.trade_mode if db_settings else "SIMULATED")

    def get_account_balance(self, exchange_rate: float | None = None) -> dict:
        balance = self.client.get_account_balance(exchange_rate)
        balance["is_mock"] = not self.client.is_real
        balance["provider"] = "TOSS"
        return balance

    def get_holdings(self, exchange_rate: float | None = None) -> list:
        # 스텁 구현
        return []

    def buy_order(self, ticker: str, quantity: int, price: float, session: str = "REGULAR_MARKET", client_order_id: str | None = None) -> dict:
        res = self.client.buy_overseas_order(ticker, quantity, price, session, client_order_id)
        if res and res.get("rt_cd") == "0":
            return {"success": True, "order_no": "TOSS-BUY-" + str(uuid.uuid4())[:8], "filled_qty": quantity, "filled_price": price, "message": "Success"}
        return {"success": False, "order_no": "", "filled_qty": 0, "filled_price": 0, "message": "Failed"}

    def sell_order(self, ticker: str, quantity: int, price: float, session: str = "REGULAR_MARKET", client_order_id: str | None = None) -> dict:
        res = self.client.sell_overseas_order(ticker, quantity, price, session, client_order_id)
        if res and res.get("rt_cd") == "0":
            return {"success": True, "order_no": "TOSS-SELL-" + str(uuid.uuid4())[:8], "filled_qty": quantity, "filled_price": price, "message": "Success"}
        return {"success": False, "order_no": "", "filled_qty": 0, "filled_price": 0, "message": "Failed"}

    def check_order_status(self, order_no: str, order_date: str | None = None) -> dict:
        return {"status": "UNFILLED", "filled_qty": 0, "ordered_qty": 0, "filled_price": 0.0, "order_no": order_no}

    def list_order_history(self, start_date: str, end_date: str) -> list[dict]:
        return []

    def get_order_metadata(self, ticker: str, session: str) -> dict:
        return {"exchange_code": "NASD", "order_division": "00"}
