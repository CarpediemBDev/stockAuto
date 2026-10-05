"""갭상승 청산 A/B 회귀 테스트 (2026-10-04).

근거: 헬스케어 소형·페니주 53종목 일봉에서 정규장 시가 갭 +15% 이상인 날의 시가→종가
중앙값이 학습·검증 두 구간 모두 약 -8%였다. 롱 전용 시스템은 이를 "들고 있던 종목이
갭상승하면 그날 판다"는 청산 규칙으로만 쓴다.

고정하는 계약
  1. 스위치가 꺼져 있으면 규칙이 아예 돌지 않는다(시세 조회도 없음) - 기존 동작 보존.
  2. 처치군(짝수 user_id)은 봇 보유분을 전량 매도, 대조군(홀수)은 "팔았다면"만 하루 한 번 기록.
  3. 정규장에서만, 개장 전부터 들고 있던 보유분만 대상이다.
  4. 외부(EXTERNAL) 보유분은 기존 방어 계약(guard_action·매도 비율)을 그대로 따른다.
"""

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.bot.gap_exit as gap_exit
import app.bot.scheduler as scheduler
from app.bot.trade_calculations import check_gap_exit, compute_session_gap_pct
from app.core.database import Base
from app.core.models import (
    EXTERNAL_STRATEGY_TYPE,
    GUARD_ACTION_ALERT_ONLY,
    GUARD_ACTION_LIQUIDATE,
    GUARD_ACTION_SHADOW,
    MANAGEMENT_BOT_OWNED,
    MANAGEMENT_EXTERNAL,
    ActionLog,
    Holding,
    TradeLog,
    User,
    UserSettings,
    utc_now_aware,
)


# ======================================================================================
# 1. 순수 판정
# ======================================================================================

def test_gap_pct_is_open_over_previous_close():
    assert compute_session_gap_pct(1.0, 1.15) == Decimal("15.00")
    assert compute_session_gap_pct(0.865, 1.11).quantize(Decimal("0.1")) == Decimal("28.3")  # HCTI 2026-09-23


def test_gap_pct_is_unknown_rather_than_zero_when_inputs_are_missing():
    """시세를 못 받은 것과 갭이 없는 것을 구분한다."""
    assert compute_session_gap_pct(None, 1.0) is None
    assert compute_session_gap_pct(1.0, None) is None
    assert compute_session_gap_pct(0, 1.0) is None
    assert compute_session_gap_pct(1.0, 0) is None


def test_threshold_is_inclusive_and_unknown_never_fires():
    assert check_gap_exit(Decimal("15.0")) is True
    assert check_gap_exit(Decimal("14.99")) is False
    assert check_gap_exit(Decimal("-20")) is False   # 갭하락은 대상 아님
    assert check_gap_exit(None) is False
    assert check_gap_exit(Decimal("50"), threshold_pct=0) is False


def test_session_gap_requires_todays_bar():
    """개장 직후 일봉이 아직 안 붙었으면 어제 갭을 오늘 갭으로 착각하지 않는다."""
    df = pd.DataFrame(
        {"Open": [0.795, 1.11], "Close": [0.865, 0.911]},
        index=pd.to_datetime(["2026-09-22", "2026-09-23"]),
    )
    assert gap_exit.extract_session_gap_pct(df, date(2026, 9, 24)) is None
    gap = gap_exit.extract_session_gap_pct(df, date(2026, 9, 23))
    assert gap is not None and gap > 28
    assert gap_exit.extract_session_gap_pct(df.iloc[:1], date(2026, 9, 22)) is None


def test_arm_assignment_is_off_by_default_and_parity_when_on(monkeypatch):
    monkeypatch.setattr(gap_exit, "is_system_setting_enabled", lambda _k: False)
    assert gap_exit.resolve_gap_exit_arm(2) is None
    monkeypatch.setattr(gap_exit, "is_system_setting_enabled", lambda _k: True)
    assert gap_exit.resolve_gap_exit_arm(2) == gap_exit.GAP_EXIT_ARM_TREATMENT
    assert gap_exit.resolve_gap_exit_arm(3) == gap_exit.GAP_EXIT_ARM_CONTROL


# ======================================================================================
# 2. 스케줄러 통합 (실제 매도 판정 루프)
# ======================================================================================

@pytest.fixture(autouse=True)
def _reset_event_marks():
    gap_exit._logged_events.clear()
    gap_exit._gap_cache.clear()
    yield
    gap_exit._logged_events.clear()
    gap_exit._gap_cache.clear()


def _make_db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _make_user(db, user_id):
    user = User(id=user_id, username=f"gap_{user_id}", hashed_password="hashed")
    db.add(user)
    db.flush()
    db.add(UserSettings(
        user_id=user.id, strategy_type="test_slot", trade_mode="SIMULATED", is_running=True,
    ))
    db.commit()
    db.refresh(user)
    return user


