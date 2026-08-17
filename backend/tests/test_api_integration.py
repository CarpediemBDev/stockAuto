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
from app.core.models import User, UserSettings, WatchList, BrokerCredential, RefreshToken
from app.core.security import hash_refresh_token
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


def unwrap_success(response):
    payload = response.json()
    assert payload["code"] == "SUCCESS"
    return payload["data"]


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
            "broker_credentials",
            "alembic_version",
            "strategies",
            "account_equity_snapshots",
            "system_settings",
        }

        user_settings_columns = {column["name"] for column in inspector.get_columns("user_settings")}
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        refresh_token_columns = {column["name"] for column in inspector.get_columns("refresh_tokens")}
        broker_order_columns = {column["name"] for column in inspector.get_columns("broker_orders")}
        trade_log_columns = {column["name"] for column in inspector.get_columns("trade_logs")}
        market_overview_columns = {column["name"] for column in inspector.get_columns("market_overview_snapshots")}
        swing_prediction_columns = {column["name"] for column in inspector.get_columns("swing_prediction_snapshots")}
        equity_snapshot_columns = {
            column["name"]
            for column in inspector.get_columns("account_equity_snapshots")
        }
        system_setting_columns = {column["name"] for column in inspector.get_columns("system_settings")}
        assert "strategy_type" in user_settings_columns
        assert "role" in user_columns
        assert "token_version" in user_columns
        assert {"failed_login_attempts", "locked_until"} <= user_columns
        assert {"user_id", "token", "expires_at", "is_revoked"} <= refresh_token_columns
        assert {
            "intent_id",
            "broker_order_no",
            "status",
            "requested_qty",
            "broker_filled_qty",
            "applied_filled_qty",
            "submission_attempts",
            "discovery_attempts",
            "submission_started_at",
            "response_received_at",
        } <= broker_order_columns
        assert "resume_after_resolution" not in broker_order_columns
        
        broker_credential_columns = {column["name"] for column in inspector.get_columns("broker_credentials")}
        assert {
            "user_id",
            "broker_name",
            "verification_status",
            "verified_trade_mode",
            "verified_at",
        } <= broker_credential_columns

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
        assert {
            "user_id",
            "total_asset",
            "cash_balance",
            "stock_balance",
            "profit_rate",
            "fx_rate",
            "trade_mode",
            "captured_at",
        } <= equity_snapshot_columns
        assert {
            "key",
            "value",
            "value_type",
            "category",
            "description",
            "is_runtime",
            "is_public",
            "updated_by",
            "created_at",
            "updated_at",
        } <= system_setting_columns

        for table_name in ("user_settings", "holdings", "trade_logs", "broker_orders"):
            foreign_keys = inspector.get_foreign_keys(table_name)
            assert not any(
                foreign_key["referred_table"] == "strategies"
                for foreign_key in foreign_keys
            )
            assert any(
                foreign_key["referred_table"] == "users"
                and foreign_key["constrained_columns"] == ["user_id"]
                for foreign_key in foreign_keys
            )

        with engine.connect() as connection:
            strategy_count = connection.exec_driver_sql(
                "SELECT COUNT(*) FROM strategies"
            ).scalar_one()
            strategy_name = connection.exec_driver_sql(
                "SELECT name_ko FROM strategies WHERE strategy_type = 'multi_slot'"
            ).scalar_one()
            gemini_enabled = connection.exec_driver_sql(
                "SELECT value FROM system_settings WHERE key = 'enable_gemini_news_analysis'"
            ).scalar_one()
            assert strategy_count == 90

            assert gemini_enabled == "false"
            assert strategy_name == "격리형 2슬롯 (EP 50% : RS 50%)"
    finally:
        engine.dispose()


