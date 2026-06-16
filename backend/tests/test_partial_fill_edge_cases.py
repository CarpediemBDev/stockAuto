import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.bot.order_reconciler as reconciler
from app.bot.simulated_broker import LocalSimulatedBroker
from app.core.database import Base
from app.core.models import BrokerOrder, Holding, User, UserSettings


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def create_user_settings(session_factory):
    db = session_factory()
    user = User(username="partial-fill-user", hashed_password="hashed")
    db.add(user)
    db.flush()
    db_settings = UserSettings(
        user_id=user.id,
        trade_mode="SIMULATED",
        is_running=True,
    )
    db.add(db_settings)
    db.commit()
    db.refresh(db_settings)
    return db, db_settings


def test_partial_buy_balance_uses_only_applied_fill_delta(
    session_factory,
    monkeypatch,
):
    db, db_settings = create_user_settings(session_factory)

    monkeypatch.setattr(
        "app.bot.simulated_broker.settings.SIMULATED_INITIAL_CASH_KRW",
        14_000_000.0,
    )
    monkeypatch.setattr(
        "app.bot.simulated_broker.settings.SIMULATED_INITIAL_FX_RATE",
        1_400.0,
    )
    monkeypatch.setattr(
        "app.bot.scheduler.latest_scanned_signals",
        [{"ticker": "AAPL", "price": "100.0"}],
    )
    monkeypatch.setattr("app.bot.scheduler.latest_watchlist_signals", {})
    monkeypatch.setattr(
        "app.bot.simulated_broker.SessionLocal",
        session_factory,
    )

    application = reconciler.record_submitted_order(
        db,
        db_settings,
        side="BUY",
        ticker="AAPL",
        prefixed_ticker="AAPL",
        strategy_type="episodic_pivot",
        ticker_name="Apple",
        requested_qty=100,
        submitted_price=100.0,
        order_result={
            "order_submitted": True,
            "status": "PARTIAL",
            "order_no": "SIM-PARTIAL-100",
            "filled_qty": 30,
            "filled_price": 100.0,
        },
        buy_stage=1,
        regime_mode="BULLISH",
        signal_score=80,
    )

    assert application.applied_qty == 30
    assert application.is_unresolved is True
    assert db_settings.is_running is False

    order = db.query(BrokerOrder).one()
    holding = db.query(Holding).one()
    assert order.requested_qty == 100
    assert order.applied_filled_qty == 30
    assert order.broker_filled_qty == 30
    assert holding.quantity == 30
    assert holding.avg_price == 100.0

    broker = LocalSimulatedBroker(db_settings=db_settings)
    balance = broker.get_account_balance(exchange_rate=1_400.0)
    assert balance["cash_balance"] == 9_800_000
    assert balance["stock_balance"] == 4_200_000

    duplicate = reconciler.apply_broker_report(
        db,
        order,
        {"status": "PARTIAL", "filled_qty": 30, "filled_price": 100.0},
    )
    db.commit()

    assert duplicate.applied_qty == 0
    assert db.query(Holding).one().quantity == 30
    assert order.applied_filled_qty == 30

    balance_after_duplicate = broker.get_account_balance(exchange_rate=1_400.0)
    assert balance_after_duplicate["cash_balance"] == 9_800_000
    assert balance_after_duplicate["stock_balance"] == 4_200_000

    db.close()
