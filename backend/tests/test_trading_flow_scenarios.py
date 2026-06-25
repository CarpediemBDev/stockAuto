from types import SimpleNamespace

import pytest

import app.bot.multi_strategy_manager as strategy_module
import app.bot.scheduler as scheduler
from app.core.models import Holding, TradeLog, UserSettings


class FakeQuery:
    def __init__(self, items=None, first_value=None, count_value=None):
        self.items = list(items or [])
        self.first_value = first_value
        self.count_value = count_value

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return list(self.items)

    def first(self):
        if self.first_value is not None:
            return self.first_value
        return self.items[0] if self.items else None

    def count(self):
        if self.count_value is not None:
            return self.count_value
        return len(self.items)


class FakeDb:
    def __init__(self, user_settings=None, holdings=None):
        self.user_settings = user_settings
        self.holdings = list(holdings or [])
        self.added = []
        self.deleted = []
        self.trade_logs = []
        self.commit_count = 0
        self.rollback_count = 0
        self.closed = False

    def query(self, model):
        if model is UserSettings:
            return FakeQuery(first_value=self.user_settings)
        if model is Holding:
            return FakeQuery(items=self.holdings)
        if model is TradeLog:
            return FakeQuery(items=self.trade_logs)
        return FakeQuery()

    def add(self, item):
        self.added.append(item)
        if isinstance(item, Holding):
            self.holdings.append(item)
        elif isinstance(item, TradeLog):
            self.trade_logs.append(item)

    def delete(self, item):
        self.deleted.append(item)
        if item in self.holdings:
            self.holdings.remove(item)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        self.closed = True

    def expunge_all(self):
        pass

    def merge(self, instance):
        return instance


class FakeBroker:
    def __init__(self, holdings_payload=None, buy_result=None, sell_result=None):
        self.holdings_payload = list(holdings_payload or [])
        self.buy_result = buy_result or {
            "success": True,
            "filled_price": 100.0,
            "filled_qty": 10,
            "order_no": "BUY-1",
        }
        self.sell_result = sell_result or {
            "success": True,
            "filled_price": 100.0,
            "filled_qty": 3,
            "order_no": "SELL-1",
        }
        self.buy_calls = []
        self.sell_calls = []

    def get_holdings(self, exchange_rate=None):
        return list(self.holdings_payload)

    def get_account_balance(self, exchange_rate=None):
        return {
            "total_asset": 15_000_000.0,
            "cash_balance": 15_000_000.0,
        }

    def get_order_metadata(self, ticker, session):
        return {"exchange_code": "NASD", "order_division": "00"}

    def buy_order(self, ticker, quantity, price=None, session="REGULAR_MARKET"):
        self.buy_calls.append((ticker, quantity, price))
        return dict(self.buy_result)

    def sell_order(self, ticker, quantity, price=None, session="REGULAR_MARKET"):
        self.sell_calls.append((ticker, quantity, price))
        return dict(self.sell_result)


class FakeStrategy:
    name = "FakeStrategy"
    base_allocation_pct = 0.1
    min_allocation_usd = 0.0
    min_smart_exit_profit = 999.0

    def __init__(self, entry_score=50):
        self.entry_score = entry_score

    def calculate_score(self, data, sentiment, is_entry=True):
        return self.entry_score if is_entry else 0

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
    SLOTS = {"slot": {"prefix": "slot_", "weight": 1.0, "name": "FakeStrategy", "strategy_key": "regime_switching"}}

    def __init__(self, strategy):
        self.strategies = {"slot": strategy}

    def get_focused_tickers(self, all_signals):
        return [signal["ticker"] for signal in all_signals]

    def calculate_slots_allocation(self, total_asset_usd, cash_balance_usd, holdings, sentiment, session="REGULAR_MARKET"):
        return {
            "slot": {
                "cash_balance": cash_balance_usd,
                "total_asset": total_asset_usd,
                "prefix": "slot_",
            }
        }


def make_user_settings():
    return SimpleNamespace(
        user_id=1,
        is_running=True,
        trade_mode="SIMULATED",
        strategy_type="regime_switching",
    )


def make_signal(price=100.0):
    return {
        "ticker": "AAPL",
        "name": "Apple",
        "price": price,
        "details": {},
    }


