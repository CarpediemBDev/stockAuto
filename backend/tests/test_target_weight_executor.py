"""목표비중형 자율 슬롯 라이브 집행부(canary_allocation) 통합 테스트.

고정하는 계약
  1. 이번 달 첫 정규장 사이클에 한 번 판단해 기록하고, 같은 달에는 다시 판단·주문하지 않는다(멱등).
  2. 리밸런싱은 매도 먼저, 매수 나중. 수량은 plan_target_weight_orders(백테스트와 동일).
  3. 밴드 안 변화는 HELD(매매 없음). 데이터 결측은 기록하지 않고 다음 사이클 재시도.
  4. 정규장 밖·SIMULATED 외 모드에서는 아무것도 하지 않는다.
  5. 매도 미체결이면 EXECUTING으로 남고 매수하지 않는다 → 다음 사이클에 남은 차이만 집행.
  6. 사용자별 상태·보유는 섞이지 않는다.
  7. 기존 IN/OUT 자율 경로는 목표비중 전략을 건드리지 않는다.
"""
import asyncio
import json
from datetime import datetime
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.bot.scheduler as scheduler
import app.bot.target_weight_executor as twe
from app.bot.market_session import ET
from app.core.database import Base
from app.core.models import AutonomousSlotState, Holding, TradeLog, User, UserSettings
from app.strategies import canary_allocation as ca
from app.strategies.canary_allocation import CanaryAllocation

SLOT = "canary_allocation"
TODAY = datetime.now(tz=ET).date()
CAL = pd.bdate_range(end=pd.Timestamp(TODAY) - pd.Timedelta(days=1), periods=420)
DECISION = ca.latest_decision_date(CAL, TODAY)
DECISION_MONTH = twe.previous_decision_month(TODAY)


def _trend(slope):
    return pd.Series(100.0 * np.exp(np.arange(len(CAL)) * slope), index=CAL)


def _closes(warn: tuple = ()):
    """warn에 든 가격 신호 티커는 하락 추세(경고)로 만든다."""
    c = {t: _trend(0.001) for t in ca.DATA_TICKERS}
    c["SPY"] = _trend(0.0008)
    c["IEF"] = _trend(0.0002)
    c["BIL"] = _trend(0.0001)
    for t in warn:
        c[t] = _trend(-0.001)
    return c


def _nfci(direction=-1.0):
    weeks = pd.date_range(CAL[0] - pd.Timedelta(days=400), pd.Timestamp(TODAY), freq="W-FRI")
    return pd.Series(direction * np.linspace(0, 1, len(weeks)), index=weeks)


def _make_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _make_user(db, user_id):
    db.add(User(id=user_id, username=f"canary_{user_id}", hashed_password="h"))
    db.flush()
    db.add(UserSettings(user_id=user_id, strategy_type=SLOT, trade_mode="SIMULATED", is_running=True))
    db.commit()


class _Broker:
    def __init__(self, fill_sells=True):
        self.calls = []
        self.fill_sells = fill_sells

    def buy_order(self, ticker, quantity, **kw):
        self.calls.append(("BUY", ticker, quantity))
        return {"success": True, "order_no": f"B{len(self.calls)}", "filled_qty": quantity,
                "filled_price": kw["price"] / 1.001, "status": "FILLED"}

    def sell_order(self, ticker, quantity, **kw):
        self.calls.append(("SELL", ticker, quantity))
        if not self.fill_sells:
            return {"success": False, "message": "rejected"}
        return {"success": True, "order_no": f"S{len(self.calls)}", "filled_qty": quantity,
                "filled_price": kw["price"] / 0.999, "status": "FILLED"}


PRICES = {"QQQ": 500.0, "IEF": 95.0, "BIL": 91.5}


@pytest.fixture
def env(monkeypatch):
    db = _make_db()
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    state = {"closes": _closes(), "nfci": _nfci(-1), "loads": 0}

    async def _load(_strategy, _today):
        state["loads"] += 1
        return state["closes"], state["nfci"]

    async def _price(t):
        return PRICES.get(t)

    monkeypatch.setattr(twe, "load_signal_inputs", _load)
    monkeypatch.setattr(scheduler, "get_realtime_price", _price)
    monkeypatch.setattr(scheduler, "send_message_async", lambda *a, **k: None)
    scheduler.WARNING_COOLDOWN_CACHE.clear()
    scheduler.MARKET_CLOSED_LOG_CACHE.clear()
    yield db, state
    db.close()


