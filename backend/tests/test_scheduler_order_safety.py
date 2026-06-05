from types import SimpleNamespace

import pytest

import app.bot.scheduler as scheduler


class FakeQuery:
    def __init__(self, count_value=0, first_value=None):
        self.count_value = count_value
        self.first_value = first_value

    def filter(self, *args, **kwargs):
        return self

    def count(self):
        return self.count_value

    def first(self):
        return self.first_value


class FakeDb:
    def __init__(self):
        self.added = []
        self.deleted = []
        self.commit_count = 0

    def query(self, *args, **kwargs):
        return FakeQuery()

    def add(self, item):
        self.added.append(item)

    def delete(self, item):
        self.deleted.append(item)

    def commit(self):
        self.commit_count += 1


class FakeBroker:
    def __init__(self):
        self.buy_calls = []
        self.sell_calls = []

    def buy_order(self, *args, **kwargs):
        self.buy_calls.append((args, kwargs))
        raise AssertionError("buy_order must not be called while REAL safety lock is active")

    def sell_order(self, *args, **kwargs):
        self.sell_calls.append((args, kwargs))
        raise AssertionError("sell_order must not be called while REAL safety lock is active")


class FakeStrategy:
    name = "FakeStrategy"
    base_allocation_pct = 0.1
    min_allocation_usd = 0.0
    min_smart_exit_profit = 999.0

    def calculate_score(self, data, sentiment, is_entry=True):
        return 100 if is_entry else 0

    def get_cutoff_score(self, sentiment):
        return 50

    def get_initial_entry_factor(self, sentiment):
        return 1.0

    def get_pyramid_trigger(self, stage):
        return 999.0

    def get_stop_loss_pct(self, atr, current_price):
        return 1.0

    def get_trailing_stop_pct(self, atr, current_price):
        return 1.0

    def is_signal_collapsed(self, score, sentiment):
        return False


class FakeStrategyManager:
    def __init__(self):
        self.strategies = {"slot": FakeStrategy()}

    def get_focused_tickers(self, all_signals):
        return [signal["ticker"] for signal in all_signals]

    def make_prefixed_ticker(self, slot_key, ticker):
        return f"{slot_key}_{ticker}"

    def get_slot_by_holding_ticker(self, ticker):
        prefix, clean = ticker.split("_", 1)
        return prefix, clean


def make_locked_context(db=None, broker=None, holdings=None):
    signals = [{"ticker": "AAPL", "name": "Apple", "price": 100.0, "details": {}}]
    return SimpleNamespace(
        db=db or FakeDb(),
        user_id=1,
        session="REGULAR_MARKET",
        sentiment="BULLISH",
        exchange_rate=1500.0,
        holdings=holdings or [],
        broker=broker or FakeBroker(),
        real_order_locked=True,
        ms_manager=FakeStrategyManager(),
        all_signals=signals,
    )


@pytest.mark.asyncio
async def test_process_entry_signals_blocks_buy_order_when_real_safety_lock_is_on(monkeypatch):
    db = FakeDb()
    broker = FakeBroker()
    ctx = make_locked_context(db=db, broker=broker)
    log_messages = []

    async def fail_if_safe_broker_call_runs(*args, **kwargs):
        raise AssertionError("safe_broker_call must not run for a locked REAL buy order")

    async def fake_get_realtime_price(ticker):
        return 100.0

    monkeypatch.setattr(scheduler, "log_action", lambda _db, _user_id, message, level="INFO": log_messages.append((level, message)))
    monkeypatch.setattr(scheduler, "has_recent_sell", lambda *args, **kwargs: False)
    monkeypatch.setattr(scheduler, "get_realtime_price", fake_get_realtime_price)
    monkeypatch.setattr(scheduler, "safe_broker_call", fail_if_safe_broker_call_runs)

    processed = await scheduler.process_entry_signals(
        ctx,
        target_signals=ctx.all_signals,
        slot_allocations={"slot": {"cash_balance": 10000.0, "total_asset": 100000.0, "prefix": "slot_"}},
    )

    assert processed is True
    assert broker.buy_calls == []
    assert any(level == "ERROR" and "BUY BLOCKED" in message for level, message in log_messages)


@pytest.mark.asyncio
async def test_process_exit_signals_blocks_sell_order_when_real_safety_lock_is_on(monkeypatch):
    db = FakeDb()
    broker = FakeBroker()
    holding = SimpleNamespace(
        ticker="slot_AAPL",
        ticker_name="Apple",
        avg_price=120.0,
        highest_price=120.0,
        quantity=3,
    )
    ctx = make_locked_context(db=db, broker=broker, holdings=[holding])
    log_messages = []

    async def fail_if_safe_broker_call_runs(*args, **kwargs):
        raise AssertionError("safe_broker_call must not run for a locked REAL sell order")

    scheduler.BREACH_COUNT_CACHE[(ctx.user_id, holding.ticker)] = 1
    monkeypatch.setattr(scheduler, "log_action", lambda _db, _user_id, message, level="INFO": log_messages.append((level, message)))
    monkeypatch.setattr(scheduler, "safe_broker_call", fail_if_safe_broker_call_runs)

    try:
        await scheduler.process_exit_signals(
            ctx,
            target_signal_map={"AAPL": {"ticker": "AAPL", "name": "Apple", "price": 100.0, "details": {}}},
        )
    finally:
        scheduler.BREACH_COUNT_CACHE.pop((ctx.user_id, holding.ticker), None)

    assert broker.sell_calls == []
    assert db.deleted == []
    assert any(level == "ERROR" and "SELL BLOCKED" in message for level, message in log_messages)
