from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.bot.simulated_broker as simulated_broker_module
from app.bot.simulated_broker import LocalSimulatedBroker
from app.core.config import settings
from app.core.database import Base
from app.core.models import Holding, User


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
