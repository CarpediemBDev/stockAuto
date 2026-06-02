from app.bot.kis_broker import KISBroker
from app.bot.simulated_broker import LocalSimulatedBroker
from app.bot.base_broker import BaseBroker

# 안전하게 연동을 허용할 증권사 클래스 레지스트리 (화이트리스트)
BROKER_REGISTRY = {
    "SIMULATED": LocalSimulatedBroker,    # 가상 모의투자 시뮬레이터
    "MOCK": KISBroker,                    # 한국투자증권 모의투자
    "REAL": KISBroker,                    # 한국투자증권 실전투자
}

def get_broker_client(db_settings=None) -> BaseBroker:
    """
    3-Mode 트레이딩 체계에 따라 알맞은 브로커 객체를 반환하는 팩토리 함수 (멀티유저 대응).
    """
    if not db_settings:
        return LocalSimulatedBroker(None)

    mode = (db_settings.trade_mode or "SIMULATED").upper()
    broker_class = BROKER_REGISTRY.get(mode, LocalSimulatedBroker)
    return broker_class(db_settings)

def is_real_order_locked(db_settings=None) -> bool:
    """
    REAL 모드에서도 사용자가 별도 안전 스위치를 켜기 전까지는 실제 주문 전송을 차단합니다.
    계좌 조회는 허용하되 buy/sell 주문 직전에 이 값을 확인합니다.
    """
    if not db_settings:
        return False
    mode = (db_settings.trade_mode or "SIMULATED").upper()
    return mode == "REAL" and not bool(db_settings.is_real_enabled)
