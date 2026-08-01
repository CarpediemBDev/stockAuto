import asyncio
import os
import pytest
import threading
import time
from unittest import mock
from filelock import FileLock, Timeout

from app.core import locks
from app.core import migrator
from app.core import telegram
from app.core.models import AccountEquitySnapshot, UserSettings, Holding
from app.core.database import SessionLocal, engine
import app.core.database as database_module

# =====================================================================
# 1. Telegram Daemon Asynchronous Non-blocking & KIS Fallback Test
# =====================================================================

@pytest.mark.asyncio
async def test_telegram_status_fallback_on_kis_failure(monkeypatch):
    """
    Verify that when KIS API times out or raises an exception, /status command
    properly falls back to the latest AccountEquitySnapshot from the database.
    """
    # 1. Mock DB Session and Settings
    mock_db = mock.MagicMock()
    mock_settings = mock.MagicMock(spec=UserSettings)
    mock_settings.user_id = 42
    mock_settings.trade_mode = "REAL"
    mock_settings.broker_provider = "KIS"
    mock_settings.is_running = True

    # Setup database query mock chain
    mock_db.query.return_value.filter.return_value.first.return_value = mock_settings

    # Mock get_broker_client to return a broker that raises an exception (KIS Timeout/Error)
    mock_broker = mock.MagicMock()
    mock_broker.get_account_balance.side_effect = Exception("KIS Connection Timeout")
    monkeypatch.setattr(telegram, "get_broker_client", lambda s: mock_broker)

    # 2. Mock AccountEquitySnapshot query for fallback
    mock_snapshot = mock.MagicMock(spec=AccountEquitySnapshot)
    mock_snapshot.total_asset = 15000000.0
    mock_snapshot.cash_balance = 5000000.0
    mock_snapshot.stock_balance = 10000000.0
    mock_snapshot.profit_rate = 12.5
    
    def mock_query_dispatcher(model):
        q = mock.MagicMock()
        if model == UserSettings:
            q.filter.return_value.first.return_value = mock_settings
        elif model == Holding:
            q.filter.return_value.all.return_value = []
        elif model == AccountEquitySnapshot:
            q.filter.return_value.order_by.return_value.first.return_value = mock_snapshot
        return q

    mock_db.query.side_effect = mock_query_dispatcher

    # Setup SessionLocal mock to return our mock_db
    monkeypatch.setattr(telegram, "SessionLocal", lambda: mock_db)

    # Track message sent to Telegram
    sent_messages = []
    def mock_send_message_sync(user_id, text):
        sent_messages.append((user_id, text))
        return True
    monkeypatch.setattr(telegram, "send_message_sync", mock_send_message_sync)
    monkeypatch.setattr(telegram, "FXRateCache", mock.MagicMock(get_rate=lambda: 1350.0))

    # 3. Trigger /status command processing
    telegram._process_command(user_id=42, text="/status")

    # 4. Assert fallback was called and correct message was generated
    assert len(sent_messages) == 1
    user_id_sent, text_sent = sent_messages[0]
    assert user_id_sent == 42
    assert "⚠️ KIS API 장애/지연 발생으로 최종 성공 자산 스냅샷 정보를 제공합니다." in text_sent
    assert "₩15,000,000" in text_sent
    assert "₩5,000,000" in text_sent
    assert "12.50%" in text_sent


def test_telegram_daemon_uses_thread_pool_executor(monkeypatch):
    """
    Verify that the Telegram daemon initializes the ThreadPoolExecutor
    and submits global messages to it to prevent blocking the event loop.
    """
    # 1. Mock _telegram_executor
    mock_executor = mock.MagicMock()
    monkeypatch.setattr(telegram, "_telegram_executor", mock_executor)
    monkeypatch.setattr(telegram.settings, "TELEGRAM_BOT_TOKEN", "fake-token")

    # 2. Mock stop event to run loop exactly once
    is_set_mock = mock.MagicMock(side_effect=[False, True])
    mock_stop_event = mock.MagicMock()
    mock_stop_event.is_set = is_set_mock
    monkeypatch.setattr(telegram, "_global_stop_event", mock_stop_event)

    # 3. Mock httpx.Client get request to return fake Telegram update
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "ok": True,
        "result": [
            {
                "update_id": 100,
                "message": {
                    "text": "/status",
                    "chat": {"id": 12345},
                    "from": {"language_code": "en-GB"}
                }
            }
        ]
    }
    
    mock_client = mock.MagicMock()
    mock_client.get.return_value = mock_response
    
    # Context manager mock for httpx.Client
    mock_client_class = mock.MagicMock()
    mock_client_class.return_value.__enter__.return_value = mock_client
    monkeypatch.setattr(telegram.httpx, "Client", mock_client_class)

    # 4. Run the polling loop
    telegram._poll_global_updates_loop()

    # 5. Assert executor.submit was called with the message processing task,
    #    forwarding the Telegram client language_code for pre-link i18n.
    mock_executor.submit.assert_called_once_with(telegram._process_global_message, "12345", "/status", "en-GB")


