import pytest

import app.core.locks as locks


@pytest.mark.asyncio
async def test_symbol_lock_keys_are_isolated_by_user(monkeypatch):
    captured_keys = []

    async def fake_acquire(key, request_id, ttl_seconds):
        captured_keys.append((key, request_id, ttl_seconds))
        return object()

    monkeypatch.setattr(locks, "_acquire_lease", fake_acquire)

    first = await locks.acquire_symbol_order_lock(1, "aapl", "request-1")
    second = await locks.acquire_symbol_order_lock(2, "AAPL", "request-2")

    assert first is not None
    assert second is not None
    assert captured_keys[0][0] == "lock:order_submit:1:AAPL"
    assert captured_keys[1][0] == "lock:order_submit:2:AAPL"


@pytest.mark.asyncio
async def test_lock_acquisition_returns_none_when_key_is_busy(monkeypatch):
    async def busy_set(*_args, **_kwargs):
        return False

    monkeypatch.setattr(locks, "_call_redis", busy_set)

    lease = await locks.acquire_user_operation_lock(7, "request-7")

    assert lease is None
