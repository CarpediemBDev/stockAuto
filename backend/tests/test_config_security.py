import pytest

from app.core import config


def test_production_origins_do_not_implicitly_include_localhost(monkeypatch):
    monkeypatch.setattr(config, "APP_ENV", "prod")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://stock.example.com")

    assert config.get_allowed_origins() == ["https://stock.example.com"]


def test_production_rejects_insecure_refresh_cookie(monkeypatch):
    monkeypatch.setattr(config.Settings, "IS_PROD", True)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("REFRESH_COOKIE_SECURE", "false")

    with pytest.raises(RuntimeError, match="Production refresh cookies"):
        config.Settings()
