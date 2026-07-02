from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.models import SystemSetting
import app.core.system_settings as system_settings


def make_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(autocommit=False, autoflush=False, bind=engine)


def test_system_setting_defaults_to_gemini_disabled(monkeypatch):
    engine, session_factory = make_session_factory()
    monkeypatch.setattr(system_settings, "SessionLocal", session_factory)
    system_settings.clear_system_settings_cache()

    try:
        assert (
            system_settings.is_system_setting_enabled(
                system_settings.SETTING_ENABLE_GEMINI_NEWS_ANALYSIS
            )
            is False
        )
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        system_settings.clear_system_settings_cache()


def test_system_setting_reads_boolean_row(monkeypatch):
    engine, session_factory = make_session_factory()
    monkeypatch.setattr(system_settings, "SessionLocal", session_factory)
    system_settings.clear_system_settings_cache()

    db = session_factory()
    try:
        db.add(
            SystemSetting(
                key=system_settings.SETTING_ENABLE_GEMINI_NEWS_ANALYSIS,
                value="true",
                value_type="bool",
                category="ai",
                description="test",
            )
        )
        db.commit()
    finally:
        db.close()

    try:
        assert (
            system_settings.is_system_setting_enabled(
                system_settings.SETTING_ENABLE_GEMINI_NEWS_ANALYSIS
            )
            is True
        )
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        system_settings.clear_system_settings_cache()


def test_system_setting_invalid_bool_falls_back_to_safe_default(monkeypatch):
    engine, session_factory = make_session_factory()
    monkeypatch.setattr(system_settings, "SessionLocal", session_factory)
    system_settings.clear_system_settings_cache()

    db = session_factory()
    try:
        db.add(
            SystemSetting(
                key=system_settings.SETTING_ENABLE_GEMINI_NEWS_ANALYSIS,
                value="definitely",
                value_type="bool",
                category="ai",
                description="test",
            )
        )
        db.commit()
    finally:
        db.close()

    try:
        assert (
            system_settings.is_system_setting_enabled(
                system_settings.SETTING_ENABLE_GEMINI_NEWS_ANALYSIS
            )
            is False
        )
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        system_settings.clear_system_settings_cache()
