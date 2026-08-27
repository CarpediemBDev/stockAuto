import os

import httpx
import pytest

from app.core.config import settings


class FakeRedisLease:
    async def release(self):
        return None


@pytest.fixture(autouse=True)
def mock_order_locks(monkeypatch):
    async def acquire_lock(*_args, **_kwargs):
        return FakeRedisLease()

    import app.bot.scheduler as scheduler
    import app.trades.router_account as account_router

    monkeypatch.setattr(scheduler, "acquire_user_operation_lock", acquire_lock)
    monkeypatch.setattr(scheduler, "acquire_symbol_order_lock", acquire_lock)
    monkeypatch.setattr(account_router, "acquire_user_operation_lock", acquire_lock)
    monkeypatch.setattr(account_router, "acquire_symbol_order_lock", acquire_lock)


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    import app.core.rate_limiter as rate_limiter_mod
    with rate_limiter_mod._global_fallback_lock:
        rate_limiter_mod._global_fallback_windows.clear()
    yield
    with rate_limiter_mod._global_fallback_lock:
        rate_limiter_mod._global_fallback_windows.clear()


_TELEGRAM_API_HOST = "api.telegram.org"


@pytest.fixture(autouse=True)
def block_real_telegram_api(monkeypatch):
    """모든 테스트에서 실제 텔레그램 발송 경로를 차단한다.

    배경 - 통합 테스트가 격리된 인메모리 DB를 쓰면서도 알림 함수가 모듈 레벨 SessionLocal로
    기본 DB를 조회한 탓에, 테스트 계정(인메모리 user.id=1)의 계정 잠금 경고가 기본 DB의
    user_id=1 연동 채팅으로 실제 발송된 사고가 있었다(2026-08-17). 호출부를 하나씩 고치는
    방식은 새 호출부가 생기면 다시 뚫리므로, 발송이 불가능한 상태를 여기서 한 번 더 만든다.

    1) 토큰을 비운다. 발송 함수들은 토큰이 없으면 HTTP 호출 전에 False로 빠지고,
       start_telegram_bot도 폴링을 건너뛴다.
    2) 토큰을 다시 채우는 테스트가 있어도 텔레그램 호스트로 나가는 요청은 실패시킨다.
       텔레그램 외 호스트는 원래 동작으로 통과시키므로 TestClient(내부적으로 httpx 사용)나
       다른 외부 호출 모킹에는 영향이 없다.
    """
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "", raising=False)

    # 발송 함수들은 예외를 Fail-Safe로 삼켜 False를 반환하므로, raise만으로는 위반한 테스트가
    # 실패하지 않는다. 위반을 기록해 두고 teardown에서 확인해야 실제로 드러난다.
    violations = []

    def _guard(original):
        def wrapper(self, url, *args, **kwargs):
            if _TELEGRAM_API_HOST in str(url):
                violations.append(str(url))
                raise AssertionError(f"테스트가 실제 텔레그램 API를 호출했다: {url}")
            return original(self, url, *args, **kwargs)

        return wrapper

    def _async_guard(original):
        async def wrapper(self, url, *args, **kwargs):
            if _TELEGRAM_API_HOST in str(url):
                violations.append(str(url))
                raise AssertionError(f"테스트가 실제 텔레그램 API를 호출했다(async): {url}")
            return await original(self, url, *args, **kwargs)

        return wrapper

    monkeypatch.setattr(httpx.Client, "post", _guard(httpx.Client.post))
    monkeypatch.setattr(httpx.Client, "get", _guard(httpx.Client.get))
    monkeypatch.setattr(httpx.AsyncClient, "post", _async_guard(httpx.AsyncClient.post))

    yield

    assert not violations, (
        f"테스트가 실제 텔레그램 API 호출을 시도했다: {violations}. "
        "발송 함수를 모킹하거나 호출자 세션(db) 주입으로 격리 DB를 조회하게 하라."
    )


def _clone_reference_tables(session_factory):
    """전략 카탈로그·종목명 번역을 개발 DB에서 읽어 격리 DB에 복사한다.

    strategies/stock_translations는 마이그레이션이 아니라 개발 DB에만 적재돼 있어
    create_all만으로는 비어 있다. 이 두 테이블을 읽는 테스트(예: 전략 번역값 검증)가
    빈 카탈로그를 보고 무의미하게 통과하거나 실패하지 않도록 읽기 전용으로 복제한다.
    쓰기는 격리 DB에만 남으므로 개발 DB는 그대로 보존된다.
    """
    import sqlite3

    from app.core import models
    from app.core.database import IS_SQLITE_DATABASE, db_path

    if not IS_SQLITE_DATABASE or not os.path.exists(db_path):
        return

    try:
        source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return

    try:
        source.row_factory = sqlite3.Row
        session = session_factory()
        try:
            for model in (models.Strategy, models.StockTranslation):
                table = model.__table__
                columns = ", ".join(column.name for column in table.columns)
                try:
                    rows = source.execute(f"select {columns} from {table.name}").fetchall()
                except sqlite3.Error:
                    continue
                if rows:
                    session.execute(table.insert(), [dict(row) for row in rows])
            session.commit()
        finally:
            session.close()
    finally:
        source.close()

