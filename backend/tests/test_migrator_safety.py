from app.core import migrator


def test_competitive_seed_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SEED_COMPETITIVE_USERS", raising=False)

    assert migrator.competitive_seed_enabled() is False


def test_competitive_seed_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("SEED_COMPETITIVE_USERS", "true")

    assert migrator.competitive_seed_enabled() is True
