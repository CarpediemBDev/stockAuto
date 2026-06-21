from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.bot.order_reconciler as reconciler
from app.core.database import Base
from app.core.models import BrokerOrder, Holding, TradeLog, User, UserSettings, BrokerCredential


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


def create_user_settings(session_factory, *, is_running=True):
    db = session_factory()
    user = User(username="trader", hashed_password="hashed")
    db.add(user)
    db.flush()
    cred = BrokerCredential(user_id=user.id, broker_name='KIS', app_key='x', app_secret='x', account_no='x', verification_status='verified', verified_trade_mode='MOCK')
    db.add(cred)
    db_settings = UserSettings(
        user_id=user.id,
        trade_mode="MOCK",
        is_running=is_running,
    )
    db.add(db_settings)
    db.commit()
    db.refresh(db_settings)
    return db, db_settings


def test_partial_buy_is_applied_idempotently_and_resumes_after_final_fill(
    session_factory,
    monkeypatch,
):
    db, db_settings = create_user_settings(session_factory)
    application = reconciler.record_submitted_order(
        db,
        db_settings,
        side="BUY",
        ticker="AAPL",
        prefixed_ticker="AAPL",
        strategy_type="episodic_pivot",
        ticker_name="Apple",
        requested_qty=5,
        submitted_price=100.0,
        order_result={
            "order_submitted": True,
            "status": "PARTIAL",
            "order_no": "BUY-100",
            "filled_qty": 2,
            "filled_price": 100.0,
        },
        buy_stage=1,
        regime_mode="BULLISH",
        signal_score=75,
    )

    assert application.applied_qty == 2
    assert application.is_unresolved is True
    assert db_settings.is_running is False
    holding = db.query(Holding).filter(Holding.user_id == db_settings.user_id).one()
    assert holding.ticker == "AAPL"
    assert holding.strategy_type == "episodic_pivot"
    assert holding.quantity == 2
    assert holding.avg_price == 100.0

    order = db.query(BrokerOrder).one()
    duplicate = reconciler.apply_broker_report(
        db,
        order,
        {"status": "PARTIAL", "filled_qty": 2, "filled_price": 100.0},
    )
    db.commit()
    assert duplicate.applied_qty == 0
    assert db.query(Holding).one().quantity == 2
    db.close()

    broker = SimpleNamespace(
        check_order_status=lambda order_no, order_date=None: {
            "status": "FILLED",
            "filled_qty": 5,
            "filled_price": 100.6,
            "ordered_qty": 5,
        }
    )
    messages = []
    monkeypatch.setattr(reconciler, "get_broker_client", lambda _settings: broker)
    monkeypatch.setattr(reconciler, "send_message_async", lambda user_id, text: messages.append((user_id, text)))

    assert reconciler.reconcile_open_orders_once(session_factory) == 1

    check_db = session_factory()
    final_order = check_db.query(BrokerOrder).one()
    final_holding = check_db.query(Holding).one()
    final_settings = check_db.query(UserSettings).one()
    assert final_order.status == "FILLED"
    assert final_order.applied_filled_qty == 5
    assert final_holding.ticker == "AAPL"
    assert final_holding.strategy_type == "episodic_pivot"
    assert final_holding.quantity == 5
    assert final_holding.avg_price == pytest.approx(100.6)
    assert final_settings.is_running is True
    assert messages
    check_db.close()


