from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from app.admin import router as admin_router
from app.admin.router import (
    CredentialSchema,
    SettingsUpdateSchema,
    get_user_settings,
    save_credential,
    update_user_settings,
)
from app.core.credentials import ENCRYPTED_PREFIX, decrypt_credential
from app.core.config import TRADE_MODE_CATALOG, settings as app_settings
from app.core.models import BrokerCredential

class FakeQuery:
    def __init__(self, items=None):
        self.items = items or []
        
    def filter_by(self, **kwargs):
        filtered = []
        for item in self.items:
            match = True
            for k, v in kwargs.items():
                if getattr(item, k, None) != v:
                    match = False
                    break
            if match:
                filtered.append(item)
        return FakeQuery(filtered)

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.items[0] if self.items else None

    def all(self):
        return self.items

class FakeDb:
    def __init__(self, creds=None, settings=None):
        self.added = []
        self.commit_count = 0
        self.refreshed = []
        self.creds = creds or []
        self.settings = settings or []

    def add(self, item):
        self.added.append(item)
        if item.__class__.__name__ == "BrokerCredential" or isinstance(item, BrokerCredential):
            self.creds.append(item)

    def delete(self, item):
        if item in self.creds:
            self.creds.remove(item)

    def query(self, model):
        name = getattr(model, "__name__", "")
        if name == "BrokerCredential" or model is BrokerCredential:
            return FakeQuery(self.creds)
        if name == "UserSettings" or model is getattr(self, "settings_model", None):
            return FakeQuery(self.settings)
        return FakeQuery()

    def commit(self):
        self.commit_count += 1

    def refresh(self, item):
        self.refreshed.append(item)
        name = getattr(item, "__class__", None).__name__ if getattr(item, "__class__", None) else ""
        if name == "UserSettings" or isinstance(item, SimpleNamespace):
            item.credentials = list(self.creds)


def make_settings(**overrides):
    defaults = {
        "id": 10,
        "user_id": 1,
        "trade_mode": "SIMULATED",
        "broker_provider": "KIS",
        "telegram_chat_id": None,
        "telegram_enabled": False,
        "is_running": False,
        "credentials": []
    }

    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_cred(user_id=1, broker_name="KIS", **overrides):
    defaults = {
        "user_id": user_id,
        "broker_name": broker_name,
        "app_key": None,
        "app_secret": None,
        "account_no": None,
        "verification_status": "unverified",
        "verified_trade_mode": None,
        "verified_at": None,
    }
    defaults.update(overrides)
    return BrokerCredential(**defaults)


def assert_safe_settings_response(response):
    assert "kis_app_key" not in response
    assert "kis_app_secret" not in response
    assert "kis_account_no" not in response
    assert "toss_app_key" not in response
    # also check inside credentials list
    for cred in response.get("credentials", []):
        assert "app_key" not in cred
        assert "app_secret" not in cred
        assert "account_no" not in cred


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
    cred = make_cred(
        app_key="old-key",
        app_secret="old-secret",
        account_no="87654321-01",
        verification_status="verified",
        verified_trade_mode="MOCK",
    )
    current_settings = make_settings(
        trade_mode="MOCK",
        credentials=[cred]
    )
    current_user = SimpleNamespace(id=1, settings=current_settings)
    db = FakeDb(creds=[cred])
    
    payload = SettingsUpdateSchema(
        trade_mode="SIMULATED",
        broker_provider="KIS",
        telegram_chat_id="chat",
        telegram_enabled=True,
    )

    result = update_user_settings(payload=payload, current_user=current_user, db=db)

    assert current_settings.trade_mode == "SIMULATED"
    assert current_settings.telegram_chat_id == "chat"
    assert current_settings.telegram_enabled is True
    assert db.commit_count == 1
    assert db.refreshed == [current_settings]
    assert_safe_settings_response(result)


