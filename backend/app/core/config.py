import os
from dotenv import load_dotenv
from app.core.logging import logger

# Determine which environment to load (Default to local)
APP_ENV = os.getenv("APP_ENV", "local").lower()
env_file = f".env.{APP_ENV}"

# app/core/config.py의 위치 기준, 두 단계 위인 backend/ 루트 디렉터리를 찾아 해당 환경 파일만 로드합니다.
core_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.dirname(core_dir)
backend_dir = os.path.dirname(app_dir)

# 지정한 단일 환경 설정 파일만 로드 (중복/오버라이드 없음)
full_env_path = os.path.join(backend_dir, env_file)
if os.path.exists(full_env_path):
    # 12-Factor App 원칙: 실제 클라우드 OS 환경변수가 우선이어야 하므로 override=False (기본값) 사용
    load_dotenv(full_env_path, override=False)
    logger.info(f"[*] Environment loaded from: {full_env_path} (APP_ENV: {APP_ENV.upper()})")
else:
    logger.warning(f"[⚠️ WARNING] Environment file not found: {full_env_path}")

# 거래 모드 식별자와 사용자 노출 메타데이터의 단일 정의입니다.
TRADE_MODE_CATALOG = (
    {
        "id": "SIMULATED",
        "label": "SIMULATED",
        "description": "실시간 가격 기반 가상 투자 모드",
        "tone": "blue",
        "requires_credentials": False,
    },
    {
        "id": "MOCK",
        "label": "MOCK",
        "description": "증권사 모의투자 서버 연동 모드",
        "tone": "amber",
        "requires_credentials": True,
    },
    {
        "id": "REAL",
        "label": "REAL",
        "description": "실전 계좌 기반 자동매매 모드",
        "tone": "red",
        "requires_credentials": True,
    },
)
VALID_TRADE_MODES = tuple(item["id"] for item in TRADE_MODE_CATALOG)
DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_allowed_origins() -> list[str]:
    configured = os.getenv("ALLOWED_ORIGINS", "")
    origins = [*DEFAULT_ALLOWED_ORIGINS]
    origins.extend(origin.strip() for origin in configured.split(",") if origin.strip())
    return list(dict.fromkeys(origins))

