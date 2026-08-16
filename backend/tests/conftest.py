import pytest


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

