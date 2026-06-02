from app.bot.base_broker import BaseBroker
from app.bot.kis_api import KISClient
from app.core.logging import logger
import time

class KISBroker(BaseBroker):
    """
    한국투자증권(KIS) API 실연동 브로커 클라이언트.
    BaseBroker 인터페이스 규격에 맞춰 KIS API의 실제 응답 데이터를 매핑합니다.
    
    MOCK 모드: KIS 모의투자 서버(vts-openapi)에 주문 전송
    REAL 모드: KIS 실전 서버(openapi)에 주문 전송
    """
    # 💡 체결 확인 폴링 설정 (최대 5회 × 2초 = 10초 대기)
    FILL_POLL_MAX_RETRIES = 5
    FILL_POLL_INTERVAL_SEC = 2.0

    def __init__(self, db_settings=None):
        super().__init__(db_settings)
        self.client = KISClient(db_settings)

    def _confirm_fill(self, order_no: str, submitted_qty: int, submitted_price: float) -> dict:
        """
        주문 번호를 기반으로 KIS API에 체결 상태를 폴링하여
        실제 체결 수량/가격을 확인합니다.
        
        최대 FILL_POLL_MAX_RETRIES 회 시도 후에도 미체결이면
        주문 제출 시의 수량/가격을 fallback으로 반환합니다.
        """
        if not order_no:
            return {"filled_qty": submitted_qty, "filled_price": submitted_price, "confirmed": False}

        for attempt in range(1, self.FILL_POLL_MAX_RETRIES + 1):
            time.sleep(self.FILL_POLL_INTERVAL_SEC)
            try:
                status = self.client.check_order_status(order_no)
                
                if status.get("status") == "FILLED":
                    logger.info(f"[KISBroker] Order {order_no} FILLED confirmed on attempt {attempt}: "
                                f"qty={status['filled_qty']}, price=${status['filled_price']:.2f}")
                    return {
                        "filled_qty": status["filled_qty"],
                        "filled_price": status["filled_price"],
                        "confirmed": True
                    }
                elif status.get("status") == "PARTIAL":
                    logger.warning(f"[KISBroker] Order {order_no} PARTIAL fill on attempt {attempt}: "
                                   f"{status['filled_qty']}/{status['ordered_qty']} filled")
                    # 부분 체결은 체결된 만큼만 반환
                    if status["filled_qty"] > 0:
                        return {
                            "filled_qty": status["filled_qty"],
                            "filled_price": status["filled_price"],
                            "confirmed": True
                        }
                elif status.get("status") == "ERROR":
                    logger.error(f"[KISBroker] Order status check error: {status.get('message')}")
                    break
                else:
                    logger.info(f"[KISBroker] Order {order_no} not yet filled (attempt {attempt}/{self.FILL_POLL_MAX_RETRIES})")
            except Exception as e:
                logger.error(f"[KISBroker] Fill confirmation polling error: {e}")
                break

        # 폴링 실패 시 제출 값을 fallback으로 사용 (기존 동작 호환)
        logger.warning(f"[KISBroker] Order {order_no} fill confirmation timed out after {self.FILL_POLL_MAX_RETRIES} attempts. "
                       f"Using submitted values as fallback: qty={submitted_qty}, price=${submitted_price:.2f}")
        return {"filled_qty": submitted_qty, "filled_price": submitted_price, "confirmed": False}

    def get_account_balance(self, exchange_rate: float | None = None) -> dict:
        # KISClient의 계좌 조회 실행 (내부에 이미 dynamic provider가 구현됨)
        return self.client.get_account_balance(exchange_rate=exchange_rate)

    def get_holdings(self, exchange_rate: float | None = None) -> list:
        # KIS API를 통한 실시간 해외 보유 종목 조회
        if exchange_rate is None:
            from app.bot.fx_cache import FXRateCache
            exchange_rate = FXRateCache.get_rate()

        try:
            actual_holdings = self.client.get_overseas_present_balance()
            result = []
            for idx, item in enumerate(actual_holdings):
                trade_mode = (self.db_settings.trade_mode or "SIMULATED").upper()
                result.append({
                    "id": idx + 1000,  # KIS 실계좌 종목은 1000번대부터 시작하여 구분
                    "ticker": item["ticker"],
                    "ticker_name": item["name"],
                    "avg_price": item["buy_price"],
                    "quantity": item["qty"],
                    "highest_price": max(item["buy_price"], item["current_price"]),
                    "current_price": item["current_price"],
                    "fx_rate": exchange_rate,
                    "is_mock": trade_mode != "REAL",
                    "provider": "KIS Live" if trade_mode == "REAL" else "KIS Mock"
                })
            return result
        except Exception as e:
            logger.error(f"[KISBroker] Failed to fetch holdings from KIS: {e}")
            raise e

    def buy_order(self, ticker: str, quantity: int, price: float) -> dict:
        """
        KIS API를 통한 해외주식 매수 주문.
        KISClient.buy_overseas_order()를 호출하고, 체결 확인 후 결과를 표준 형식으로 매핑합니다.
        """
        try:
            res = self.client.buy_overseas_order(ticker, quantity, price=price)
            if res and res.get("rt_cd") == "0":
                order_no = res.get("output", {}).get("ODNO", "")
                
                # 💡 체결 확인 폴링 — 실제 체결 수량/가격 확인
                fill_info = self._confirm_fill(order_no, quantity, price)
                
                return {
                    "success": True,
                    "order_no": order_no,
                    "filled_qty": fill_info["filled_qty"],
                    "filled_price": fill_info["filled_price"],
                    "fill_confirmed": fill_info["confirmed"],
                    "message": f"KIS buy order {'confirmed' if fill_info['confirmed'] else 'submitted'}: "
                               f"{ticker} x{fill_info['filled_qty']} at ${fill_info['filled_price']:.2f}"
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
        체결 확인 폴링을 통해 실제 체결 데이터를 확인합니다.
        """
        try:
            res = self.client.sell_overseas_order(ticker, quantity, price=price)
            if res and res.get("rt_cd") == "0":
                order_no = res.get("output", {}).get("ODNO", "")
                
                # 💡 체결 확인 폴링 — 실제 체결 수량/가격 확인
                fill_info = self._confirm_fill(order_no, quantity, price)
                
                return {
                    "success": True,
                    "order_no": order_no,
                    "filled_qty": fill_info["filled_qty"],
                    "filled_price": fill_info["filled_price"],
                    "fill_confirmed": fill_info["confirmed"],
                    "message": f"KIS sell order {'confirmed' if fill_info['confirmed'] else 'submitted'}: "
                               f"{ticker} x{fill_info['filled_qty']} at ${fill_info['filled_price']:.2f}"
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