def install_flow_fakes(monkeypatch, fake_db, fake_broker, strategy, realtime_price=100.0):
    logs = []
    messages = []

    async def fake_safe_broker_call(func, *args, **kwargs):
        return func(*args, **kwargs)

    async def fake_get_realtime_price(ticker):
        return realtime_price

    monkeypatch.setattr(scheduler, "SessionLocal", lambda: fake_db)
    monkeypatch.setattr(scheduler, "get_broker_client", lambda settings: fake_broker)
    monkeypatch.setattr(strategy_module, "MultiStrategyManager", lambda strategy_type="regime_switching": FakeStrategyManager(strategy))
    monkeypatch.setattr(scheduler, "safe_broker_call", fake_safe_broker_call)
    monkeypatch.setattr(scheduler, "get_realtime_price", fake_get_realtime_price)
    monkeypatch.setattr(scheduler, "has_recent_sell", lambda *args, **kwargs: False)
    monkeypatch.setattr(scheduler, "log_action", lambda _db, _user_id, message, level="INFO": logs.append((level, message)))
    monkeypatch.setattr(scheduler, "send_message_async", lambda user_id, message: messages.append((user_id, message)))

    return logs, messages


@pytest.mark.asyncio
async def test_run_user_trading_flow_records_successful_new_buy(monkeypatch):
    signal = make_signal()
    fake_db = FakeDb(user_settings=make_user_settings())
    fake_broker = FakeBroker()
    logs, messages = install_flow_fakes(monkeypatch, fake_db, fake_broker, FakeStrategy())

    await scheduler.run_user_trading_flow(
        user_id=1,
        signal_map={"AAPL": signal},
        all_signals=[signal],
        exchange_rate=1500.0,
        sentiment="BULLISH",
        session="REGULAR_MARKET",
    )

    assert fake_broker.buy_calls == [("AAPL", 10, 100.0)]
    assert fake_broker.sell_calls == []
    assert fake_db.closed is True
    assert fake_db.rollback_count == 0
    assert len(fake_db.holdings) == 1

    holding = fake_db.holdings[0]
    assert holding.ticker == "AAPL"
    assert holding.strategy_type == "slot"
    assert holding.ticker_name == "Apple"
    assert holding.avg_price == 100.0
    assert holding.quantity == 10
    assert holding.buy_stage == 3
    assert any("SUCCESS: AAPL (slot) purchased" in message for _level, message in logs)
    assert any("BUY-1" in message for _user_id, message in messages)


@pytest.mark.asyncio
async def test_run_user_trading_flow_skips_holding_write_when_buy_fails(monkeypatch):
    signal = make_signal()
    fake_db = FakeDb(user_settings=make_user_settings())
    fake_broker = FakeBroker(
        buy_result={
            "success": False,
            "message": "broker rejected",
        }
    )
    logs, messages = install_flow_fakes(monkeypatch, fake_db, fake_broker, FakeStrategy())

    await scheduler.run_user_trading_flow(
        user_id=1,
        signal_map={"AAPL": signal},
        all_signals=[signal],
        exchange_rate=1500.0,
        sentiment="BULLISH",
        session="REGULAR_MARKET",
    )

    assert fake_broker.buy_calls == [("AAPL", 10, 100.0)]
    assert fake_db.holdings == []
    assert not any(isinstance(item, Holding) for item in fake_db.added)
    assert messages == []
    assert any(level == "ERROR" and "BUY FAILED: AAPL (slot) | broker rejected" in message for level, message in logs)


@pytest.mark.asyncio
async def test_run_user_trading_flow_preserves_bot_preference_when_buy_fill_is_unconfirmed(monkeypatch):
    signal = make_signal()
    user_settings = make_user_settings()
    fake_db = FakeDb(user_settings=user_settings)
    fake_broker = FakeBroker(
        buy_result={
            "success": False,
            "order_submitted": True,
            "fill_confirmed": False,
            "status": "PENDING",
            "order_no": "BUY-PENDING",
            "filled_qty": 0,
            "filled_price": 0.0,
            "message": "pending",
        }
    )
    logs, messages = install_flow_fakes(monkeypatch, fake_db, fake_broker, FakeStrategy())

    await scheduler.run_user_trading_flow(
        user_id=1,
        signal_map={"AAPL": signal},
        all_signals=[signal],
        exchange_rate=1500.0,
        sentiment="BULLISH",
        session="REGULAR_MARKET",
    )
    assert fake_db.holdings == []
    assert user_settings.is_running is True
    assert any("ORDER RECONCILIATION" in message for _level, message in logs)
    assert any("BUY-PENDING" in message for _user_id, message in messages)