def test_partial_sell_uses_only_fill_delta_and_manual_stop_disables_auto_resume(
    session_factory,
    monkeypatch,
):
    db, db_settings = create_user_settings(session_factory)
    db.add(Holding(
        user_id=db_settings.user_id,
        ticker="AAPL",
        strategy_type="episodic_pivot",
        ticker_name="Apple",
        avg_price=100.0,
        quantity=10,
        highest_price=112.0,
        regime_mode="BULLISH",
        buy_stage=1,
    ))
    db.commit()

    application = reconciler.record_submitted_order(
        db,
        db_settings,
        side="SELL",
        ticker="AAPL",
        prefixed_ticker="AAPL",
        strategy_type="episodic_pivot",
        ticker_name="Apple",
        requested_qty=10,
        submitted_price=110.0,
        order_result={
            "order_submitted": True,
            "status": "PARTIAL",
            "order_no": "SELL-100",
            "filled_qty": 4,
            "filled_price": 110.0,
        },
        regime_mode="BULLISH",
        signal_score=20,
        sell_reason="test",
    )
    assert application.applied_qty == 4
    assert application.remaining_qty == 6
    assert db.query(TradeLog).count() == 1
    trade_log = db.query(TradeLog).one()
    assert trade_log.ticker == "AAPL"
    assert trade_log.strategy_type == "episodic_pivot"

    order = db.query(BrokerOrder).one()
    transient_error = reconciler.apply_broker_report(
        db,
        order,
        {"status": "ERROR", "message": "temporary timeout"},
    )
    db.commit()
    assert transient_error.applied_qty == 0
    assert order.applied_filled_qty == 4
    assert db.query(Holding).one().quantity == 6

    reconciler.disable_auto_resume_for_user(db, db_settings.user_id)
    db.commit()
    db.close()

    broker = SimpleNamespace(
        check_order_status=lambda order_no, order_date=None: {
            "status": "FILLED",
            "filled_qty": 10,
            "filled_price": 111.0,
            "ordered_qty": 10,
        }
    )
    monkeypatch.setattr(reconciler, "get_broker_client", lambda _settings: broker)
    monkeypatch.setattr(reconciler, "send_message_async", lambda *_args, **_kwargs: None)

    assert reconciler.reconcile_open_orders_once(session_factory) == 1

    check_db = session_factory()
    final_order = check_db.query(BrokerOrder).one()
    sell_logs = check_db.query(TradeLog).order_by(TradeLog.id).all()
    final_settings = check_db.query(UserSettings).one()
    assert final_order.status == "FILLED"
    assert final_order.applied_filled_qty == 10
    assert check_db.query(Holding).count() == 0
    assert [log.quantity for log in sell_logs] == [4, 6]
    assert final_settings.is_running is False
    check_db.close()


def test_unresolved_order_guard_detects_pending_order(session_factory):
    db, db_settings = create_user_settings(session_factory)
    reconciler.record_submitted_order(
        db,
        db_settings,
        side="BUY",
        ticker="MSFT",
        prefixed_ticker="MSFT",
        strategy_type="regime_switching",
        ticker_name="Microsoft",
        requested_qty=1,
        submitted_price=400.0,
        order_result={
            "order_submitted": True,
            "status": "PENDING",
            "order_no": "BUY-200",
            "filled_qty": 0,
            "filled_price": 0.0,
        },
    )

    assert reconciler.has_unresolved_orders(db, db_settings.user_id) is True
    assert db_settings.is_running is False
    db.close()


def test_multiple_order_intents_inherit_auto_resume_until_all_are_terminal(session_factory):
    db, db_settings = create_user_settings(session_factory)
    orders = []

    for ticker in ("AAPL", "MSFT"):
        order = reconciler.create_order_intent(
            db,
            db_settings,
            side="BUY",
            ticker=ticker,
            prefixed_ticker=ticker,
            ticker_name=ticker,
            requested_qty=1,
            submitted_price=100.0,
            exchange_code="NASD",
            order_division="00",
        )
        reconciler.begin_order_submission(db, order, db_settings)
        orders.append(order)

    assert [order.resume_after_resolution for order in orders] == [True, True]

    for index, order in enumerate(orders, start=1):
        reconciler.finalize_order_submission(
            db,
            order,
            db_settings,
            {
                "success": True,
                "order_submitted": True,
                "fill_confirmed": True,
                "status": "FILLED",
                "order_no": f"BUY-{index}",
                "filled_qty": 1,
                "filled_price": 100.0,
            },
        )

    db.refresh(db_settings)
    assert [order.status for order in orders] == ["FILLED", "FILLED"]
    assert db_settings.is_running is True
    db.close()
