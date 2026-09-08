"""6단계 위임(DELEGATED) 모드 회귀 테스트.

위임은 사용자가 이미 들고 있던 포지션을 봇에 통째로 넘기는 모드다. 수확·방어가
"이런 조건에서만 팔아라"라면 위임은 "네 규칙대로 알아서 해라"다.

여기서 고정하는 계약은 다섯 가지다.
  1. 리스크 앵커는 avg_price가 아니라 risk_basis_price(위임 시점가)다. 그렇지 않으면
     반토막 종목을 맡기는 순간 손절선이 이미 뚫려 있어 인수 즉시 청산된다.
  2. 실현손익은 여전히 avg_price로 계산한다. 리스크만 분리하고 원장은 손대지 않는다.
  3. 위임 시점에 즉시 청산하지 않는다. 청산은 다음 사이클의 정상 규칙에 맡긴다.
     위임 버튼이 곧 매도 버튼이 되면 아무도 누르지 않는다.
  4. 추가매수는 봉인한다(buy_stage=3). 봇이 물타기로 사용자의 손실 포지션을 키우면
     위임의 취지와 정반대가 된다.
  5. BOT_OWNED로는 전환할 수 없다. 봇 매수분과 원장을 섞으면 전략 성과 측정이 깨진다.

재진입 심사는 게이트가 아니라 통보다. 미달이어도 위임은 그대로 적용된다 - 이미 들고 있는
것을 맡기는 결정과 새로 사는 결정은 다른 판단이며, 후자의 기준으로 전자를 거부하면
손실 난 종목은 영원히 맡길 수 없다.

설계 정본은 docs/plans/holding_management_modes.md 5.5절.
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
from app.core.database import Base
from app.core.models import (
    EXTERNAL_STRATEGY_TYPE,
    MANAGEMENT_BOT_OWNED,
    MANAGEMENT_DELEGATED,
    MANAGEMENT_EXTERNAL,
    Holding,
    Strategy,
    User,
    UserSettings,
    utc_now_aware,
)


SLOT = "regime_switching"


def _make_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    db.add(Strategy(
        strategy_type=SLOT, name_ko="레짐 스위칭", is_active=True, is_selectable=True,
    ))
    db.commit()
    return db


def _make_user(db, username="delegator"):
    user = User(username=username, hashed_password="hashed")
    db.add(user)
    db.flush()
    db.add(UserSettings(
        user_id=user.id, strategy_type=SLOT, trade_mode="SIMULATED", is_running=True,
    ))
    db.commit()
    db.refresh(user)
    return user


def _add_external(db, user, **overrides):
    """반토막 난 외부 유입 포지션. 120에 사서 60까지 빠진 상태."""
    fields = dict(
        user_id=user.id, ticker="HCTI", ticker_name="Healthcare Triangle",
        strategy_type=EXTERNAL_STRATEGY_TYPE, management=MANAGEMENT_EXTERNAL,
        avg_price=120.0, quantity=100, highest_price=120.0,
    )
    fields.update(overrides)
    h = Holding(**fields)
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


class _Broker:
    def __init__(self):
        self.sell_calls = []

    def get_holdings(self, exchange_rate=None):
        return []

    def sell_order(self, ticker, quantity, **kwargs):
        self.sell_calls.append((ticker, quantity))
        return {
            "success": True, "order_no": "SIM-D1", "filled_qty": quantity,
            "filled_price": kwargs.get("price", 1.0), "message": "Success", "status": "FILLED",
        }


def _slot_strategies():
    """운영과 같은 전략 인스턴스를 슬롯에 채운다.

    비워 두면 process_exit_signals가 strategy_instance is None에서 continue 하므로,
    위임분이 판정부에 도달하지 못한 채 테스트가 "안 팔았다"로 통과해 버린다.
    격리 테스트에서 실제로 겪은 거짓 통과와 같은 함정이다.

    시그널 붕괴 판정만 끈다. 이 테스트가 묻는 것은 손절 앵커가 avg_price인지
    risk_basis_price인지이고, 붕괴 판정은 그 질문과 무관한 별개 경로다. 게다가 여기서
    쓰는 가짜 시그널에는 지표가 없어 어떤 전략이든 0점을 매기고 곧바로 붕괴로 판정한다 -
    끄지 않으면 앵커가 무엇이든 매도가 나가 테스트가 아무것도 검증하지 못한다.

    붕괴 경로가 위임분에 어떻게 적용되어야 하는지는 별도 과제다. 현재는 손절과 달리
    노이즈 버퍼도 리스크 앵커도 타지 않는다.
    """
    from app.strategies.strategy_factory import get_strategy
    strategy = get_strategy(SLOT)
    strategy.is_signal_collapsed = lambda *args, **kwargs: False
    return {SLOT: strategy}


def _delegate(db, user, monkeypatch, *, price=60.0, slot=SLOT, verdict="BELOW_CUTOFF",
              strategy_type=None):
    """위임 엔드포인트를 호출한다. 시세와 심사는 네트워크를 타지 않도록 대체한다."""
    async def _fake_price(holding):
        return price

    async def _fake_screen(slot_key, clean_ticker):
        return {"verdict": verdict, "score": 40.0, "cutoff_score": 55.0, "reason": "테스트"}

    monkeypatch.setattr(account_router, "_resolve_market_price", _fake_price)
    monkeypatch.setattr(account_router, "_screen_reentry", _fake_screen)
    return asyncio.run(account_router.change_holding_delegation(
        ticker="HCTI",
        payload=account_router.HoldingDelegationRequest(
            action="DELEGATE", delegate_slot=slot, strategy_type=strategy_type,
        ),
        current_user=user, db=db,
    ))


def _run_cycle(db, user, broker, holding_id, price, monkeypatch, atr=1.0):
    # micro_session은 모듈 전역 SessionLocal로 자기 세션을 새로 연다. 인메모리 DB를 쓰는
    # 테스트에서는 그 세션이 다른 DB를 보게 되므로 같은 세션을 돌려주도록 묶는다.
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    fresh = db.query(Holding).filter(Holding.id == holding_id).first()
    if fresh is None:
        return
    signal_map = {fresh.ticker: {"price": price, "details": {"atr": atr, "is_smart_exit": False}}}
    settings_row = db.query(UserSettings).filter_by(user_id=user.id).one()
    ctx = scheduler.TradingFlowContext(
        db=db, user_id=user.id, db_settings=settings_row, trade_mode="SIMULATED",
        session="REGULAR_MARKET", sentiment="BULLISH", exchange_rate=1350.0,
        holdings=[fresh], broker=broker,
        ms_manager=SimpleNamespace(strategies=_slot_strategies()),
        first_slot_key=SLOT, signal_map=signal_map, all_signals=[],
    )
    asyncio.run(scheduler.process_exit_signals(ctx, signal_map))


def _age_exit_breach(db, holding_id, minutes=10):
    """손절 노이즈 버퍼의 시간 축을 과거로 민다.

    버퍼는 관측 횟수와 경과 시간을 모두 요구한다. 테스트는 사이클을 즉시 연달아 돌리므로
    시간 조건이 만족되지 않는다 - 시간만 흘려보내는 것이 목적이다.
    """
    db.query(Holding).filter(Holding.id == holding_id).update(
        {Holding.exit_breach_started_at: utc_now_aware() - timedelta(minutes=minutes)},
        synchronize_session=False,
    )
    db.commit()


# ======================================================================================
# 1. 관할권 전환
# ======================================================================================

def test_delegation_sets_risk_anchor_without_touching_cost_basis(monkeypatch):
    """핵심 계약 - 리스크 기준가는 위임 시점가, 매수가는 그대로."""
    db = _make_db()
    user = _make_user(db)
    holding = _add_external(db, user)
    assert float(holding.avg_price) == 120.0

    result = _delegate(db, user, monkeypatch, price=60.0)

    db.refresh(holding)
    assert holding.management == MANAGEMENT_DELEGATED
    assert holding.strategy_type == SLOT
    assert float(holding.risk_basis_price) == 60.0
    assert holding.highest_price == 60.0
    # 원장은 손대지 않는다. 120에 산 사실이 60으로 바뀌면 실현손익이 거짓이 된다.
    assert float(holding.avg_price) == 120.0
    assert result["management"] == MANAGEMENT_DELEGATED
    assert result["risk_basis_price"] == 60.0


def test_delegation_seals_pyramiding(monkeypatch):
    """추가매수 봉인. 봇이 물타기로 사용자의 손실 포지션을 키우면 안 된다."""
    db = _make_db()
    user = _make_user(db)
    holding = _add_external(db, user, buy_stage=1)

    _delegate(db, user, monkeypatch)

    db.refresh(holding)
    assert holding.buy_stage == 3
    # resolve_entry_stage는 buy_stage가 3이면 무조건 None을 돌려준다(피라미딩 종료 단계).
    assert scheduler.resolve_entry_stage(
        SimpleNamespace(sentiment="BULLISH", user_id=user.id),
        SimpleNamespace(get_pyramid_trigger=lambda n: 3.0),
        "HCTI", {"price": 60.0}, holding,
    ) is None


def test_delegation_turns_off_external_only_switches(monkeypatch):
    """수확·방어는 EXTERNAL 전용이다. 위임과 동시에 꺼야 판정이 이중으로 돌지 않는다."""
    db = _make_db()
    user = _make_user(db)
    holding = _add_external(
        db, user, harvest_enabled=True, harvest_armed=True, guard_enabled=True,
    )

    _delegate(db, user, monkeypatch)

    db.refresh(holding)
    assert holding.harvest_enabled is False
    assert holding.harvest_armed is False
    assert holding.guard_enabled is False


def test_switches_are_rejected_while_delegated(monkeypatch):
    """위임 중에는 스위치 계약이 닫힌다."""
    db = _make_db()
    user = _make_user(db)
    _add_external(db, user)
    _delegate(db, user, monkeypatch)

    with pytest.raises(HTTPException) as exc:
        account_router.update_holding_management(
            ticker="HCTI",
            payload=account_router.HoldingManagementRequest(harvest_enabled=True),
            current_user=user, db=db,
        )
    assert exc.value.status_code == 400


def test_bot_owned_cannot_be_delegated(monkeypatch):
    """봇이 산 종목은 관할권을 바꿀 수 없다."""
    db = _make_db()
    user = _make_user(db)
    _add_external(
        db, user, strategy_type=SLOT, management=MANAGEMENT_BOT_OWNED,
    )

    with pytest.raises(HTTPException) as exc:
        _delegate(db, user, monkeypatch)
    assert exc.value.status_code == 400


def test_revoke_returns_jurisdiction_and_clears_risk_anchor(monkeypatch):
    """되돌릴 수 없는 위임은 아무도 누르지 않는다.

    되돌리면 봇은 즉시 손을 떼야 하므로 슬롯 키와 리스크 기준가를 함께 되돌린다.
    기준가를 남기면 다시 위임했을 때 옛 시점가로 손절을 재게 된다.
    """
    db = _make_db()
    user = _make_user(db)
    holding = _add_external(db, user)
    _delegate(db, user, monkeypatch)

    asyncio.run(account_router.change_holding_delegation(
        ticker="HCTI",
        payload=account_router.HoldingDelegationRequest(action="REVOKE"),
        current_user=user, db=db,
    ))

    db.refresh(holding)
    assert holding.management == MANAGEMENT_EXTERNAL
    assert holding.strategy_type == EXTERNAL_STRATEGY_TYPE
    assert holding.risk_basis_price is None
    assert float(holding.avg_price) == 120.0


def test_delegation_rejects_slot_already_holding_the_ticker(monkeypatch):
    """유니크 제약 충돌. 평단가가 섞이지 않도록 합치지 않고 거부한다."""
    db = _make_db()
    user = _make_user(db)
    _add_external(db, user)
    _add_external(
        db, user, strategy_type=SLOT, management=MANAGEMENT_BOT_OWNED, avg_price=80.0,
    )

    with pytest.raises(HTTPException) as exc:
        _delegate(db, user, monkeypatch, strategy_type=EXTERNAL_STRATEGY_TYPE)
    assert exc.value.status_code == 409


def test_delegation_rejects_unselectable_slot(monkeypatch):
    """카탈로그에 없는 슬롯에는 맡길 수 없다."""
    db = _make_db()
    user = _make_user(db)
    _add_external(db, user)

    with pytest.raises(HTTPException) as exc:
        _delegate(db, user, monkeypatch, slot="no_such_strategy")
    assert exc.value.status_code == 400


def test_screening_is_advisory_not_a_gate(monkeypatch):
    """심사는 게이트가 아니라 통보다. 미달이어도 위임은 적용된다."""
    db = _make_db()
    user = _make_user(db)
    holding = _add_external(db, user)

    result = _delegate(db, user, monkeypatch, verdict="BELOW_CUTOFF")

    db.refresh(holding)
    assert holding.management == MANAGEMENT_DELEGATED
    assert result["screening"]["verdict"] == "BELOW_CUTOFF"


# ======================================================================================
# 2. 스케줄러 판정
# ======================================================================================

def test_delegated_position_is_not_liquidated_on_the_spot(monkeypatch):
    """위임 직후 사이클에서 손절이 터지지 않는다.

    avg_price(120)를 앵커로 쓰면 현재가 60은 -50%라 어떤 손절선도 즉시 뚫린다.
    risk_basis_price(60)를 앵커로 쓰면 손익 0%이므로 아무 일도 일어나지 않는다.
    이 테스트가 깨지면 위임 버튼이 곧 매도 버튼이 된 것이다.
    """
    db = _make_db()
    user = _make_user(db)
    holding = _add_external(db, user)
    _delegate(db, user, monkeypatch, price=60.0)

    broker = _Broker()
    # 사이클을 한 번만 돌리면 이 테스트는 아무것도 증명하지 못한다. 노이즈 버퍼가 어떤
    # 앵커를 쓰든 첫 이탈을 대기시키기 때문이다. 버퍼 너머까지 밀어야 앵커가 드러난다.
    _run_cycle(db, user, broker, holding.id, 60.0, monkeypatch)
    _age_exit_breach(db, holding.id)
    _run_cycle(db, user, broker, holding.id, 60.0, monkeypatch)

    assert broker.sell_calls == [], (
        "위임 직후 청산됐다 - 리스크 앵커가 avg_price로 새고 있다"
    )
    # 애초에 이탈로 기록조차 되지 않아야 한다. 리스크 기준가로는 손익 0%다.
    # micro_session이 expunge_all을 돌리므로 refresh 대신 다시 조회한다.
    fresh = db.query(Holding).filter(Holding.id == holding.id).first()
    assert fresh is not None
    assert fresh.exit_breach_started_at is None, (
        "이탈로 기록됐다 - 손절 판정이 사용자의 과거 손실을 리스크로 잡고 있다"
    )


def test_delegated_position_is_judged_by_bot_rules_afterwards(monkeypatch):
    """위임분은 이후 봇의 정상 규칙을 그대로 받는다 - 격리가 아니다.

    위임 시점가 60에서 30까지 반토막 나면 리스크 기준 -50%라 손절이 걸려야 한다.
    노이즈 버퍼가 있으므로 첫 사이클은 대기하고, 시간을 흘려보낸 뒤 두 번째에 판다.
    """
    db = _make_db()
    user = _make_user(db)
    holding = _add_external(db, user)
    _delegate(db, user, monkeypatch, price=60.0)

    broker = _Broker()
    _run_cycle(db, user, broker, holding.id, 30.0, monkeypatch)
    assert broker.sell_calls == [], "노이즈 버퍼 없이 첫 관측에 팔았다"

    _age_exit_breach(db, holding.id)

    _run_cycle(db, user, broker, holding.id, 30.0, monkeypatch)
    assert broker.sell_calls == [("HCTI", 100)], (
        "위임분이 봇 규칙으로 청산되지 않았다 - 관할권 이전이 판정부에 반영되지 않았다"
    )


def test_delegated_position_counts_toward_slot_capital(monkeypatch):
    """위임분은 슬롯 자본에서 제외되지 않는다.

    제외하면 봇이 같은 슬롯에 자본이 남았다고 착각해 과다 배분한다.
    슬롯 자본 계산은 EXTERNAL만 제외하므로, 관할권이 DELEGATED가 된 시점에 산입된다.
    """
    db = _make_db()
    user = _make_user(db)
    holding = _add_external(db, user)
    _delegate(db, user, monkeypatch)
    db.refresh(holding)

    assert holding.management != MANAGEMENT_EXTERNAL
    assert holding.strategy_type == SLOT
