"""방어 경보(Defense Guard) 회귀 테스트.

"무너지면 알림" - 경보만 보내고 주문은 절대 내지 않는 단계다.

여기서 고정하는 계약은 다섯 가지다.
  1. 절대 점수선을 쓰지 않는다. 이미 물린 종목이 켜는 순간 울리면 안 된다.
  2. 점수 추가 악화와 신저가 갱신을 둘 다 요구한다.
  3. 저가 기준선은 단조 감소 래칫이다. 반등해도 따라 올라가지 않는다.
  4. 주문은 어떤 경우에도 나가지 않는다.
  5. 껐다 켜면 기준선이 재설정된다.

설계 정본은 docs/plans/holding_management_modes.md 5.3절.
"""

import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.bot.scheduler as scheduler
import app.trades.router_account as account_router
from app.bot.trade_calculations import (
    GUARD_SCORE_DROP_DELTA,
    check_guard_breach,
    compute_guard_low,
)
from app.core.database import Base
from app.core.models import (
    EXTERNAL_STRATEGY_TYPE,
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
# 1. 순수 판정 함수
# ======================================================================================

def test_guard_low_ratchets_downward_only():
    """저가 기준선은 내려가기만 한다. 반등해도 따라 올라가지 않는다.

    래칫이 없으면 반등할 때 기준선이 올라가 다음 하락에서 '신저가'가 매번 참이 되고,
    정상 등락이 전부 경보가 된다.
    """
    assert compute_guard_low(None, 10.0) == 10.0   # 최초 설정
    assert compute_guard_low(10.0, 12.0) == 10.0   # 반등 - 유지
    assert compute_guard_low(10.0, 8.0) == 8.0     # 신저가 - 갱신
    assert compute_guard_low(8.0, 12.0) == 8.0     # 큰 반등에도 유지


def test_breach_requires_both_conditions():
    """점수 악화와 신저가를 둘 다 만족해야 한다."""
    # 점수 -20(>=15), 가격 7 < 저가 8 -> 발동
    assert check_guard_breach(30, 50, 7.0, 8.0) is True
    # 점수만 -5 -> 미발동
    assert check_guard_breach(45, 50, 7.0, 8.0) is False
    # 신저가 아님 -> 미발동
    assert check_guard_breach(30, 50, 9.0, 8.0) is False
    # 기준선 미설정 -> 미발동
    assert check_guard_breach(30, None, 7.0, 8.0) is False
    assert check_guard_breach(30, 50, 7.0, None) is False


def test_already_collapsed_position_does_not_fire_on_its_own():
    """이 설계에서 가장 큰 함정 - 이미 붕괴된 종목이 켜는 순간 울리면 안 된다.

    절대 점수선(예: 40점 미만)을 쓰면 -50% 물린 종목은 켜자마자 참이 되어, 이 프로젝트가
    처음에 문제 삼았던 '관측 시작 즉시 청산'이 이름만 바꿔 재현된다. 전이 기반은 점수가
    이미 낮아도 그 자리에 머물러 있으면 울리지 않는다.
    """
    already_bad = 12.0   # 절대선(40) 한참 아래
    # 켠 시점 점수가 곧 기준선이므로 변화량은 0이다.
    assert check_guard_breach(already_bad, already_bad, 5.0, 5.0) is False
    # 가격이 더 빠져도 점수가 그대로면 울리지 않는다.
    assert check_guard_breach(already_bad, already_bad, 4.0, 5.0) is False
    # 점수까지 추가로 무너져야 비로소 울린다.
    assert check_guard_breach(
        already_bad - GUARD_SCORE_DROP_DELTA, already_bad, 4.0, 5.0
    ) is True


# ======================================================================================
# 2. 스케줄러 통합
# ======================================================================================

def _make_db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _make_user(db, username="guardian"):
    user = User(username=username, hashed_password="hashed")
    db.add(user)
    db.flush()
    db.add(UserSettings(
        user_id=user.id, strategy_type="regime_switching",
        trade_mode="SIMULATED", is_running=True,
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
        return {"success": True, "order_no": "X", "filled_qty": quantity,
                "filled_price": 1.0, "message": "ok", "status": "FILLED"}


class _FixedScoreEvaluator:
    """고정 평가자를 대체한다. 사이클마다 점수를 주입해 전이를 만든다."""

    def __init__(self, score=50.0):
        self.score = score

    def calculate_score(self, *_args, **_kwargs):
        return self.score


def _add_external(db, user, **overrides):
    fields = dict(
        user_id=user.id, ticker="HCTI", ticker_name="Healthcare Triangle",
        strategy_type=EXTERNAL_STRATEGY_TYPE, management=MANAGEMENT_EXTERNAL,
        avg_price=100.0, quantity=100, highest_price=50.0,
    )
    fields.update(overrides)
    h = Holding(**fields)
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


def _run_cycle(db, user, broker, holding, price):
    """운영과 동일하게 사이클마다 보유분을 DB에서 다시 읽는다."""
    fresh = db.query(Holding).filter(Holding.id == holding.id).first()
    if fresh is None:
        return
    signal_map = {fresh.ticker: {"price": price, "details": {"atr": 1.0, "is_smart_exit": False}}}
    settings_row = db.query(UserSettings).filter_by(user_id=user.id).one()
    ctx = scheduler.TradingFlowContext(
        db=db, user_id=user.id, db_settings=settings_row, trade_mode="SIMULATED",
        session="REGULAR_MARKET", sentiment="BULLISH", exchange_rate=1350.0,
        holdings=[fresh], broker=broker, ms_manager=SimpleNamespace(strategies={}),
        first_slot_key="regime_switching", signal_map=signal_map, all_signals=[],
    )
    asyncio.run(scheduler.process_exit_signals(ctx, signal_map))


def _logs(db, user):
    return [row.message for row in db.query(ActionLog).filter_by(user_id=user.id).all()]


def _age_baseline(db, holding_id, minutes):
    """유예기간을 통과시키기 위해 켠 시각을 과거로 민다."""
    db.query(Holding).filter(Holding.id == holding_id).update(
        {Holding.guard_enabled_at: utc_now_aware() - timedelta(minutes=minutes)},
        synchronize_session=False,
    )
    db.commit()


@pytest.fixture
def fixed_evaluator(monkeypatch):
    evaluator = _FixedScoreEvaluator()
    monkeypatch.setattr(scheduler, "_get_guard_evaluator", lambda: evaluator)
    return evaluator


def test_guard_sets_baseline_on_first_cycle(monkeypatch, fixed_evaluator):
    db = _make_db()
    user = _make_user(db)
    holding = _add_external(db, user, guard_enabled=True)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    fixed_evaluator.score = 42.0

    _run_cycle(db, user, _Broker(), holding, price=10.0)

    row = db.query(Holding).filter_by(user_id=user.id).one()
    assert row.guard_baseline_score == 42.0
    assert float(row.guard_baseline_low) == 10.0
    assert any("Baseline set" in m for m in _logs(db, user))
    db.close()


def test_guard_alerts_only_on_transition_and_never_sells(monkeypatch, fixed_evaluator):
    """점수 추가 악화 + 신저가일 때만 경보하고, 어떤 경우에도 주문을 내지 않는다."""
    db = _make_db()
    user = _make_user(db)
    holding = _add_external(db, user, guard_enabled=True)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    broker = _Broker()

    fixed_evaluator.score = 50.0
    _run_cycle(db, user, broker, holding, price=10.0)     # 기준선 score 50 / low 10
    _age_baseline(db, holding.id, 60)

    # 가격만 하락 - 점수가 그대로라 울리지 않는다.
    _run_cycle(db, user, broker, holding, price=8.0)
    assert not any("[Guard] ALERT" in m for m in _logs(db, user))

    # 점수만 하락 - 신저가가 아니라 울리지 않는다(래칫이 8로 내려가 있다).
    fixed_evaluator.score = 20.0
    _run_cycle(db, user, broker, holding, price=9.0)
    assert not any("[Guard] ALERT" in m for m in _logs(db, user))

    # 둘 다 - 경보.
    _run_cycle(db, user, broker, holding, price=7.0)
    assert any("[Guard] ALERT" in m for m in _logs(db, user))

    # 경보는 났지만 주문은 없다. 이것이 4단계의 전부다.
    assert broker.sell_calls == []
    assert db.query(TradeLog).count() == 0
    assert db.query(Holding).filter_by(user_id=user.id).one().quantity == 100
    db.close()


def test_guard_stays_silent_during_grace_period(monkeypatch, fixed_evaluator):
    """켠 직후에는 조건을 만족해도 울리지 않는다."""
    db = _make_db()
    user = _make_user(db)
    holding = _add_external(db, user, guard_enabled=True)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)

    fixed_evaluator.score = 50.0
    _run_cycle(db, user, _Broker(), holding, price=10.0)
    # 유예기간을 밀지 않은 채로 붕괴 조건을 만든다.
    fixed_evaluator.score = 10.0
    _run_cycle(db, user, _Broker(), holding, price=5.0)

    assert not any("[Guard] ALERT" in m for m in _logs(db, user))
    db.close()


def test_guard_alert_respects_cooldown(monkeypatch, fixed_evaluator):
    """1분 사이클마다 같은 경보를 반복하지 않는다."""
    db = _make_db()
    user = _make_user(db)
    holding = _add_external(db, user, guard_enabled=True)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)

    fixed_evaluator.score = 50.0
    _run_cycle(db, user, _Broker(), holding, price=10.0)
    _age_baseline(db, holding.id, 60)

    fixed_evaluator.score = 10.0
    _run_cycle(db, user, _Broker(), holding, price=7.0)
    _run_cycle(db, user, _Broker(), holding, price=6.0)
    _run_cycle(db, user, _Broker(), holding, price=5.0)

    alerts = [m for m in _logs(db, user) if "[Guard] ALERT" in m]
    assert len(alerts) == 1
    db.close()


def test_disabled_guard_does_nothing(monkeypatch, fixed_evaluator):
    db = _make_db()
    user = _make_user(db)
    holding = _add_external(db, user, guard_enabled=False)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)

    fixed_evaluator.score = 50.0
    _run_cycle(db, user, _Broker(), holding, price=10.0)
    fixed_evaluator.score = 5.0
    _run_cycle(db, user, _Broker(), holding, price=3.0)

    row = db.query(Holding).filter_by(user_id=user.id).one()
    assert row.guard_baseline_score is None
    assert not any("Guard" in m for m in _logs(db, user))
    db.close()


