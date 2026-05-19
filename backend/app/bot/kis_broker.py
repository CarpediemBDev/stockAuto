from app.bot.base_broker import BaseBroker
from app.bot.kis_api import KISClient
from app.core.config import settings

class KISBroker(BaseBroker):
    """
    한국투자증권(KIS) API 실연동 브로커 클라이언트.
    BaseBroker 인터페이스 규격에 맞춰 KIS API의 실제 응답 데이터를 매핑합니다.
    """
    def __init__(self):
        self.client = KISClient()

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
                    "is_mock": not settings.IS_REAL,
                    "provider": "KIS Live" if settings.IS_REAL else "KIS Mock"
                })
            return result
        except Exception as e:
            print(f"[KISBroker] Failed to fetch holdings from KIS: {e}")
            raise e