class Settings:
    """
    시스템 전역 설정을 관리하는 클래스.
    환경별 .env 파일에서 설정값을 읽어오며, TRADE_MODE에 따라 API URL과 TR_ID를 자동으로 설정합니다.

    3-Mode 체계:
      - SIMULATED: 증권사 API를 전혀 사용하지 않고, yfinance 시세 기반 가상 체결 (Paper Trading)
      - MOCK:      증권사 모의투자 서버에 실제 API 호출 (KIS 모의투자 등)
      - REAL:      증권사 실전 서버에 실제 API 호출 (진짜 돈)
    """
    # 💡 Spring Boot style Active Profile (local, dev, prod)
    PROFILE = APP_ENV
    IS_LOCAL = PROFILE == "local"
    IS_DEV = PROFILE == "dev"
    IS_PROD = PROFILE == "prod"

    # 브로커 공급자 초기 기본값 (main.py에서 DB 값을 읽어와 덮어씌웁니다)
    BROKER_PROVIDER = "KIS"

    # 3-Mode 트레이딩 모드 기본값 세팅
    TRADE_MODE = "SIMULATED"
    IS_SIMULATED = True
    IS_MOCK = False
    IS_REAL = False

    # API endpoints
    KIS_BASE_URL = ""
    TR_ID_BALANCE = ""
    TR_ID_BUY_OVERSEAS = ""
    TR_ID_SELL_OVERSEAS = ""
    TR_ID_OVERSEAS_BALANCE = ""
    TR_ID_ORDER_HISTORY = ""

    def __init__(self):
        # Telegram Bot Settings (Phase 11)
        self.TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

        # Gemini API Key for AI Sentiment (Phase 21)
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

        cookie_samesite = os.getenv("REFRESH_COOKIE_SAMESITE", "lax").strip().lower()
        if cookie_samesite not in {"lax", "strict", "none"}:
            raise RuntimeError("REFRESH_COOKIE_SAMESITE must be one of: lax, strict, none")

        self.REFRESH_COOKIE_SAMESITE = cookie_samesite
        self.REFRESH_COOKIE_SECURE = _env_bool(
            "REFRESH_COOKIE_SECURE",
            self.IS_PROD or cookie_samesite == "none",
        )
        self.REFRESH_COOKIE_DOMAIN = os.getenv("REFRESH_COOKIE_DOMAIN") or None

        if cookie_samesite == "none" and not self.REFRESH_COOKIE_SECURE:
            raise RuntimeError("SameSite=None refresh cookies require REFRESH_COOKIE_SECURE=true")

        # 1. 초기 생성 시 무조건 안전한 SIMULATED 모드로 하드코딩 셋업
        # (이후 main.py에서 사용자가 화면(어드민)을 통해 저장한 DB 값을 읽어와 덮어씌웁니다)
        self.apply_trade_mode("SIMULATED")

    def apply_trade_mode(self, mode: str):
        """
        TRADE_MODE에 따라 IS_* 플래그와 KIS API 엔드포인트/TR_ID를
        단일 창구에서 일괄 업데이트하는 핵심 함수. (중복 로직 제거)
        """
        if mode not in VALID_TRADE_MODES:
            mode = "SIMULATED"

        self.TRADE_MODE = mode
        self.IS_SIMULATED = self.TRADE_MODE == "SIMULATED"
        self.IS_MOCK = self.TRADE_MODE == "MOCK"
        self.IS_REAL = self.TRADE_MODE == "REAL"

        if self.IS_REAL:
            self.KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"
            self.TR_ID_BALANCE = "TTTC8434R" # 실전 잔고조회
            self.TR_ID_BUY_OVERSEAS = "TTTT1002U" # 해외주식 매수
            self.TR_ID_SELL_OVERSEAS = "TTTT1006U" # 해외주식 매도
            self.TR_ID_OVERSEAS_BALANCE = "CTRP6504R" # 해외 잔고조회 (실전)
            self.TR_ID_ORDER_HISTORY = "JTTT3010R" # 체결내역 (실전)
        else:
            # MOCK과 SIMULATED 모두 모의투자 서버 설정 사용
            self.KIS_BASE_URL = "https://vts-openapi.koreainvestment.com:29443"
            self.TR_ID_BALANCE = "VTTC8434R" # 모의 잔고조회
            self.TR_ID_BUY_OVERSEAS = "VTTT1002U" # 해외주식 매수 (모의)
            self.TR_ID_SELL_OVERSEAS = "VTTT1001U" # 해외주식 매도 (모의)
            self.TR_ID_OVERSEAS_BALANCE = "VTRP6504R" # 해외 잔고조회 (모의)
            self.TR_ID_ORDER_HISTORY = "VTTS3010R" # 체결내역 (모의)

    # Global Constants
    API_TITLE = "StockAuto API"
    VERSION = "2.0.0" # 3-Mode Architecture

    # [Phase 36] 실시간 라이브 트레이딩 적용 마스터 전략 타입 설정 (기본값: regime_switching)
    STRATEGY_TYPE = "regime_switching"

    # [Phase 29] 안전 거래 가드 상수 (Safety & Cost Optimization)
    MAX_HOLDINGS = 5
    MIN_CASH_BALANCE_USD = 200.0
    MIN_SMART_EXIT_PROFIT_RATE = 2.5
    REENTRY_COOLDOWN_MINUTES = 60

    # 로컬 시뮬레이션 계좌는 시작 시점에 원화를 USD로 환전한 것으로 간주합니다.
    SIMULATED_INITIAL_CASH_KRW = 10_000_000.0
    SIMULATED_INITIAL_FX_RATE = 1_350.0

    # [Phase 30] 거래 수수료 및 제비용 상수
    KIS_FEE_RATE = 0.0008         # 0.08% KIS 우대 수수료율
    SEC_FEE_RATE = 0.0000278      # 0.00278% 미국 매도 제비용 (SEC Fee)

settings = Settings()
logger.info(f"[*] Active Profile: {settings.PROFILE.upper()} | Trade Mode: {settings.TRADE_MODE} | Real-Trading Ready: {settings.IS_REAL}")
