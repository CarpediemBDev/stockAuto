import os
from dotenv import load_dotenv

# Determine which environment to load
APP_ENV = os.getenv("APP_ENV", "dev").lower()
env_file = f".env.{APP_ENV}"

# app/core/config.py의 위치 기준, 두 단계 위인 backend/ 루트 디렉터리를 찾아 .env를 로드합니다.
core_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.dirname(core_dir)
backend_dir = os.path.dirname(app_dir)
full_env_path = os.path.join(backend_dir, env_file)

# Load the specific environment file
if os.path.exists(full_env_path):
    load_dotenv(full_env_path, override=True)
    print(f"[*] Configuration loaded from {full_env_path}")
else:
    # Fallback to default .env if specific one not found
    fallback_path = os.path.join(backend_dir, ".env")
    load_dotenv(fallback_path, override=True)
    print(f"[!] {env_file} not found. Falling back to default .env at {fallback_path}")

# 유효한 트레이딩 모드 목록
VALID_TRADE_MODES = ("SIMULATED", "MOCK", "REAL")

class Settings:
    """
    시스템 전역 설정을 관리하는 클래스.
    환경별 .env 파일에서 설정값을 읽어오며, TRADE_MODE에 따라 API URL과 TR_ID를 자동으로 설정합니다.

    3-Mode 체계:
      - SIMULATED: 증권사 API를 전혀 사용하지 않고, yfinance 시세 기반 가상 체결 (Paper Trading)
      - MOCK:      증권사 모의투자 서버에 실제 API 호출 (KIS 모의투자 등)
      - REAL:      증권사 실전 서버에 실제 API 호출 (진짜 돈)
    """
    # 브로커 공급자 (KIS, TOSS 등)
    BROKER_PROVIDER = os.getenv("BROKER_PROVIDER", "KIS").upper()

    # 3-Mode 트레이딩 모드
    _raw_trade_mode = os.getenv("TRADE_MODE", "SIMULATED").upper()

    # 하위 호환: 기존 "VIRTUAL" 값을 "MOCK"으로 자동 변환
    if _raw_trade_mode == "VIRTUAL":
        _raw_trade_mode = "MOCK"

    # 유효하지 않은 모드인 경우 안전하게 SIMULATED로 폴백
    if _raw_trade_mode not in VALID_TRADE_MODES:
        print(f"[!] Invalid TRADE_MODE '{_raw_trade_mode}'. Falling back to SIMULATED.")
        _raw_trade_mode = "SIMULATED"

    TRADE_MODE = _raw_trade_mode
    IS_SIMULATED = TRADE_MODE == "SIMULATED"
    IS_MOCK = TRADE_MODE == "MOCK"
    IS_REAL = TRADE_MODE == "REAL"

    # KIS API Keys (Integrated Names)
    KIS_APP_KEY = os.getenv("KIS_APP_KEY")
    KIS_APP_SECRET = os.getenv("KIS_APP_SECRET")
    KIS_ACCOUNT_NO = os.getenv("KIS_ACCOUNT_NO")

    # Mode-based Dynamic Settings
    if IS_REAL:
        KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"
        TR_ID_BALANCE = "TTTC8434R" # 실전 잔고조회
        TR_ID_BUY_OVERSEAS = "JTTT1002U" # 해외주식 매수
        TR_ID_SELL_OVERSEAS = "JTTT1001U" # 해외주식 매도
        TR_ID_OVERSEAS_BALANCE = "CTRP6504R" # 해외주식 잔고조회 (실전)
        TR_ID_ORDER_HISTORY = "JTTT3010R" # 해외주식 체결내역 (실전)
    else:
        # MOCK과 SIMULATED 모두 모의투자 서버 설정 사용
        # (SIMULATED 모드에서는 실제로 호출되지 않지만, 설정은 유지)
        KIS_BASE_URL = "https://vts-openapi.koreainvestment.com:29443"
        TR_ID_BALANCE = "VTTC8434R" # 모의 잔고조회
        TR_ID_BUY_OVERSEAS = "VTTT1002U" # 해외주식 매수 (모의)
        TR_ID_SELL_OVERSEAS = "VTTT1001U" # 해외주식 매도 (모의)
        TR_ID_OVERSEAS_BALANCE = "VTRP6504R" # 해외주식 잔고조회 (모의)
        TR_ID_ORDER_HISTORY = "VTTS3010R" # 해외주식 체결내역 (모의)

    # Global Constants
    API_TITLE = "StockAuto API"
    VERSION = "2.0.0" # 3-Mode Architecture

settings = Settings()
print(f"[*] Trade Mode: {settings.TRADE_MODE} | Broker: {settings.BROKER_PROVIDER} | Real: {settings.IS_REAL}")
