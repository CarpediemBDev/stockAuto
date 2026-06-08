import requests
import json
from datetime import datetime, timedelta
from app.core.credentials import decrypt_credential

class TossClient:
    def __init__(self, db_credential=None, trade_mode: str = "SIMULATED"):
        trade_mode = (trade_mode or "SIMULATED").upper()
        self.trade_mode = trade_mode
        self.is_real = trade_mode == "REAL"

        if not db_credential or trade_mode == "SIMULATED":
            from app.core.exceptions import StockAutoException
            raise StockAutoException(
                code="INVALID_TOSS_CREDENTIALS",
                message="토스증권 연동을 위해서는 유효한 DB 설정 정보가 필요합니다.",
                status_code=400
            )

        self.user_id = db_credential.user_id
        self.app_key = decrypt_credential(db_credential.app_key)
        self.app_secret = decrypt_credential(db_credential.app_secret)
        self.account_no = decrypt_credential(db_credential.account_no)

        placeholder_keys = {
            "YOUR_APP_KEY_HERE", "your_toss_app_key_here",
            None, ""
        }
        if (self.app_key in placeholder_keys or
            self.app_secret in placeholder_keys or
            not self.account_no or
            self.account_no in ["00000000", "your_account_no_here", ""]):
            
            from app.core.exceptions import StockAutoException
            raise StockAutoException(
                code="INVALID_TOSS_CREDENTIALS",
                message="토스증권(TOSS) API 연동 키가 누락되었거나 유효하지 않습니다.",
                status_code=400
            )

        # 토스증권 API 공식 호스트는 추후 공식 문서를 반영하여 업데이트 (스텁)
        self.base_url = "https://api.tossinvest.com/v1" 
        self.token = None
        self.token_expired_at = None

    def get_access_token(self):
        # 스텁 구현
        return "TOSS_STUB_TOKEN"

    def get_account_balance(self, exchange_rate: float | None = None):
        return {"total_asset": 0, "cash_balance": 0, "stock_balance": 0, "profit_rate": 0.0}

    def buy_overseas_order(self, ticker: str, quantity: int, price: float = 0, session: str = "REGULAR_MARKET", client_order_id: str | None = None):
        return {"rt_cd": "0", "msg1": "STUB", "msg_cd": "STUB"}

    def sell_overseas_order(self, ticker: str, quantity: int, price: float = 0, session: str = "REGULAR_MARKET", client_order_id: str | None = None):
        return {"rt_cd": "0", "msg1": "STUB", "msg_cd": "STUB"}
