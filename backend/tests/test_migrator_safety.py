from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.core import migrator


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def make_alembic_config(db_url: str) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.attributes["sqlalchemy_url"] = db_url
    return config


def test_competitive_seed_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SEED_COMPETITIVE_USERS", raising=False)

    assert migrator.competitive_seed_enabled() is False


def test_competitive_seed_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("SEED_COMPETITIVE_USERS", "true")

    assert migrator.competitive_seed_enabled() is True


def test_unversioned_baseline_database_is_upgraded_to_head(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy_stockauto.db"
    db_url = f"sqlite:///{db_path}"
    alembic_config = make_alembic_config(db_url)
    command.upgrade(alembic_config, "001_baseline")

    legacy_engine = create_engine(db_url)
    with legacy_engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE alembic_version")

    monkeypatch.setattr(migrator, "engine", legacy_engine)
    monkeypatch.setattr(migrator, "competitive_seed_enabled", lambda: False)

    try:
        migrator.run_migrations_programmatically()

        schema = inspect(legacy_engine)
        assert "refresh_tokens" in schema.get_table_names()
        assert "broker_orders" in schema.get_table_names()
        user_columns = {column["name"] for column in schema.get_columns("users")}
        assert {"role", "token_version", "failed_login_attempts", "locked_until"} <= user_columns
    finally:
        legacy_engine.dispose()
