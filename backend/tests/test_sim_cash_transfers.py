"""SIMULATED 입출금 원장(sim_cash_transfers) 회귀 테스트.

고정하는 계약:
  1. 투입 자본 = 초기자금 + 입출금 합계. 현금·손익·수익률은 투입 자본 기준이다.
     입금이 수익으로 잡히면 안 된다(1천만원 입금 = +100% 오표시).
  2. 사용자 격리. 한 사용자의 입금은 다른 사용자 잔고에 영향이 없다.
  3. 입금이 없는 사용자는 종전 계산과 완전히 같다.
  4. 원장 기록은 SIMULATED 사용자에게만 허용한다(실계좌는 증권사가 잔고를 계산).
  5. 시뮬 잔고 초기화는 원장도 비운다.
"""
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.brokers.simulated_broker as simulated_broker_module
import app.trades.router_account as account_router
from app.brokers.simulated_broker import LocalSimulatedBroker
from app.core.config import settings
from app.core.database import Base
from app.core.models import (
    EXTERNAL_STRATEGY_TYPE,
    MANAGEMENT_EXTERNAL,
    Holding,
    SimCashTransfer,
    TradeLog,
    User,
    UserSettings,
)
from app.trades.sim_cash import SimCashTransferError, record_sim_cash_transfer

FX = 1_350.0  # SIMULATED_INITIAL_FX_RATE와 같게 두어 평가금 환산 차이를 없앤다
INITIAL = int(settings.SIMULATED_INITIAL_CASH_KRW)


@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'sim_cash.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(simulated_broker_module, "SessionLocal", factory)
    monkeypatch.setattr(simulated_broker_module.settings, "SIMULATED_INITIAL_FX_RATE", FX)
    db = factory()

    def make_user(name, trade_mode="SIMULATED"):
        user = User(username=name, hashed_password="hash")
        db.add(user)
        db.flush()
        db.add(UserSettings(user_id=user.id, trade_mode=trade_mode, strategy_type="regime_switching"))
        db.commit()
        db.refresh(user)
        return user

    def balance(user):
        return LocalSimulatedBroker(db_settings=SimpleNamespace(user_id=user.id)).get_account_balance(exchange_rate=FX)

    yield SimpleNamespace(db=db, make_user=make_user, balance=balance)
    db.close()
    engine.dispose()


def test_deposit_raises_capital_without_counting_as_profit(env):
    user = env.make_user("depositor")
    record_sim_cash_transfer(env.db, user.id, 10_000_000, "HCTI 입고 자금")

    b = env.balance(user)
    assert b["total_asset"] == INITIAL + 10_000_000
    assert b["cash_balance"] == INITIAL + 10_000_000
    assert b["profit_loss"] == 0
    assert b["profit_rate"] == 0.0


def test_deposit_is_isolated_per_user_and_no_deposit_user_is_unchanged(env):
    rich = env.make_user("rich")
    plain = env.make_user("plain")
    before = env.balance(plain)

    record_sim_cash_transfer(env.db, rich.id, 10_000_000)

    assert env.balance(plain) == before
    assert env.balance(plain)["total_asset"] == INITIAL
    assert env.balance(rich)["total_asset"] == INITIAL + 10_000_000


def test_profit_rate_uses_invested_capital(env):
    """투입 2천만원에서 +100만원이면 +5%다(초기자금 기준 +10%가 아니다)."""
    user = env.make_user("gainer")
    record_sim_cash_transfer(env.db, user.id, 10_000_000)
    # $1,000 매수 후 $1,740.74로 평가 -> +$740.74 = +1,000,000원
    env.db.add(Holding(
        user_id=user.id, ticker="AAA", strategy_type=EXTERNAL_STRATEGY_TYPE, management=MANAGEMENT_EXTERNAL,
        avg_price=10.0, quantity=100, highest_price=17.407407, last_price=17.407407,
    ))
    env.db.commit()

    b = env.balance(user)
    assert b["profit_loss"] == pytest.approx(1_000_000, abs=2)
    assert b["profit_rate"] == pytest.approx(5.0, abs=0.01)


def test_hcti_restore_scenario_keeps_cash_positive(env):
    """2026-09-24 admin 복원 시나리오: 입금 없이 복원하면 현금이 음수(0으로 절단)였다."""
    user = env.make_user("admin_like")
    env.db.add(TradeLog(user_id=user.id, ticker="OLD", trade_type="SELL", price=1.0, quantity=1,
                        realized_pnl=-274.42, strategy_type="regime_switching"))
    env.db.add(Holding(user_id=user.id, ticker="HCTI", strategy_type=EXTERNAL_STRATEGY_TYPE,
                       management=MANAGEMENT_EXTERNAL, avg_price=1.4852, quantity=4762,
                       highest_price=1.60, last_price=1.4852))
    env.db.add(Holding(user_id=user.id, ticker="BOT", strategy_type="regime_switching",
                       avg_price=794.35, quantity=1, highest_price=794.35, last_price=794.35))
    env.db.commit()
    assert env.balance(user)["cash_balance"] == 0  # 음수 현금이 0으로 잘린 상태

    record_sim_cash_transfer(env.db, user.id, 10_000_000, "HCTI 입고 자금")
    b = env.balance(user)
    invested_usd = (INITIAL + 10_000_000) / FX
    expected_cash = (invested_usd - 274.42 - 4762 * 1.4852 - 794.35) * FX
    assert b["cash_balance"] == pytest.approx(expected_cash, abs=2)
    assert b["cash_balance"] > 0


def test_withdrawal_reduces_capital(env):
    user = env.make_user("withdrawer")
    record_sim_cash_transfer(env.db, user.id, 10_000_000)
    record_sim_cash_transfer(env.db, user.id, -3_000_000, "출금")
    b = env.balance(user)
    assert b["total_asset"] == INITIAL + 7_000_000
    assert b["profit_rate"] == 0.0


def test_transfer_rules(env):
    sim = env.make_user("sim")
    real = env.make_user("real", trade_mode="REAL")
    with pytest.raises(SimCashTransferError):
        record_sim_cash_transfer(env.db, sim.id, 0)
    with pytest.raises(SimCashTransferError):
        record_sim_cash_transfer(env.db, real.id, 1_000_000)
    with pytest.raises(SimCashTransferError):
        record_sim_cash_transfer(env.db, 999_999, 1_000_000)
    assert env.db.query(SimCashTransfer).count() == 0


def test_reset_balance_clears_only_own_transfers(env, monkeypatch):
    me = env.make_user("me")
    other = env.make_user("other")
    record_sim_cash_transfer(env.db, me.id, 10_000_000)
    record_sim_cash_transfer(env.db, other.id, 5_000_000)
    monkeypatch.setattr(account_router, "record_equity_snapshot", lambda *a, **k: True)

    account_router.reset_balance(current_user=me, db=env.db)

    assert env.db.query(SimCashTransfer).filter_by(user_id=me.id).count() == 0
    assert env.db.query(SimCashTransfer).filter_by(user_id=other.id).count() == 1
    assert env.balance(me)["total_asset"] == INITIAL
    assert env.balance(other)["total_asset"] == INITIAL + 5_000_000


def test_deleting_user_cascades_transfers(env):
    user = env.make_user("leaver")
    record_sim_cash_transfer(env.db, user.id, 1_000_000)
    env.db.delete(user)
    env.db.commit()
    assert env.db.query(SimCashTransfer).count() == 0