class _Broker:
    def __init__(self):
        self.sell_calls = []

    def get_holdings(self, exchange_rate=None):
        return []

    def sell_order(self, ticker, quantity, **kwargs):
        self.sell_calls.append((ticker, quantity))
        return {"success": True, "order_no": "GAP1", "filled_qty": quantity,
                "filled_price": kwargs.get("price", 1.0), "message": "ok", "status": "FILLED"}


class _QuietStrategy:
    """어떤 기존 청산 조건도 만족하지 않는 전략 - 갭 규칙만 매도를 낼 수 있게 한다."""
    name = "QuietStrategy"
    is_autonomous = False
    min_smart_exit_profit = 999.0
    use_rolling_box_stop = False

    def calculate_score(self, *_a, **_k):
        return 80.0

    def is_signal_collapsed(self, *_a, **_k):
        return False

    def get_stop_loss_pct(self, *_a, **_k):
        return 50.0

    def get_trailing_stop_pct(self, *_a, **_k):
        return 50.0


def _add_holding(db, user, bought_minutes_ago=60 * 24 * 2, **overrides):
    fields = dict(
        user_id=user.id, ticker="GAPY", ticker_name="Gap Co",
        strategy_type="test_slot", management=MANAGEMENT_BOT_OWNED,
        avg_price=1.0, quantity=100, highest_price=1.2,
    )
    fields.update(overrides)
    h = Holding(**fields)
    db.add(h)
    if bought_minutes_ago is not None:
        db.add(TradeLog(
            user_id=user.id, ticker=fields["ticker"], trade_type="BUY", price=1.0,
            quantity=fields["quantity"], strategy_type=fields["strategy_type"],
            executed_at=utc_now_aware() - timedelta(minutes=bought_minutes_ago),
        ))
    db.commit()
    db.refresh(h)
    return h


def _patch_gap(monkeypatch, arm, gap_pct, session_open_minutes_ago=30):
    calls = []

    async def _fake_gap(ticker, _day):
        calls.append(ticker)
        return None if gap_pct is None else Decimal(str(gap_pct))

    monkeypatch.setattr(scheduler, "resolve_gap_exit_arm", lambda _uid: arm)
    monkeypatch.setattr(scheduler, "get_session_gap_pct", _fake_gap)
    # 개장 시각을 "지금 - N분"으로 고정해 테스트 실행 시각과 무관하게 만든다.
    monkeypatch.setattr(
        scheduler, "regular_open_utc",
        lambda _d: utc_now_aware() - timedelta(minutes=session_open_minutes_ago),
    )
    return calls


def _cycle(db, user, broker, holding, session="REGULAR_MARKET", price=1.2):
    fresh = db.query(Holding).filter(Holding.id == holding.id).first()
    if fresh is None:
        return
    signal_map = {fresh.ticker: {"price": price, "details": {"atr": 0.01, "is_smart_exit": False}}}
    settings_row = db.query(UserSettings).filter_by(user_id=user.id).one()
    ctx = scheduler.TradingFlowContext(
        db=db, user_id=user.id, db_settings=settings_row, trade_mode="SIMULATED",
        session=session, sentiment="BULLISH", exchange_rate=1350.0,
        holdings=[fresh], broker=broker,
        ms_manager=SimpleNamespace(strategies={"test_slot": _QuietStrategy()}),
        first_slot_key="test_slot", signal_map=signal_map, all_signals=[],
    )
    asyncio.run(scheduler.process_exit_signals(ctx, signal_map))


def _logs(db, user):
    return [r.message for r in db.query(ActionLog).filter_by(user_id=user.id).all()]


def test_switch_off_means_no_lookup_and_no_sell(monkeypatch):
    db = _make_db()
    user = _make_user(db, 2)
    holding = _add_holding(db, user)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    calls = _patch_gap(monkeypatch, None, 40)
    broker = _Broker()

    _cycle(db, user, broker, holding)

    assert calls == []                 # 시세 조회조차 없다
    assert broker.sell_calls == []
    assert not any("[GapExit]" in m for m in _logs(db, user))
    db.close()


def test_treatment_sells_whole_position_on_gap_up(monkeypatch):
    db = _make_db()
    user = _make_user(db, 2)
    holding = _add_holding(db, user)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    _patch_gap(monkeypatch, gap_exit.GAP_EXIT_ARM_TREATMENT, 28.3)
    broker = _Broker()

    _cycle(db, user, broker, holding)

    assert broker.sell_calls == [("GAPY", 100)]
    assert db.query(Holding).filter_by(user_id=user.id).count() == 0
    logs = _logs(db, user)
    assert any("[GapExit][TREATMENT] GAPY gap=+28.3% selling_qty=100" in m for m in logs)
    assert db.query(TradeLog).filter_by(trade_type="SELL").count() == 1
    db.close()


def test_control_only_records_once_per_day(monkeypatch):
    db = _make_db()
    user = _make_user(db, 3)
    holding = _add_holding(db, user)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    _patch_gap(monkeypatch, gap_exit.GAP_EXIT_ARM_CONTROL, 20)
    broker = _Broker()

    _cycle(db, user, broker, holding)
    _cycle(db, user, broker, holding)

    assert broker.sell_calls == []
    assert db.query(Holding).one().quantity == 100
    records = [m for m in _logs(db, user) if "[GapExit][CONTROL]" in m]
    assert len(records) == 1
    assert "would_sell_qty=100" in records[0] and "no order placed" in records[0]
    db.close()