@pytest.mark.asyncio
async def test_run_user_trading_flow_records_partial_buy_and_preserves_bot_preference(monkeypatch):
    signal = make_signal()
    user_settings = make_user_settings()
    fake_db = FakeDb(user_settings=user_settings)
    fake_broker = FakeBroker(
        buy_result={
            "success": True,
            "order_submitted": True,
            "fill_confirmed": False,
            "status": "PARTIAL",
            "order_no": "BUY-PARTIAL",
            "filled_qty": 4,
            "filled_price": 100.5,
            "message": "partial",
        }
    )
    logs, messages = install_flow_fakes(monkeypatch, fake_db, fake_broker, FakeStrategy())

    await scheduler.run_user_trading_flow(
        user_id=1,
        signal_map={"AAPL": signal},
        all_signals=[signal],
        exchange_rate=1500.0,
        sentiment="BULLISH",
        session="REGULAR_MARKET",
    )

    assert len(fake_db.holdings) == 1
    assert fake_db.holdings[0].quantity == 4
    assert fake_db.holdings[0].avg_price == 100.5
    assert user_settings.is_running is True
    assert any("BUY-PARTIAL" in message for _user_id, message in messages)


@pytest.mark.asyncio
async def test_run_user_trading_flow_records_successful_sell(monkeypatch):
    signal = make_signal()
    holding = Holding(
        user_id=1,
        ticker="AAPL",
        strategy_type="slot",
        ticker_name="Apple",
        avg_price=120.0,
        quantity=3,
        highest_price=120.0,
        regime_mode="BULLISH",
        buy_stage=3,
    )
    fake_db = FakeDb(user_settings=make_user_settings(), holdings=[holding])
    fake_broker = FakeBroker(
        holdings_payload=[
            {
                "ticker": "AAPL",
                "ticker_name": "Apple",
                "quantity": 3,
                "avg_price": 120.0,
            }
        ],
    )
    logs, messages = install_flow_fakes(
        monkeypatch,
        fake_db,
        fake_broker,
        FakeStrategy(entry_score=0),
    )

    scheduler.BREACH_COUNT_CACHE[(1, "AAPL", "slot")] = 1
    try:
        await scheduler.run_user_trading_flow(
            user_id=1,
            signal_map={"AAPL": signal},
            all_signals=[signal],
            exchange_rate=1500.0,
            sentiment="BULLISH",
            session="REGULAR_MARKET",
        )
    finally:
        scheduler.BREACH_COUNT_CACHE.pop((1, "AAPL", "slot"), None)

    assert fake_broker.sell_calls == [("AAPL", 3, 100.0)]
    assert fake_broker.buy_calls == []
    assert fake_db.holdings == []
    assert fake_db.deleted == [holding]
    assert len(fake_db.trade_logs) == 1

    trade_log = fake_db.trade_logs[0]
    assert trade_log.ticker == "AAPL"
    assert trade_log.strategy_type == "slot"
    assert trade_log.trade_type == "SELL"
    assert trade_log.price == 100.0
    assert trade_log.quantity == 3
    assert trade_log.order_no == "SELL-1"
    assert trade_log.realized_pnl < 0
    assert any("SUCCESS: AAPL (slot) sold" in message for _level, message in logs)
    assert any("SELL-1" in message for _user_id, message in messages)


@pytest.mark.asyncio
async def test_run_user_trading_flow_preserves_bot_preference_without_deleting_unconfirmed_sell(monkeypatch):
    signal = make_signal()
    user_settings = make_user_settings()
    holding = Holding(
        user_id=1,
        ticker="AAPL",
        strategy_type="slot",
        ticker_name="Apple",
        avg_price=120.0,
        quantity=5,
        highest_price=120.0,
        regime_mode="BULLISH",
        buy_stage=3,
    )
    fake_db = FakeDb(user_settings=user_settings, holdings=[holding])
    fake_broker = FakeBroker(
        holdings_payload=[
            {
                "ticker": "AAPL",
                "ticker_name": "Apple",
                "quantity": 5,
                "avg_price": 120.0,
            }
        ],
        sell_result={
            "success": False,
            "order_submitted": True,
            "fill_confirmed": False,
            "status": "PENDING",
            "order_no": "SELL-PENDING",
            "filled_qty": 0,
            "filled_price": 0.0,
            "message": "pending",
        },
    )
    logs, messages = install_flow_fakes(
        monkeypatch,
        fake_db,
        fake_broker,
        FakeStrategy(entry_score=0),
    )

    scheduler.BREACH_COUNT_CACHE[(1, "AAPL", "slot")] = 1
    try:
        await scheduler.run_user_trading_flow(
            user_id=1,
            signal_map={"AAPL": signal},
            all_signals=[signal],
            exchange_rate=1500.0,
            sentiment="BULLISH",
            session="REGULAR_MARKET",
        )
    finally:
        scheduler.BREACH_COUNT_CACHE.pop((1, "AAPL", "slot"), None)

    assert fake_db.holdings == [holding]
    assert fake_db.deleted == []
    assert fake_db.trade_logs == []
    assert user_settings.is_running is True
    assert any("SELL-PENDING" in message for _user_id, message in messages)


