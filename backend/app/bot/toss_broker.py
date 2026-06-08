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
        """
        토스증권 assets API 목록을 받아 공통 Holding 포맷으로 매핑합니다.
        """
        assets = self.client.get_assets()
        if not assets:
            return []

        holdings_list = []
        for asset in assets:
            # 수량과 금액 파싱 가드 장착
            def parse_float(val, default=0.0):
                try:
                    return float(val or default)
                except (ValueError, TypeError):
                    return default

            qty = int(parse_float(asset.get("quantity")))
            if qty <= 0:
                continue

            ticker = asset.get("symbol")
            avg_price = parse_float(asset.get("purchasePrice"))
            ticker_name = asset.get("name") or ticker

            # StockAuto 공통 보유 종목 스키마 반환
            holdings_list.append({
                "ticker": ticker,
                "ticker_name": ticker_name,
                "quantity": qty,
                "avg_price": avg_price
            })

        return holdings_list

    def buy_order(self, ticker: str, quantity: int, price: float, session: str = "REGULAR_MARKET", client_order_id: str | None = None) -> dict:
        res = self.client.buy_overseas_order(ticker, quantity, price, session, client_order_id)
        if res and res.get("rt_cd") == "0":
            order_id = res.get("orderId") or ("TOSS-BUY-" + str(uuid.uuid4())[:8])
            return {
                "success": True, 
                "order_no": order_id, 
                "filled_qty": 0,  # 비동기 주문이므로 초기 체결은 0
                "filled_price": price, 
                "message": "Success",
                "status": "PENDING"
            }
        
        err_msg = res.get("msg1") if res else "Unknown API Error"
        return {"success": False, "order_no": "", "filled_qty": 0, "filled_price": 0, "message": err_msg, "status": "ERROR"}

    def sell_order(self, ticker: str, quantity: int, price: float, session: str = "REGULAR_MARKET", client_order_id: str | None = None) -> dict:
        res = self.client.sell_overseas_order(ticker, quantity, price, session, client_order_id)
        if res and res.get("rt_cd") == "0":
            order_id = res.get("orderId") or ("TOSS-SELL-" + str(uuid.uuid4())[:8])
            return {
                "success": True, 
                "order_no": order_id, 
                "filled_qty": 0, 
                "filled_price": price, 
                "message": "Success",
                "status": "PENDING"
            }
        
        err_msg = res.get("msg1") if res else "Unknown API Error"
        return {"success": False, "order_no": "", "filled_qty": 0, "filled_price": 0, "message": err_msg, "status": "ERROR"}

    def check_order_status(self, order_no: str, order_date: str | None = None) -> dict:
        """
        토스증권 개별 주문 상태를 실 조회하고 공통 규격으로 정규화합니다.
        """
        order_detail = self.client.get_order_status(order_no)
        if not order_detail:
            # 조회 실패 또는 토큰 에러 시 UNCONFIRMED/ERROR 리턴
            return {
                "status": "ERROR", 
                "filled_qty": 0, 
                "ordered_qty": 0, 
                "filled_price": 0.0, 
                "order_no": order_no,
                "message": "토스 주문 상태 조회 실패"
            }

        # 상태 정규화
        raw_status = (order_detail.get("status") or "OPEN").upper()
        if raw_status in ["RECEIVED", "OPEN", "SUBMITTED", "PENDING"]:
            status = "PENDING"
        elif raw_status == "FILLED":
            status = "FILLED"
        elif raw_status == "PARTIAL":
            status = "PARTIAL"
        elif raw_status == "CANCELED":
            status = "CANCELED"
        elif raw_status == "REJECTED":
            status = "REJECTED"
        else:
            status = "ERROR"

        # 수량 및 가격 정보 파싱
        def parse_val(val, default=0.0):
            try:
                return float(val or default)
            except (ValueError, TypeError):
                return default

        ordered_qty = int(parse_val(order_detail.get("quantity")))
        filled_qty = int(parse_val(order_detail.get("filledQuantity")))
        filled_price = parse_val(order_detail.get("filledPrice"))

        return {
            "status": status,
            "filled_qty": filled_qty,
            "ordered_qty": ordered_qty,
            "filled_price": filled_price,
            "order_no": order_no
        }

    def list_order_history(self, start_date: str, end_date: str) -> list[dict]:
        """
        토스증권 주문 이력을 조회하고 공통 포맷으로 가공합니다.
        """
        orders = self.client.get_order_history(status=None)
        if not orders:
            return []

        history_list = []
        for o in orders:
            order_id = o.get("orderId")
            if not order_id:
                continue

            raw_status = (o.get("status") or "OPEN").upper()
            if raw_status in ["RECEIVED", "OPEN"]:
                status = "UNFILLED"
            elif raw_status == "FILLED":
                status = "FILLED"
            elif raw_status == "PARTIAL":
                status = "PARTIAL"
            elif raw_status == "CANCELED":
                status = "CANCELED"
            else:
                status = "REJECTED"

            def parse_val(val, default=0.0):
                try:
                    return float(val or default)
                except (ValueError, TypeError):
                    return default

            ordered_qty = int(parse_val(o.get("quantity")))
            filled_qty = int(parse_val(o.get("filledQuantity")))
            filled_price = parse_val(o.get("filledPrice"))
            order_price = parse_val(o.get("price"))

            history_list.append({
                "order_no": order_id,
                "original_order_no": "",
                "order_date": start_date,  # 토스 API에서 일자 정보를 얻지 못하면 기본값
                "order_time": "000000",
                "side": (o.get("side") or "BUY").upper(),
                "ticker": o.get("symbol"),
                "ticker_name": o.get("symbol"),
                "exchange_code": "NASD",  # 기본값
                "ordered_qty": ordered_qty,
                "order_price": order_price,
                "filled_qty": filled_qty,
                "filled_price": filled_price,
                "unfilled_qty": max(0, ordered_qty - filled_qty),
                "status": status,
                "reject_reason": o.get("rejectReason") or ""
            })

        return history_list

    def get_order_metadata(self, ticker: str, session: str) -> dict:
        return {"exchange_code": "NASD", "order_division": "00"}
