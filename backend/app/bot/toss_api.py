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

        # 토스증권 API 공식 서버 호스트 설정
        self.base_url = "https://openapi.tossinvest.com" 
        self.token = None
        self.token_expired_at = None
        self.account_seq = None

    def get_access_token(self) -> str | None:
        """
        OAuth 2.0 Client Credentials Grant 방식을 이용해 실제 토스증권 액세스 토큰을 발급받습니다.
        Form URL-Encoded 방식으로 통신합니다.
        """
        if not self.app_key or self.app_key in ["YOUR_APP_KEY_HERE", "your_toss_app_key_here", ""]:
            return None

        # 캐싱된 토큰 유효 시 즉시 반환
        if self.token and self.token_expired_at and datetime.now() < self.token_expired_at:
            return self.token

        url = f"{self.base_url}/oauth2/token"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        body = {
            "grant_type": "client_credentials",
            "client_id": self.app_key,
            "client_secret": self.app_secret
        }

        try:
            res = requests.post(url, headers=headers, data=body, timeout=5)
            if res.status_code == 200:
                data = res.json()
                self.token = data.get("access_token")
                # 만료 시간(초)을 기반으로 만료 예정 시각 설정 (보통 86400초, 안전하게 1시간 전에 만료되도록 차감)
                expires_in = data.get("expires_in", 86400)
                self.token_expired_at = datetime.now() + timedelta(seconds=max(0, expires_in - 3600))
                return self.token
            else:
                print(f"[Toss API] Token request failed with status {res.status_code}: {res.text}")
                return None
        except Exception as e:
            print(f"[Toss API] Exception during token request: {e}")
            return None

    def get_account_sequence(self) -> str | None:
        """
        주문/조회 시 필수 헤더로 사용되는 사용자의 계좌 시퀀스(accountSeq)를 가져옵니다.
        """
        if self.account_seq:
            return self.account_seq

        token = self.get_access_token()
        if not token:
            return None

        url = f"{self.base_url}/api/v1/accounts"
        headers = {
            "Authorization": f"Bearer {token}"
        }

        try:
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200:
                data = res.json()
                # result는 활성 계좌의 배열 리스트로 구성됨
                accounts = data.get("result", [])
                # 유효한 계좌 시퀀스 추출
                active_accounts = [a for a in accounts if a.get("status") == "ACTIVE" or not a.get("status")]
                if active_accounts:
                    self.account_seq = active_accounts[0].get("accountSeq")
                    return self.account_seq
                elif accounts:
                    self.account_seq = accounts[0].get("accountSeq")
                    return self.account_seq
                return None
            else:
                print(f"[Toss API] Accounts request failed with status {res.status_code}: {res.text}")
                return None
        except Exception as e:
            print(f"[Toss API] Exception during accounts request: {e}")
            return None

    def get_account_balance(self, exchange_rate: float | None = None) -> dict:
        """
        토스증권 자산 API를 통해 전체 자산 요약을 획득하고 KIS 반환 형식과 규격을 맞춥니다.
        """
        token = self.get_access_token()
        account_seq = self.get_account_sequence()
        if not token or not account_seq:
            from app.core.exceptions import StockAutoException
            raise StockAutoException(
                code="INVALID_TOSS_CREDENTIALS",
                message="토스증권 API 토큰 또는 계좌 시퀀스를 발급받지 못했습니다.",
                status_code=400
            )

        from app.bot.fx_cache import FXRateCache
        if exchange_rate is None:
            exchange_rate = FXRateCache.get_rate()

        url = f"{self.base_url}/api/v1/assets"
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Tossinvest-Account": account_seq
        }

        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                result = data.get("result", {})
                summary = result.get("summary", {})
                
                # 금액 파싱 (문자열로 응답되므로 형변환 시 예외 가드 장착)
                def parse_amount(val, default=0.0):
                    try:
                        return float(val or default)
                    except (ValueError, TypeError):
                        return default

                total_asset = int(parse_amount(summary.get("totalAssetAmount")))
                cash_balance = int(parse_amount(summary.get("cashBalance")))
                evaluate_amount = int(parse_amount(summary.get("totalEvaluateAmount")))
                profit_rate = parse_amount(summary.get("totalProfitLossRate"))
                profit_loss = int(parse_amount(summary.get("totalProfitLossAmount")))

                return {
                    "total_asset": total_asset,
                    "cash_balance": cash_balance,
                    "stock_balance": evaluate_amount,
                    "profit_rate": profit_rate,
                    "profit_loss": profit_loss,
                    "fx_rate": exchange_rate,
                    "is_mock": not self.is_real,
                    "provider": "TOSS"
                }
            else:
                print(f"[Toss API] Assets query failed with status {res.status_code}: {res.text}")
                return {"total_asset": 0, "cash_balance": 0, "stock_balance": 0, "profit_rate": 0.0}
        except Exception as e:
            print(f"[Toss API] Exception during assets query: {e}")
            return {"total_asset": 0, "cash_balance": 0, "stock_balance": 0, "profit_rate": 0.0}

    def buy_overseas_order(self, ticker: str, quantity: int, price: float = 0, session: str = "REGULAR_MARKET", client_order_id: str | None = None) -> dict:
        """
        토스증권 해외주식 매수 주문 (지정가 / 시장가)
        """
        return self._place_order("BUY", ticker, quantity, price, session, client_order_id)

    def sell_overseas_order(self, ticker: str, quantity: int, price: float = 0, session: str = "REGULAR_MARKET", client_order_id: str | None = None) -> dict:
        """
        토스증권 해외주식 매도 주문 (지정가 / 시장가)
        """
        return self._place_order("SELL", ticker, quantity, price, session, client_order_id)

    def _place_order(self, side: str, ticker: str, quantity: int, price: float = 0, session: str = "REGULAR_MARKET", client_order_id: str | None = None) -> dict:
        token = self.get_access_token()
        account_seq = self.get_account_sequence()
        if not token or not account_seq:
            return {"rt_cd": "9", "msg1": "No valid token or account sequence", "msg_cd": "AUTH_ERROR"}

        url = f"{self.base_url}/api/v1/orders"
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Tossinvest-Account": account_seq,
            "Content-Type": "application/json"
        }

        # 가격이 0 이하이거나 시장가 성격인 경우 MARKET, 지정가는 LIMIT
        order_type = "MARKET" if price <= 0 else "LIMIT"
        
        body = {
            "symbol": ticker,
            "side": side.upper(),
            "orderType": order_type,
            "quantity": str(quantity)
        }
        if order_type == "LIMIT":
            body["price"] = f"{price:.2f}"

        try:
            res = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
            data = res.json()
            # 표준 API envelope: {"code": "SUCCESS", "message": "...", "result": {"orderId": "..."}}
            # KISBroker는 rt_cd 가 "0"일 때 성공 처리하므로 토스 응답 코드를 KIS 호환 형태로 매핑해 줍니다.
            if res.status_code in [200, 201]:
                result = data.get("result", {})
                order_id = result.get("orderId")
                if order_id:
                    return {
                        "rt_cd": "0",
                        "msg1": "SUCCESS",
                        "msg_cd": "SUCCESS",
                        "orderId": order_id
                    }
            
            # 실패 시 에러 처리
            error_data = data.get("error", {})
            err_msg = error_data.get("message") or data.get("message") or f"HTTP {res.status_code}"
            err_code = error_data.get("code") or "ORDER_REJECTED"
            print(f"[Toss API] Order rejected: {err_msg} ({err_code})")
            return {
                "rt_cd": "9",
                "msg1": err_msg,
                "msg_cd": err_code
            }
        except Exception as e:
            print(f"[Toss API] Exception during order placement: {e}")
            return {
                "rt_cd": "9",
                "msg1": f"Exception: {e}",
                "msg_cd": "SYSTEM_EXCEPTION"
            }

    def get_order_status(self, order_id: str) -> dict | None:
        """
        토스증권 개별 주문 상세 조회 API
        """
        token = self.get_access_token()
        account_seq = self.get_account_sequence()
        if not token or not account_seq:
            return None

        url = f"{self.base_url}/api/v1/orders/{order_id}"
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Tossinvest-Account": account_seq
        }

        try:
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200:
                return res.json().get("result")
            else:
                print(f"[Toss API] Order status query failed for {order_id} (Status {res.status_code}): {res.text}")
                return None
        except Exception as e:
            print(f"[Toss API] Exception during order status query: {e}")
            return None

    def get_order_history(self, status: str = "OPEN") -> list | None:
        """
        토스증권 주문 목록(이력) 조회 API
        """
        token = self.get_access_token()
        account_seq = self.get_account_sequence()
        if not token or not account_seq:
            return None

        url = f"{self.base_url}/api/v1/orders"
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Tossinvest-Account": account_seq
        }
        params = {}
        if status:
            params["status"] = status

        try:
            res = requests.get(url, headers=headers, params=params, timeout=5)
            if res.status_code == 200:
                return res.json().get("result", [])
            else:
                print(f"[Toss API] Order history query failed (Status {res.status_code}): {res.text}")
                return None
        except Exception as e:
            print(f"[Toss API] Exception during order history query: {e}")
            return None

    def get_assets(self) -> list:
        """
        토스증권 상세 보유 자산 리스트 조회 API
        """
        token = self.get_access_token()
        account_seq = self.get_account_sequence()
        if not token or not account_seq:
            return []

        url = f"{self.base_url}/api/v1/assets"
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Tossinvest-Account": account_seq
        }

        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                return data.get("result", {}).get("assets", [])
            else:
                print(f"[Toss API] Assets list query failed (Status {res.status_code}): {res.text}")
                return []
        except Exception as e:
            print(f"[Toss API] Exception during assets list query: {e}")
            return []