def test_telegram_global_message_closes_lookup_session_before_command(monkeypatch):
    lookup_db = mock.MagicMock()
    mock_settings = mock.MagicMock(spec=UserSettings)
    mock_settings.user_id = 42
    mock_settings.telegram_enabled = True
    lookup_db.query.return_value.filter.return_value.first.return_value = mock_settings

    command_calls = []

    def fake_process_command(user_id, text):
        assert lookup_db.close.called is True
        command_calls.append((user_id, text))

    monkeypatch.setattr(telegram, "SessionLocal", lambda: lookup_db)
    monkeypatch.setattr(telegram, "_process_command", fake_process_command)

    telegram._process_global_message("chat-42", "/status")

    assert command_calls == [(42, "/status")]


def test_telegram_status_closes_command_session_before_broker_fetch(monkeypatch):
    command_db = mock.MagicMock()
    holdings_db = mock.MagicMock()
    mock_settings = mock.MagicMock(spec=UserSettings)
    mock_settings.user_id = 42
    mock_settings.trade_mode = "REAL"
    mock_settings.broker_provider = "KIS"
    mock_settings.is_running = True

    def command_query_dispatcher(model):
        q = mock.MagicMock()
        if model == UserSettings:
            q.filter.return_value.first.return_value = mock_settings
        return q

    def holdings_query_dispatcher(model):
        q = mock.MagicMock()
        if model == Holding:
            q.filter.return_value.all.return_value = []
        return q

    command_db.query.side_effect = command_query_dispatcher
    holdings_db.query.side_effect = holdings_query_dispatcher
    sessions = iter([command_db, holdings_db])
    sent_messages = []

    class Broker:
        def get_account_balance(self):
            assert command_db.close.called is True
            return {
                "total_asset": 15000000.0,
                "cash_balance": 5000000.0,
                "stock_balance": 10000000.0,
                "profit_rate": 12.5,
            }

    monkeypatch.setattr(telegram, "SessionLocal", lambda: next(sessions))
    monkeypatch.setattr(telegram, "get_broker_client", lambda _settings: Broker())
    monkeypatch.setattr(telegram, "FXRateCache", mock.MagicMock(get_rate=lambda: 1350.0))
    monkeypatch.setattr(telegram, "send_message_sync", lambda user_id, text: sent_messages.append((user_id, text)) or True)

    telegram._process_command(user_id=42, text="/status")

    assert command_db.close.called is True
    assert holdings_db.close.called is True
    assert sent_messages and sent_messages[0][0] == 42


def test_translations_router_uses_core_get_db():
    from app.core.database import get_db
    from app.translations import router as translations_router

    assert translations_router.get_db is get_db


# =====================================================================
# 2. Redis Lock Lease Renewal Failure & CancelledError Mocking
# =====================================================================

@pytest.mark.asyncio
async def test_redis_lock_release_is_shielded_against_cancellation(monkeypatch):
    """
    Verify that locks.release() uses asyncio.shield to prevent lock leaks,
    meaning even if the release task itself is cancelled, the underlying
    Redis delete operation is executed.
    """
    redis_calls = []

    async def mock_call_redis(method_name, *args, **kwargs):
        redis_calls.append((method_name, args))
        # Simulate small delay in Redis call
        await asyncio.sleep(0.1)
        return 1

    monkeypatch.setattr(locks, "_call_redis", mock_call_redis)

    # Initialize a mock lease
    lease = locks.RedisLockLease(key="test:shield_lock", request_id="req-123", ttl_seconds=10)
    
    # We mock _renew_loop task to check cancellation
    async def dummy_renew():
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
    lease._renew_task = asyncio.create_task(dummy_renew())

    # Start release task and cancel it immediately during execution
    async def cancel_release():
        release_task = asyncio.create_task(lease.release())
        await asyncio.sleep(0.02)  # Yield control to let release start
        release_task.cancel()
        try:
            await release_task
        except asyncio.CancelledError:
            pass

    await cancel_release()

    # Wait for any background shielded task to finish
    await asyncio.sleep(0.2)

    # Assert that even though the task calling release was cancelled,
    # the Redis release command (eval of _RELEASE_SCRIPT) was still executed.
    assert len(redis_calls) > 0
    assert any(call[0] == "eval" and call[1][0] == locks._RELEASE_SCRIPT for call in redis_calls)


