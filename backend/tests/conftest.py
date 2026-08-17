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