def test_get_user_settings_returns_only_safe_metadata():
    cred = make_cred(
        app_key="valid-app-key",
        app_secret="valid-secret",
        account_no="87654321-01",
        verification_status="verified",
        verified_trade_mode="MOCK",
    )
    current_settings = make_settings(credentials=[cred])
    current_user = SimpleNamespace(id=1, settings=current_settings)

    result = get_user_settings(current_user=current_user, db=FakeDb())

    assert_safe_settings_response(result)
    assert len(result["credentials"]) == 1
    c_meta = result["credentials"][0]
    assert c_meta["has_credentials"] is True
    assert c_meta["account_no_masked"] == "8765...-01"
    assert c_meta["verification_status"] == "verified"
    assert result["available_trade_modes"] == list(TRADE_MODE_CATALOG)
    assert {broker["id"] for broker in result["available_brokers"]} == {"KIS", "TOSS"}
    assert result["simulated_initial_cash_krw"] == app_settings.SIMULATED_INITIAL_CASH_KRW


def test_settings_save_rejects_unregistered_broker():
    current_settings = make_settings()
    current_user = SimpleNamespace(id=1, settings=current_settings)

    with pytest.raises(HTTPException) as exc_info:
        update_user_settings(
            payload=SettingsUpdateSchema(
                trade_mode="MOCK",
                broker_provider="UNKNOWN",
            ),
            current_user=current_user,
            db=FakeDb(),
        )

    assert exc_info.value.status_code == 400
    assert "지원하지 않는 증권사" in exc_info.value.detail


def test_save_credential_encrypts_and_returns_safe_response(monkeypatch):
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("KIS_CREDENTIAL_MASTER_KEY", key)
    monkeypatch.setattr(admin_router, "_verify_credential_values", lambda *args: (True, "ok"))

    current_settings = make_settings()
    current_user = SimpleNamespace(id=1, settings=current_settings)
    db = FakeDb(settings=[current_settings])
    payload = CredentialSchema(
        trade_mode="MOCK",
        broker_name="KIS",
        app_key="valid-app-key",
        app_secret="valid-secret",
        account_no="87654321-01",
    )

    result = save_credential(payload=payload, current_user=current_user, db=db)

    cred = db.creds[0]
    assert cred.app_key.startswith(ENCRYPTED_PREFIX)
    assert cred.app_secret.startswith(ENCRYPTED_PREFIX)
    assert cred.account_no.startswith(ENCRYPTED_PREFIX)
    assert "valid-secret" not in cred.app_secret
    assert decrypt_credential(cred.app_secret) == "valid-secret"
    assert cred.verification_status == "verified"
    assert cred.verified_trade_mode == "MOCK"
    assert cred.verified_at is not None
    assert db.commit_count == 1
    
    assert result["success"] is True
    assert_safe_settings_response(result["settings"])
    assert result["settings"]["credentials"][0]["has_credentials"] is True


def test_broker_factory_simulated_mode_ignores_null_provider():
    from app.bot.broker_factory import get_broker_client
    from app.bot.simulated_broker import LocalSimulatedBroker
    
    # broker_provider가 None이거나 비어있더라도 SIMULATED 모드이면 가상 브로커를 리턴해야 함
    settings = make_settings(trade_mode="SIMULATED", broker_provider=None)
    broker = get_broker_client(settings)
    assert isinstance(broker, LocalSimulatedBroker)


def test_broker_factory_mock_real_mode_raises_value_error_if_provider_is_null():
    from app.bot.broker_factory import get_broker_client
    
    # MOCK/REAL 모드인데 broker_provider가 None이면 ValueError가 나야 함
    settings_mock = make_settings(trade_mode="MOCK", broker_provider=None)
    with pytest.raises(ValueError) as exc_info:
        get_broker_client(settings_mock)
    assert "broker_provider" in str(exc_info.value)

    settings_real = make_settings(trade_mode="REAL", broker_provider=None)
    with pytest.raises(ValueError) as exc_info:
        get_broker_client(settings_real)
    assert "broker_provider" in str(exc_info.value)
