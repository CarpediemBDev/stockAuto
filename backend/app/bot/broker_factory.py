from app.core.config import settings
from app.bot.kis_broker import KISBroker
from app.bot.simulated_broker import LocalSimulatedBroker
from app.bot.base_broker import BaseBroker

def get_broker_client() -> BaseBroker:
    """
    3-Mode 트레이딩 체계에 따라 알맞은 브로커 객체를 반환하는 팩토리 함수.
    
    분기 로직:
      - SIMULATED: 항상 LocalSimulatedBroker (증권사 API 미사용)
      - MOCK:      KIS API Key가 유효하면 KISBroker(모의서버), 아니면 SimulatedBroker로 폴백
      - REAL:      KIS API Key가 유효하면 KISBroker(실전서버), 아니면 에러 로그 + SimulatedBroker로 폴백
    """
    mode = settings.TRADE_MODE

    if mode == "SIMULATED":
        return LocalSimulatedBroker()

    # MOCK 또는 REAL → 증권사 API Key 유효성 검사
    has_valid_keys = _has_valid_kis_keys()

    if mode == "MOCK":
        if has_valid_keys:
            return KISBroker()
        else:
            print("[BrokerFactory] MOCK mode but no valid KIS keys. Falling back to SimulatedBroker.")
            return LocalSimulatedBroker()

    if mode == "REAL":
        if has_valid_keys:
            return KISBroker()
        else:
            print("[BrokerFactory] ⚠️  REAL mode but no valid KIS keys! Falling back to SimulatedBroker for safety.")
            return LocalSimulatedBroker()

    # 알 수 없는 모드 (config.py에서 이미 방어하므로 도달 불가)
    return LocalSimulatedBroker()


def _has_valid_kis_keys() -> bool:
    """KIS API Key가 실제로 입력되어 있는지 확인합니다."""
    placeholder_keys = {
        "YOUR_APP_KEY_HERE", "your_virtual_app_key_here",
        "your_real_app_key_here", "your_app_key_here",
        None, ""
    }
    return settings.KIS_APP_KEY not in placeholder_keys
