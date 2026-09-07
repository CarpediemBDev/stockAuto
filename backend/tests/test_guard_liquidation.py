"""5단계 방어 조치(섀도 · 부분 청산) 회귀 테스트.

4단계는 경보만 냈다. 5단계는 "무엇을 할지"를 붙인다 - 다만 기본값은 여전히 알림만이다.

당초 이 단계는 "경보가 실제 붕괴를 예측한다는 근거가 없으니 수 주간 실측 후 착수"로
미뤄뒀는데, 그 실측 계획이 사람이 로그를 눈으로 상관분석하는 것이었다. SHADOW 모드를
기능 안에 넣으면 그 측정이 코드가 하는 일이 된다. 증거 부족은 기본값과 가드를 어떻게
잡을지의 근거이지 기능을 만들지 말라는 근거가 아니다.

여기서 고정하는 계약은 다섯 가지다.
  1. 기본값 ALERT_ONLY. 청산은 사용자가 명시적으로 켜야 한다.
  2. SHADOW는 절대 주문을 내지 않는다. 기록만 남긴다.
  3. LIQUIDATE는 부분 청산이다. 포지션 전체를 확정하지 않는다.
  4. 연속 충족(10사이클)을 요구한다. 수확의 2사이클보다 훨씬 엄격하다.
  5. 하루 한 번만 조치한다.

설계 정본은 docs/plans/holding_management_modes.md 5.4절.
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
    GUARD_SUSTAIN_CYCLES,
    GUARD_SUSTAIN_MINUTES,
    resolve_guard_sell_qty,
)
from app.core.database import Base
from app.core.models import (
    EXTERNAL_STRATEGY_TYPE,
    GUARD_ACTION_ALERT_ONLY,
    GUARD_ACTION_LIQUIDATE,
    GUARD_ACTION_SHADOW,
    MANAGEMENT_EXTERNAL,
    ActionLog,
    Holding,
    TradeLog,
    User,
    UserSettings,
    utc_now_aware,
)


# ======================================================================================
# 1. 부분 청산 수량
# ======================================================================================

def test_partial_sell_quantity_never_zero_or_over():
    """비율로 나눌 수 없는 소량 보유에서도 조치가 조용히 미발동되지 않는다."""
    assert resolve_guard_sell_qty(100, 0.5) == 50
    assert resolve_guard_sell_qty(3, 0.5) == 1      # 내림하되 최소 1주
    assert resolve_guard_sell_qty(1, 0.5) == 1      # 1주 보유도 조치 가능
    assert resolve_guard_sell_qty(100, 1.0) == 100  # 전량도 허용
    assert resolve_guard_sell_qty(0, 0.5) == 0      # 보유 없음
    assert resolve_guard_sell_qty(100, None) == 50  # 기본 비율


# ======================================================================================
# 2. 스케줄러 통합
# ======================================================================================

def _make_db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _make_user(db):
    user = User(username="defender", hashed_password="hashed")
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
        return {"success": True, "order_no": "G1", "filled_qty": quantity,
                "filled_price": kwargs.get("price", 1.0), "message": "ok", "status": "FILLED"}


class _FixedScore:
    def __init__(self, score=50.0):
        self.score = score

    def calculate_score(self, *_a, **_k):
        return self.score


@pytest.fixture
def evaluator(monkeypatch):
    ev = _FixedScore()
    monkeypatch.setattr(scheduler, "_get_guard_evaluator", lambda: ev)
    return ev


def _add(db, user, **overrides):
    fields = dict(
        user_id=user.id, ticker="HCTI", ticker_name="Healthcare Triangle",
        strategy_type=EXTERNAL_STRATEGY_TYPE, management=MANAGEMENT_EXTERNAL,
        avg_price=100.0, quantity=100, highest_price=50.0, guard_enabled=True,
    )
    fields.update(overrides)
    h = Holding(**fields)
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


def _cycle(db, user, broker, holding, price):
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
    return [r.message for r in db.query(ActionLog).filter_by(user_id=user.id).all()]


def _age(db, hid, minutes):
    db.query(Holding).filter(Holding.id == hid).update(
        {Holding.guard_enabled_at: utc_now_aware() - timedelta(minutes=minutes)},
        synchronize_session=False,
    )
    db.commit()


def _age_streak(db, hid, minutes):
    """연속 충족 시작 시각을 과거로 민다.

    조치 게이트는 사이클 수와 실제 경과 시간을 모두 요구한다. 테스트는 사이클을 즉시
    돌리므로 벽시계 조건이 만족되지 않는다 - 시간만 흘려보내는 것이 목적이다.
    """
    db.query(Holding).filter(Holding.id == hid).update(
        {Holding.guard_streak_started_at: utc_now_aware() - timedelta(minutes=minutes)},
        synchronize_session=False,
    )
    db.commit()


def _collapse(db, user, broker, holding, evaluator, cycles, start=7.0, age_streak=True):
    """조건을 연속 충족시킨다. 신저가를 갱신해야 하므로 가격을 계속 낮춘다."""
    evaluator.score = 20.0
    price = start
    for i in range(cycles):
        _cycle(db, user, broker, holding, price)
        price -= 0.1
        # 첫 사이클에서 연속이 시작되므로 그 직후 한 번만 과거로 민다.
        # 이후 사이클은 기존 시작 시각을 보존하므로 되돌아가지 않는다.
        if i == 0 and age_streak:
            _age_streak(db, holding.id, GUARD_SUSTAIN_MINUTES + 1)


def test_alert_only_is_the_default_and_never_sells(monkeypatch, evaluator):
    """기본값에서는 조건을 아무리 오래 충족해도 주문이 나가지 않는다."""
    db = _make_db()
    user = _make_user(db)
    holding = _add(db, user)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    broker = _Broker()

    assert db.query(Holding).one().guard_action == GUARD_ACTION_ALERT_ONLY

    evaluator.score = 50.0
    _cycle(db, user, broker, holding, 10.0)
    _age(db, holding.id, 60)
    _collapse(db, user, broker, holding, evaluator, GUARD_SUSTAIN_CYCLES + 5)

    assert broker.sell_calls == []
    assert db.query(TradeLog).count() == 0
    assert db.query(Holding).one().quantity == 100
    assert any("[Guard] ALERT" in m for m in _logs(db, user))
    db.close()


def test_shadow_records_counterfactual_without_ordering(monkeypatch, evaluator):
    """SHADOW는 '팔았다면 이랬을 것'만 남기고 주문을 내지 않는다.

    이 로그가 5단계 착수 근거를 만드는 측정 원천이다.
    """
    db = _make_db()
    user = _make_user(db)
    holding = _add(db, user, guard_action=GUARD_ACTION_SHADOW)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    broker = _Broker()

    evaluator.score = 50.0
    _cycle(db, user, broker, holding, 10.0)
    _age(db, holding.id, 60)
    _collapse(db, user, broker, holding, evaluator, GUARD_SUSTAIN_CYCLES + 2)

    shadow = [m for m in _logs(db, user) if "[SHADOW]" in m]
    assert len(shadow) == 1
    assert "would_sell_qty=50" in shadow[0]
    assert "no order placed" in shadow[0]

    assert broker.sell_calls == []
    assert db.query(TradeLog).count() == 0
    assert db.query(Holding).one().quantity == 100
    db.close()


def test_liquidate_sells_only_the_configured_fraction(monkeypatch, evaluator):
    """LIQUIDATE는 부분 청산이다. 포지션 전체를 확정하지 않는다."""
    db = _make_db()
    user = _make_user(db)
    holding = _add(db, user, guard_action=GUARD_ACTION_LIQUIDATE, guard_sell_ratio=0.5)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    broker = _Broker()

    evaluator.score = 50.0
    _cycle(db, user, broker, holding, 10.0)
    _age(db, holding.id, 60)
    _collapse(db, user, broker, holding, evaluator, GUARD_SUSTAIN_CYCLES + 2)

    assert broker.sell_calls == [("HCTI", 50)]
    row = db.query(Holding).filter_by(user_id=user.id).one()
    assert row.quantity == 50          # 절반은 남는다
    log = db.query(TradeLog).one()
    assert log.quantity == 50
    db.close()


def test_liquidate_requires_sustained_breach(monkeypatch, evaluator):
    """짧게 스친 붕괴로는 팔지 않는다. 수확의 2사이클보다 훨씬 엄격하다."""
    db = _make_db()
    user = _make_user(db)
    holding = _add(db, user, guard_action=GUARD_ACTION_LIQUIDATE)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    broker = _Broker()

    evaluator.score = 50.0
    _cycle(db, user, broker, holding, 10.0)
    _age(db, holding.id, 60)

    _collapse(db, user, broker, holding, evaluator, GUARD_SUSTAIN_CYCLES - 1)
    assert broker.sell_calls == []
    assert db.query(Holding).one().guard_streak == GUARD_SUSTAIN_CYCLES - 1
    db.close()


def test_recovery_resets_the_streak(monkeypatch, evaluator):
    """조건이 한 번 끊기면 연속 카운터가 0으로 돌아간다."""
    db = _make_db()
    user = _make_user(db)
    holding = _add(db, user, guard_action=GUARD_ACTION_LIQUIDATE)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    broker = _Broker()

    evaluator.score = 50.0
    _cycle(db, user, broker, holding, 10.0)
    _age(db, holding.id, 60)

    _collapse(db, user, broker, holding, evaluator, GUARD_SUSTAIN_CYCLES - 2)
    assert db.query(Holding).one().guard_streak > 0

    # 점수 회복 -> 조건 미충족 -> 리셋
    evaluator.score = 50.0
    _cycle(db, user, broker, holding, 6.0)
    assert db.query(Holding).one().guard_streak == 0
    assert broker.sell_calls == []
    db.close()


def test_daily_cap_blocks_second_liquidation(monkeypatch, evaluator):
    """무너지는 날 같은 보유분을 반복 청산하지 않는다."""
    db = _make_db()
    user = _make_user(db)
    holding = _add(db, user, guard_action=GUARD_ACTION_LIQUIDATE)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    broker = _Broker()

    evaluator.score = 50.0
    _cycle(db, user, broker, holding, 10.0)
    _age(db, holding.id, 60)

    _collapse(db, user, broker, holding, evaluator, GUARD_SUSTAIN_CYCLES + 2)
    assert len(broker.sell_calls) == 1

    # 계속 무너져도 24시간 안에는 다시 팔지 않는다.
    _collapse(db, user, broker, holding, evaluator, GUARD_SUSTAIN_CYCLES + 5, start=5.0)
    assert len(broker.sell_calls) == 1
    db.close()


# ======================================================================================
# 3. 토글 API
# ======================================================================================

def test_action_mode_requires_guard_enabled():
    """방어가 꺼진 상태에서 청산 모드를 켤 수 없다."""
    db = _make_db()
    user = _make_user(db)
    _add(db, user, guard_enabled=False)

    with pytest.raises(HTTPException) as exc:
        account_router.update_holding_management(
            ticker="HCTI",
            payload=account_router.HoldingManagementRequest(guard_action="LIQUIDATE"),
            current_user=user, db=db,
        )
    assert exc.value.status_code == 400
    db.close()


def test_unknown_action_is_rejected():
    db = _make_db()
    user = _make_user(db)
    _add(db, user, guard_enabled=True)

    with pytest.raises(HTTPException) as exc:
        account_router.update_holding_management(
            ticker="HCTI",
            payload=account_router.HoldingManagementRequest(guard_action="SELL_EVERYTHING"),
            current_user=user, db=db,
        )
    assert exc.value.status_code == 400
    db.close()


def test_switching_mode_resets_streak():
    """알림만으로 쌓인 연속 충족이 청산 모드 전환 즉시 조치로 이어지면 안 된다."""
    db = _make_db()
    user = _make_user(db)
    _add(db, user, guard_enabled=True, guard_streak=GUARD_SUSTAIN_CYCLES + 3)

    result = account_router.update_holding_management(
        ticker="HCTI",
        payload=account_router.HoldingManagementRequest(guard_action=GUARD_ACTION_LIQUIDATE),
        current_user=user, db=db,
    )
    assert result["guard_action"] == GUARD_ACTION_LIQUIDATE
    assert db.query(Holding).one().guard_streak == 0
    db.close()


def test_turning_guard_off_resets_action_to_alert_only():
    """방어를 끄면 조치 모드도 기본값으로 돌아간다.

    끌 때 LIQUIDATE가 남으면 나중에 방어를 다시 켜는 순간 사용자가 의도하지 않은 채
    청산 모드로 재개된다. 되돌릴 수 없는 매도는 매번 명시적으로 선택되어야 한다.
    """
    db = _make_db()
    user = _make_user(db)
    _add(db, user, guard_enabled=True, guard_action=GUARD_ACTION_LIQUIDATE, guard_sell_ratio=0.75)

    off = account_router.update_holding_management(
        ticker="HCTI",
        payload=account_router.HoldingManagementRequest(guard_enabled=False),
        current_user=user, db=db,
    )
    assert off["guard_enabled"] is False
    assert off["guard_action"] == GUARD_ACTION_ALERT_ONLY

    # 다시 켜도 청산 모드로 재개되지 않는다.
    on = account_router.update_holding_management(
        ticker="HCTI",
        payload=account_router.HoldingManagementRequest(guard_enabled=True),
        current_user=user, db=db,
    )
    assert on["guard_action"] == GUARD_ACTION_ALERT_ONLY
    db.close()


def test_shadow_sends_the_record_to_the_user(monkeypatch, evaluator):
    """섀도 기록은 로그로만 남기면 안 된다 - 사용자가 볼 수 있어야 모드가 쓸모를 갖는다.

    ActionLog는 관리자 패널에만 노출되므로, 측정 결과가 사용자 손에 들어오는 경로는
    현재 텔레그램뿐이다. 조치 시점은 10사이클 지속 + 일일 1회로 좁혀져 있어 잦지 않다.
    """
    db = _make_db()
    user = _make_user(db)
    holding = _add(db, user, guard_action=GUARD_ACTION_SHADOW)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)

    sent = []
    monkeypatch.setattr(scheduler, "send_message_async", lambda uid, msg: sent.append((uid, msg)))

    broker = _Broker()
    evaluator.score = 50.0
    _cycle(db, user, broker, holding, 10.0)
    _age(db, holding.id, 60)
    _collapse(db, user, broker, holding, evaluator, GUARD_SUSTAIN_CYCLES + 2)

    # 경보 1건 + 매도 시점 알림 1건. 문구가 바뀌어도 흔들리지 않도록 핵심 주장으로 매칭한다.
    shadow_msgs = [
        m for _uid, m in sent
        if "실제로 팔지는 않았습니다" in m or "Nothing was actually sold" in m
    ]
    assert len(shadow_msgs) == 1
    body = shadow_msgs[0]
    assert "50" in body                 # 팔았을 수량(100주의 50%)
    assert "매도 시점 알림" in body or "Sell-point alerts" in body

    # 그래도 주문은 없다.
    assert broker.sell_calls == []
    assert db.query(TradeLog).count() == 0
    db.close()


def test_enough_cycles_without_enough_time_does_not_act(monkeypatch, evaluator):
    """사이클 수만 채워도 실제 시간이 안 지났으면 조치하지 않는다.

    스케줄러는 1분 간격으로 등록돼 있지만 실측 주기는 중앙값 124초에 편차가 104~846초다
    (2026-09-06 admin action_logs 40표본). 사이클 수만 게이트로 쓰면 같은 10사이클이
    20분일 수도 두 시간일 수도 있고, 반대로 주기가 빨라지면 순식간에 조치가 나간다.
    되돌릴 수 없는 매도의 조건이 그렇게 흔들려서는 안 된다.
    """
    db = _make_db()
    user = _make_user(db)
    holding = _add(db, user, guard_action=GUARD_ACTION_LIQUIDATE)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    broker = _Broker()

    evaluator.score = 50.0
    _cycle(db, user, broker, holding, 10.0)
    _age(db, holding.id, 60)

    # 사이클은 넉넉히 채우되 시간은 흘리지 않는다.
    _collapse(db, user, broker, holding, evaluator, GUARD_SUSTAIN_CYCLES + 5, age_streak=False)

    row = db.query(Holding).filter_by(user_id=user.id).one()
    assert row.guard_streak >= GUARD_SUSTAIN_CYCLES   # 횟수 조건은 충족됐다
    assert row.guard_streak_started_at is not None    # 시작 시각은 기록됐다
    assert broker.sell_calls == []                    # 그럼에도 팔지 않았다
    assert db.query(TradeLog).count() == 0

    # 시간까지 흐르면 그때 조치한다.
    _age_streak(db, holding.id, GUARD_SUSTAIN_MINUTES + 1)
    _collapse(db, user, broker, holding, evaluator, 1, start=5.0, age_streak=False)
    assert broker.sell_calls == [("HCTI", 50)]
    db.close()


def _switch(user, db, **kwargs):
    return account_router.update_holding_management(
        ticker="HCTI",
        payload=account_router.HoldingManagementRequest(**kwargs),
        current_user=user, db=db,
    )


def test_every_switch_change_restarts_both_streak_axes():
    """스위치를 건드리면 횟수와 시간을 모두 0부터 다시 센다.

    2026-09-06 stock-auto-mobile 세션이 소스를 읽다 발견한 결함이다. guard_streak만 0으로
    되돌리고 guard_streak_started_at을 남기면, 스케줄러의 (streak_started_at or now)가 옛
    시각을 물려받아 벽시계 20분 가드가 처음부터 통과 상태가 된다. 즉 되돌릴 수 없는 매도를
    켠 직후 20분을 지켜본다는 보호가 성립하지 않는다.

    시간 축만 뚫리므로 사이클 게이트 때문에 즉시 팔리지는 않는다. 그래서 눈에 잘 띄지 않는다.
    """
    db = _make_db()
    user = _make_user(db)
    old = utc_now_aware() - timedelta(minutes=GUARD_SUSTAIN_MINUTES * 3)

    for label, kwargs in [
        ("모드 변경", dict(guard_action=GUARD_ACTION_LIQUIDATE)),
        ("비율 변경", dict(guard_sell_ratio=0.25)),
        ("방어 끔", dict(guard_enabled=False)),
        ("방어 켬", dict(guard_enabled=True)),
    ]:
        db.query(Holding).delete()
        db.commit()
        _add(db, user, guard_enabled=True, guard_action=GUARD_ACTION_LIQUIDATE,
             guard_streak=GUARD_SUSTAIN_CYCLES + 5, guard_streak_started_at=old)

        _switch(user, db, **kwargs)

        row = db.query(Holding).one()
        assert row.guard_streak == 0, f"{label}: 횟수가 리셋되지 않았다"
        assert row.guard_streak_started_at is None, f"{label}: 지속 시각이 리셋되지 않았다"
    db.close()
