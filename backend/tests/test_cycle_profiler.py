"""매매 사이클 구간 계측의 회귀 테스트.

2026-09 사이클 회귀는 `[Cycle] Duration` 총합만으로 원인을 좁히지 못했다. 계측이 틀리면
그 위에서 내린 결론도 틀리므로, 여기서는 측정 장치가 정직한지를 고정한다.

  1. 사이클 밖에서는 아무것도 기록하지 않는다 - 계측 대상 함수는 사이클 밖에서도 불린다
  2. ContextVar로 gather의 사용자별 태스크와 to_thread 작업까지 같은 프로파일에 모인다
  3. 이벤트 루프를 붙잡은 동기 작업은 loop.blocked로 드러난다
  4. 감시 태스크는 사이클이 끝나면 반드시 회수된다 - 남으면 drain이 사이클마다 수 초를 잃는다
  5. 매매 흐름이 돈 사이클에만 요약을 남긴다 - 휴장 표본이 기준선을 오염시킨 전례가 있다
"""

import asyncio
import time
from types import SimpleNamespace

import pytest

import app.bot.scheduler as scheduler
from app.bot.cycle_profiler import (
    LOOP_BLOCKED_PHASE,
    CycleProfile,
    current_profile,
    end_cycle_profile,
    monitor_loop_lag,
    phase,
    start_cycle_profile,
    stop_loop_lag_monitor,
)
from tests.test_scheduler_cycle_context import FakeSession


# ======================================================================================
# 1. 프로파일 단위
# ======================================================================================

def test_phase_is_a_no_op_outside_a_cycle():
    """프로파일이 켜지지 않은 컨텍스트에서는 기록하지도 실패하지도 않는다."""
    assert current_profile() is None
    with phase("user.anything"):
        pass
    assert current_profile() is None


def test_phase_accumulates_total_count_and_max():
    profile, token = start_cycle_profile()
    try:
        for seconds in (0.01, 0.03, 0.02):
            with phase("user.exit_signals"):
                time.sleep(seconds)
    finally:
        end_cycle_profile(token)

    stat = profile.snapshot()["user.exit_signals"]
    assert stat.count == 3
    assert stat.total_seconds >= 0.06
    assert 0.03 <= stat.max_seconds < stat.total_seconds
    assert current_profile() is None, "사이클 종료 후 프로파일이 컨텍스트에 남았다"


def test_phase_records_even_when_the_block_raises():
    """구간 안에서 예외가 나도 소요 시간은 남는다. 실패 경로가 느린 경우를 놓치면 안 된다."""
    profile, token = start_cycle_profile()
    try:
        with pytest.raises(RuntimeError):
            with phase("user.sync_broker_holdings"):
                raise RuntimeError("broker down")
    finally:
        end_cycle_profile(token)
    assert profile.snapshot()["user.sync_broker_holdings"].count == 1


def test_summary_orders_by_total_time():
    profile = CycleProfile()
    profile.add("user.entry_signals", 1.0)
    profile.add("user.exit_signals", 5.0)
    profile.add("cycle.market_sentiment", 0.5)
    summary = profile.summary()
    assert summary.index("user.exit_signals") < summary.index("user.entry_signals")
    assert summary.index("user.entry_signals") < summary.index("cycle.market_sentiment")


def test_has_user_flows_distinguishes_early_return_cycles():
    """휴장 등으로 사용자 흐름이 돌지 않은 사이클은 요약 대상이 아니다."""
    profile = CycleProfile()
    profile.add("cycle.load_active_users", 0.01)
    assert profile.has_user_flows() is False
    profile.add("user.lock_acquire", 0.01)
    assert profile.has_user_flows() is True


