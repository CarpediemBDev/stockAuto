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
    SLOTS = {"slot": {"prefix": "slot_"}}
    TARGET_TICKERS = ["AAPL"]

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

    def make_prefixed_ticker(self, slot_key, ticker):
        return f"{slot_key}_{ticker}"

    def get_slot_by_holding_ticker(self, ticker):
        if "_" not in ticker:
            return None
        slot_key, clean_ticker = ticker.split("_", 1)
        return slot_key, clean_ticker


def make_user_settings():
    return SimpleNamespace(
        user_id=1,
        is_running=True,
        trade_mode="SIMULATED",
        strategy_type="regime_switching",
        is_real_enabled=False,
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
    monkeypatch.setattr(scheduler, "is_real_order_locked", lambda settings: False)
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
    assert holding.ticker == "slot_AAPL"
    assert holding.ticker_name == "Apple"
    assert holding.avg_price == 100.0
    assert holding.quantity == 10
    assert holding.buy_stage == 3
    assert any("SUCCESS: slot_AAPL purchased" in message for _level, message in logs)
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
    assert any(level == "ERROR" and "BUY FAILED: slot_AAPL | broker rejected" in message for level, message in logs)


@pytest.mark.asyncio
async def test_run_user_trading_flow_records_successful_sell(monkeypatch):
    signal = make_signal()
    holding = Holding(
        user_id=1,
        ticker="slot_AAPL",
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

    scheduler.BREACH_COUNT_CACHE[(1, "slot_AAPL")] = 1
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
        scheduler.BREACH_COUNT_CACHE.pop((1, "slot_AAPL"), None)

    assert fake_broker.sell_calls == [("AAPL", 3, 100.0)]
    assert fake_broker.buy_calls == []
    assert fake_db.holdings == []
    assert fake_db.deleted == [holding]
    assert len(fake_db.trade_logs) == 1

    trade_log = fake_db.trade_logs[0]
    assert trade_log.ticker == "slot_AAPL"
    assert trade_log.trade_type == "SELL"
    assert trade_log.price == 100.0
    assert trade_log.quantity == 3
    assert trade_log.order_no == "SELL-1"
    assert trade_log.realized_pnl < 0
    assert any("SUCCESS: slot_AAPL sold" in message for _level, message in logs)
    assert any("SELL-1" in message for _user_id, message in messages)