def test_below_threshold_does_nothing(monkeypatch):
    db = _make_db()
    user = _make_user(db, 2)
    holding = _add_holding(db, user)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    _patch_gap(monkeypatch, gap_exit.GAP_EXIT_ARM_TREATMENT, 14.9)
    broker = _Broker()

    _cycle(db, user, broker, holding)

    assert broker.sell_calls == []
    db.close()


def test_position_bought_after_todays_open_is_not_gap_exited(monkeypatch):
    """오늘 장중에 산 종목을 갭을 이유로 곧바로 팔면 왕복 수수료만 내는 휩쏘다."""
    db = _make_db()
    user = _make_user(db, 2)
    holding = _add_holding(db, user, bought_minutes_ago=10)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    _patch_gap(monkeypatch, gap_exit.GAP_EXIT_ARM_TREATMENT, 40, session_open_minutes_ago=30)
    broker = _Broker()

    _cycle(db, user, broker, holding)

    assert broker.sell_calls == []
    db.close()


def test_only_regular_session_is_evaluated(monkeypatch):
    db = _make_db()
    user = _make_user(db, 2)
    holding = _add_holding(db, user)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    calls = _patch_gap(monkeypatch, gap_exit.GAP_EXIT_ARM_TREATMENT, 40)
    broker = _Broker()

    _cycle(db, user, broker, holding, session="PRE_MARKET")

    assert calls == []
    assert broker.sell_calls == []
    db.close()


def test_unknown_gap_does_not_sell(monkeypatch):
    db = _make_db()
    user = _make_user(db, 2)
    holding = _add_holding(db, user)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    _patch_gap(monkeypatch, gap_exit.GAP_EXIT_ARM_TREATMENT, None)
    broker = _Broker()

    _cycle(db, user, broker, holding)

    assert broker.sell_calls == []
    db.close()


# ======================================================================================
# 3. 외부 보유분 방어 경로
# ======================================================================================

def _add_external(db, user, **overrides):
    fields = dict(
        ticker="HCTI", ticker_name="Healthcare Triangle", strategy_type=EXTERNAL_STRATEGY_TYPE,
        management=MANAGEMENT_EXTERNAL, avg_price=1.4852, quantity=4762, highest_price=1.6,
        guard_enabled=True, guard_sell_ratio=0.5,
    )
    fields.update(overrides)
    return _add_holding(db, user, **fields)


@pytest.fixture
def _flat_guard_score(monkeypatch):
    # 점수 방어는 발동하지 않게 고정한다 - 갭 경로만 본다.
    monkeypatch.setattr(
        scheduler, "_get_guard_evaluator",
        lambda: SimpleNamespace(calculate_score=lambda *_a, **_k: 50.0),
    )


def test_guard_shadow_records_gap_without_ordering(monkeypatch, _flat_guard_score):
    db = _make_db()
    user = _make_user(db, 1)   # admin과 같은 홀수 계정이어도 외부 보유분은 guard_action을 따른다
    holding = _add_external(db, user, guard_action=GUARD_ACTION_SHADOW)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    _patch_gap(monkeypatch, gap_exit.GAP_EXIT_ARM_CONTROL, 28.3)
    broker = _Broker()

    _cycle(db, user, broker, holding, price=1.11)

    assert broker.sell_calls == []
    records = [m for m in _logs(db, user) if "[Guard][GAP][SHADOW]" in m]
    assert len(records) == 1 and "would_sell_qty=2381" in records[0]
    db.close()


def test_guard_alert_only_never_orders(monkeypatch, _flat_guard_score):
    db = _make_db()
    user = _make_user(db, 2)
    holding = _add_external(db, user, guard_action=GUARD_ACTION_ALERT_ONLY)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    _patch_gap(monkeypatch, gap_exit.GAP_EXIT_ARM_TREATMENT, 28.3)
    broker = _Broker()

    _cycle(db, user, broker, holding, price=1.11)

    assert broker.sell_calls == []
    db.close()


def test_guard_liquidate_sells_configured_fraction_once_a_day(monkeypatch, _flat_guard_score):
    db = _make_db()
    user = _make_user(db, 2)
    holding = _add_external(db, user, guard_action=GUARD_ACTION_LIQUIDATE)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    _patch_gap(monkeypatch, gap_exit.GAP_EXIT_ARM_TREATMENT, 28.3)
    broker = _Broker()

    _cycle(db, user, broker, holding, price=1.11)
    _cycle(db, user, broker, holding, price=1.05)

    assert broker.sell_calls == [("HCTI", 2381)]   # 절반, 하루 한 번
    assert db.query(Holding).filter_by(user_id=user.id).one().quantity == 4762 - 2381
    db.close()