def _cycle(db, user_id, broker, cash=10000.0, session="REGULAR_MARKET", trade_mode="SIMULATED"):
    settings_row = db.query(UserSettings).filter_by(user_id=user_id).one()
    settings_row.trade_mode = trade_mode
    db.commit()
    ctx = scheduler.TradingFlowContext(
        db=db, user_id=user_id, db_settings=settings_row, trade_mode=trade_mode, session=session,
        sentiment="BULLISH", exchange_rate=1350.0, holdings=[], broker=broker,
        ms_manager=SimpleNamespace(strategies={SLOT: CanaryAllocation()}), first_slot_key=SLOT,
        signal_map={}, all_signals=[],
    )
    asyncio.run(twe.process_target_weight_slots(ctx, {SLOT: {"cash_balance": cash, "total_asset": cash, "stock_value": 0.0}}))


def _holdings(db, user_id):
    return {h.ticker: h.quantity for h in db.query(Holding).filter_by(user_id=user_id, strategy_type=SLOT).all()}


def _state(db, user_id):
    return db.query(AutonomousSlotState).filter_by(user_id=user_id, slot_key=SLOT).order_by(AutonomousSlotState.decision_date.desc()).first()


def _seed_previous(db, user_id, target, holdings):
    prev_month_day = (pd.Timestamp(DECISION).to_period("M") - 1).to_timestamp(how="end").strftime("%Y-%m-%d")
    db.add(AutonomousSlotState(user_id=user_id, slot_key=SLOT, decision_date=prev_month_day,
                               target_json=json.dumps(target), signals_json="{}", status=twe.STATUS_DONE))
    for t, q in holdings.items():
        db.add(Holding(user_id=user_id, ticker=t, ticker_name=t, strategy_type=SLOT, avg_price=PRICES[t],
                       quantity=q, highest_price=PRICES[t], buy_stage=3))
    db.commit()


def test_first_entry_buys_target_and_is_idempotent(env):
    db, state = env
    _make_user(db, 1)
    broker = _Broker()
    _cycle(db, 1, broker)
    # 신호 7개 모두 양호 → QQQ 100%: floor(10000×0.995/500)=19주
    assert broker.calls == [("BUY", "QQQ", 19)]
    assert _holdings(db, 1) == {"QQQ": 19}
    st = _state(db, 1)
    assert st.status == twe.STATUS_DONE and st.decision_date == DECISION.strftime("%Y-%m-%d")
    assert json.loads(st.target_json) == {"QQQ": 1.0}
    # 같은 달 재실행: 데이터 재수집도 주문도 없음
    _cycle(db, 1, broker, cash=500.0)
    assert len(broker.calls) == 1 and state["loads"] == 1


def test_signal_change_sells_before_buys(env):
    db, state = env
    _make_user(db, 1)
    _seed_previous(db, 1, {"QQQ": 1.0}, {"QQQ": 19})
    state["closes"] = _closes(warn=("VWO", "AGG", "XHB"))  # 4/7 양호
    broker = _Broker()
    _cycle(db, 1, broker, cash=500.0)
    # 총자산 500 + 19×500 = 10000 → QQQ floor(10000×4/7×0.995/500)=11, IEF floor(10000×3/7×0.995/95)=44
    assert broker.calls == [("SELL", "QQQ", 8), ("BUY", "IEF", 44)]
    assert _holdings(db, 1) == {"QQQ": 11, "IEF": 44}
    assert _state(db, 1).status == twe.STATUS_DONE
    sells = db.query(TradeLog).filter_by(user_id=1, trade_type="SELL").all()
    assert len(sells) == 1 and sells[0].strategy_type == SLOT and sells[0].regime_mode == twe.REGIME_LABEL


def test_change_inside_band_is_held_without_orders(env):
    db, _ = env
    _make_user(db, 1)
    _seed_previous(db, 1, {"QQQ": 0.96, "IEF": 0.04}, {"QQQ": 19})  # 새 목표 QQQ 1.0과의 차이 합 0.08 < 0.10
    broker = _Broker()
    _cycle(db, 1, broker)
    assert broker.calls == []
    st = _state(db, 1)
    assert st.status == twe.STATUS_HELD and json.loads(st.target_json) == {"QQQ": 0.96, "IEF": 0.04}


