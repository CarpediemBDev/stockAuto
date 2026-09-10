"""수확 모드(Harvest Mode) 회귀 테스트.

반토막 난 종목이 급등했다가 되돌아가는 것을 사용자가 자는 동안 지켜보기만 하는 문제를
푸는 기능이다. 봇은 고점을 예측하지 않고 관측 최고가를 기록만 하다가, 고점 대비 정해진
폭만큼 내려온 상태가 두 사이클 연속되면 판다.

여기서 고정하는 계약은 네 가지다.
  1. 기본값 off. 켜지 않으면 EXTERNAL은 여전히 봇이 아무것도 하지 않는다.
  2. 무장 전에는 아무것도 하지 않는다. 급등해야 감시가 시작된다.
  3. 관측 시작가 아래에서는 절대 팔지 않는다 (하한 가드).
  4. 앵커는 avg_price(본전)가 아니라 observed_base_price(봇이 처음 본 가격)다.
     본전을 앵커로 쓰면 반토막 종목은 영원히 무장되지 않는다.

설계 정본은 docs/plans/holding_management_modes.md 5.2절.
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
    HARVEST_SUSTAIN_MINUTES,
    check_harvest_arm,
    check_harvest_breach,
    get_harvest_arm_pct,
    get_harvest_trailing_pct,
)
from app.core.database import Base
from app.core.models import (
    EXTERNAL_STRATEGY_TYPE,
    MANAGEMENT_BOT_OWNED,
    MANAGEMENT_EXTERNAL,
    ActionLog,
    Holding,
    User,
    UserSettings,
    utc_now_aware,
)


def _age_breach(db, holding_id, minutes=HARVEST_SUSTAIN_MINUTES + 1):
    """트레일링 이탈이 시작된 시각을 과거로 민다.

    노이즈 버퍼는 관측 횟수와 실제 경과 시간을 모두 요구한다. 테스트는 사이클을 즉시
    돌리므로 시간 조건이 만족되지 않는다 - 시간만 흘려보내는 것이 목적이다.
    """
    db.query(Holding).filter(Holding.id == holding_id).update(
        {Holding.harvest_breach_started_at: utc_now_aware() - timedelta(minutes=minutes)},
        synchronize_session=False,
    )
    db.commit()


# ======================================================================================
# 1. 순수 판정 함수
# ======================================================================================

def test_arm_threshold_scales_with_volatility():
    """잔잔한 종목은 낮은 임계, 밈주는 높은 임계. 상한에서 발산이 멈춘다."""
    assert get_harvest_arm_pct(0.02, 1.0) == 15.0   # ATR 2% -> 하한
    assert get_harvest_arm_pct(0.05, 1.0) == 20.0   # ATR 5% -> 동적
    assert get_harvest_arm_pct(0.50, 1.0) == 40.0   # ATR 50% -> 상한에서 절단
    # ATR을 못 구해도 기능이 꺼지지 않는다.
    assert get_harvest_arm_pct(0.0, 1.0) == 15.0


def test_trailing_is_wider_than_bot_positions():
    """수확 트레일링은 봇 진입분(최소 2%, ATR 1배)보다 넓다."""
    assert get_harvest_trailing_pct(0.01, 1.0) == 5.0    # 하한
    assert get_harvest_trailing_pct(0.10, 1.0) == 20.0   # ATR 10% * 2.0


def test_arm_requires_gain_above_threshold():
    assert check_harvest_arm(63.0, 50.0, 25.0) is True    # +26%
    assert check_harvest_arm(62.0, 50.0, 25.0) is False   # +24%
    assert check_harvest_arm(80.0, None, 25.0) is False    # 앵커 미기록


def test_breach_never_fires_below_observed_base():
    """하한 가드: 급등 후 폭락해도 관측 시작가 아래에서는 팔지 않는다.

    무장이 래치이므로 이 가드가 없으면 고점만 높게 남아 즉시 이탈 판정이 나고,
    '위로 갔다 꺾일 때만 판다'는 계약이 뒤집힌다.
    """
    # 고점 90에서 85로 꺾임, 관측 시작가 50 -> 판다
    assert check_harvest_breach(85.0, 90.0, 5.0, 50.0) is True
    # 같은 고점에서 45로 폭락 -> 관측 시작가(50) 아래이므로 팔지 않는다
    assert check_harvest_breach(45.0, 90.0, 5.0, 50.0) is False
    # 정확히 관측 시작가도 팔지 않는다
    assert check_harvest_breach(50.0, 90.0, 5.0, 50.0) is False


def test_breach_requires_peak_above_base():
    """고점이 관측 시작가를 넘긴 적이 없으면 발동하지 않는다."""
    assert check_harvest_breach(48.0, 49.0, 5.0, 50.0) is False


def test_anchor_is_observed_base_not_cost_basis():
    """반토막 종목의 핵심 시나리오 - 본전을 앵커로 쓰면 절대 발동하지 않는다.

    10만원에 사서 5만원까지 빠진 종목이 9만원까지 급등한 상황.
    본전(10만) 앵커로는 무장도 매도도 불가능하고, 관측가(5만) 앵커로는 둘 다 가능하다.
    """
    cost_basis, observed_base, peak, now = 100.0, 50.0, 90.0, 85.0

    assert check_harvest_arm(peak, observed_base, 25.0) is True
    assert check_harvest_arm(peak, cost_basis, 25.0) is False

    assert check_harvest_breach(now, peak, 5.0, observed_base) is True
    assert check_harvest_breach(now, peak, 5.0, cost_basis) is False


# ======================================================================================
# 2. 스케줄러 통합
# ======================================================================================

def _make_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _make_user(db, username="harvester"):
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
        return {
            "success": True, "order_no": "SIM-H1", "filled_qty": quantity,
            "filled_price": kwargs.get("price", 1.0), "message": "Success", "status": "FILLED",
        }


def _add_holding(db, user, **overrides):
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


def _run_cycle(db, user, broker, holding, price, atr=1.0):
    """한 사이클을 돌린다.

    보유분을 매번 DB에서 다시 읽는 것이 중요하다. 운영 경로(run_user_trading_flow)도
    사이클마다 ctx.holdings를 새로 조회하며, 관측값은 version 비간섭 Core UPDATE로만
    DB에 반영되므로 같은 detached 객체를 재사용하면 메모리 값이 DB와 어긋난 채 굳는다.
    """
    fresh = db.query(Holding).filter(Holding.id == holding.id).first()
    if fresh is None:  # 전량 매도로 행이 사라진 경우
        return
    signal_map = {fresh.ticker: {"price": price, "details": {"atr": atr, "is_smart_exit": False}}}
    settings_row = db.query(UserSettings).filter_by(user_id=user.id).one()
    ctx = scheduler.TradingFlowContext(
        db=db, user_id=user.id, db_settings=settings_row, trade_mode="SIMULATED",
        session="REGULAR_MARKET", sentiment="BULLISH", exchange_rate=1350.0,
        holdings=[fresh], broker=broker,
        ms_manager=SimpleNamespace(strategies={}),
        first_slot_key="regime_switching", signal_map=signal_map, all_signals=[],
    )
    asyncio.run(scheduler.process_exit_signals(ctx, signal_map))


def _logs(db, user):
    return [row.message for row in db.query(ActionLog).filter_by(user_id=user.id).all()]


def test_disabled_harvest_does_nothing_even_on_huge_spike(monkeypatch):
    """기본값 off - 켜지 않으면 급등해도 봇은 아무것도 하지 않는다."""
    db = _make_db()
    user = _make_user(db)
    holding = _add_holding(db, user, harvest_enabled=False)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    broker = _Broker()

    _run_cycle(db, user, broker, holding, price=50.0)
    _run_cycle(db, user, broker, holding, price=200.0)
    _run_cycle(db, user, broker, holding, price=100.0)

    assert broker.sell_calls == []
    assert not any("Harvest" in m for m in _logs(db, user))
    assert db.query(Holding).filter_by(user_id=user.id).one().harvest_armed is False
    db.close()


def test_full_harvest_lifecycle_on_halved_position(monkeypatch):
    """반토막 종목의 전체 수명주기: 관측 -> 무장 -> 추적 -> 노이즈 버퍼 -> 수확."""
    db = _make_db()
    user = _make_user(db)
    # 본전 $100, 현재 $50 언저리로 반토막 난 상태.
    holding = _add_holding(db, user, harvest_enabled=True, avg_price=100.0, highest_price=50.0)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    broker = _Broker()

    # (1) 첫 관측 - 관측 시작가가 기록되고 무장은 아직 아니다.
    _run_cycle(db, user, broker, holding, price=50.0, atr=1.0)
    row = db.query(Holding).filter_by(user_id=user.id).one()
    assert float(row.observed_base_price) == 50.0
    assert row.harvest_armed is False
    assert broker.sell_calls == []

    # (2) 완만한 상승 - 임계(ATR 2% -> 15%) 미달이라 여전히 무장 안 됨.
    _run_cycle(db, user, broker, holding, price=56.0, atr=1.0)
    assert db.query(Holding).filter_by(user_id=user.id).one().harvest_armed is False

    # (3) 급등 - 무장. 아직 팔지 않는다.
    _run_cycle(db, user, broker, holding, price=70.0, atr=1.0)
    row = db.query(Holding).filter_by(user_id=user.id).one()
    assert row.harvest_armed is True
    assert broker.sell_calls == []
    assert any("ARMED" in m for m in _logs(db, user))

    # (4) 계속 상승 - 고점 갱신만.
    _run_cycle(db, user, broker, holding, price=90.0, atr=1.0)
    assert float(db.query(Holding).filter_by(user_id=user.id).one().highest_price) == 90.0
    assert broker.sell_calls == []

    # (5) 꺾임 1회 - 노이즈 버퍼가 매도를 유예한다.
    _run_cycle(db, user, broker, holding, price=84.0, atr=1.0)
    assert broker.sell_calls == []
    assert any("Delaying sell" in m for m in _logs(db, user))

    # (6) 꺾임 2회 - 관측 횟수는 채웠지만 시간이 안 지나 아직 팔지 않는다.
    _run_cycle(db, user, broker, holding, price=83.5, atr=1.0)
    assert broker.sell_calls == []

    # (7) 시간까지 흐르면 수확한다.
    _age_breach(db, holding.id)
    _run_cycle(db, user, broker, holding, price=83.0, atr=1.0)
    assert broker.sell_calls and broker.sell_calls[0][0] == "HCTI"
    assert any("EXIT SIGNAL" in m for m in _logs(db, user))
    db.close()


def test_crash_below_observed_base_is_never_sold(monkeypatch):
    """무장 후 폭락 - 관측 시작가 아래로 떨어지면 팔지 않고 사용자에게 돌려둔다."""
    db = _make_db()
    user = _make_user(db)
    holding = _add_holding(db, user, harvest_enabled=True, avg_price=100.0, highest_price=50.0)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    broker = _Broker()

    _run_cycle(db, user, broker, holding, price=50.0, atr=1.0)   # 관측 시작가 50
    _run_cycle(db, user, broker, holding, price=90.0, atr=1.0)   # 무장 + 고점 90
    assert db.query(Holding).filter_by(user_id=user.id).one().harvest_armed is True

    # 고점 대비 -50%지만 관측 시작가(50) 아래이므로 두 사이클을 돌려도 팔지 않는다.
    _run_cycle(db, user, broker, holding, price=45.0, atr=1.0)
    _run_cycle(db, user, broker, holding, price=40.0, atr=1.0)

    assert broker.sell_calls == []
    assert db.query(Holding).filter_by(user_id=user.id).one().quantity == 100
    db.close()


def test_recovery_between_breaches_resets_noise_buffer(monkeypatch):
    """한 번 찔렀다 회복하면 카운터가 리셋되어 꼬리에 털리지 않는다."""
    db = _make_db()
    user = _make_user(db)
    holding = _add_holding(db, user, harvest_enabled=True, avg_price=100.0, highest_price=50.0)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    broker = _Broker()

    _run_cycle(db, user, broker, holding, price=50.0, atr=1.0)
    _run_cycle(db, user, broker, holding, price=90.0, atr=1.0)   # 무장, 고점 90
    _run_cycle(db, user, broker, holding, price=84.0, atr=1.0)   # 이탈 1회
    _run_cycle(db, user, broker, holding, price=89.0, atr=1.0)   # 회복 -> 리셋
    _run_cycle(db, user, broker, holding, price=84.0, atr=1.0)   # 다시 1회일 뿐

    assert broker.sell_calls == []
    db.close()


def test_bot_owned_holding_is_untouched_by_harvest(monkeypatch):
    """수확은 EXTERNAL 전용이다. 봇 소유 포지션의 판정 경로를 건드리지 않는다."""
    db = _make_db()
    user = _make_user(db)
    holding = _add_holding(
        db, user, strategy_type="regime_switching", management=MANAGEMENT_BOT_OWNED,
        harvest_enabled=True,
    )
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    broker = _Broker()

    _run_cycle(db, user, broker, holding, price=50.0, atr=1.0)
    _run_cycle(db, user, broker, holding, price=200.0, atr=1.0)

    row = db.query(Holding).filter_by(user_id=user.id).one()
    assert row.harvest_armed is False
    assert row.observed_base_price is None
    assert not any("Harvest" in m for m in _logs(db, user))
    db.close()


# ======================================================================================
# 3. 토글 API
# ======================================================================================

def test_toggle_requires_external_holding():
    """봇이 산 종목에는 위임 스위치가 없다."""
    db = _make_db()
    user = _make_user(db)
    _add_holding(db, user, strategy_type="regime_switching", management=MANAGEMENT_BOT_OWNED)

    with pytest.raises(HTTPException) as exc:
        account_router.update_holding_management(
            ticker="HCTI",
            payload=account_router.HoldingManagementRequest(harvest_enabled=True),
            current_user=user,
            db=db,
        )
    assert exc.value.status_code == 400
    db.close()


def test_toggle_off_also_disarms():
    """끄면 무장도 함께 풀린다 - 다시 켰을 때 급등 판정 없이 매도 구간에 들어가면 안 된다."""
    db = _make_db()
    user = _make_user(db)
    _add_holding(db, user, harvest_enabled=True, harvest_armed=True, observed_base_price=50.0)

    result = account_router.update_holding_management(
        ticker="HCTI",
        payload=account_router.HoldingManagementRequest(harvest_enabled=False),
        current_user=user,
        db=db,
    )
    assert result["harvest_enabled"] is False
    assert result["harvest_armed"] is False

    back_on = account_router.update_holding_management(
        ticker="HCTI",
        payload=account_router.HoldingManagementRequest(harvest_enabled=True),
        current_user=user,
        db=db,
    )
    assert back_on["harvest_enabled"] is True
    assert back_on["harvest_armed"] is False
    db.close()


def test_recovery_clears_both_buffer_axes(monkeypatch):
    """회복하면 관측 횟수와 이탈 시각을 함께 되돌린다.

    둘 중 하나만 지우면 다음 이탈에서 남은 축이 이미 충족된 상태로 시작한다. 방어 게이트에서
    정확히 그 결함이 났다 - guard_streak만 리셋하고 시각을 남겨 벽시계 가드가 처음부터
    통과 상태가 됐다(2026-09-06 stock-auto-mobile 세션 보고).
    """
    db = _make_db()
    user = _make_user(db)
    holding = _add_holding(db, user, harvest_enabled=True, avg_price=100.0, highest_price=50.0)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    broker = _Broker()

    _run_cycle(db, user, broker, holding, price=50.0)   # 관측 시작가 50
    _run_cycle(db, user, broker, holding, price=90.0)   # 무장, 고점 90

    _run_cycle(db, user, broker, holding, price=84.0)   # 이탈 - 시각 기록
    assert db.query(Holding).one().harvest_breach_started_at is not None

    _run_cycle(db, user, broker, holding, price=89.0)   # 회복 - 두 축 모두 리셋
    assert db.query(Holding).one().harvest_breach_started_at is None

    # 다시 이탈해도 시간이 처음부터 다시 흐르므로 즉시 팔리지 않는다.
    _run_cycle(db, user, broker, holding, price=84.0)
    _run_cycle(db, user, broker, holding, price=83.5)
    assert broker.sell_calls == []
    db.close()


def test_restart_does_not_reset_the_breach_clock(monkeypatch):
    """재기동으로 인메모리 카운터가 날아가도 대기 시간은 이어진다.

    시각까지 인메모리였다면 재기동마다 대기가 0으로 돌아가, 급등이 꺾인 뒤에도 매도가
    계속 미뤄진다. 횟수는 두 번 다시 관측하면 그만이지만 시간은 그렇지 않다.
    """
    db = _make_db()
    user = _make_user(db)
    holding = _add_holding(db, user, harvest_enabled=True, avg_price=100.0, highest_price=50.0)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    broker = _Broker()

    _run_cycle(db, user, broker, holding, price=50.0)
    _run_cycle(db, user, broker, holding, price=90.0)
    _run_cycle(db, user, broker, holding, price=84.0)   # 이탈 시작

    started = db.query(Holding).one().harvest_breach_started_at
    assert started is not None

    # 재기동 모사 - 인메모리 카운터만 비운다.
    scheduler.BREACH_COUNT_CACHE.clear()

    assert db.query(Holding).one().harvest_breach_started_at == started
    db.close()


# ---------------------------------------------------------------------------
# 임계값 화면 표시 (harvest_arm_pct / harvest_trailing_pct)
#
# 두 값은 ATR 파생이라 시점마다 다르고 DB 어디에도 남지 않아, 사용자는 자기 종목이 몇 %
# 올라야 무장되는지 알 수 없었다. 잔고 API가 직접 계산하려면 ATR을 얻으려 외부 시세를
# 호출해야 하므로("유저 대면 경로 외부 호출 0건" 원칙), 스케줄러가 이미 계산하는 값을
# 영속화하고 API는 읽기만 한다.
# ---------------------------------------------------------------------------


def test_thresholds_are_recorded_even_while_harvest_is_off(monkeypatch):
    """스위치를 켜기 전에도 임계가 보여야 한다 - 켤지 말지의 판단 근거이기 때문이다.

    켰을 때만 기록하면 화면이 "켜봐야 알 수 있다"가 되고, 그것은 되돌릴 수 있다 해도
    사용자에게 스위치를 눌러보게 강요하는 설계다.
    """
    db = _make_db()
    user = _make_user(db)
    holding = _add_holding(db, user, harvest_enabled=False)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)

    _run_cycle(db, user, _Broker(), holding, price=50.0, atr=1.0)

    refreshed = db.query(Holding).filter_by(id=holding.id).one()
    # ATR% = 1.0/50.0 = 2% → 무장 min(40, max(15, 8)) = 15, 트레일링 max(5, 4) = 5
    assert refreshed.harvest_arm_pct == pytest.approx(get_harvest_arm_pct(1.0, 50.0))
    assert refreshed.harvest_trailing_pct == pytest.approx(get_harvest_trailing_pct(1.0, 50.0))
    assert refreshed.harvest_enabled is False  # 기록이 스위치를 켜지는 않는다
    db.close()


def test_thresholds_follow_volatility_across_cycles(monkeypatch):
    """기록은 스냅샷이다 - ATR이 바뀌면 다음 사이클에 따라 바뀐다."""
    db = _make_db()
    user = _make_user(db)
    holding = _add_holding(db, user, harvest_enabled=True, observed_base_price=50.0)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)

    _run_cycle(db, user, _Broker(), holding, price=50.0, atr=1.0)
    calm = db.query(Holding).filter_by(id=holding.id).one().harvest_arm_pct

    _run_cycle(db, user, _Broker(), holding, price=50.0, atr=5.0)
    volatile = db.query(Holding).filter_by(id=holding.id).one()

    # ATR% 2% → 무장 15%(하한). ATR% 10% → 40%(상한에 걸림).
    assert calm == pytest.approx(15.0)
    assert volatile.harvest_arm_pct == pytest.approx(40.0)
    assert volatile.harvest_trailing_pct == pytest.approx(20.0)
    db.close()


def test_bot_owned_holding_gets_no_thresholds(monkeypatch):
    """봇 소유분에는 기록하지 않는다 - 수확 모드가 적용되지 않는 포지션이다."""
    db = _make_db()
    user = _make_user(db)
    holding = _add_holding(
        db, user, management=MANAGEMENT_BOT_OWNED, strategy_type="regime_switching",
    )
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)

    _run_cycle(db, user, _Broker(), holding, price=50.0, atr=1.0)

    refreshed = db.query(Holding).filter_by(id=holding.id).one()
    assert refreshed.harvest_arm_pct is None
    assert refreshed.harvest_trailing_pct is None
    db.close()


def test_threshold_record_does_not_bump_version_id(monkeypatch):
    """version_id를 올리면 안 된다.

    올리면 같은 사이클 Part B의 db.merge(h)가 StaleDataError로 터져 사이클이 통째로
    중단된다. last_price·highest_price가 Core UPDATE를 쓰는 것과 같은 이유이며,
    표시용 값 때문에 매매가 멎는 것은 용납할 수 없는 맞바꿈이다.
    """
    db = _make_db()
    user = _make_user(db)
    holding = _add_holding(db, user)
    before = db.query(Holding).filter_by(id=holding.id).one().version_id
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)

    _run_cycle(db, user, _Broker(), holding, price=50.0, atr=1.0)
    _run_cycle(db, user, _Broker(), holding, price=50.0, atr=1.0)

    assert db.query(Holding).filter_by(id=holding.id).one().version_id == before
    db.close()
