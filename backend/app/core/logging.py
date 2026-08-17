import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, "logs")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "stockauto.log")
SECURITY_LOG_FILE = os.path.join(LOG_DIR, "security.log")

# Windows 환경 및 특정 터미널에서 이모지(⚠️) 등 유니코드 문자 출력 시 CP949 인코딩 에러 방지
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

file_handler = RotatingFileHandler(LOG_FILE, maxBytes=10_000_000, backupCount=5, encoding="utf-8")
file_handler.setFormatter(formatter)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)

logger = logging.getLogger("stockauto")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)

# Prevent duplicate logs if imported multiple times
logger.propagate = False


# 보안 이벤트는 전용 파일에 따로 남긴다. 봇이 stockauto.log에 하루 수만 줄을 쓰기 때문에
# 같은 파일에 두면 회전(10MB × 5개)으로 며칠 만에 밀려나 사라진다. 보안 이벤트는 빈도가
# 낮아 같은 용량으로도 훨씬 오래 보존된다.
# 한 줄에 JSON 한 건을 남기는 이유는 나중에 집계·수집기 연동 시 파싱이 되게 하려는 것이다.
security_file_handler = RotatingFileHandler(
    SECURITY_LOG_FILE, maxBytes=5_000_000, backupCount=10, encoding="utf-8"
)
security_file_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))

security_logger = logging.getLogger("stockauto.security")
security_logger.setLevel(logging.INFO)
security_logger.addHandler(security_file_handler)
# stockauto 로거로 전파시키지 않는다(중복 기록 방지). 운영 디버깅용 맥락은 호출부가
# 기존 logger로 남기는 사람이 읽는 한 줄이 담당한다.
security_logger.propagate = False


def log_security_event(event_type: str, **fields) -> None:
    """보안 이벤트를 security.log에 JSON 한 줄로 남긴다.

    값이 None인 필드는 제외한다(미연동·미확인 항목이 null로 잡음이 되지 않게).
    직렬화 불가 값(datetime 등)은 문자열로 떨어뜨린다.
    """
    payload = {"event": event_type}
    payload.update({key: value for key, value in fields.items() if value is not None})
    try:
        security_logger.info(json.dumps(payload, ensure_ascii=False, default=str))
    except Exception:
        # 보안 기록 실패가 호출자(인증 트랜잭션)를 깨뜨리지 않게 한다.
        logger.exception("[Security] Failed to write security event log: %s", event_type)