@pytest.mark.asyncio
async def test_profile_propagates_into_gather_tasks_and_threads():
    """gather가 만드는 태스크와 to_thread 작업이 같은 프로파일에 기록한다."""
    profile, token = start_cycle_profile()
    try:
        async def user_flow():
            with phase("user.exit_signals"):
                await asyncio.sleep(0)

        def blocking_io():
            with phase("user.broker_thread"):
                time.sleep(0.01)

        await asyncio.gather(user_flow(), user_flow(), asyncio.to_thread(blocking_io))
    finally:
        end_cycle_profile(token)

    stats = profile.snapshot()
    assert stats["user.exit_signals"].count == 2, "gather 태스크의 기록이 누락됐다"
    assert stats["user.broker_thread"].count == 1, "to_thread 작업의 기록이 누락됐다"


@pytest.mark.asyncio
async def test_loop_lag_monitor_detects_blocking_work():
    """이벤트 루프를 붙잡는 동기 작업은 loop.blocked로 드러난다."""
    profile = CycleProfile()
    task = asyncio.create_task(monitor_loop_lag(profile))
    await asyncio.sleep(0.15)          # 감시가 한 번 돌게 한다
    time.sleep(0.4)                     # 루프를 동기로 붙잡는다
    await asyncio.sleep(0.15)          # 감시가 늦게 깨어났음을 기록하게 한다
    await stop_loop_lag_monitor(task)

    blocked = profile.snapshot().get(LOOP_BLOCKED_PHASE)
    assert blocked is not None, "루프 막힘을 감지하지 못했다"
    assert blocked.max_seconds >= 0.3
    assert task.done()


@pytest.mark.asyncio
async def test_loop_lag_monitor_ignores_a_healthy_loop():
    """막힘이 없으면 기록하지 않는다. 스케줄러 지터를 막힘으로 오인해 합계를 부풀리면 안 된다."""
    profile = CycleProfile()
    task = asyncio.create_task(monitor_loop_lag(profile))
    for _ in range(6):
        await asyncio.sleep(0.05)
    await stop_loop_lag_monitor(task)
    assert LOOP_BLOCKED_PHASE not in profile.snapshot()


# ======================================================================================
# 2. 매매 루프 통합
# ======================================================================================

def _install_loop_fakes(monkeypatch, active_users, flow):
    fake_db = FakeSession(active_users=active_users, holding_user_ids=[], watchlist_rows=[])
    logged: list[str] = []

    async def fake_sentiment():
        return "BULLISH"

    monkeypatch.setattr(scheduler, "SessionLocal", lambda: fake_db)
    monkeypatch.setattr(scheduler, "get_market_session", lambda: "REGULAR_MARKET")
    monkeypatch.setattr(scheduler, "check_market_sentiment", fake_sentiment)
    monkeypatch.setattr(scheduler.FXRateCache, "get_rate", lambda: 1400.0)
    monkeypatch.setattr(scheduler, "run_user_trading_flow", flow)
    monkeypatch.setattr(scheduler.logger, "info", lambda message, *a, **k: logged.append(str(message)))
    monkeypatch.setattr(scheduler.logger, "warning", lambda message, *a, **k: logged.append(str(message)))
    scheduler.is_processing = False
    scheduler.latest_scanned_signals = []
    scheduler.latest_watchlist_signals = {}
    return logged


