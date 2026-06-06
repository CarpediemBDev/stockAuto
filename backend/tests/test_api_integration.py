from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.watchlist.router as watchlist_router_module
from app.auth.router import router as auth_router
from app.core.database import Base, get_db
from app.core.exceptions import StockAutoException, stock_auto_exception_handler
from app.core.models import User, UserSettings, WatchList
from app.watchlist.router import router as watchlist_router


BACKEND_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def test_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    try:
        yield SessionFactory
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def integration_app(test_session_factory):
    app = FastAPI()
    app.add_exception_handler(StockAutoException, stock_auto_exception_handler)

    def override_get_db():
        db = test_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.include_router(auth_router, prefix="/api/v1/auth")
    app.include_router(watchlist_router, prefix="/api/v1/watchlist")
    return app


def make_alembic_config(db_url: str) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.attributes["sqlalchemy_url"] = db_url
    return config


def test_alembic_upgrade_head_builds_expected_core_schema(tmp_path):
    db_path = tmp_path / "stockauto_migration_test.db"
    db_url = f"sqlite:///{db_path}"
    config = make_alembic_config(db_url)

    script = ScriptDirectory.from_config(config)
    assert script.get_current_head() == "f2a3b4c5d6e7"

    command.upgrade(config, "head")

    engine = create_engine(db_url)
    try:
        inspector = inspect(engine)
        assert set(inspector.get_table_names()) >= {
            "users",
            "user_settings",
            "trade_logs",
            "holdings",
            "watch_lists",
            "stock_translations",
            "market_overview_snapshots",
            "swing_prediction_snapshots",
            "refresh_tokens",
            "broker_orders",
            "alembic_version",
        }

        user_settings_columns = {column["name"] for column in inspector.get_columns("user_settings")}
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        refresh_token_columns = {column["name"] for column in inspector.get_columns("refresh_tokens")}
        broker_order_columns = {column["name"] for column in inspector.get_columns("broker_orders")}
        trade_log_columns = {column["name"] for column in inspector.get_columns("trade_logs")}
        market_overview_columns = {column["name"] for column in inspector.get_columns("market_overview_snapshots")}
        swing_prediction_columns = {column["name"] for column in inspector.get_columns("swing_prediction_snapshots")}
        assert "strategy_type" in user_settings_columns
        assert "role" in user_columns
        assert {"failed_login_attempts", "locked_until"} <= user_columns
        assert {"user_id", "token", "expires_at", "is_revoked"} <= refresh_token_columns
        assert {
            "intent_id",
            "broker_order_no",
            "status",
            "requested_qty",
            "broker_filled_qty",
            "applied_filled_qty",
            "resume_after_resolution",
            "submission_attempts",
            "discovery_attempts",
            "submission_started_at",
            "response_received_at",
        } <= broker_order_columns
        assert {
            "kis_verification_status",
            "kis_verified_trade_mode",
            "kis_verified_at",
        } <= user_settings_columns
        assert {"realized_pnl", "return_rate"} <= trade_log_columns
        assert {
            "market_condition",
            "market_condition_sync_status",
            "nasdaq_current",
            "nasdaq_sync_status",
            "exchange_rate_current",
            "exchange_rate_sync_status",
        } <= market_overview_columns
        assert {
            "cache_key",
            "ticker_universe",
            "candidates_json",
            "sync_status",
            "created_at",
        } <= swing_prediction_columns
    finally:
        engine.dispose()


def test_role_migration_upgrades_existing_user_database(tmp_path):
    db_path = tmp_path / "stockauto_existing_user_test.db"
    db_url = f"sqlite:///{db_path}"
    config = make_alembic_config(db_url)

    command.upgrade(config, "c4f5a6b7c8d9")
    engine = create_engine(db_url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO users (username, hashed_password, created_at) "
                "VALUES ('admin', 'hash', CURRENT_TIMESTAMP)"
            )
    finally:
        engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(db_url)
    try:
        with engine.connect() as connection:
            role = connection.exec_driver_sql(
                "SELECT role FROM users WHERE username = 'admin'"
            ).scalar_one()
            assert role == "ADMIN"
    finally:
        engine.dispose()