@pytest.fixture(scope="session")
def isolated_session_factory():
    """테스트 전 구간이 공유하는 인메모리 SQLite 세션 팩토리."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    # 모델 모듈을 먼저 import해야 Base.metadata에 테이블이 등록된다.
    # (모델을 import하지 않는 테스트 파일만 단독 실행하면 빈 스키마가 만들어진다)
    from app.core import models  # noqa: F401
    from app.core.database import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    _clone_reference_tables(factory)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def isolate_default_database(monkeypatch, isolated_session_factory):
    """기본 DB 세션(SessionLocal)을 인메모리 DB로 돌려 개발 DB 쓰기를 차단한다.

    배경 - tests/test_rate_limiter.py가 get_db 오버라이드 없이 TestClient(app)로
    /auth/signup을 호출한 탓에 개발 DB(backend/stockauto.db)에 target_signup_user
    계정이 실제로 생성됐고, 2026-08-15과 2026-08-23 두 차례 관리자 사용자 목록의
    "계정 1 : 전략 1" 전제를 깨뜨렸다. 테스트 파일마다 오버라이드를 붙이는 방식은
    새 파일이 생기면 다시 뚫리므로, 기본 세션 자체가 개발 DB를 가리키지 않게 한다.

    get_db()는 호출 시점에 app.core.database의 전역 SessionLocal을 읽으므로
    이 패치만으로 FastAPI 의존성 경로까지 함께 격리된다. 함수 안에서 지연 import하는
    모듈도 호출 시점에 패치된 속성을 읽는다. 자체 엔진과
    dependency_overrides를 구성하는 테스트는 별도 FastAPI 인스턴스를 쓰므로 영향이 없다.
    """
    import sys

    import app.core.database as database_module

    original_factory = database_module.SessionLocal
    monkeypatch.setattr(database_module, "SessionLocal", isolated_session_factory)

    # `from app.core.database import SessionLocal`로 원본을 자기 전역에 묶어둔 모듈은
    # app.core.database만 갈아끼워도 여전히 개발 DB를 잡는다(앱 모듈 13개 + 테스트 모듈).
    # 목록을 손으로 관리하면 새 모듈이 생길 때마다 다시 뚫리므로 원본을 참조하는 모듈을 전수 교체한다.
    for module in list(sys.modules.values()):
        if module is None or module is database_module:
            continue
        if getattr(module, "SessionLocal", None) is original_factory:
            monkeypatch.setattr(module, "SessionLocal", isolated_session_factory)


@pytest.fixture(scope="session", autouse=True)
def guard_dev_database_untouched():
    """세션 전후로 개발 DB 주요 테이블의 행 수를 비교해 오염을 즉시 드러낸다.

    격리 픽스처가 커버하지 못하는 새 경로(직접 engine 생성 등)로 개발 DB에 쓰기가
    발생하면 조용히 넘어가지 않고 테스트 세션 자체를 실패시킨다.
    """
    import sqlite3

    from app.core.database import IS_SQLITE_DATABASE, db_path

    # 실행 중인 봇이 계속 쓰는 테이블(trade_logs, action_logs, account_equity_snapshots)은
    # 넣지 않는다. 개발 서버가 떠 있는 상태에서 테스트를 돌리면 봇의 정상 매매가
    # "테스트가 개발 DB를 오염시켰다"로 오탐된다(2026-08-24 실제 발생: 테스트 실행 중
    # user 13의 체결 1건이 기록돼 세션이 실패했다). 여기 남기는 것은 봇이 평시에
    # 건드리지 않는 테이블뿐이다.
    watched_tables = ("users", "stock_translations", "strategies")

    def _snapshot():
        if not IS_SQLITE_DATABASE or not os.path.exists(db_path):
            return None
        try:
            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5) as conn:
                return {
                    table: conn.execute(f"select count(*) from {table}").fetchone()[0]
                    for table in watched_tables
                }
        except sqlite3.Error:
            return None

    before = _snapshot()
    yield
    after = _snapshot()
    if before is not None and after is not None:
        changed = {
            table: (before[table], after[table])
            for table in watched_tables
            if before[table] != after[table]
        }
        assert not changed, (
            f"테스트가 개발 DB를 변경했다(테이블: 실행 전 -> 실행 후): {changed}. "
            "기본 SessionLocal을 우회해 개발 DB에 쓰는 경로가 있는지 확인하라."
        )
