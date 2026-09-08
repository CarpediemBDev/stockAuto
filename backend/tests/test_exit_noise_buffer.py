"""봇 소유 포지션의 손절 노이즈 버퍼가 사이클 수가 아니라 벽시계로 게이트되는지 검증한다.

버퍼의 목적은 손절선을 순간적으로 찔렀다 돌아오는 꼬리에 털리지 않는 것이다. 그래서 이탈을
두 번 확인한 뒤에 판다. 문제는 그 "두 번"이 사이클 수로만 세어져 있었다는 점이다.

사이클 주기는 등록값 1분이 아니라 실측 중앙값 124초(범위 104~846초)다. 원인은
tests/test_scheduler_cycle_interval.py에 재현으로 고정되어 있다. 그래서 같은 2사이클이
3분일 수도 28분일 수도 있었다. 게다가 카운터가 인메모리라 재기동하면 진행 중이던 대기가
0으로 돌아가 손절이 처음부터 다시 미뤄졌다.

이 파일은 두 축(관측 횟수 · 경과 시간)이 각각 실제로 게이트 역할을 하는지를 서로에 대한
네거티브 컨트롤로 확인한다. 한 축만 채워도 통과한다면 그 축은 장식이다.
"""

from datetime import timedelta

import pytest

import app.bot.scheduler as scheduler
from app.core.models import Holding, utc_now_aware

from tests.test_trading_flow_scenarios import (
    FakeBroker,
    FakeDb,
    FakeStrategy,
    install_flow_fakes,
    make_signal,
    make_user_settings,
)


def _make_breaching_holding():
    """손절선을 이탈한 상태의 봇 소유 보유분.

    avg_price 120에 현재가 100(FakeBroker 기본값)이라 -16.7%로 손절 조건을 만족한다.
    """
    return Holding(
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


async def _run_cycle(monkeypatch, holding):
    signal = make_signal()
    fake_db = FakeDb(user_settings=make_user_settings(), holdings=[holding])
    fake_broker = FakeBroker(
        holdings_payload=[
            {"ticker": "AAPL", "ticker_name": "Apple", "quantity": 3, "avg_price": 120.0}
        ],
    )
    install_flow_fakes(monkeypatch, fake_db, fake_broker, FakeStrategy(entry_score=0))
    await scheduler.run_user_trading_flow(
        user_id=1,
        signal_map={"AAPL": signal},
        all_signals=[signal],
        exchange_rate=1500.0,
        sentiment="BULLISH",
        session="REGULAR_MARKET",
    )
    return fake_broker


@pytest.fixture(autouse=True)
def _clean_breach_cache():
    scheduler.BREACH_COUNT_CACHE.clear()
    yield
    scheduler.BREACH_COUNT_CACHE.clear()


@pytest.mark.asyncio
async def test_repeated_observation_alone_does_not_confirm_the_breach(monkeypatch):
    """관측 횟수만 채워서는 팔지 않는다 - 시간 축의 네거티브 컨트롤.

    이 테스트가 통과하지 못하면 벽시계 게이트는 이름만 있고 실제로는 사이클 수로만
    판정하고 있다는 뜻이다.
    """
    holding = _make_breaching_holding()
    scheduler.BREACH_COUNT_CACHE[(1, "AAPL", "slot")] = 1  # 이미 한 번 관측
    holding.exit_breach_started_at = None                   # 그러나 시각 기록은 없다

    fake_broker = await _run_cycle(monkeypatch, holding)

    assert fake_broker.sell_calls == [], (
        "관측 횟수만으로 매도됐다 - 시간 하한이 게이트로 동작하지 않는다"
    )


@pytest.mark.asyncio
async def test_elapsed_time_alone_does_not_confirm_the_breach(monkeypatch):
    """경과 시간만 채워서는 팔지 않는다 - 관측 횟수 축의 네거티브 컨트롤.

    시각이 오래됐다는 것만으로 팔면, 재기동 직후 첫 관측에 곧바로 매도가 나간다.
    표본이 성긴 구간에서 단 한 번의 나쁜 호가에 털리지 않으려면 횟수도 필요하다.
    """
    holding = _make_breaching_holding()
    holding.exit_breach_started_at = utc_now_aware() - timedelta(hours=3)
    # 카운터는 비어 있다 (재기동 직후 상태)

    fake_broker = await _run_cycle(monkeypatch, holding)

    assert fake_broker.sell_calls == [], (
        "첫 관측에 곧바로 매도됐다 - 관측 횟수가 게이트로 동작하지 않는다"
    )


@pytest.mark.asyncio
async def test_both_axes_satisfied_confirms_the_breach(monkeypatch):
    """두 축이 모두 충족되면 판다 (포지티브 컨트롤)."""
    holding = _make_breaching_holding()
    scheduler.BREACH_COUNT_CACHE[(1, "AAPL", "slot")] = 1
    holding.exit_breach_started_at = utc_now_aware() - timedelta(
        minutes=scheduler.EXIT_NOISE_BUFFER_MINUTES + 1
    )

    fake_broker = await _run_cycle(monkeypatch, holding)

    assert fake_broker.sell_calls == [("AAPL", 3, 100.0, "slot")]


@pytest.mark.asyncio
async def test_restart_loses_the_counter_but_keeps_the_clock(monkeypatch):
    """재기동 시나리오 - 카운터는 사라져도 대기 시각은 살아남는다.

    재기동 직후 첫 사이클은 팔지 않는다(횟수 미달). 그러나 시각이 DB에 남아 있으므로
    다음 사이클에서 곧바로 판다. 시각까지 인메모리였다면 여기서 대기가 처음부터
    다시 시작해 손절이 두 배로 미뤄졌을 것이다.
    """
    holding = _make_breaching_holding()
    holding.exit_breach_started_at = utc_now_aware() - timedelta(hours=1)
    scheduler.BREACH_COUNT_CACHE.clear()  # 재기동으로 카운터 소실

    first = await _run_cycle(monkeypatch, holding)
    assert first.sell_calls == [], "재기동 직후 첫 관측에 팔면 안 된다"

    second = await _run_cycle(monkeypatch, holding)
    assert second.sell_calls == [("AAPL", 3, 100.0, "slot")], (
        "시각이 보존됐는데도 두 번째 사이클에서 팔지 않았다"
    )


def test_buffer_constants_are_wall_clock_backed():
    """상수 자체를 고정한다.

    시간 하한이 0이면 게이트가 사실상 없어지므로, 누군가 값을 0으로 낮추면 여기서 걸린다.
    """
    assert scheduler.EXIT_NOISE_BUFFER_CYCLES >= 2
    assert scheduler.EXIT_NOISE_BUFFER_MINUTES > 0
    assert "exit_breach_started_at" in Holding.__table__.columns
