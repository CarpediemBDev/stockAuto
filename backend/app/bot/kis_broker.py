from app.bot.base_broker import BaseBroker
from app.bot.kis_api import KISClient
from app.core.config import settings

class KISBroker(BaseBroker):
    """
    한국투자증권(KIS) API 실연동 브로커 클라이언트.
    BaseBroker 인터페이스 규격에 맞춰 KIS API의 실제 응답 데이터를 매핑합니다.
    
    MOCK 모드: KIS 모의투자 서버(vts-openapi)에 주문 전송
    REAL 모드: KIS 실전 서버(openapi)에 주문 전송
    """
    def __init__(self, user_settings=None):
        self.user_settings = user_settings
        self.client = KISClient(user_settings)

    def get_account_balance(self) -> dict:
        # KISClient의 계좌 조회 실행 (내부에 이미 dynamic provider가 구현됨)
        return self.client.get_account_balance()

    def get_holdings(self) -> list:
        # KIS API를 통한 실시간 해외 보유 종목 조회
        from app.bot.fx_cache import FXRateCache
        exchange_rate = FXRateCache.get_rate()

        try:
            actual_holdings = self.client.get_overseas_present_balance()
            result = []
            for idx, item in enumerate(actual_holdings):
                result.append({
                    "id": idx + 1000,  # KIS 실계좌 종목은 1000번대부터 시작하여 구분
                    "ticker": item["ticker"],
                    "ticker_name": item["name"],
                    "avg_price": item["buy_price"],
                    "quantity": item["qty"],
                    "highest_price": max(item["buy_price"], item["current_price"]),
                    "current_price": item["current_price"],
                    "fx_rate": exchange_rate,
                    "is_mock": not (self.user_settings.trade_mode == "REAL" if self.user_settings else settings.IS_REAL),
                    "provider": "KIS Live" if (self.user_settings.trade_mode == "REAL" if self.user_settings else settings.IS_REAL) else "KIS Mock"
                })
            return result
        except Exception as e:
            print(f"[KISBroker] Failed to fetch holdings from KIS: {e}")
            raise e

    def buy_order(self, ticker: str, quantity: int, price: float) -> dict:
        """
        KIS API를 통한 해외주식 매수 주문.
        KISClient.buy_overseas_order()를 호출하고 결과를 표준 형식으로 매핑합니다.
        """
        try:
            res = self.client.buy_overseas_order(ticker, quantity, price=price)
            if res and res.get("rt_cd") == "0":
                order_no = res.get("output", {}).get("ODNO", "")
                return {
                    "success": True,
                    "order_no": order_no,
                    "filled_qty": quantity,  # 발주 수량 (체결 확인은 check_order_status로)
                    "filled_price": price,
                    "message": f"KIS buy order submitted: {ticker} x{quantity} at ${price:.2f}"
                }
            else:
                msg = res.get("msg1", "Unknown error") if res else "No response"
                return {
                    "success": False,
                    "order_no": "",
                    "filled_qty": 0,
                    "filled_price": 0,
                    "message": f"KIS buy order rejected: {msg}"
                }
        except Exception as e:
            return {
                "success": False,
                "order_no": "",
                "filled_qty": 0,
                "filled_price": 0,
                "message": f"KIS buy order exception: {str(e)}"
            }

    def sell_order(self, ticker: str, quantity: int, price: float) -> dict:
        """
        KIS API를 통한 해외주식 매도 주문.
        """
        try:
            res = self.client.sell_overseas_order(ticker, quantity, price=price)
            if res and res.get("rt_cd") == "0":
                order_no = res.get("output", {}).get("ODNO", "")
                return {
                    "success": True,
                    "order_no": order_no,
                    "filled_qty": quantity,
                    "filled_price": price,
                    "message": f"KIS sell order submitted: {ticker} x{quantity} at ${price:.2f}"
                }
            else:
                msg = res.get("msg1", "Unknown error") if res else "No response"
                return {
                    "success": False,
                    "order_no": "",
                    "filled_qty": 0,
                    "filled_price": 0,
                    "message": f"KIS sell order rejected: {msg}"
                }
        except Exception as e:
            return {
                "success": False,
                "order_no": "",
                "filled_qty": 0,
                "filled_price": 0,
                "message": f"KIS sell order exception: {str(e)}"
            }
