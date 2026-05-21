from abc import ABC, abstractmethod

class BaseBroker(ABC):
    """
    모든 증권사 연동 클라이언트가 상속받아야 하는 공통 추상 인터페이스.
    이 규격을 충족하면 새로운 증권사(미래에셋, 토스 등)를 언제든 플러그인 형태로 조립할 수 있습니다.

    3-Mode 체계:
      - SimulatedBroker: 증권사 API 없이 DB + yfinance 기반 가상 체결
      - KISBroker (MOCK): KIS 모의투자 서버 연동
      - KISBroker (REAL): KIS 실전 서버 연동
    """

    @abstractmethod
    def get_account_balance(self) -> dict:
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
    def get_holdings(self) -> list:
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
    def buy_order(self, ticker: str, quantity: int, price: float) -> dict:
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
    def sell_order(self, ticker: str, quantity: int, price: float) -> dict:
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