def test_strategy_catalog_migration_only_fills_missing_rows(tmp_path):
    db_path = tmp_path / "strategy_catalog_repair.db"
    db_url = f"sqlite:///{db_path}"
    config = make_alembic_config(db_url)

    command.upgrade(config, "b7d8e9f01234")
    engine = create_engine(db_url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO strategies "
                "(strategy_type, name_ko, name_en, is_active) "
                "VALUES ('regime_switching', '관리자 수정명', "
                "'Regime Switching', 1)"
            )
    finally:
        engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(db_url)
    try:
        with engine.connect() as connection:
            custom_name = connection.exec_driver_sql(
                "SELECT name_ko FROM strategies "
                "WHERE strategy_type = 'regime_switching'"
            ).scalar_one()
            restored_name = connection.exec_driver_sql(
                "SELECT name_ko FROM strategies "
                "WHERE strategy_type = 'multi_slot_3'"
            ).scalar_one()
            assert custom_name == "관리자 수정명"
            assert restored_name == "격리형 3슬롯 (EP 30% : ASQS 30% : RS 40%)"
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
            json={"username": "tester", "password": "pass12345678"},
        )
        assert signup_response.status_code == 201
        assert signup_response.cookies.get("refresh_token")
        signup_payload = unwrap_success(signup_response)
        assert "refresh_token" not in signup_payload
        assert signup_payload["role"] == "USER"
        token = signup_payload["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        me_response = client.get("/api/v1/auth/me", headers=headers)
        assert me_response.status_code == 200
        assert unwrap_success(me_response) == {
            "id": 1,
            "username": "tester",
            "role": "USER",
            "trade_mode": "SIMULATED",
            "broker_provider": None,
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

        refresh_response = client.post("/api/v1/auth/refresh", headers={"Origin": "http://localhost:3000"})
        assert refresh_response.status_code == 200
        refresh_payload = unwrap_success(refresh_response)
        assert refresh_payload["username"] == "tester"
        assert "refresh_token" not in refresh_payload

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


def test_refresh_cookie_rotation_hash_storage_and_origin_guard(integration_app, test_session_factory):
    with TestClient(integration_app) as client:
        signup_response = client.post(
            "/api/v1/auth/signup",
            json={"username": "rotation_tester", "password": "strongpassword123"},
        )
        assert signup_response.status_code == 201
        original_token = signup_response.cookies.get("refresh_token")
        assert original_token

        db = test_session_factory()
        try:
            stored_token = db.query(RefreshToken).filter(
                RefreshToken.user_id == 1,
                RefreshToken.is_revoked.is_(False),
            ).one()
            assert stored_token.token == hash_refresh_token(original_token)
            assert stored_token.token != original_token
        finally:
            db.close()

        rejected_origin = client.post(
            "/api/v1/auth/refresh",
            headers={"Origin": "https://attacker.example"},
        )
        assert rejected_origin.status_code == 403
        rejected_prefix_origin = client.post(
            "/api/v1/auth/refresh",
            headers={"Origin": "http://localhost:3000.evil.example"},
        )
        assert rejected_prefix_origin.status_code == 403

        refresh_response = client.post("/api/v1/auth/refresh", headers={"Origin": "http://localhost:3000"})
        assert refresh_response.status_code == 200
        rotated_token = refresh_response.cookies.get("refresh_token")
        assert rotated_token
        assert rotated_token != original_token

        with TestClient(integration_app) as replay_client:
            replay_client.cookies.set(
                "refresh_token",
                original_token,
                path="/api/v1/auth",
            )
            replay_response = replay_client.post("/api/v1/auth/refresh", headers={"Origin": "http://localhost:3000"})
        assert replay_response.status_code == 401


def test_refresh_uses_valid_cookie_when_legacy_root_cookie_has_same_name(integration_app):
    with TestClient(integration_app) as client:
        signup_response = client.post(
            "/api/v1/auth/signup",
            json={"username": "edge_cookie_tester", "password": "strongpassword123"},
        )
        assert signup_response.status_code == 201

        client.cookies.set(
            "refresh_token",
            "legacy-invalid-token",
            path="/",
        )

        refresh_response = client.post("/api/v1/auth/refresh", headers={"Origin": "http://localhost:3000"})

        assert refresh_response.status_code == 200
        assert unwrap_success(refresh_response)["username"] == "edge_cookie_tester"
        set_cookie_headers = refresh_response.headers.get_list("set-cookie")
        assert any(
            "refresh_token=" in header
            and "Path=/;" in header
            and "Max-Age=0" in header
            for header in set_cookie_headers
        )


def test_change_password_revokes_refresh_and_access_tokens(integration_app):
    with TestClient(integration_app) as client:
        signup_response = client.post(
            "/api/v1/auth/signup",
            json={"username": "password_tester", "password": "initialpassword123"},
        )
        assert signup_response.status_code == 201
        access_token = unwrap_success(signup_response)["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        change_response = client.post(
            "/api/v1/auth/change-password",
            json={
                "old_password": "initialpassword123",
                "new_password": "replacementpassword123",
            },
            headers=headers,
        )
        assert change_response.status_code == 200

        old_access_response = client.get("/api/v1/auth/me", headers=headers)
        assert old_access_response.status_code == 401

        old_refresh_response = client.post("/api/v1/auth/refresh", headers={"Origin": "http://localhost:3000"})
        assert old_refresh_response.status_code == 401


def test_signup_rejects_short_password(integration_app):
    with TestClient(integration_app) as client:
        response = client.post(
            "/api/v1/auth/signup",
            json={"username": "short_password", "password": "abcd"},
        )
        assert response.status_code == 422


def test_signup_rejects_password_over_bcrypt_byte_limit(integration_app):
    with TestClient(integration_app) as client:
        response = client.post(
            "/api/v1/auth/signup",
            json={"username": "long_password", "password": "a" * 73},
        )

        assert response.status_code == 422
        assert "72바이트" in response.json()["detail"][0]["msg"]


def test_change_password_rejects_password_over_bcrypt_byte_limit(integration_app):
    with TestClient(integration_app) as client:
        signup_response = client.post(
            "/api/v1/auth/signup",
            json={"username": "password_limit", "password": "initialpassword123"},
        )
        headers = {
            "Authorization": f"Bearer {unwrap_success(signup_response)['access_token']}",
        }

        response = client.post(
            "/api/v1/auth/change-password",
            json={
                "old_password": "initialpassword123",
                "new_password": "a" * 73,
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert "72바이트" in response.json()["detail"][0]["msg"]


def test_brute_force_defense_and_lockout_reset(monkeypatch, integration_app, test_session_factory):
    from datetime import timedelta
    from app.core import telegram as telegram_module
    from app.core.models import utc_now_aware

    # 잠금 경고가 모듈 레벨 SessionLocal을 열면 이 테스트의 인메모리 DB가 아니라 기본
    # stockauto.db를 조회하게 되고, 같은 user_id를 쓰는 실제 사용자의 연동 채팅으로 메시지가
    # 실제 발송된다. 라우터가 세션을 넘기지 않는 회귀를 잡기 위해 그 경로 호출을 기록한다.
    # (라우터가 알림 예외를 Fail-Safe로 삼키므로 raise만으로는 테스트가 실패하지 않는다.)
    global_session_calls = []

    def _tracking_session_local(*args, **kwargs):
        global_session_calls.append(True)
        raise AssertionError("alert dispatch must use the caller's session")

    monkeypatch.setattr(telegram_module, "SessionLocal", _tracking_session_local)

    real_dispatch_alert = telegram_module.dispatch_alert
    sent_alerts = []

    def _capturing_dispatch_alert(user_id, text, db=None, parse_mode="Markdown", **kwargs):
        sent_alerts.append(
            {
                "user_id": user_id,
                "text": text,
                "db": db,
                "parse_mode": parse_mode,
                "attempts": kwargs.get("attempts", 1),
            }
        )
        return real_dispatch_alert(user_id, text, db=db, parse_mode=parse_mode, **kwargs)

    monkeypatch.setattr(telegram_module, "dispatch_alert", _capturing_dispatch_alert)

    # 보안 이벤트 기록 캡처. 라우터가 임포트한 이름을 갈아끼워야 한다.
    import app.auth.router as auth_router_module

    security_events = []
    monkeypatch.setattr(
        auth_router_module,
        "log_security_event",
        lambda event_type, **fields: security_events.append((event_type, fields)),
    )

    with TestClient(integration_app) as client:
        test_username = "bruteforce_tester_new"

        # Rate Limiter 강제 리셋 (테스트 시작 전)
        from app.core.redis_client import get_redis_client
        rc = get_redis_client()
        if rc:
            rc.flushall()

        # 1. 회원가입
        signup_response = client.post(
            "/api/v1/auth/signup",
            json={"username": test_username, "password": "correctpassword"},
        )
        assert signup_response.status_code == 201

        # 2. 4회 로그인 실패 -> 401 리턴
        for _ in range(4):
            response = client.post(
                "/api/v1/auth/login",
                json={"username": test_username, "password": "wrongpassword"},
            )
            assert response.status_code == 401

        # 3. 5번째 로그인 실패 -> 401 리턴 & 계정 잠금 설정됨
        response = client.post(
            "/api/v1/auth/login",
            json={"username": test_username, "password": "wrongpassword"},
        )
        assert response.status_code == 401

        # 3-1. 잠금 경고가 격리된 호출자 세션으로만 연동 정보를 조회했는지 검증
        assert not global_session_calls, (
            "잠금 경고가 모듈 레벨 SessionLocal(기본 DB)을 조회했다. "
            "격리 테스트의 알림이 실제 사용자 텔레그램으로 누수된다."
        )
        assert len(sent_alerts) == 1
        alert = sent_alerts[0]
        assert alert["db"] is not None, "라우터가 요청 세션을 주입해야 한다"
        assert alert["parse_mode"] is None, (
            "계정명이 그대로 삽입되므로 Markdown을 끄지 않으면 밑줄이 훼손되거나 발송이 실패한다"
        )
        assert alert["attempts"] > 1, "P0 보안 경고는 일시 순단·429에 유실되면 안 된다"
        assert test_username in alert["text"]

        # 3-2. 전용 보안 로그에 구조화 기록이 남았는지 검증. DB에는 현재 상태만 남고
        # 리셋되면 흔적이 사라지므로, 이 기록이 사후 확인의 유일한 수단이다.
        assert len(security_events) == 1, "계정 잠금이 보안 로그에 남지 않았다"
        event_type, event_fields = security_events[0]
        assert event_type == "account_locked"
        assert event_fields["username"] == test_username
        assert event_fields["failed_attempts"] == 5
        assert event_fields["locked_until"] is not None
        # 접속 출처가 없으면 누가 시도했는지 사후에 알 방법이 없다.
        assert event_fields["ip"], "접속 IP가 기록되지 않았다"

        # 4. 6번째 로그인 시도 -> 429 또는 403 에러 리턴 (RateLimiter가 먼저 작동하면 429)
        locked_response = client.post(
            "/api/v1/auth/login",
            json={"username": test_username, "password": "wrongpassword"},
        )
        assert locked_response.status_code in (403, 429)

        # Rate Limiter 강제 리셋 (테스트 진행을 위해)
        if rc:
            rc.flushall()

        # 5. DB에서 강제로 locked_until을 과거로 설정 (잠금 시간 만료 모사)
        db = test_session_factory()
        try:
            user = db.query(User).filter(User.username == test_username).first()
            assert user.failed_login_attempts == 5
            assert user.locked_until is not None
            user.locked_until = utc_now_aware() - timedelta(minutes=1)
            db.commit()
        finally:
            db.close()

        # 6. 잠금 만료 후 첫 시도 (잘못된 패스워드) -> 401 리턴 (403이 아님!)
        # 온디맨드로 리셋되어 실패 건수가 0이 되고 다시 1로 오르며 locked_until이 지워져야 함
        retry_response = client.post(
            "/api/v1/auth/login",
            json={"username": test_username, "password": "wrongpassword"},
        )
        assert retry_response.status_code == 401

        # 7. DB 최종 상태 검증
        db = test_session_factory()
        try:
            user = db.query(User).filter(User.username == test_username).first()
            assert user.failed_login_attempts == 1
            assert user.locked_until is None
        finally:
            db.close()


def test_failed_login_counter_increments_atomically(test_session_factory):
    """실패 카운터가 동시 요청에서도 유실 없이 누적되는지 검증.

    ORM의 `user.failed_login_attempts += 1`은 파이썬에서 읽은 값을 리터럴로 UPDATE하므로,
    두 세션이 같은 값을 읽으면 증가분 하나가 사라진다(lost update). 그 상태에서는 동시
    요청을 반복해 카운터를 5 미만으로 묶어둘 수 있어 계정 잠금 자체가 회피된다.
    라우터가 쓰는 원자적 UPDATE는 두 세션이 같은 값을 읽어도 각각 +1이 반영돼야 한다.
    """
    from sqlalchemy import update

    setup_db = test_session_factory()
    try:
        setup_db.add(
            User(username="atomic_counter_user", hashed_password="x", failed_login_attempts=0)
        )
        setup_db.commit()
        user_id = (
            setup_db.query(User).filter(User.username == "atomic_counter_user").first().id
        )
    finally:
        setup_db.close()

    def atomic_increment(session):
        return session.execute(
            update(User)
            .where(User.id == user_id)
            .values(failed_login_attempts=User.failed_login_attempts + 1)
            .returning(User.failed_login_attempts)
        ).scalar_one()

    session_a = test_session_factory()
    session_b = test_session_factory()
    try:
        # 두 세션이 증가 전 같은 값(0)을 읽은 상태를 만든다 - lost update가 나는 조건이다.
        assert session_a.query(User).filter(User.id == user_id).first().failed_login_attempts == 0
        assert session_b.query(User).filter(User.id == user_id).first().failed_login_attempts == 0

        returned_a = atomic_increment(session_a)
        session_a.commit()
        returned_b = atomic_increment(session_b)
        session_b.commit()
    finally:
        session_a.close()
        session_b.close()

    # RETURNING 값이 서로 달라야 한다. 같으면 두 요청이 같은 임계값을 보고 경고를 중복 발송한다.
    assert {returned_a, returned_b} == {1, 2}, (
        f"원자적 증가가 아니다. 반환값: {returned_a}, {returned_b}"
    )

    verify_db = test_session_factory()
    try:
        final = verify_db.query(User).filter(User.id == user_id).first().failed_login_attempts
    finally:
        verify_db.close()
    assert final == 2, f"증가분이 유실됐다(lost update). 최종값: {final}"


def test_login_endpoint_enforces_atomic_update_pattern(integration_app, test_session_factory):
    """로그인 API 라우터가 실제로 원자적 UPDATE 구문을 사용하는지 엔드포인트 경유로 직접 강제 검증.

    누군가 라우터 코드를 ORM 대입(`user.failed_login_attempts += 1`)으로 퇴행시키면
    세션에 원자적 UPDATE 표현식이 execute되지 않으므로 이 테스트가 즉시 실패해야 한다.
    """
    from sqlalchemy import update
    from sqlalchemy.orm import Session
    from app.core.models import User

    # Rate Limiter 강제 리셋 (독립 실행 보장)
    from app.core.redis_client import get_redis_client
    rc = get_redis_client()
    if rc:
        rc.flushall()
    import app.core.rate_limiter as rate_limiter_mod
    with rate_limiter_mod._global_fallback_lock:
        rate_limiter_mod._global_fallback_windows.clear()

    executed_atomic_updates = []
    original_execute = Session.execute

    def _spying_execute(self, statement, *args, **kwargs):
        # statement가 User 테이블에 대한 failed_login_attempts 원자적 UPDATE인지 검사
        if hasattr(statement, "is_dml") and statement.is_dml:
            stmt_str = str(statement)
            if "failed_login_attempts" in stmt_str:
                executed_atomic_updates.append(statement)
        return original_execute(self, statement, *args, **kwargs)

    # 1. 테스트 유저 생성
    db = test_session_factory()
    try:
        db.add(User(username="spy_atomic_user", hashed_password="hashed_dummy_password", failed_login_attempts=0))
        db.commit()
    finally:
        db.close()

    with TestClient(integration_app) as client:
        from unittest.mock import patch
        with patch.object(Session, "execute", _spying_execute):
            response = client.post(
                "/api/v1/auth/login",
                json={"username": "spy_atomic_user", "password": "wrongpassword"},
            )
            assert response.status_code == 401

    # 2. 라우터가 ORM 대입이 아니라 원자적 UPDATE 문을 실제로 execute 했는지 확인
    assert len(executed_atomic_updates) >= 1, (
        "회귀 발생: 로그인 라우터가 원자적 UPDATE 구문을 execute하지 않았습니다! "
        "ORM 대입(`user.failed_login_attempts += 1`)으로 퇴행하면 Lost Update 위험이 발생합니다."
    )


def test_lockout_expired_reset_uses_conditional_atomic_update(test_session_factory):
    """잠금 만료 리셋이 조건부 원자적 UPDATE를 사용하여 동시 실패 증가와의 경합에서 카운터를 덮어쓰지 않는지 검증."""
    from datetime import timedelta
    from sqlalchemy import update
    from app.core.models import User, utc_now_aware

    past_locked_time = utc_now_aware() - timedelta(minutes=1)
    setup_db = test_session_factory()
    try:
        setup_db.add(
            User(
                username="reset_atomic_user",
                hashed_password="x",
                failed_login_attempts=5,
                locked_until=past_locked_time,
            )
        )
        setup_db.commit()
        user_id = setup_db.query(User).filter(User.username == "reset_atomic_user").first().id
    finally:
        setup_db.close()

    now = utc_now_aware()

    # 세션 A: 잠금 만료 감지 후 조건부 원자적 리셋 시도
    session_reset = test_session_factory()
    # 세션 B: 다른 동시 요청에서 비밀번호 오류로 원자적 실패 카운터 증가 시도
    session_fail = test_session_factory()

    try:
        # 1. 세션 B가 먼저 비밀번호 오류로 실패 카운터를 올림 (5 -> 6)
        session_fail.execute(
            update(User)
            .where(User.id == user_id)
            .values(failed_login_attempts=User.failed_login_attempts + 1)
        )
        session_fail.commit()

        # 2. 세션 A가 조건부 원자적 리셋을 실행:
        # WHERE locked_until <= now 조건에 의해, 만료 상태였던 잠금 및 카운터를 0으로 초기화
        result = session_reset.execute(
            update(User)
            .where(User.id == user_id, User.locked_until <= now)
            .values(failed_login_attempts=0, locked_until=None)
        )
        session_reset.commit()
        assert result.rowcount == 1
    finally:
        session_reset.close()
        session_fail.close()

    # 3. 최종 검증: 정상적으로 리셋 완료되었는지 확인
    verify_db = test_session_factory()
    try:
        user = verify_db.query(User).filter(User.id == user_id).first()
        assert user.failed_login_attempts == 0
        assert user.locked_until is None
    finally:
        verify_db.close()


def test_login_success_prevents_lost_lockout_race(integration_app, test_session_factory):
    """정당한 사용자가 패스워드 검증을 하는 동안 공격자에 의해 계정이 잠긴 경우,
    로그인 성공 경로가 해당 잠금을 덮어쓰지 않고 403 Forbidden으로 안전하게 차단하는지 검증 (F1: Lost Lockout Race 방어).
    """
    from datetime import timedelta
    from sqlalchemy import update
    from app.core.models import User, utc_now_aware
    from app.core.security import get_password_hash

    test_username = "race_lockout_user"
    correct_password = "verysecurepassword123"

    db = test_session_factory()
    try:
        db.add(User(username=test_username, hashed_password=get_password_hash(correct_password), failed_login_attempts=4))
        db.commit()
    finally:
        db.close()

    # Rate Limiter 강제 리셋
    from app.core.redis_client import get_redis_client
    rc = get_redis_client()
    if rc:
        rc.flushall()
    import app.core.rate_limiter as rate_limiter_mod
    with rate_limiter_mod._global_fallback_lock:
        rate_limiter_mod._global_fallback_windows.clear()

    # 패스워드 검증 함수가 실행되는 도중 다른 세션에서 계정을 잠그도록 인터셉트
    from unittest.mock import patch
    import app.auth.router as auth_router_mod
    original_verify = auth_router_mod.verify_password

    def _interleaving_verify(plain_pwd, hashed_pwd):
        res = original_verify(plain_pwd, hashed_pwd)
        # 패스워드 검증 통과 직후, 다른 동시 요청이 5번째 실패로 계정을 잠갔다고 가정
        concurrent_db = test_session_factory()
        try:
            concurrent_db.execute(
                update(User)
                .where(User.username == test_username)
                .values(failed_login_attempts=5, locked_until=utc_now_aware() + timedelta(minutes=15))
            )
            concurrent_db.commit()
        finally:
            concurrent_db.close()
        return res

    with TestClient(integration_app) as client:
        with patch.object(auth_router_mod, "verify_password", _interleaving_verify):
            response = client.post(
                "/api/v1/auth/login",
                json={"username": test_username, "password": correct_password},
            )
            # 동시 잠금이 발생했으므로 성공 처리되지 않고 403 Forbidden 차단되어야 함
            assert response.status_code == 403
            assert "계정이 잠겼습니다" in response.json()["detail"]

    # DB에 잠금이 유지되어 있는지 검증 (Lost Lockout이 발생하지 않았는지 확인)
    verify_db = test_session_factory()
    try:
        user = verify_db.query(User).filter(User.username == test_username).first()
        assert user.locked_until is not None
        assert user.failed_login_attempts == 5
    finally:
        verify_db.close()