@pytest.mark.asyncio
async def test_trading_loop_logs_profile_with_user_phases_and_loop_blocking(monkeypatch):
    """사이클 요약에 사용자 구간·사이클 구간·루프 막힘이 함께 담긴다."""
    active_users = [SimpleNamespace(user_id=1, is_running=True), SimpleNamespace(user_id=2, is_running=True)]

    async def blocking_flow(user_id, signal_map, all_signals, exchange_rate, sentiment, session):
        # 실제 사용자 흐름 안의 동기 DB·브로커 작업을 흉내 낸다. await 없이 루프를 붙잡는다.
        with phase("user.exit_signals"):
            await asyncio.sleep(0.12)
            time.sleep(0.25)

    logged = _install_loop_fakes(monkeypatch, active_users, blocking_flow)
    await scheduler.async_trading_loop()

    profile_lines = [line for line in logged if line.startswith("[Cycle] Profile")]
    assert len(profile_lines) == 1, f"요약 줄이 정확히 한 번 남아야 한다: {logged}"
    line = profile_lines[0]
    assert "2 users" in line
    assert "user.exit_signals=" in line and "/2회" in line
    assert "cycle.user_flows_wall=" in line
    assert "cycle.load_active_users=" in line
    assert f"{LOOP_BLOCKED_PHASE}=" in line, "사용자 흐름의 동기 작업이 루프 막힘으로 잡히지 않았다"

    assert current_profile() is None, "사이클 종료 후 프로파일이 컨텍스트에 남았다"
    leftovers = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    assert leftovers == [], f"감시 태스크가 회수되지 않았다: {leftovers}"


@pytest.mark.asyncio
async def test_trading_loop_skips_profile_line_when_no_user_flow_runs(monkeypatch):
    """가동 유저가 없어 조기 반환한 사이클은 요약을 남기지 않는다. 감시 태스크는 그래도 회수된다."""
    async def never_called(*args, **kwargs):
        raise AssertionError("사용자 흐름이 돌면 안 된다")

    logged = _install_loop_fakes(monkeypatch, [], never_called)
    await scheduler.async_trading_loop()

    assert not any(line.startswith("[Cycle] Profile") for line in logged)
    assert any(line.startswith("[Cycle] Duration") for line in logged)
    leftovers = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    assert leftovers == [], f"조기 반환 경로에서 감시 태스크가 회수되지 않았다: {leftovers}"


@pytest.mark.asyncio
async def test_real_user_flow_records_its_phases(monkeypatch):
    """실제 run_user_trading_flow에 구간이 배선되어 있다.

    위 통합 테스트는 가짜 사용자 흐름을 쓴다. 스케줄러 본체의 phase 배선이 빠져도 통과하므로,
    매도가 실제로 일어나는 기존 시나리오를 프로파일 아래에서 돌려 소비 경로를 확인한다.
    """
    from tests.test_trading_flow_scenarios import (
        FakeBroker,
        FakeDb,
        FakeStrategy,
        clear_pending_breach,
        install_flow_fakes,
        make_signal,
        make_user_settings,
        seed_pending_breach,
    )
    from app.core.models import Holding

    holding = Holding(
        user_id=1, ticker="AAPL", strategy_type="slot", ticker_name="Apple",
        avg_price=120.0, quantity=3, highest_price=120.0, regime_mode="BULLISH", buy_stage=3,
    )
    fake_db = FakeDb(user_settings=make_user_settings(), holdings=[holding])
    fake_broker = FakeBroker(
        holdings_payload=[{"ticker": "AAPL", "ticker_name": "Apple", "quantity": 3, "avg_price": 120.0}],
    )
    install_flow_fakes(monkeypatch, fake_db, fake_broker, FakeStrategy(entry_score=0))
    signal = make_signal()

    profile, token = start_cycle_profile()
    seed_pending_breach(holding)
    try:
        await scheduler.run_user_trading_flow(
            user_id=1, signal_map={"AAPL": signal}, all_signals=[signal],
            exchange_rate=1500.0, sentiment="BULLISH", session="REGULAR_MARKET",
        )
    finally:
        clear_pending_breach(holding)
        end_cycle_profile(token)

    assert fake_broker.sell_calls, "시나리오 전제가 깨졌다 - 매도가 일어나지 않았다"
    stats = profile.snapshot()
    for name in (
        "user.lock_acquire",
        "user.prepare_context",
        "user.sync_broker_holdings",
        "user.exit_signals",
        "user.lock_release",
        "db.micro_session.setup",
        "db.micro_session.total",
    ):
        assert name in stats, f"{name} 구간이 기록되지 않았다 - 스케줄러 배선 누락"
