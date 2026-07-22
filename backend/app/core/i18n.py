import json
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

class I18n:
    _instance = None
    _locales: Dict[str, Dict[str, Any]] = {}

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(I18n, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    @classmethod
    def load_locales(cls):
        """프로젝트 최상단의 locales 디렉토리에서 JSON 파일들을 읽어 캐싱합니다."""
        # backend/app/core/i18n.py -> backend/app/core -> backend/app -> backend -> root/locales
        base_dir = Path(__file__).resolve().parent.parent.parent.parent
        locales_dir = base_dir / "locales"

        if not locales_dir.exists():
            logger.warning(f"[i18n] Locales directory not found at {locales_dir}")
            return

        cls._locales = {}
        for file_path in locales_dir.glob("*.json"):
            lang = file_path.stem
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    cls._locales[lang] = json.load(f)
                logger.info(f"[i18n] Loaded {lang} translations ({len(cls._locales[lang])} root keys)")
            except Exception as e:
                logger.error(f"[i18n] Failed to load {file_path.name}: {e}")

    @classmethod
    def _get_nested(cls, d: dict, keys: list, default: str):
        for key in keys:
            if isinstance(d, dict) and key in d:
                d = d[key]
            else:
                return default
        return d

    @classmethod
    def get_msg(cls, lang: str, key: str, default: str | None = None, **kwargs) -> str:
        """
        주어진 언어와 키에 해당하는 메시지를 포맷팅하여 반환합니다.
        예: get_msg('ko', 'telegram.order_success', ticker='AAPL')

        default는 이름 있는 매개변수다. **kwargs로 흘러들어가면 포맷 인자로 오해되어
        키를 못 찾았을 때 'ui.order_resolved' 같은 날 키 문자열이 그대로 사용자에게
        전달된다(실제로 발생했던 결함). 요청 언어에 키가 없으면 ko로 한 번 더 찾아보고,
        그래도 없으면 default를 쓰며, default도 없을 때만 키 문자열로 강등한다.
        """
        if not lang or lang not in cls._locales:
            lang = "ko"

        keys = key.split(".")
        _MISSING = object()
        template = cls._get_nested(cls._locales.get(lang, {}), keys, default=_MISSING)

        if template is _MISSING and lang != "ko":
            # 번역이 아직 없는 언어는 한국어로 강등한다 (키 노출보다 낫다).
            template = cls._get_nested(cls._locales.get("ko", {}), keys, default=_MISSING)

        if template is _MISSING:
            if default is None:
                logger.warning(f"[i18n] Missing key '{key}' for lang '{lang}' and no default given.")
                template = key
            else:
                template = default

        if isinstance(template, str) and kwargs:
            try:
                return template.format(**kwargs)
            except Exception as e:
                logger.error(f"[i18n] Formatting error for key '{key}' with args {kwargs}: {e}")
                return template
        return str(template)


def resolve_user_language(db, user_id: int) -> str:
    """사용자의 UserSettings.language를 조회한다. 알림 언어 결정의 SSOT.

    설정이 없거나 조회가 실패해도 알림 자체는 나가야 하므로 항상 'ko'로 폴백한다.
    """
    try:
        from app.core.models import UserSettings

        language = (
            db.query(UserSettings.language)
            .filter(UserSettings.user_id == user_id)
            .scalar()
        )
        return language or "ko"
    except Exception as e:
        logger.warning(f"[i18n] Language lookup failed for user={user_id}, falling back to ko: {e}")
        return "ko"

# 서버 시작 시 로드
I18n.load_locales()
