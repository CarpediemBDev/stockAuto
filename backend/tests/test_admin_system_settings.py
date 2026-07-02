from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.admin.router import (
    SystemSettingUpdateSchema,
    list_system_settings,
    update_system_setting,
)
from app.core.database import Base
from app.core.system_settings import SETTING_ENABLE_GEMINI_NEWS_ANALYSIS


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_admin_system_settings_list_uses_registered_default(db_session):
    result = list_system_settings(current_user=SimpleNamespace(id=1), db=db_session)

    gemini_setting = next(
        item
        for item in result["settings"]
        if item["key"] == SETTING_ENABLE_GEMINI_NEWS_ANALYSIS
    )
    assert gemini_setting["value"] is False
    assert gemini_setting["default"] is False
    assert gemini_setting["value_type"] == "bool"


def test_admin_system_setting_update_persists_boolean_value(db_session):
    admin_user = SimpleNamespace(id=99)

    updated = update_system_setting(
        key=SETTING_ENABLE_GEMINI_NEWS_ANALYSIS,
        payload=SystemSettingUpdateSchema(value=True),
        current_user=admin_user,
        db=db_session,
    )
    listed = list_system_settings(current_user=admin_user, db=db_session)

    gemini_setting = next(
        item
        for item in listed["settings"]
        if item["key"] == SETTING_ENABLE_GEMINI_NEWS_ANALYSIS
    )
    assert updated["value"] is True
    assert updated["updated_by"] == 99
    assert gemini_setting["value"] is True
    assert gemini_setting["updated_by"] == 99


def test_admin_system_setting_update_rejects_unknown_key(db_session):
    with pytest.raises(HTTPException) as exc_info:
        update_system_setting(
            key="unknown_runtime_flag",
            payload=SystemSettingUpdateSchema(value=True),
            current_user=SimpleNamespace(id=1),
            db=db_session,
        )

    assert exc_info.value.status_code == 400
