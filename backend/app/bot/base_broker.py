from abc import ABC, abstractmethod

class BaseBroker(ABC):
    """
    모든 증권사 연동 클라이언트가 상속받아야 하는 공통 추상 인터페이스.
    이 규격을 충족하면 새로운 증권사(미래에셋, 토스 등)를 언제든 플러그인 형태로 조립할 수 있습니다.

    3-Mode 체계:
      - SimulatedBroker: 증권사 API 없이 DB + yfinance 기반 가상 체결
      - KISBroker (MOCK): KIS 모의투자 서버 연동
      - KISBroker (REAL): KIS 실전 서버 연동

    생성자 규격:
      모든 하위 브로커는 반드시 db_settings 객체를 받는 동일한 생성자 시그니처를 따라야 합니다.
      팩토리(broker_factory.py)에서 broker_class(db_settings)로 통일 호출됩니다.
    """

    def __init__(self, db_settings=None, db_credential=None):
        self.db_settings = db_settings
        self.db_credential = db_credential

    @abstractmethod
    def get_account_balance(self, exchange_rate: float | None = None) -> dict:
        """
        계좌 예수금, 주식 평가금, 총자산 및 실시간 수익률을 딕셔너리로 조회하여 반환합니다.

        반환 규격:
        {
            "total_asset": int,
            "cash_balance": int,
            "stock_balance": int,
            "profit_rate": float,
            "is_mock": bool,
            "provider": str
        }
        """
        pass

    @abstractmethod
    def get_holdings(self, exchange_rate: float | None = None) -> list:
        """
        현재 계좌의 실시간 해외주식 보유 포트폴리오 리스트를 반환합니다.

        반환 규격:
        [
            {
                "id": int,
                "ticker": str,
                "ticker_name": str,
                "avg_price": float,
                "quantity": int,
                "highest_price": float,
                "current_price": float,
                "is_mock": bool,
                "provider": str
            },
            ...
        ]
        """
        pass

    @abstractmethod
    def buy_order(
        self,
        ticker: str,
        quantity: int,
        price: float,
        session: str = "REGULAR_MARKET",
        client_order_id: str | None = None,
    ) -> dict:
        """
        해외주식 매수 주문을 실행합니다.

        반환 규격:
        {
            "success": bool,
            "order_no": str,          # 주문번호 (SIMULATED 모드에서는 "SIM-BUY-{타임스탬프}")
            "filled_qty": int,        # 체결 수량
            "filled_price": float,    # 체결 단가
            "message": str
        }
        """
        pass

    @abstractmethod
    def sell_order(
        self,
        ticker: str,
        quantity: int,
        price: float,
        session: str = "REGULAR_MARKET",
        client_order_id: str | None = None,
    ) -> dict:
        """
        해외주식 매도 주문을 실행합니다.

        반환 규격:
        {
            "success": bool,
            "order_no": str,
            "filled_qty": int,
            "filled_price": float,
            "message": str
        }
        """
        pass

    @abstractmethod
    def check_order_status(self, order_no: str, order_date: str | None = None) -> dict:
        """증권사 주문의 누적 체결 상태를 조회합니다."""
        pass

    @abstractmethod
    def list_order_history(self, start_date: str, end_date: str) -> list[dict]:
        """지정 기간의 주문·체결내역 전체 페이지를 정규화하여 반환합니다."""
        pass

    @abstractmethod
    def get_order_metadata(self, ticker: str, session: str) -> dict:
        """주문 사전 원장에 저장할 거래소와 주문 구분 코드를 반환합니다."""
        pass
