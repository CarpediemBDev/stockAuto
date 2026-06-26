from app.bot.base_broker import BaseBroker
from app.bot.kis_api import KISClient
from app.bot.kis_broker import KISBroker
from app.bot.simulated_broker import LocalSimulatedBroker
from app.bot.toss_api import TossClient
from app.bot.toss_broker import TossBroker
from app.core.config import VALID_TRADE_MODES


# 실행 클래스, 인증 클라이언트, 사용자 노출 정보를 함께 관리하는 증권사 SSOT입니다.
BROKER_REGISTRY = {
    "KIS": {
        "label": "한국투자증권",
        "tone": "amber",
        "client_class": KISClient,
        "broker_classes": {
            "SIMULATED": LocalSimulatedBroker,
            "MOCK": KISBroker,
            "REAL": KISBroker,
        },
    },
    "TOSS": {
        "label": "토스증권",
        "tone": "blue",
        "client_class": TossClient,
        "broker_classes": {
            "SIMULATED": LocalSimulatedBroker,
        },
    },
}


def get_broker_catalog() -> list[dict]:
    return [
        {
            "id": provider,
            "label": definition["label"],
            "tone": definition["tone"],
            "supported_modes": [
                mode
                for mode in VALID_TRADE_MODES
                if mode in definition["broker_classes"]
            ],
        }
        for provider, definition in BROKER_REGISTRY.items()
    ]


def normalize_broker_provider(provider: str | None) -> str:
    normalized = (provider or "").upper().strip()
    if normalized not in BROKER_REGISTRY:
        raise ValueError(f"지원하지 않는 증권사입니다: {provider}")
    return normalized


def broker_supports_trade_mode(provider: str | None, trade_mode: str | None) -> bool:
    normalized = normalize_broker_provider(provider)
    mode = (trade_mode or "SIMULATED").upper().strip()
    return mode in BROKER_REGISTRY[normalized]["broker_classes"]


def ensure_broker_supports_trade_mode(provider: str | None, trade_mode: str | None) -> str:
    normalized = normalize_broker_provider(provider)
    mode = (trade_mode or "SIMULATED").upper().strip()
    if mode not in BROKER_REGISTRY[normalized]["broker_classes"]:
        raise ValueError(f"{normalized} 증권사는 {mode} 모드를 지원하지 않습니다.")
    return normalized


def create_broker_verification_client(provider: str, credential, trade_mode: str):
    normalized = ensure_broker_supports_trade_mode(provider, trade_mode)
    client_class = BROKER_REGISTRY[normalized]["client_class"]
    return client_class(db_credential=credential, trade_mode=trade_mode)


def get_broker_client(db_settings=None) -> BaseBroker:
    if not db_settings:
        return LocalSimulatedBroker(None)

    mode = (db_settings.trade_mode or "SIMULATED").upper()
    if mode == "SIMULATED":
        return LocalSimulatedBroker(db_settings)

    provider = (db_settings.broker_provider or "").upper()
    if not provider:
        raise ValueError("MOCK 또는 REAL 모드에서는 증권사(broker_provider)가 반드시 지정되어야 합니다.")
    provider = normalize_broker_provider(provider)

    cred = None
    if getattr(db_settings, "credentials", None):
        for candidate in db_settings.credentials:
            if candidate.broker_name.upper() == provider:
                cred = candidate
                break

    ensure_broker_supports_trade_mode(provider, mode)
    provider_map = BROKER_REGISTRY[provider]["broker_classes"]
    broker_class = provider_map.get(mode)
    return broker_class(db_settings, db_credential=cred)
