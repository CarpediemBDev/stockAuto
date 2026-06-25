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

    def fake_fetch_bulk_ohlcv_sync(*args, **kwargs):
        return simulated_broker_module.pd.DataFrame({"Close": [120.0]})

    monkeypatch.setattr(
        simulated_broker_module,
        "fetch_bulk_ohlcv_sync",
        fake_fetch_bulk_ohlcv_sync,
    )

    db = session_factory()
    try:
        idle_user = User(username="idle", hashed_password="hash")
        active_user = User(username="active", hashed_password="hash")
        db.add_all([idle_user, active_user])
        db.commit()
        db.refresh(idle_user)
        db.refresh(active_user)

        db.add(
            Holding(
                user_id=active_user.id,
                ticker="AAPL",
                ticker_name="Apple",
                avg_price=100.0,
                quantity=10,
                highest_price=120.0,
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