# ======================================================================================
# 3. 토글 API
# ======================================================================================

def test_toggle_guard_resets_baseline_each_time():
    """껐다 켜면 기준선이 재설정된다.

    예전 기준선을 물려받으면 꺼져 있던 동안의 하락이 전부 '추가 악화'로 잡혀,
    켜자마자 경보가 나간다.
    """
    db = _make_db()
    user = _make_user(db)
    _add_external(
        db, user, guard_enabled=True, guard_baseline_score=50.0,
        guard_baseline_low=10.0, guard_enabled_at=utc_now_aware(),
    )

    off = account_router.update_holding_management(
        ticker="HCTI",
        payload=account_router.HoldingManagementRequest(guard_enabled=False),
        current_user=user, db=db,
    )
    assert off["guard_enabled"] is False
    assert off["guard_baseline_score"] is None
    assert off["guard_baseline_low"] is None

    on = account_router.update_holding_management(
        ticker="HCTI",
        payload=account_router.HoldingManagementRequest(guard_enabled=True),
        current_user=user, db=db,
    )
    assert on["guard_enabled"] is True
    # 기준선은 시세를 아는 스케줄러가 다음 사이클에 채운다.
    assert on["guard_baseline_score"] is None
    db.close()


def test_guard_toggle_requires_external_holding():
    db = _make_db()
    user = _make_user(db)
    _add_external(db, user, strategy_type="regime_switching", management=MANAGEMENT_BOT_OWNED)

    with pytest.raises(HTTPException) as exc:
        account_router.update_holding_management(
            ticker="HCTI",
            payload=account_router.HoldingManagementRequest(guard_enabled=True),
            current_user=user, db=db,
        )
    assert exc.value.status_code == 400
    db.close()


def test_harvest_and_guard_are_independent(monkeypatch, fixed_evaluator):
    """두 스위치는 배타적이지 않다. 함께 켜면 급등엔 수확, 붕괴엔 경보다."""
    db = _make_db()
    user = _make_user(db)
    holding = _add_external(db, user, harvest_enabled=True, guard_enabled=True)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    broker = _Broker()

    fixed_evaluator.score = 50.0
    _run_cycle(db, user, broker, holding, price=50.0)   # 관측 시작가 50, 방어 기준선 50/50
    row = db.query(Holding).filter_by(user_id=user.id).one()
    assert float(row.observed_base_price) == 50.0
    assert row.guard_baseline_score == 50.0

    _run_cycle(db, user, broker, holding, price=90.0)   # 급등 -> 수확 무장
    row = db.query(Holding).filter_by(user_id=user.id).one()
    assert row.harvest_armed is True
    assert broker.sell_calls == []
    db.close()
