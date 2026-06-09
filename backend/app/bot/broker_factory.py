from app.bot.kis_broker import KISBroker
from app.bot.toss_broker import TossBroker
from app.bot.simulated_broker import LocalSimulatedBroker
from app.bot.base_broker import BaseBroker

# 안전하게 연동을 허용할 증권사 클래스 레지스트리 (화이트리스트)
BROKER_REGISTRY = {
    "KIS": {
        "SIMULATED": LocalSimulatedBroker,    # 가상 모의투자 시뮬레이터
        "MOCK": KISBroker,                    # 한국투자증권 모의투자
        "REAL": KISBroker,                    # 한국투자증권 실전투자
    },
    "TOSS": {
        "SIMULATED": LocalSimulatedBroker,
        "MOCK": TossBroker,                   # 토스는 별도 모의투자가 없다면 내부적으로 처리되거나 실패할 수 있음
        "REAL": TossBroker,                   # 토스증권 실전투자
    }
}

def get_broker_client(db_settings=None) -> BaseBroker:
    if not db_settings:
        return LocalSimulatedBroker(None)

    mode = (db_settings.trade_mode or "SIMULATED").upper()
    if mode == "SIMULATED":
        return LocalSimulatedBroker(db_settings)

    provider = (db_settings.broker_provider or "").upper()
    if not provider:
        raise ValueError("MOCK 또는 REAL 모드에서는 증권사(broker_provider)가 반드시 지정되어야 합니다.")

    cred = None
    if getattr(db_settings, "credentials", None):
        for c in db_settings.credentials:
            if c.broker_name.upper() == provider:
                cred = c
                break

    provider_map = BROKER_REGISTRY.get(provider)
    if not provider_map:
        raise ValueError(f"지원하지 않는 증권사입니다: {provider}")

    broker_class = provider_map.get(mode, LocalSimulatedBroker)
    return broker_class(db_settings, db_credential=cred)

