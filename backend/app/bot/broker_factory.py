from app.core.config import settings
from app.bot.kis_broker import KISBroker
from app.bot.simulated_broker import LocalSimulatedBroker
from app.bot.base_broker import BaseBroker

def get_broker_client(user_settings=None) -> BaseBroker:
    """
    3-Mode 트레이딩 체계에 따라 알맞은 브로커 객체를 반환하는 팩토리 함수 (멀티유저 대응).
    """
    if user_settings:
        mode = user_settings.trade_mode
        kis_app_key = user_settings.kis_app_key
        user_id = user_settings.user_id
    else:
        mode = settings.TRADE_MODE
        kis_app_key = settings.KIS_APP_KEY
        user_id = None

    if mode == "SIMULATED":
        return LocalSimulatedBroker(user_id=user_id)

    # MOCK 또는 REAL → 증권사 API Key 유효성 검사
    has_valid_keys = _has_valid_kis_keys(kis_app_key)

    if mode == "MOCK":
        if has_valid_keys:
            return KISBroker(user_settings)
        else:
            print(f"[BrokerFactory] MOCK mode but no valid KIS keys for user {user_id}. Falling back to SimulatedBroker.")
            return LocalSimulatedBroker(user_id=user_id)

    if mode == "REAL":
        if has_valid_keys:
            return KISBroker(user_settings)
        else:
            print(f"[BrokerFactory] ⚠️  REAL mode but no valid KIS keys for user {user_id}! Falling back to SimulatedBroker for safety.")
            return LocalSimulatedBroker(user_id=user_id)

    return LocalSimulatedBroker(user_id=user_id)


def _has_valid_kis_keys(kis_app_key: str) -> bool:
    """KIS API Key가 실제로 입력되어 있는지 확인합니다."""
    placeholder_keys = {
        "YOUR_APP_KEY_HERE", "your_virtual_app_key_here",
        "your_real_app_key_here", "your_app_key_here",
        None, ""
    }
    return kis_app_key not in placeholder_keys
