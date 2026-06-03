from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.admin.router import SettingsUpdateSchema, update_user_settings


class FakeDb:
    def __init__(self):
        self.added = []
        self.commit_count = 0
        self.refreshed = []

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.commit_count += 1

    def refresh(self, item):
        self.refreshed.append(item)


def test_mock_kis_save_is_blocked_when_credentials_are_missing():
    current_settings = SimpleNamespace(
        trade_mode="SIMULATED",
        broker_provider="KIS",
        kis_app_key=None,
        kis_app_secret=None,
        kis_account_no=None,
        telegram_chat_id=None,
        telegram_enabled=False,
    )
    current_user = SimpleNamespace(id=1, settings=current_settings)
    db = FakeDb()
    payload = SettingsUpdateSchema(
        trade_mode="MOCK",
        broker_provider="KIS",
        kis_app_key="",
        kis_app_secret="",
        kis_account_no="",
    )

    with pytest.raises(HTTPException) as exc_info:
        update_user_settings(payload=payload, current_user=current_user, db=db)

    assert exc_info.value.status_code == 400
    assert "KIS" in exc_info.value.detail
    assert db.commit_count == 0
    assert db.added == []
    assert current_settings.trade_mode == "SIMULATED"


def test_simulated_settings_save_does_not_require_kis_validation():
    current_settings = SimpleNamespace(
        trade_mode="MOCK",
        broker_provider="KIS",
        kis_app_key="old",
        kis_app_secret="old",
        kis_account_no="old",
        telegram_chat_id=None,
        telegram_enabled=False,
    )
    current_user = SimpleNamespace(id=1, settings=current_settings)
    db = FakeDb()
    payload = SettingsUpdateSchema(
        trade_mode="SIMULATED",
        broker_provider="KIS",
        kis_app_key="",
        kis_app_secret="",
        kis_account_no="",
        telegram_chat_id="chat",
        telegram_enabled=True,
    )

    result = update_user_settings(payload=payload, current_user=current_user, db=db)

    assert result is current_settings
    assert current_settings.trade_mode == "SIMULATED"
    assert current_settings.telegram_chat_id == "chat"
    assert current_settings.telegram_enabled is True
    assert db.commit_count == 1
    assert db.refreshed == [current_settings]
