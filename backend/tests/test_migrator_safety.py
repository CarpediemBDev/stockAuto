from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.core import migrator
from app.core.database import Base
from app.core.models import User


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


def test_competitive_seed_preserves_existing_user_settings(tmp_path, monkeypatch):
    db_path = tmp_path / "seed_preserves_settings.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    import app.core.database as database_module
    import app.core.security as security_module

    monkeypatch.setattr(database_module, "SessionLocal", session_factory)
    monkeypatch.setattr(security_module, "get_password_hash", lambda value: f"hashed-{value}")

    try:
        migrator.seed_competitive_users()

        db = session_factory()
        try:
            admin = db.query(User).filter(User.username == "admin").one()
            admin.settings.strategy_type = "strategy_c"
            admin.settings.trade_mode = "REAL"
            admin.settings.is_running = False
            db.commit()
        finally:
            db.close()

        migrator.seed_competitive_users()

        db = session_factory()
        try:
            admin = db.query(User).filter(User.username == "admin").one()
            assert admin.settings.strategy_type == "strategy_c"
            assert admin.settings.trade_mode == "REAL"
            assert admin.settings.is_running is False
        finally:
            db.close()
    finally:
        engine.dispose()