def test_missing_data_records_nothing_and_retries(env):
    db, state = env
    _make_user(db, 1)
    state["nfci"] = None
    broker = _Broker()
    _cycle(db, 1, broker)
    assert broker.calls == [] and _state(db, 1) is None
    state["nfci"] = _nfci(-1)  # 데이터 회복 → 같은 달 다음 사이클에 정상 판단
    _cycle(db, 1, broker)
    assert broker.calls == [("BUY", "QQQ", 19)] and _state(db, 1).status == twe.STATUS_DONE


@pytest.mark.parametrize("session,mode", [("PRE_MARKET", "SIMULATED"), ("AFTER_HOURS", "SIMULATED"), ("REGULAR_MARKET", "MOCK")])
def test_outside_regular_or_non_simulated_does_nothing(env, session, mode):
    db, state = env
    _make_user(db, 1)
    broker = _Broker()
    _cycle(db, 1, broker, session=session, trade_mode=mode)
    assert broker.calls == [] and _state(db, 1) is None and state["loads"] == 0


def test_unfilled_sell_blocks_buys_then_resumes(env):
    db, state = env
    _make_user(db, 1)
    _seed_previous(db, 1, {"QQQ": 1.0}, {"QQQ": 19})
    state["closes"] = _closes(warn=("VWO", "AGG", "XHB"))
    broker = _Broker(fill_sells=False)
    _cycle(db, 1, broker, cash=500.0)
    assert broker.calls == [("SELL", "QQQ", 8)]          # 매수로 넘어가지 않음
    assert _state(db, 1).status == twe.STATUS_EXECUTING
    assert _holdings(db, 1) == {"QQQ": 19}
    broker.fill_sells = True
    _cycle(db, 1, broker, cash=500.0)                     # 남은 차이를 다시 계산해 집행
    assert broker.calls[1:] == [("SELL", "QQQ", 8), ("BUY", "IEF", 44)]
    assert _state(db, 1).status == twe.STATUS_DONE and state["loads"] == 1


def test_users_are_isolated(env):
    db, state = env
    _make_user(db, 1)
    _make_user(db, 2)
    _seed_previous(db, 2, {"QQQ": 3 / 7, "BIL": 4 / 7}, {"QQQ": 8, "BIL": 60})
    b1, b2 = _Broker(), _Broker()
    _cycle(db, 1, b1)
    assert _holdings(db, 2) == {"QQQ": 8, "BIL": 60} and b2.calls == []
    _cycle(db, 2, b2, cash=0.0)
    # 총자산 8×500 + 60×91.5 = 9490 → QQQ 목표 floor(9490×0.995/500)=18 → 추가 10주
    assert b2.calls == [("SELL", "BIL", 60), ("BUY", "QQQ", 10)]
    assert _holdings(db, 1) == {"QQQ": 19}
    assert {r.user_id for r in db.query(AutonomousSlotState).filter_by(decision_date=DECISION.strftime("%Y-%m-%d"))} == {1, 2}


def test_inout_autonomous_path_ignores_target_weight_strategy(env, monkeypatch):
    db, _ = env
    _make_user(db, 1)
    called = []

    async def _no_fetch(*a, **k):
        called.append(a)
        return pd.DataFrame()

    monkeypatch.setattr(scheduler, "fetch_ohlcv", _no_fetch)
    settings_row = db.query(UserSettings).filter_by(user_id=1).one()
    ctx = scheduler.TradingFlowContext(
        db=db, user_id=1, db_settings=settings_row, trade_mode="SIMULATED", session="REGULAR_MARKET",
        sentiment="BULLISH", exchange_rate=1350.0, holdings=[], broker=_Broker(),
        ms_manager=SimpleNamespace(strategies={SLOT: CanaryAllocation()}), first_slot_key=SLOT,
        signal_map={}, all_signals=[],
    )
    asyncio.run(scheduler.process_autonomous_slots(ctx, {SLOT: {"cash_balance": 10000.0}}))
    assert called == []  # asset_ticker 없는 목표비중 전략으로 IN/OUT 판정을 시도하지 않는다
