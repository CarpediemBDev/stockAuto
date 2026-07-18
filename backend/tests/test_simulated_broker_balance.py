from decimal import Decimal, ROUND_HALF_UP
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.brokers.simulated_broker as simulated_broker_module
from app.brokers.simulated_broker import LocalSimulatedBroker
from app.bot.trade_calculations import to_decimal
from app.core.config import settings
from app.core.database import Base
from app.core.models import Holding, TradeLog, User


def test_simulated_balance_keeps_uninvested_cash_fx_neutral(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'simulated_balance.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(simulated_broker_module, "SessionLocal", session_factory)

    db = session_factory()
    try:
        user = User(username="simulator", hashed_password="hash")
        db.add(user)
        db.commit()
        db.refresh(user)
    finally:
        db.close()

    broker = LocalSimulatedBroker(db_settings=SimpleNamespace(user_id=user.id))
    current_fx_rate = 1_400.0
    balance = broker.get_account_balance(exchange_rate=current_fx_rate)

    expected_total = int(settings.SIMULATED_INITIAL_CASH_KRW)
    assert balance["total_asset"] == expected_total
    assert balance["cash_balance"] == expected_total
    assert balance["stock_balance"] == 0
    assert balance["profit_rate"] == 0.0

    engine.dispose()


def test_simulated_balance_reflects_user_open_position_pnl(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'simulated_position.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(simulated_broker_module, "SessionLocal", session_factory)

    db = session_factory()
    try:
        idle_user = User(username="idle", hashed_password="hash")
        active_user = User(username="active", hashed_password="hash")
        db.add_all([idle_user, active_user])
        db.commit()
        db.refresh(idle_user)
        db.refresh(active_user)

        # 유저 대면 경로 외부 호출 제거 이후, 평가금은 스케줄러가 영속화한 last_price를 사용한다.
        db.add(
            Holding(
                user_id=active_user.id,
                ticker="AAPL",
                ticker_name="Apple",
                avg_price=100.0,
                quantity=10,
                highest_price=120.0,
                last_price=120.0,
                strategy_type="regime_switching",
            )
        )
        db.commit()
        idle_user_id = idle_user.id
        active_user_id = active_user.id
    finally:
        db.close()

    current_fx_rate = 1_400.0
    idle_balance = LocalSimulatedBroker(
        db_settings=SimpleNamespace(user_id=idle_user_id)
    ).get_account_balance(exchange_rate=current_fx_rate)
    active_balance = LocalSimulatedBroker(
        db_settings=SimpleNamespace(user_id=active_user_id)
    ).get_account_balance(exchange_rate=current_fx_rate)
    active_balance_high_fx = LocalSimulatedBroker(
        db_settings=SimpleNamespace(user_id=active_user_id)
    ).get_account_balance(exchange_rate=1_600.0)

    expected_profit_loss = int(
        (120.0 - 100.0)
        * 10
        * settings.SIMULATED_INITIAL_FX_RATE
    )
    expected_total = int(settings.SIMULATED_INITIAL_CASH_KRW + expected_profit_loss)

    assert idle_balance["profit_rate"] == 0.0
    assert active_balance["total_asset"] == expected_total
    assert active_balance["cash_balance"] == 8_650_000
    assert active_balance["stock_balance"] == 1_620_000
    assert active_balance["profit_loss"] == expected_profit_loss
    assert active_balance["profit_rate"] == 2.7
    assert active_balance_high_fx["total_asset"] == expected_total
    assert active_balance_high_fx["profit_loss"] == expected_profit_loss
    assert active_balance_high_fx["profit_rate"] == active_balance["profit_rate"]

    engine.dispose()


def test_simulated_balance_falls_back_to_avg_price_without_last_price(tmp_path, monkeypatch):
    """last_price가 아직 기록되지 않은 보유종목은 평단가 평가(손익 0)로 폴백해야 한다."""
    engine = create_engine(f"sqlite:///{tmp_path / 'simulated_fallback.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(simulated_broker_module, "SessionLocal", session_factory)

    db = session_factory()
    try:
        user = User(username="fresh", hashed_password="hash")
        db.add(user)
        db.commit()
        db.refresh(user)

        db.add(
            Holding(
                user_id=user.id,
                ticker="MSFT",
                ticker_name="Microsoft",
                avg_price=200.0,
                quantity=5,
                highest_price=210.0,
                strategy_type="regime_switching",
            )
        )
        db.commit()
        user_id = user.id
    finally:
        db.close()

    balance = LocalSimulatedBroker(
        db_settings=SimpleNamespace(user_id=user_id)
    ).get_account_balance(exchange_rate=1_400.0)

    # 평가액 = 매수액 → 미실현 손익 0, 총자산은 초기 자본 그대로
    assert balance["profit_loss"] == 0
    assert balance["profit_rate"] == 0.0
    assert balance["total_asset"] == int(settings.SIMULATED_INITIAL_CASH_KRW)


def test_simulated_realized_pnl_sql_sum_matches_python_sum(tmp_path, monkeypatch):
    """누적 실현손익을 DB SQL SUM으로 집계해도 파이썬 Decimal 합산(구 방식)과 동일해야 한다.

    소수점 scale4·음수 손익을 섞고, 다른 유저 손익·BUY 로그·realized_pnl NULL은
    집계에서 제외되는지까지 강제해 전량 스캔 제거 리팩터의 행동 보존을 방어한다.
    """
    engine = create_engine(f"sqlite:///{tmp_path / 'simulated_realized.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(simulated_broker_module, "SessionLocal", session_factory)

    realized_values = [Decimal("100.1234"), Decimal("50.5000"), Decimal("-30.2500")]

    db = session_factory()
    try:
        seller = User(username="seller", hashed_password="hash")
        other = User(username="other", hashed_password="hash")
        db.add_all([seller, other])
        db.commit()
        db.refresh(seller)
        db.refresh(other)

        for value in realized_values:
            db.add(TradeLog(
                user_id=seller.id, ticker="AAPL", ticker_name="Apple",
                trade_type="SELL", price=100.0, quantity=1,
                realized_pnl=value, strategy_type="regime_switching",
            ))
        # 다른 유저의 매도 손익은 집계에 섞이면 안 됨(유저 격리)
        db.add(TradeLog(
            user_id=other.id, ticker="TSLA", ticker_name="Tesla",
            trade_type="SELL", price=100.0, quantity=1,
            realized_pnl=Decimal("9999.9999"), strategy_type="regime_switching",
        ))
        # BUY 로그와 realized_pnl NULL은 집계에서 제외돼야 함
        db.add(TradeLog(
            user_id=seller.id, ticker="AAPL", ticker_name="Apple",
            trade_type="BUY", price=100.0, quantity=1,
            realized_pnl=None, strategy_type="regime_switching",
        ))
        db.commit()
        seller_id = seller.id
    finally:
        db.close()

    balance = LocalSimulatedBroker(
        db_settings=SimpleNamespace(user_id=seller_id)
    ).get_account_balance(exchange_rate=1_400.0)

    # 기준값: 파이썬 Decimal 합산(구 방식)으로 직접 계산한 profit_loss(KRW)
    expected_realized_usd = sum(realized_values)  # 120.3734
    expected_profit_loss = int(
        (expected_realized_usd * to_decimal(settings.SIMULATED_INITIAL_FX_RATE)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    assert balance["stock_balance"] == 0
    assert balance["profit_loss"] == expected_profit_loss

    engine.dispose()