@pytest.mark.asyncio
async def test_run_user_trading_flow_keeps_remaining_quantity_after_partial_sell(monkeypatch):
    signal = make_signal()
    user_settings = make_user_settings()
    holding = Holding(
        user_id=1,
        ticker="AAPL",
        strategy_type="slot",
        ticker_name="Apple",
        avg_price=120.0,
        quantity=5,
        highest_price=120.0,
        regime_mode="BULLISH",
        buy_stage=3,
    )
    fake_db = FakeDb(user_settings=user_settings, holdings=[holding])
    fake_broker = FakeBroker(
        holdings_payload=[
            {
                "ticker": "AAPL",
                "ticker_name": "Apple",
                "quantity": 5,
                "avg_price": 120.0,
            }
        ],
        sell_result={
            "success": True,
            "order_submitted": True,
            "fill_confirmed": False,
            "status": "PARTIAL",
            "order_no": "SELL-PARTIAL",
            "filled_qty": 2,
            "filled_price": 100.0,
            "message": "partial",
        },
    )
    logs, messages = install_flow_fakes(
        monkeypatch,
        fake_db,
        fake_broker,
        FakeStrategy(entry_score=0),
    )

    scheduler.BREACH_COUNT_CACHE[(1, "AAPL", "slot")] = 1
    try:
        await scheduler.run_user_trading_flow(
            user_id=1,
            signal_map={"AAPL": signal},
            all_signals=[signal],
            exchange_rate=1500.0,
            sentiment="BULLISH",
            session="REGULAR_MARKET",
        )
    finally:
        scheduler.BREACH_COUNT_CACHE.pop((1, "AAPL", "slot"), None)

    assert holding.quantity == 3
    assert fake_db.deleted == []
    assert len(fake_db.trade_logs) == 1
    assert fake_db.trade_logs[0].quantity == 2
    assert any("partially sold" in message for _level, message in logs)
    assert any("SELL-PARTIAL" in message for _user_id, message in messages)


@pytest.mark.asyncio
async def test_symbol_lock_contention_does_not_create_broker_order_intent(monkeypatch):
    signal = make_signal()
    user_settings = make_user_settings()
    user_settings.trade_mode = "MOCK"
    fake_db = FakeDb(user_settings=user_settings)
    fake_broker = FakeBroker()
    install_flow_fakes(monkeypatch, fake_db, fake_broker, FakeStrategy())

    async def busy_symbol_lock(*_args, **_kwargs):
        return None

    def fail_if_intent_created(*_args, **_kwargs):
        raise AssertionError("Order intent must not be created before acquiring the symbol lock")

    monkeypatch.setattr(scheduler, "acquire_symbol_order_lock", busy_symbol_lock)
    monkeypatch.setattr(scheduler, "create_order_intent", fail_if_intent_created)

    await scheduler.run_user_trading_flow(
        user_id=1,
        signal_map={"AAPL": signal},
        all_signals=[signal],
        exchange_rate=1500.0,
        sentiment="BULLISH",
        session="REGULAR_MARKET",
    )

    assert fake_broker.buy_calls == []
    assert fake_db.added == []


@pytest.mark.asyncio
async def test_redis_unavailable_fails_closed_before_opening_user_session(monkeypatch):
    async def unavailable_user_lock(*_args, **_kwargs):
        raise scheduler.RedisLockUnavailable("redis unavailable")

    monkeypatch.setattr(scheduler, "acquire_user_operation_lock", unavailable_user_lock)
    monkeypatch.setattr(
        scheduler,
        "SessionLocal",
        lambda: (_ for _ in ()).throw(AssertionError("DB session must not open")),
    )

    await scheduler.run_user_trading_flow(
        user_id=1,
        signal_map={},
        all_signals=[],
        exchange_rate=1500.0,
        sentiment="NEUTRAL",
        session="REGULAR_MARKET",
    )
