import pytest
from app.translations.translator import Translator
from app.core.database import SessionLocal
from app.core import models

def test_strategy_translation_values():
    # Load cache (should load YAML file automatically)
    Translator.load_cache()

    # Test existing strategy translations in ko and en
    assert Translator.translate_strategy("regime_switching", "ko") == "마스터 레짐스위칭"
    assert Translator.translate_strategy("regime_switching", "en") == "Regime Switching"

    assert Translator.translate_strategy("episodic_pivot", "ko") == "에피소딕 피벗"
    assert Translator.translate_strategy("episodic_pivot", "en") == "Episodic Pivot"

    assert Translator.translate_strategy("senior_simple", "ko") == "시니어 단순화"
    assert Translator.translate_strategy("senior_simple", "en") == "Strategy S"

    # Test lowercase conversion / stripping robustness
    assert Translator.translate_strategy("   REGIME_SWITCHING   ", "ko") == "마스터 레짐스위칭"


def test_strategy_translation_fallbacks():
    # Test missing strategy key fallbacks
    assert Translator.translate_strategy("non_existent_strategy_abc", "ko") == "단일 전략 (non_existent_strategy_abc)"
    assert Translator.translate_strategy("non_existent_strategy_abc", "en") == "non_existent_strategy_abc"

    # Test None/empty key fallbacks
    assert Translator.translate_strategy("", "ko") == "미지정 전략"
    assert Translator.translate_strategy(None, "en") == "Unspecified Strategy"


def test_legacy_strategy_database_cleanup():
    # Insert legacy STRATEGY: dummy record into the real test DB to check cleanup
    db = SessionLocal()
    dummy_ticker = "STRATEGY:TEST_DUMMY_CLEANUP_KEY"
    try:
        # Clean up any existing left-over first
        existing = db.query(models.StockTranslation).filter(models.StockTranslation.ticker == dummy_ticker).first()
        if existing:
            db.delete(existing)
            db.commit()

        # Insert new dummy legacy record
        legacy_record = models.StockTranslation(ticker=dummy_ticker, name_ko="임시 테스트 전략명")
        db.add(legacy_record)
        db.commit()

        # Verify it was inserted
        inserted = db.query(models.StockTranslation).filter(models.StockTranslation.ticker == dummy_ticker).first()
        assert inserted is not None

        # Call load_cache() which executes the DB cleanup routine
        Translator.load_cache()

        # Verify it has been deleted
        cleaned = db.query(models.StockTranslation).filter(models.StockTranslation.ticker == dummy_ticker).first()
        assert cleaned is None

    finally:
        db.close()
