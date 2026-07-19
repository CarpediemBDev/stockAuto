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
    def get_msg(cls, lang: str, key: str, **kwargs) -> str:
        """
        주어진 언어와 키에 해당하는 메시지를 포맷팅하여 반환합니다.
        예: get_msg('ko', 'telegram.order_success', ticker='AAPL')
        """
        if not lang or lang not in cls._locales:
            lang = "ko"

        keys = key.split(".")
        template = cls._get_nested(cls._locales.get(lang, {}), keys, default=key)

        if isinstance(template, str) and kwargs:
            try:
                return template.format(**kwargs)
            except Exception as e:
                logger.error(f"[i18n] Formatting error for key '{key}' with args {kwargs}: {e}")
                return template
        return str(template)

# 서버 시작 시 로드
I18n.load_locales()
