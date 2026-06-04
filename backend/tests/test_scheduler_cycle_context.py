from types import SimpleNamespace

import pytest

import app.bot.scheduler as scheduler
from app.core.models import Holding, UserSettings


class FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def distinct(self):
        return self

    def all(self):
        return self._rows


class FakeSession:
    def __init__(self, active_users, holding_user_ids):
        self.active_users = active_users
        self.holding_user_ids = holding_user_ids
        self.closed = False
        self.rolled_back = False

    def query(self, *entities):
        first_entity = entities[0] if entities else None
        if first_entity is UserSettings:
            return FakeQuery(self.active_users)
        if first_entity is Holding.user_id:
            return FakeQuery([(user_id,) for user_id in self.holding_user_ids])
        return FakeQuery([])

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_async_trading_loop_injects_cycle_context_once(monkeypatch):
    active_users = [
        SimpleNamespace(user_id=1, is_running=True),
        SimpleNamespace(user_id=2, is_running=True),
    ]
    fake_db = FakeSession(active_users=active_users, holding_user_ids=[])
    flow_calls = []
    sentiment_calls = 0
    fx_calls = 0

    async def fake_check_market_sentiment():
        nonlocal sentiment_calls
        sentiment_calls += 1
        return "BULLISH"

    def fake_get_rate():
        nonlocal fx_calls
        fx_calls += 1
        return 1517.56

    async def fake_run_user_trading_flow(user_id, signal_map, all_signals, exchange_rate, sentiment, market_open):
        flow_calls.append(
            {
                "user_id": user_id,
                "signal_map": signal_map,
                "all_signals": all_signals,
                "exchange_rate": exchange_rate,
                "sentiment": sentiment,
                "market_open": market_open,
            }
        )

    scheduler.is_processing = False
    scheduler.latest_scanned_signals = [{"ticker": "QQQ", "price": 100.0}]

    monkeypatch.setattr(scheduler, "SessionLocal", lambda: fake_db)
    monkeypatch.setattr(scheduler, "is_us_market_open", lambda: True)
    monkeypatch.setattr(scheduler, "check_market_sentiment", fake_check_market_sentiment)
    monkeypatch.setattr(scheduler.FXRateCache, "get_rate", fake_get_rate)
    monkeypatch.setattr(scheduler, "run_user_trading_flow", fake_run_user_trading_flow)

    await scheduler.async_trading_loop()

    assert sentiment_calls == 1
    assert fx_calls == 1
    assert fake_db.closed is True
    assert fake_db.rolled_back is False
    assert [call["user_id"] for call in flow_calls] == [1, 2]
    assert all(call["exchange_rate"] == 1517.56 for call in flow_calls)
    assert all(call["sentiment"] == "BULLISH" for call in flow_calls)
    assert all(call["market_open"] is True for call in flow_calls)
    assert all(call["signal_map"] == {"QQQ": {"ticker": "QQQ", "price": 100.0}} for call in flow_calls)


def test_start_scheduler_registers_swing_prediction_jobs(monkeypatch):
    class FakeScheduler:
        running = False

        def __init__(self):
            self.jobs = []
            self.started = False

        def add_job(self, func, trigger, **kwargs):
            self.jobs.append({"func": func, "trigger": trigger, **kwargs})

        def start(self):
            self.started = True
            self.running = True

    fake_scheduler = FakeScheduler()
    monkeypatch.setattr(scheduler, "scheduler", fake_scheduler)

    scheduler.start_scheduler()

    job_by_id = {job["id"]: job for job in fake_scheduler.jobs}
    assert fake_scheduler.started is True
    assert job_by_id["swing_prediction_startup_job"]["trigger"] == "date"
    assert job_by_id["swing_prediction_startup_job"]["func"] is scheduler.swing_prediction_cache_wrapper
    assert job_by_id["swing_prediction_daily_job"]["trigger"] == "cron"
    assert job_by_id["swing_prediction_daily_job"]["hour"] == 8
    assert job_by_id["swing_prediction_daily_job"]["minute"] == 0
    assert job_by_id["swing_prediction_daily_job"]["func"] is scheduler.swing_prediction_cache_wrapper
