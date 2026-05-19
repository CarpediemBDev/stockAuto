from app.core.config import settings
from app.bot.kis_broker import KISBroker
from app.bot.simulated_broker import LocalSimulatedBroker
from app.bot.base_broker import BaseBroker

def get_broker_client() -> BaseBroker:
    """
    설정 파일(.env)의 BROKER_PROVIDER 값에 따라 알맞은 증권사 객체를 조립해 주는 팩토리 함수.
    KIS, MIRAE, TOSS 등이 추가되면 이 팩토리 함수에서 수용하여 알맞은 클라이언트를 생성합니다.
    """
    provider = settings.BROKER_PROVIDER.upper() if settings.BROKER_PROVIDER else "KIS"
    
    # KIS API 연동을 위한 키 설정 확인
    has_kis_keys = False
    if settings.KIS_APP_KEY and settings.KIS_APP_KEY not in ["YOUR_APP_KEY_HERE", "your_virtual_app_key_here"]:
        has_kis_keys = True

    if provider == "KIS" and has_kis_keys:
        return KISBroker()
    else:
        # 지정된 브로커가 없거나 API 키가 미등록 상태이면 로컬 가상 모의투자 브로커 반환
        return LocalSimulatedBroker()
