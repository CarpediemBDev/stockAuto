from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.bot.simulated_broker as simulated_broker_module
from app.bot.simulated_broker import LocalSimulatedBroker
from app.core.config import settings
from app.core.database import Base
from app.core.models import User


def test_simulated_balance_uses_fixed_initial_fx_rate(tmp_path, monkeypatch):
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

    expected_total = int(
        settings.SIMULATED_INITIAL_CASH_KRW
        / settings.SIMULATED_INITIAL_FX_RATE
        * current_fx_rate
    )
    assert balance["total_asset"] == expected_total
    assert balance["cash_balance"] == expected_total
    assert balance["stock_balance"] == 0
    assert balance["profit_rate"] == 3.7

    engine.dispose()