def test_auth_and_watchlist_routes_share_isolated_test_database(monkeypatch, integration_app, test_session_factory):
    async def fake_fetch_ohlcv(ticker, interval="1d", period="1d"):
        return SimpleNamespace(empty=False)

    monkeypatch.setattr(watchlist_router_module, "fetch_ohlcv", fake_fetch_ohlcv)

    with TestClient(integration_app) as client:
        signup_response = client.post(
            "/api/v1/auth/signup",
            json={"username": "tester", "password": "pass1234"},
        )
        assert signup_response.status_code == 201
        assert signup_response.cookies.get("refresh_token")
        token = signup_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        me_response = client.get("/api/v1/auth/me", headers=headers)
        assert me_response.status_code == 200
        assert me_response.json() == {
            "id": 1,
            "username": "tester",
            "trade_mode": "SIMULATED",
            "broker_provider": "KIS",
            "telegram_enabled": False,
        }

        add_response = client.post(
            "/api/v1/watchlist/",
            json={"ticker": "aapl", "ticker_name": "Apple"},
            headers=headers,
        )
        assert add_response.status_code == 200
        assert add_response.json()["data"]["ticker"] == "AAPL"
        assert add_response.json()["data"]["ticker_name"] == "Apple"

        duplicate_response = client.post(
            "/api/v1/watchlist/",
            json={"ticker": "AAPL", "ticker_name": "Apple"},
            headers=headers,
        )
        assert duplicate_response.status_code == 400
        assert duplicate_response.json()["error"]["code"] == "WATCHLIST_DUPLICATE"

        list_response = client.get("/api/v1/watchlist/", headers=headers)
        assert list_response.status_code == 200
        assert [item["ticker"] for item in list_response.json()["data"]] == ["AAPL"]

        refresh_response = client.post("/api/v1/auth/refresh")
        assert refresh_response.status_code == 200
        assert refresh_response.json()["username"] == "tester"

        refresh_token = signup_response.cookies.get("refresh_token")
        refresh_as_access = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {refresh_token}"},
        )
        assert refresh_as_access.status_code == 401

    db = test_session_factory()
    try:
        assert db.query(User).count() == 1
        assert db.query(UserSettings).count() == 1
        assert db.query(WatchList).count() == 1
    finally:
        db.close()


def test_brute_force_defense_and_lockout_reset(integration_app, test_session_factory):
    from datetime import timedelta
    from app.core.models import utc_now_naive

    with TestClient(integration_app) as client:
        # 1. 회원가입
        signup_response = client.post(
            "/api/v1/auth/signup",
            json={"username": "bruteforce_tester", "password": "correctpassword"},
        )
        assert signup_response.status_code == 201

        # 2. 4회 로그인 실패 -> 401 리턴
        for _ in range(4):
            response = client.post(
                "/api/v1/auth/login",
                json={"username": "bruteforce_tester", "password": "wrongpassword"},
            )
            assert response.status_code == 401

        # 3. 5번째 로그인 실패 -> 401 리턴 & 계정 잠금 설정됨
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "bruteforce_tester", "password": "wrongpassword"},
        )
        assert response.status_code == 401

        # 4. 6번째 로그인 시도 -> 403 잠금 상태 에러 리턴
        locked_response = client.post(
            "/api/v1/auth/login",
            json={"username": "bruteforce_tester", "password": "wrongpassword"},
        )
        assert locked_response.status_code == 403
        assert "잠겼습니다" in locked_response.json()["detail"]

        # 5. DB에서 강제로 locked_until을 과거로 설정 (잠금 시간 만료 모사)
        db = test_session_factory()
        try:
            user = db.query(User).filter(User.username == "bruteforce_tester").first()
            assert user.failed_login_attempts == 5
            assert user.locked_until is not None
            user.locked_until = utc_now_naive() - timedelta(minutes=1)
            db.commit()
        finally:
            db.close()

        # 6. 잠금 만료 후 첫 시도 (잘못된 패스워드) -> 401 리턴 (403이 아님!)
        # 온디맨드로 리셋되어 실패 건수가 0이 되고 다시 1로 오르며 locked_until이 지워져야 함
        retry_response = client.post(
            "/api/v1/auth/login",
            json={"username": "bruteforce_tester", "password": "wrongpassword"},
        )
        assert retry_response.status_code == 401

        # 7. DB 최종 상태 검증
        db = test_session_factory()
        try:
            user = db.query(User).filter(User.username == "bruteforce_tester").first()
            assert user.failed_login_attempts == 1
            assert user.locked_until is None
        finally:
            db.close()
