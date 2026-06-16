import logging
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.core import models
from app.scanner.data_provider import fetch_ticker_info_sync

logger = logging.getLogger(__name__)

class Translator:
    _instance = None
    _cache = {}
    _strategy_cache = {}

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Translator, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    @classmethod
    def load_cache(cls):
        """DB의 종목·전략 번역을 메모리에 캐싱하고 레거시 데이터를 정리합니다."""
        db: Session = SessionLocal()
        try:
            # 1. DB 주식 번역 조회 및 캐시 적재
            translations = db.query(models.StockTranslation).all()
            cls._cache = {t.ticker.upper().strip(): t.name_ko for t in translations}
            logger.info(f"Successfully loaded {len(cls._cache)} stock translations into memory cache.")
            print(f"[i18n] Loaded {len(cls._cache)} stock translations from DB into memory cache.")

            # 2. DB 내 STRATEGY: 레거시 데이터 자동 정리(Clean-up)
            try:
                deleted_count = db.query(models.StockTranslation).filter(
                    models.StockTranslation.ticker.like("STRATEGY:%")
                ).delete(synchronize_session=False)
                if deleted_count > 0:
                    db.commit()
                    logger.info(f"Cleaned up {deleted_count} legacy strategy translations from stock_translations table.")
                    print(f"[i18n] Cleaned up {deleted_count} legacy strategy translations from DB.")
            except Exception as db_err:
                logger.error(f"Failed to clean up legacy strategy translations from DB: {db_err}")
                print(f"[i18n] Warning: Failed to clean up legacy strategy DB records: {db_err}")
            
            # 3. DB strategies 테이블에서 전략 번역 로드 (SSOT 단일화)
            try:
                db_strategies = db.query(models.Strategy).all()
                cls._strategy_cache = {
                    s.strategy_type: {
                        "ko": s.name_ko,
                        "en": s.name_en or s.strategy_type
                    }
                    for s in db_strategies
                }
                logger.info(f"Successfully loaded {len(cls._strategy_cache)} strategy translations from DB strategies table.")
                print(f"[i18n] Loaded {len(cls._strategy_cache)} strategy translations from DB strategies table.")
            except Exception as db_strategy_err:
                logger.error(f"Failed to load strategies from DB: {db_strategy_err}")
                print(f"[i18n] Error loading strategies from DB: {db_strategy_err}")

        except Exception as e:
            logger.error(f"Failed to initialize translation cache: {e}")
            print(f"[i18n] Error loading translation cache: {e}")
        finally:
            db.close()

    @classmethod
    def translate_strategy(cls, strategy_type: str, locale: str = "ko") -> str:
        """strategies 테이블에서 캐싱한 전략 한글/영문 매핑을 반환합니다."""
        if not strategy_type:
            return "미지정 전략" if locale == "ko" else "Unspecified Strategy"

        strategy_clean = strategy_type.lower().strip()
        if strategy_clean in cls._strategy_cache:
            strategy_info = cls._strategy_cache[strategy_clean]
            return strategy_info.get(locale, strategy_type)

        # Fallback: 캐시에 매핑이 없으면 기본 이름 포맷 또는 원본 반환
        return f"단일 전략 ({strategy_type})" if locale == "ko" else strategy_type

    @classmethod
    def translate(cls, ticker: str, default_name: str = None, db = None) -> str:
        """
        [메모리 캐시 -> 로컬 DB -> AI 자동 번역 및 자가학습 캐싱]으로 연결되는
        초고성능 전역 주식 한글화 번역 함수입니다.
        """
        if not ticker:
            return ""
            
        if "_" in ticker:
            ticker = ticker.split("_")[-1]
        ticker_clean = ticker.upper().strip()
        
        # 1. 1단계: 메모리 캐시 조회 (0ms 초고속 서빙)
        if ticker_clean in cls._cache:
            return cls._cache[ticker_clean]
            
        # 2. 2단계: 로컬 DB 조회 및 메모리 캐시 적재
        is_local_session = False
        if db is None:
            db = SessionLocal()
            is_local_session = True
            
        try:
            db_trans = db.query(models.StockTranslation).filter(models.StockTranslation.ticker == ticker_clean).first()
            if db_trans:
                # DB에 번역이 존재하면 메모리 캐시에 동기화하고 반환
                cls._cache[ticker_clean] = db_trans.name_ko
                return db_trans.name_ko
                
            # 3. 3단계: 로컬에 아예 존재하지 않는 신규 종목의 경우 -> AI 실시간 번역 및 자가학습 가동!
            info = fetch_ticker_info_sync(ticker_clean)
            
            # 실제 나스닥 상장 주식이 아닌 가짜 티커인 경우 Fallback
            if not info or "symbol" not in info or not info.get("symbol"):
                return default_name or ticker_clean
                
            english_name = info.get("shortName", "") or info.get("longName", "") or ticker_clean
            
            # AI 실시간 번역 수행
            translated_ko = cls.auto_translate_name(english_name)
            
            # 번역된 결과를 마스터 DB에 영구 저장 (자가학습)
            new_trans = models.StockTranslation(ticker=ticker_clean, name_ko=translated_ko)
            db.add(new_trans)
            db.commit()
            
            # 메모리 핫 캐시 동기화
            cls._cache[ticker_clean] = translated_ko
            return translated_ko
            
        except Exception as e:
            # 실패 시 다운을 막기 위한 안전장치
            logger.error(f"Error translating/auto-learning ticker '{ticker_clean}': {e}")
            print(f"[i18n] Error translating/auto-learning ticker '{ticker_clean}': {e}")
            return default_name or ticker_clean
        finally:
            if is_local_session:
                db.close()

    @classmethod
    def auto_translate_name(cls, english_name: str) -> str:
        """영문 법인명을 정제한 후 무료 구글 번역 OpenAPI를 통해 깔끔한 한글 주식명으로 자동 실시간 번역합니다."""
        if not english_name:
            return ""
            
        # 1. 흔히 쓰이는 영문 주식명 접미사 제거 (예: Apple Inc. -> Apple)하여 번역 퀄리티 극대화
        cleaned = english_name
        suffixes = [
            r",\s*Inc\b\.?", r"\s*Inc\b\.?", 
            r",\s*Corp\b\.?", r"\s*Corp\b\.?", r"\s*Corporation\b",
            r",\s*Co\b\.?", r"\s*Company\b",
            r",\s*Ltd\b\.?", r"\s*Limited\b",
            r",\s*plc\b\.?", r"\s*PLC\b",
            r",\s*Group\b", r"\s*Holdings?\b"
        ]
        import re
        for suffix in suffixes:
            cleaned = re.sub(suffix, "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip()

        if not cleaned:
            return english_name

        # 2. 구글 번역 무료 OpenAPI 호출 (현대식 고성능 httpx 클라이언트 가동!)
        import urllib.parse
        import httpx
        try:
            url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ko&dt=t&q={urllib.parse.quote(cleaned)}"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            with httpx.Client(timeout=3.0) as client:
                response = client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if data and len(data) > 0 and data[0] and len(data[0]) > 0:
                        translated = data[0][0][0]
                        return translated.strip()
        except Exception as e:
            logger.error(f"Automatic translation failed for '{english_name}': {e}")
            print(f"[i18n] Translation failed for {english_name}: {e}")
        
        return cleaned

    @classmethod
    def update_cache_item(cls, ticker: str, name_ko: str):
        """실시간 종목 추가/수정 시 즉각적으로 메모리 캐시를 동적 싱크(동기화)합니다."""
        ticker_clean = ticker.upper().strip()
        cls._cache[ticker_clean] = name_ko
        logger.info(f"Dynamically updated cache translation: {ticker_clean} -> {name_ko}")
