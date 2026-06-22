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
