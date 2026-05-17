import logging
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.core import models

logger = logging.getLogger(__name__)

class Translator:
    _instance = None
    _cache = {}

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Translator, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    @classmethod
    def load_cache(cls):
        """DB에서 한글 매핑 사전을 조회하여 메모리에 초고속 캐싱합니다."""
        db: Session = SessionLocal()
        try:
            # 1. DB 조회
            translations = db.query(models.StockTranslation).all()
            
            # 2. 메모리 캐시 적재
            cls._cache = {t.ticker.upper().strip(): t.name_ko for t in translations}
            logger.info(f"Successfully loaded {len(cls._cache)} stock translations into memory cache.")
            print(f"[i18n] Loaded {len(cls._cache)} stock translations from DB into memory cache.")
            
        except Exception as e:
            logger.error(f"Failed to initialize translation cache: {e}")
            print(f"[i18n] Error loading translation cache: {e}")
        finally:
            db.close()

    @classmethod
    def translate(cls, ticker: str, default_name: str = None) -> str:
        """메모리 캐시에서 번역을 찾고, 사전에 존재하지 않으면 인풋받은 영문/티커명을 뱉는 Fallback을 구현합니다."""
        if not ticker:
            return ""
            
        ticker_clean = ticker.upper().strip()
        
        # 1. 메모리 캐시에 매핑이 있을 때 한글 리턴
        if ticker_clean in cls._cache:
            return cls._cache[ticker_clean]
            
        # 2. 사전에 없을 때 영어 원천명 또는 티커명으로 안전 Fallback
        return default_name or ticker_clean

    @classmethod
    def update_cache_item(cls, ticker: str, name_ko: str):
        """실시간 종목 추가/수정 시 즉각적으로 메모리 캐시를 동적 싱크(동기화)합니다."""
        ticker_clean = ticker.upper().strip()
        cls._cache[ticker_clean] = name_ko
        logger.info(f"Dynamically updated cache translation: {ticker_clean} -> {name_ko}")
