from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import requests
from datetime import datetime, timedelta
from app.core.credentials import decrypt_credential
from app.core.exceptions import StockAutoException


ZERO_DECIMAL = Decimal("0")

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

    @staticmethod
    def _parse_decimal(value, default: Decimal = ZERO_DECIMAL) -> Decimal:
        try:
            if value is None or value == "":
                return default
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return default

    @staticmethod
    def _to_int_amount(value: Decimal) -> int:
        return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def _headers(self, token: str, account_seq: str | int | None = None, json_content: bool = False) -> dict:
        headers = {"Authorization": f"Bearer {token}"}
        if account_seq is not None:
            headers["X-Tossinvest-Account"] = str(account_seq)
        if json_content:
            headers["Content-Type"] = "application/json"
        return headers

    def _currency_bucket_to_krw(self, bucket: dict | None, exchange_rate: float) -> Decimal:
        if not isinstance(bucket, dict):
            return ZERO_DECIMAL
        krw = self._parse_decimal(bucket.get("krw"))
        usd = self._parse_decimal(bucket.get("usd"))
        return krw + (usd * self._parse_decimal(exchange_rate))

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

    def get_account_sequence(self) -> str | int | None:
        """
        주문/조회 시 필수 헤더로 사용되는 사용자의 계좌 시퀀스(accountSeq)를 가져옵니다.
        """
        if self.account_seq:
            return self.account_seq

        token = self.get_access_token()
        if not token:
            return None

        url = f"{self.base_url}/api/v1/accounts"
        headers = self._headers(token)

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
        토스증권 보유 주식/매수 가능 금액 API를 조합해 KIS 반환 형식과 규격을 맞춥니다.
        """
        token = self.get_access_token()
        account_seq = self.get_account_sequence()
        if not token or not account_seq:
            raise StockAutoException(
                code="INVALID_TOSS_CREDENTIALS",
                message="토스증권 API 토큰 또는 계좌 시퀀스를 발급받지 못했습니다.",
                status_code=400
            )

        from app.bot.fx_cache import FXRateCache
        if exchange_rate is None:
            exchange_rate = FXRateCache.get_rate()

        try:
            holdings = self.get_holdings_payload()
            market_value = holdings.get("marketValue", {})
            profit_loss_payload = holdings.get("profitLoss", {})
            if (
                "marketValue" not in holdings
                or "profitLoss" not in holdings
                or not isinstance(market_value, dict)
                or not isinstance(profit_loss_payload, dict)
            ):
                raise StockAutoException(
                    code="TOSS_BALANCE_UNAVAILABLE",
                    message="토스증권 보유 주식 응답에 평가금액 정보가 없습니다.",
                    status_code=502,
                )

            stock_balance_decimal = self._currency_bucket_to_krw(
                market_value.get("amount"),
                exchange_rate,
            )
            profit_loss_decimal = self._currency_bucket_to_krw(
                profit_loss_payload.get("amount"),
                exchange_rate,
            )
            cash_balance_decimal = (
                self.get_buying_power("KRW")
                + (self.get_buying_power("USD") * self._parse_decimal(exchange_rate))
            )
            profit_rate_decimal = self._parse_decimal(profit_loss_payload.get("rate")) * Decimal("100")

            cash_balance = self._to_int_amount(cash_balance_decimal)
            stock_balance = self._to_int_amount(stock_balance_decimal)
            total_asset = cash_balance + stock_balance
            profit_loss = self._to_int_amount(profit_loss_decimal)

            return {
                "total_asset": total_asset,
                "cash_balance": cash_balance,
                "stock_balance": stock_balance,
                "profit_rate": float(profit_rate_decimal),
                "profit_loss": profit_loss,
                "fx_rate": exchange_rate,
                "is_mock": not self.is_real,
                "provider": "TOSS"
            }
        except StockAutoException:
            raise
        except Exception as e:
            raise StockAutoException(
                code="TOSS_BALANCE_UNAVAILABLE",
                message="토스증권 자산을 조회하지 못했습니다.",
                status_code=502,
            ) from e

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
        headers = self._headers(token, account_seq, json_content=True)

        if price <= 0:
            return {
                "rt_cd": "9",
                "msg1": "토스증권 시장가 수량 주문은 아직 StockAuto에서 지원하지 않습니다.",
                "msg_cd": "UNSUPPORTED_TOSS_MARKET_ORDER",
            }
        
        body = {
            "symbol": ticker.upper(),
            "side": side.upper(),
            "orderType": "LIMIT",
            "timeInForce": "DAY",
            "quantity": str(quantity),
            "price": f"{self._parse_decimal(price):.2f}",
        }
        if client_order_id:
            body["clientOrderId"] = client_order_id[:64]

        try:
            res = requests.post(url, headers=headers, json=body, timeout=10)
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
        headers = self._headers(token, account_seq)

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

    def get_order_history(self, status: str = "OPEN", start_date: str | None = None, end_date: str | None = None) -> list | None:
        """
        토스증권 주문 목록(이력) 조회 API
        """
        token = self.get_access_token()
        account_seq = self.get_account_sequence()
        if not token or not account_seq:
            return None

        url = f"{self.base_url}/api/v1/orders"
        headers = self._headers(token, account_seq)
        params = {"status": status or "OPEN"}
        if start_date:
            params["from"] = start_date
        if end_date:
            params["to"] = end_date

        try:
            res = requests.get(url, headers=headers, params=params, timeout=5)
            if res.status_code == 200:
                result = res.json().get("result", {})
                if isinstance(result, dict):
                    return result.get("orders", [])
                if isinstance(result, list):
                    return result
                return []
            else:
                print(f"[Toss API] Order history query failed (Status {res.status_code}): {res.text}")
                return None
        except Exception as e:
            print(f"[Toss API] Exception during order history query: {e}")
            return None

    def get_holdings_payload(self) -> dict:
        """
        토스증권 공식 보유 주식 조회 API의 result 객체를 반환합니다.
        """
        token = self.get_access_token()
        account_seq = self.get_account_sequence()
        if not token or not account_seq:
            raise StockAutoException(
                code="INVALID_TOSS_CREDENTIALS",
                message="토스증권 API 토큰 또는 계좌 시퀀스를 발급받지 못했습니다.",
                status_code=400,
            )

        url = f"{self.base_url}/api/v1/holdings"
        headers = self._headers(token, account_seq)

        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                result = data.get("result", {})
                if isinstance(result, dict):
                    return result
                return {}
            raise StockAutoException(
                code="TOSS_BALANCE_UNAVAILABLE",
                message=f"토스증권 보유 주식 조회에 실패했습니다. HTTP {res.status_code}",
                status_code=502,
            )
        except StockAutoException:
            raise
        except Exception as e:
            raise StockAutoException(
                code="TOSS_BALANCE_UNAVAILABLE",
                message="토스증권 보유 주식을 조회하지 못했습니다.",
                status_code=502,
            ) from e

    def get_buying_power(self, currency: str) -> Decimal:
        token = self.get_access_token()
        account_seq = self.get_account_sequence()
        if not token or not account_seq:
            raise StockAutoException(
                code="INVALID_TOSS_CREDENTIALS",
                message="토스증권 API 토큰 또는 계좌 시퀀스를 발급받지 못했습니다.",
                status_code=400,
            )

        normalized_currency = (currency or "").upper()
        if normalized_currency not in {"KRW", "USD"}:
            raise ValueError(f"Unsupported Toss buying power currency: {currency}")

        url = f"{self.base_url}/api/v1/buying-power"
        headers = self._headers(token, account_seq)
        try:
            res = requests.get(
                url,
                headers=headers,
                params={"currency": normalized_currency},
                timeout=10,
            )
            if res.status_code == 200:
                result = res.json().get("result", {})
                return self._parse_decimal(result.get("cashBuyingPower"))
            raise StockAutoException(
                code="TOSS_BALANCE_UNAVAILABLE",
                message=f"토스증권 매수 가능 금액 조회에 실패했습니다. HTTP {res.status_code}",
                status_code=502,
            )
        except StockAutoException:
            raise
        except Exception as e:
            raise StockAutoException(
                code="TOSS_BALANCE_UNAVAILABLE",
                message="토스증권 매수 가능 금액을 조회하지 못했습니다.",
                status_code=502,
            ) from e

    def get_assets(self) -> list:
        """
        기존 TossBroker 소비자를 위한 호환 래퍼입니다.
        """
        return self.get_holdings_payload().get("items", [])
