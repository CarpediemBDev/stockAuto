from datetime import UTC, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.bot.order_discovery as discovery
from app.bot.order_reconciler import begin_order_submission, create_order_intent
from app.core.database import Base
from app.core.models import BrokerOrder, Holding, User, UserSettings, BrokerCredential, utc_now_aware


ET = ZoneInfo("America/New_York")


def broker_order_date_time(order):
    timestamp = order.submission_started_at.replace(tzinfo=UTC).astimezone(ET)
    return timestamp.strftime("%Y%m%d"), timestamp.strftime("%H%M%S")


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


def create_settings(session_factory):
    db = session_factory()
    user = User(username="discovery-user", hashed_password="hashed")
    db.add(user)
    db.flush()
    cred = BrokerCredential(user_id=user.id, broker_name='KIS', app_key='x', app_secret='x', account_no='x', verification_status='verified', verified_trade_mode='REAL')
    db.add(cred)
    settings = UserSettings(
        user_id=user.id,
        trade_mode="MOCK",
        is_running=True,
    )
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return db, settings


def create_submitting_buy(db, settings):
    order = create_order_intent(
        db,
        settings,
        side="BUY",
        ticker="AAPL",
        prefixed_ticker="AAPL",
        strategy_type="episodic_pivot",
        ticker_name="Apple",
        requested_qty=3,
        submitted_price=200.0,
        exchange_code="NASD",
        order_division="00",
        buy_stage=1,
        regime_mode="BULLISH",
        signal_score=80,
    )
    begin_order_submission(db, order, settings)
    return order


def test_submitting_intent_is_recovered_without_resubmitting_order(
    session_factory,
    monkeypatch,
):
    db, settings = create_settings(session_factory)
    order = create_submitting_buy(db, settings)
    intent_id = order.intent_id
    order_date, order_time = broker_order_date_time(order)
    db.close()

    class HistoryOnlyBroker:
        def __init__(self):
            self.history_calls = []
            self.submit_calls = 0

        def list_order_history(self, start_date, end_date):
            self.history_calls.append((start_date, end_date))
            return [{
                "order_no": "KIS-RECOVERED-1",
                "order_date": order_date,
                "order_time": order_time,
                "side": "BUY",
                "ticker": "AAPL",
                "exchange_code": "NASD",
                "ordered_qty": 3,
                "order_price": 200.0,
                "filled_qty": 3,
                "filled_price": 199.5,
                "status": "FILLED",
            }]

        def buy_order(self, *args, **kwargs):
            self.submit_calls += 1
            raise AssertionError("Recovery must never resubmit an order.")

    broker = HistoryOnlyBroker()
    monkeypatch.setattr(discovery, "get_broker_client", lambda _settings: broker)
    monkeypatch.setattr(discovery, "send_message_async", lambda *_args, **_kwargs: None)

    assert discovery.discover_orphan_orders_once(session_factory) == 1

    check_db = session_factory()
    recovered = check_db.query(BrokerOrder).filter(BrokerOrder.intent_id == intent_id).one()
    holding = check_db.query(Holding).one()
    recovered_settings = check_db.query(UserSettings).one()
    assert recovered.broker_order_no == "KIS-RECOVERED-1"
    assert recovered.status == "FILLED"
    assert recovered.applied_filled_qty == 3
    assert holding.ticker == "AAPL"
    assert holding.strategy_type == "episodic_pivot"
    assert holding.quantity == 3
    assert holding.avg_price == 199.5
    assert recovered_settings.is_running is True
    assert broker.history_calls == [(order_date, order_date)]
    assert broker.submit_calls == 0
    check_db.close()


def test_multiple_matching_orders_are_not_linked(session_factory, monkeypatch):
    db, settings = create_settings(session_factory)
    order = create_submitting_buy(db, settings)
    intent_id = order.intent_id
    order_date, order_time = broker_order_date_time(order)
    db.close()

    candidates = [
        {
            "order_no": f"KIS-DUPLICATE-{index}",
            "order_date": order_date,
            "order_time": order_time,
            "side": "BUY",
            "ticker": "AAPL",
            "exchange_code": "NASD",
            "ordered_qty": 3,
            "order_price": 200.0,
            "filled_qty": 0,
            "filled_price": 0.0,
            "status": "UNFILLED",
        }
        for index in (1, 2)
    ]
    broker = type(
        "Broker",
        (),
        {"list_order_history": lambda self, start, end: candidates},
    )()
    monkeypatch.setattr(discovery, "get_broker_client", lambda _settings: broker)
    monkeypatch.setattr(discovery, "send_message_async", lambda *_args, **_kwargs: None)

    assert discovery.discover_orphan_orders_once(session_factory) == 0

    check_db = session_factory()
    unresolved = check_db.query(BrokerOrder).filter(BrokerOrder.intent_id == intent_id).one()
    assert unresolved.status == "AMBIGUOUS"
    assert unresolved.broker_order_no is None
    assert check_db.query(UserSettings).one().is_running is True
    assert order_date == unresolved.broker_order_date
    check_db.close()


def test_stale_intent_created_before_submission_is_aborted(session_factory, monkeypatch):
    db, settings = create_settings(session_factory)
    order = create_order_intent(
        db,
        settings,
        side="BUY",
        ticker="MSFT",
        prefixed_ticker="MSFT",
        strategy_type="regime_switching",
        ticker_name="Microsoft",
        requested_qty=1,
        submitted_price=400.0,
        exchange_code="NASD",
        order_division="00",
    )
    order.submitted_at = utc_now_aware() - timedelta(minutes=2)
    db.commit()
    db.close()
    monkeypatch.setattr(discovery, "send_message_async", lambda *_args, **_kwargs: None)

    assert discovery.discover_orphan_orders_once(session_factory) == 0

    check_db = session_factory()
    aborted = check_db.query(BrokerOrder).one()
    assert aborted.status == "ABORTED"
    assert aborted.submission_attempts == 0
    assert check_db.query(UserSettings).one().is_running is True
    check_db.close()