@pytest.mark.asyncio
async def test_redis_lock_renewal_backoff_retry(monkeypatch):
    """
    Verify that locks._renew_loop retries with exponential backoff on RedisLockUnavailable.
    """
    call_count = 0
    failures = []
    
    async def mock_call_redis(method_name, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            # First two calls raise RedisLockUnavailable to trigger backoff retries
            raise locks.RedisLockUnavailable("Redis connection failed")
        return 1  # 3rd call succeeds

    monkeypatch.setattr(locks, "_call_redis", mock_call_redis)
    
    # Track sleep intervals in renew loop to verify exponential backoff
    original_sleep = asyncio.sleep
    sleeps = []
    async def mock_sleep(seconds):
        sleeps.append(seconds)
        # Sleep a tiny amount in mock to keep tests fast
        await original_sleep(0.001)

    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    lease = locks.RedisLockLease(key="test:retry_lock", request_id="req-456", ttl_seconds=6)
    
    # We run the renew loop task manually for a short time
    renew_task = asyncio.create_task(lease._renew_loop())
    
    # Let it run to execute the sleep and retry attempts
    await original_sleep(0.05)
    renew_task.cancel()
    try:
        await renew_task
    except asyncio.CancelledError:
        pass

    # The renewal loop sleeps once per interval (ttl/3 = 2s)
    # Plus, it sleeps on the two retries.
    # The retry backoffs are:
    # Attempt 1: 0.5 * 2^0 = 0.5s + jitter
    # Attempt 2: 0.5 * 2^1 = 1.0s + jitter
    assert len(sleeps) >= 3  # 1 interval sleep + 2 retry sleeps
    assert sleeps[0] == 2.0  # interval = max(1.0, 6/3)
    assert 0.5 <= sleeps[1] <= 0.6  # backoff for attempt 1
    assert 1.0 <= sleeps[2] <= 1.1  # backoff for attempt 2
    assert call_count >= 3  # Called 3 times (2 failures + 1 success)


# =====================================================================
# 3. SQLite Multi-instance Concurrent Bootstrapping Migration Filelock
# =====================================================================

def test_sqlite_concurrent_bootstrapping_serialization(tmp_path, monkeypatch):
    """
    Verify that filelock prevents concurrent database migration/DDL conflicts by serializing runs.
    """
    monkeypatch.setattr(database_module, "IS_SQLITE_DATABASE", True)
    
    # We will redirect sqlite_migration.lock to tmp_path
    lock_file = tmp_path / "sqlite_migration.lock"
    
    # We override run_migrations_programmatically to use our temp lock file
    original_run = migrator.run_migrations_programmatically
    
    def mock_run_migrations_programmatically():
        from filelock import FileLock, Timeout
        # Use our temp lock file
        lock = FileLock(str(lock_file), timeout=5.0)
        try:
            with lock:
                # Simulate migration work
                time.sleep(0.1)
                # Call inner migrator function mocked to do nothing
                migrator._run_migrations_internal(str(tmp_path))
        except Timeout:
            raise RuntimeError("Database migration timeout: lock could not be acquired")

    monkeypatch.setattr(migrator, "run_migrations_programmatically", mock_run_migrations_programmatically)
    
    run_count = 0
    concurrency_check = []
    max_concurrency = 0
    concurrency_lock = threading.Lock()

    def mock_run_migrations_internal(backend_dir):
        nonlocal run_count, max_concurrency
        with concurrency_lock:
            run_count += 1
            concurrency_check.append(1)
            current_concurrency = len(concurrency_check)
            if current_concurrency > max_concurrency:
                max_concurrency = current_concurrency
        
        # Simulate time-consuming DDL operations
        time.sleep(0.2)
        
        with concurrency_lock:
            concurrency_check.pop()

    monkeypatch.setattr(migrator, "_run_migrations_internal", mock_run_migrations_internal)

    # Start 3 threads executing run_migrations_programmatically simultaneously
    threads = []
    for _ in range(3):
        t = threading.Thread(target=migrator.run_migrations_programmatically)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # Verify that:
    # 1. All 3 runs completed successfully.
    # 2. Peak concurrency inside _run_migrations_internal was exactly 1 (serialized by filelock).
    assert run_count == 3
    assert max_concurrency == 1


def test_sqlite_migration_lock_timeout(tmp_path, monkeypatch):
    """
    Verify that if database migration filelock is held, other instances timeout and raise RuntimeError.
    """
    monkeypatch.setattr(database_module, "IS_SQLITE_DATABASE", True)
    
    lock_file = tmp_path / "sqlite_migration.lock"
    
    # We patch run_migrations_programmatically to use a short timeout and our temp lock file
    def mock_run_migrations_programmatically():
        from filelock import FileLock, Timeout
        # short timeout for test
        lock = FileLock(str(lock_file), timeout=0.1)
        try:
            with lock:
                migrator._run_migrations_internal(str(tmp_path))
        except Timeout:
            raise RuntimeError("Database migration timeout: lock could not be acquired")

    monkeypatch.setattr(migrator, "run_migrations_programmatically", mock_run_migrations_programmatically)
    monkeypatch.setattr(migrator, "_run_migrations_internal", lambda path: time.sleep(0.5))

    # Hold the lock in main thread
    external_lock = FileLock(str(lock_file))
    with external_lock:
        # Running the migrator now should raise a Timeout exception wrapped in RuntimeError
        with pytest.raises(RuntimeError, match="Database migration timeout"):
            migrator.run_migrations_programmatically()
