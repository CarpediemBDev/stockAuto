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

        최대 FILL_POLL_MAX_RETRIES 회 시도 후에도 미체결이면 PENDING을 반환합니다.
        체결이 확인되지 않은 주문을 제출 수량/가격으로 임의 체결 처리하지 않습니다.
        """
        if not order_no:
            return {
                "status": "UNCONFIRMED",
                "filled_qty": 0,
                "filled_price": 0.0,
                "confirmed": False,
            }

        for attempt in range(1, self.FILL_POLL_MAX_RETRIES + 1):
            time.sleep(self.FILL_POLL_INTERVAL_SEC)
            try:
                status = self.client.check_order_status(order_no)

                if status.get("status") == "FILLED":
                    logger.info(f"[KISBroker] Order {order_no} FILLED confirmed on attempt {attempt}: "
                                f"qty={status['filled_qty']}, price=${status['filled_price']:.2f}")
                    return {
                        "status": "FILLED",
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
                            "status": "PARTIAL",
                            "filled_qty": status["filled_qty"],
                            "filled_price": status["filled_price"],
                            "confirmed": False
                        }
                elif status.get("status") == "ERROR":
                    logger.error(f"[KISBroker] Order status check error: {status.get('message')}")
                    break
                else:
                    logger.info(f"[KISBroker] Order {order_no} not yet filled (attempt {attempt}/{self.FILL_POLL_MAX_RETRIES})")
            except Exception as e:
                logger.error(f"[KISBroker] Fill confirmation polling error: {e}")
                break

        logger.warning(f"[KISBroker] Order {order_no} fill confirmation timed out after {self.FILL_POLL_MAX_RETRIES} attempts. "
                       "Keeping the order pending for background reconciliation.")
        return {
            "status": "PENDING",
            "filled_qty": 0,
            "filled_price": 0.0,
            "confirmed": False,
        }

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

    def check_order_status(self, order_no: str, order_date: str | None = None) -> dict:
        return self.client.check_order_status(order_no, order_date=order_date)

    def list_order_history(self, start_date: str, end_date: str) -> list[dict]:
        return self.client.list_order_history(start_date, end_date)

    def get_order_metadata(self, ticker: str, session: str) -> dict:
        return {
            "exchange_code": self.client._get_exchange_code(ticker),
            "order_division": self.client._order_division_for_session(session),
        }

    def buy_order(
        self,
        ticker: str,
        quantity: int,
        price: float,
        session: str = "REGULAR_MARKET",
        client_order_id: str | None = None,
    ) -> dict:
        """
        KIS API를 통한 해외주식 매수 주문.
        KISClient.buy_overseas_order()를 호출하고, 체결 확인 후 결과를 표준 형식으로 매핑합니다.
        """
        try:
            res = self.client.buy_overseas_order(
                ticker,
                quantity,
                price=price,
                session=session,
                client_order_id=client_order_id,
            )
            if res and res.get("rt_cd") == "0":
                order_no = res.get("output", {}).get("ODNO", "")

                # 💡 체결 확인 폴링 — 실제 체결 수량/가격 확인
                fill_info = self._confirm_fill(order_no, quantity, price)

                status = fill_info["status"]
                is_recordable_fill = status in {"FILLED", "PARTIAL"} and fill_info["filled_qty"] > 0
                return {
                    "success": is_recordable_fill,
                    "order_submitted": True,
                    "status": status,
                    "order_no": order_no,
                    "filled_qty": fill_info["filled_qty"],
                    "filled_price": fill_info["filled_price"],
                    "fill_confirmed": fill_info["confirmed"],
                    "message": f"KIS buy order status={status}: "
                               f"{ticker} x{fill_info['filled_qty']} at ${fill_info['filled_price']:.2f}"
                }
            elif res is None or res.get("submission_unknown"):
                return {
                    "success": False,
                    "order_submitted": True,
                    "submission_unknown": True,
                    "status": "ACK_UNKNOWN",
                    "order_no": "",
                    "filled_qty": 0,
                    "filled_price": 0,
                    "fill_confirmed": False,
                    "message": "KIS buy order acknowledgement was not received.",
                }
            else:
                msg = res.get("msg1", "Unknown error") if res else "No response"
                return {
                    "success": False,
                    "order_submitted": False,
                    "status": "REJECTED",
                    "order_no": "",
                    "filled_qty": 0,
                    "filled_price": 0,
                    "message": f"KIS buy order rejected: {msg}"
                }
        except Exception as e:
            return {
                "success": False,
                "order_submitted": True,
                "submission_unknown": True,
                "status": "ACK_UNKNOWN",
                "order_no": "",
                "filled_qty": 0,
                "filled_price": 0,
                "fill_confirmed": False,
                "message": f"KIS buy order acknowledgement unknown: {str(e)}"
            }

    def sell_order(
        self,
        ticker: str,
        quantity: int,
        price: float,
        session: str = "REGULAR_MARKET",
        client_order_id: str | None = None,
    ) -> dict:
        """
        KIS API를 통한 해외주식 매도 주문.
        체결 확인 폴링을 통해 실제 체결 데이터를 확인합니다.
        """
        try:
            res = self.client.sell_overseas_order(
                ticker,
                quantity,
                price=price,
                session=session,
                client_order_id=client_order_id,
            )
            if res and res.get("rt_cd") == "0":
                order_no = res.get("output", {}).get("ODNO", "")

                # 💡 체결 확인 폴링 — 실제 체결 수량/가격 확인
                fill_info = self._confirm_fill(order_no, quantity, price)

                status = fill_info["status"]
                is_recordable_fill = status in {"FILLED", "PARTIAL"} and fill_info["filled_qty"] > 0
                return {
                    "success": is_recordable_fill,
                    "order_submitted": True,
                    "status": status,
                    "order_no": order_no,
                    "filled_qty": fill_info["filled_qty"],
                    "filled_price": fill_info["filled_price"],
                    "fill_confirmed": fill_info["confirmed"],
                    "message": f"KIS sell order status={status}: "
                               f"{ticker} x{fill_info['filled_qty']} at ${fill_info['filled_price']:.2f}"
                }
            elif res is None or res.get("submission_unknown"):
                return {
                    "success": False,
                    "order_submitted": True,
                    "submission_unknown": True,
                    "status": "ACK_UNKNOWN",
                    "order_no": "",
                    "filled_qty": 0,
                    "filled_price": 0,
                    "fill_confirmed": False,
                    "message": "KIS sell order acknowledgement was not received.",
                }
            else:
                msg = res.get("msg1", "Unknown error") if res else "No response"
                return {
                    "success": False,
                    "order_submitted": False,
                    "status": "REJECTED",
                    "order_no": "",
                    "filled_qty": 0,
                    "filled_price": 0,
                    "message": f"KIS sell order rejected: {msg}"
                }
        except Exception as e:
            return {
                "success": False,
                "order_submitted": True,
                "submission_unknown": True,
                "status": "ACK_UNKNOWN",
                "order_no": "",
                "filled_qty": 0,
                "filled_price": 0,
                "fill_confirmed": False,
                "message": f"KIS sell order acknowledgement unknown: {str(e)}"
            }
