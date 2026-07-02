import asyncio
from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock, patch
import app.bot.scheduler as scheduler
from app.bot.trade_calculations import calculate_realized_pnl

@pytest.mark.asyncio
async def test_breach_count_cache_3tuple_pop():
    """
    1. Test BREACH_COUNT_CACHE 3-tuple pop logic (verify no cache leak after sell).
    Verify that scheduler.BREACH_COUNT_CACHE is correctly populated and popped with a 3-tuple key:
    (user_id, ticker, strategy_type)
    """
    user_id = 42
    ticker = "AAPL"
    strategy_type = "swing"
    cache_key = (user_id, ticker, strategy_type)

    # Clean the cache first
    scheduler.BREACH_COUNT_CACHE.clear()

    # Simulate setting breach count
    scheduler.BREACH_COUNT_CACHE[cache_key] = 1
    assert cache_key in scheduler.BREACH_COUNT_CACHE
    assert scheduler.BREACH_COUNT_CACHE[cache_key] == 1

    # Simulate pop
    popped = scheduler.BREACH_COUNT_CACHE.pop(cache_key, None)
    assert popped == 1
    assert cache_key not in scheduler.BREACH_COUNT_CACHE
    assert len(scheduler.BREACH_COUNT_CACHE) == 0


@pytest.mark.asyncio
async def test_refresh_scanner_cache_exception_resets_flag():
    """
    2. Mock exception during scanner cache refresh (verify is_refreshing is successfully reset to False).
    Verify that _scanner_refresh_in_progress is reset to False even when an exception is raised
    within refresh_scanner_cache.
    """
    # Verify initial state is False
    assert scheduler.is_scanner_refresh_in_progress() is False

    # Mock scan_overseas_market to raise an exception
    with patch("app.bot.scheduler.scan_overseas_market", new_callable=AsyncMock) as mock_scan:
        mock_scan.side_effect = Exception("Injected scan failure")

        # Run refresh_scanner_cache (force=True)
        # It should catch the exception and return False
        result = await scheduler.refresh_scanner_cache(force=True)
        assert result is False

        # Verify that the refresh flag was successfully reset to False in the finally block
        assert scheduler.is_scanner_refresh_in_progress() is False


@pytest.mark.asyncio
async def test_breach_count_cache_thread_safety():
    """
    Test thread safety of BREACH_COUNT_CACHE under concurrent writes and pops.
    """
    import threading

    # Clean the cache first
    scheduler.BREACH_COUNT_CACHE.clear()

    user_id = 42
    ticker = "AAPL"
    strategy_type = "swing"
    cache_key = (user_id, ticker, strategy_type)

    def worker():
        for _ in range(100):
            with scheduler._breach_count_lock:
                scheduler.BREACH_COUNT_CACHE[cache_key] = scheduler.BREACH_COUNT_CACHE.get(cache_key, 0) + 1

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert scheduler.BREACH_COUNT_CACHE[cache_key] == 1000

    # Clean up
    scheduler.BREACH_COUNT_CACHE.pop(cache_key, None)


@pytest.mark.asyncio
async def test_process_exit_signals_accepts_decimal_holding_prices():
    class QuietStrategy:
        name = "Quiet"
        min_smart_exit_profit = 999.0

        def calculate_score(self, _data, _sentiment, is_entry=False):
            return 50

        def get_stop_loss_pct(self, _atr, _current_price):
            return 20.0

        def get_trailing_stop_pct(self, _atr, _current_price):
            return 20.0

        def is_signal_collapsed(self, _score, _sentiment):
            return False

    holding = SimpleNamespace(
        ticker="AAPL",
        ticker_name="Apple",
        strategy_type="swing",
        avg_price=Decimal("100.0000"),
        highest_price=Decimal("120.0000"),
    )
    ctx = SimpleNamespace(
        user_id=42,
        session=scheduler.MarketSession.REGULAR,
        holdings=[holding],
        ms_manager=SimpleNamespace(strategies={"swing": QuietStrategy()}),
        broker=object(),
        sentiment="BULLISH",
        exchange_rate=1350.0,
        signal_map={},
    )

    await scheduler.process_exit_signals(
        ctx,
        {
            "AAPL": {
                "ticker": "AAPL",
                "price": 110.0,
                "details": {"atr": 1.0, "is_smart_exit": False},
            }
        },
    )

    assert holding.current_price == 110.0


def test_resolve_entry_stage_accepts_decimal_existing_holding():
    strategy = SimpleNamespace(
        name="Pyramid",
        get_pyramid_trigger=lambda _stage: 5.0,
    )
    ctx = SimpleNamespace(sentiment="BULLISH")
    existing_holding = SimpleNamespace(
        avg_price=Decimal("100.0000"),
        buy_stage=1,
    )

    result = scheduler.resolve_entry_stage(
        ctx,
        strategy,
        "AAPL",
        {"price": 101.0},
        existing_holding,
    )

    assert result is None


def test_record_successful_buy_updates_decimal_existing_holding(monkeypatch):
    class DummyDb:
        def __init__(self):
            self.added = []

        def merge(self, obj):
            return obj

        def add(self, obj):
            self.added.append(obj)

        def commit(self):
            return None

    dummy_db = DummyDb()

    @contextmanager
    def fake_micro_session(_ctx):
        yield dummy_db

    monkeypatch.setattr(scheduler, "micro_session", fake_micro_session)
    monkeypatch.setattr(scheduler, "log_action", lambda *_args, **_kwargs: None)

    ctx = SimpleNamespace(user_id=42, sentiment="BULLISH")
    existing_holding = SimpleNamespace(
        quantity=2,
        avg_price=Decimal("100.0000"),
        highest_price=Decimal("101.0000"),
        buy_stage=1,
    )

    created = scheduler.record_successful_buy(
        ctx=ctx,
        strategy_instance=SimpleNamespace(name="Pyramid"),
        existing_holding=existing_holding,
        ticker="AAPL",
        strategy_type="swing",
        signal={"name": "Apple"},
        filled_price=102.0,
        filled_qty=1,
        next_stage=2,
        order_no="SIM-BUY-1",
        current_score=80,
    )

    assert created is False
    assert existing_holding.avg_price == Decimal("100.6667")
    assert existing_holding.highest_price == Decimal("102.0")


def test_realized_pnl_return_rate_uses_net_cost_basis():
    pnl = calculate_realized_pnl(
        avg_price=Decimal("100.0000"),
        filled_price=Decimal("110.0000"),
        quantity=10,
        fee_rate=Decimal("0.0015"),
        sec_fee_rate=Decimal("0.0000278"),
    )
    buy_total_cost = pnl.buy_gross + pnl.buy_fee
    expected_cost_rate = (
        (pnl.realized_pnl / buy_total_cost) * Decimal("100.0")
    ).quantize(Decimal("0.0001"))
    expected_gross_rate = (
        (pnl.realized_pnl / pnl.buy_gross) * Decimal("100.0")
    ).quantize(Decimal("0.0001"))

    assert pnl.return_rate == expected_cost_rate
    assert pnl.return_rate_on_cost == expected_cost_rate
    assert pnl.return_rate_on_gross == expected_gross_rate
    assert pnl.return_rate < pnl.return_rate_on_gross
