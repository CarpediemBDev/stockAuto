from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from app.admin import router as admin_router
from app.admin.router import (
    KisCredentialsSchema,
    SettingsUpdateSchema,
    get_user_settings,
    save_kis_credentials,
    update_user_settings,
)
from app.core.credentials import ENCRYPTED_PREFIX, decrypt_credential


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


def make_settings(**overrides):
    defaults = {
        "id": 10,
        "user_id": 1,
        "trade_mode": "SIMULATED",
        "broker_provider": "KIS",
        "kis_app_key": None,
        "kis_app_secret": None,
        "kis_account_no": None,
        "kis_verification_status": "unverified",
        "kis_verified_trade_mode": None,
        "kis_verified_at": None,
        "telegram_chat_id": None,
        "telegram_enabled": False,
        "is_running": False,
        "is_real_enabled": False,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def assert_safe_settings_response(response):
    assert "kis_app_key" not in response
    assert "kis_app_secret" not in response
    assert "kis_account_no" not in response


def test_mock_settings_save_is_blocked_when_credentials_are_missing():
    current_settings = make_settings()
    current_user = SimpleNamespace(id=1, settings=current_settings)
    db = FakeDb()
    payload = SettingsUpdateSchema(trade_mode="MOCK", broker_provider="KIS")

    with pytest.raises(HTTPException) as exc_info:
        update_user_settings(payload=payload, current_user=current_user, db=db)

    assert exc_info.value.status_code == 400
    assert "KIS" in exc_info.value.detail
    assert db.commit_count == 0
    assert db.added == []
    assert current_settings.trade_mode == "SIMULATED"


def test_simulated_settings_save_preserves_kis_credentials_without_validation():
    current_settings = make_settings(
        trade_mode="MOCK",
        kis_app_key="old-key",
        kis_app_secret="old-secret",
        kis_account_no="87654321-01",
        kis_verification_status="verified",
        kis_verified_trade_mode="MOCK",
    )
    current_user = SimpleNamespace(id=1, settings=current_settings)
    db = FakeDb()
    payload = SettingsUpdateSchema(
        trade_mode="SIMULATED",
        broker_provider="KIS",
        telegram_chat_id="chat",
        telegram_enabled=True,
    )

    result = update_user_settings(payload=payload, current_user=current_user, db=db)

    assert current_settings.trade_mode == "SIMULATED"
    assert current_settings.kis_app_key == "old-key"
    assert current_settings.kis_app_secret == "old-secret"
    assert current_settings.kis_account_no == "87654321-01"
    assert current_settings.telegram_chat_id == "chat"
    assert current_settings.telegram_enabled is True
    assert db.commit_count == 1
    assert db.refreshed == [current_settings]
    assert_safe_settings_response(result)


def test_get_user_settings_returns_only_safe_kis_metadata():
    current_settings = make_settings(
        kis_app_key="valid-app-key",
        kis_app_secret="valid-secret",
        kis_account_no="87654321-01",
        kis_verification_status="verified",
        kis_verified_trade_mode="MOCK",
    )
    current_user = SimpleNamespace(id=1, settings=current_settings)

    result = get_user_settings(current_user=current_user, db=FakeDb())

    assert_safe_settings_response(result)
    assert result["has_kis_credentials"] is True
    assert result["kis_account_no_masked"] == "8765...-01"
    assert result["kis_verification_status"] == "verified"


def test_save_kis_credentials_encrypts_and_returns_safe_response(monkeypatch):
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("KIS_CREDENTIAL_MASTER_KEY", key)
    monkeypatch.setattr(admin_router, "_verify_kis_values", lambda *args: (True, "ok"))

    current_settings = make_settings()
    current_user = SimpleNamespace(id=1, settings=current_settings)
    db = FakeDb()
    payload = KisCredentialsSchema(
        trade_mode="MOCK",
        kis_app_key="valid-app-key",
        kis_app_secret="valid-secret",
        kis_account_no="87654321-01",
    )

    result = save_kis_credentials(payload=payload, current_user=current_user, db=db)

    assert current_settings.kis_app_key.startswith(ENCRYPTED_PREFIX)
    assert current_settings.kis_app_secret.startswith(ENCRYPTED_PREFIX)
    assert current_settings.kis_account_no.startswith(ENCRYPTED_PREFIX)
    assert "valid-secret" not in current_settings.kis_app_secret
    assert decrypt_credential(current_settings.kis_app_secret) == "valid-secret"
    assert current_settings.kis_verification_status == "verified"
    assert current_settings.kis_verified_trade_mode == "MOCK"
    assert current_settings.kis_verified_at is not None
    assert db.commit_count == 1
    assert db.refreshed == [current_settings]
    assert result["success"] is True
    assert_safe_settings_response(result["settings"])
    assert result["settings"]["has_kis_credentials"] is True


def test_save_kis_credentials_requires_master_key(monkeypatch):
    monkeypatch.delenv("KIS_CREDENTIAL_MASTER_KEY", raising=False)
    monkeypatch.setattr(admin_router, "_verify_kis_values", lambda *args: (True, "ok"))

    current_settings = make_settings()
    current_user = SimpleNamespace(id=1, settings=current_settings)
    db = FakeDb()
    payload = KisCredentialsSchema(
        trade_mode="MOCK",
        kis_app_key="valid-app-key",
        kis_app_secret="valid-secret",
        kis_account_no="87654321-01",
    )

    with pytest.raises(HTTPException) as exc_info:
        save_kis_credentials(payload=payload, current_user=current_user, db=db)

    assert exc_info.value.status_code == 500
    assert db.commit_count == 0


def test_verified_mock_settings_can_be_saved_without_raw_kis_payload():
    current_settings = make_settings(
        trade_mode="SIMULATED",
        kis_app_key="valid-app-key",
        kis_app_secret="valid-secret",
        kis_account_no="87654321-01",
        kis_verification_status="verified",
        kis_verified_trade_mode="MOCK",
    )
    current_user = SimpleNamespace(id=1, settings=current_settings)
    db = FakeDb()
    payload = SettingsUpdateSchema(trade_mode="MOCK", broker_provider="KIS")

    result = update_user_settings(payload=payload, current_user=current_user, db=db)

    assert current_settings.trade_mode == "MOCK"
    assert current_settings.kis_app_secret == "valid-secret"
    assert db.commit_count == 1
    assert_safe_settings_response(result)
