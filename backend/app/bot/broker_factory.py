from app.core.config import settings
from app.bot.kis_broker import KISBroker
from app.bot.simulated_broker import LocalSimulatedBroker
from app.bot.base_broker import BaseBroker

# 안전하게 연동을 허용할 증권사 클래스 레지스트리 (화이트리스트)
BROKER_REGISTRY = {
    "SIMULATED": LocalSimulatedBroker,    # 가상 모의투자 시뮬레이터
    "MOCK": KISBroker,                    # 한국투자증권 모의투자
    "REAL": KISBroker,                    # 한국투자증권 실전투자
    # "TOSS_MOCK": TossBroker,            # 추후 토스증권 모의투자 연동 시
    # "TOSS_REAL": TossBroker,            # 추후 토스증권 실전투자 연동 시
}

def get_broker_client(user_settings=None) -> BaseBroker:
    """
    3-Mode 트레이딩 체계에 따라 알맞은 브로커 객체를 반환하는 팩토리 함수 (멀티유저 대응).
    """
    mode = user_settings.trade_mode if user_settings else settings.TRADE_MODE
    kis_app_key = user_settings.kis_app_key if user_settings else settings.KIS_APP_KEY

    # KIS API Key 유효성 검사 — 키가 없으면 안전하게 SIMULATED로 폴백
    if mode in ["MOCK", "REAL"] and not _has_valid_kis_keys(kis_app_key):
        print(f"[BrokerFactory] ⚠️ {mode} mode but no valid KIS keys. Falling back to SIMULATED.")
        mode = "SIMULATED"

    # 검증된 레지스트리에서 브로커 클래스를 꺼내어 조립 (미등록 모드는 기본 시뮬레이터)
    broker_class = BROKER_REGISTRY.get(mode, LocalSimulatedBroker)
    return broker_class(user_settings)


def _has_valid_kis_keys(kis_app_key: str) -> bool:
    """KIS API Key가 실제로 입력되어 있는지 확인합니다."""
    placeholder_keys = {
        "YOUR_APP_KEY_HERE", "your_virtual_app_key_here",
        "your_real_app_key_here", "your_app_key_here",
        None, ""
    }
    return kis_app_key not in placeholder_keys

