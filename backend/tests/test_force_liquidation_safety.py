import asyncio
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.bot.scheduler as scheduler
import app.trades.router_account as account_router
from app.core.database import Base
from app.core.models import BrokerOrder, Holding, User, UserSettings, BrokerCredential


def test_kis_force_liquidation_keeps_holdings_and_bot_paused_when_ack_is_unknown(
    monkeypatch,
):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(autocommit=False, autoflush=False, bind=engine)()

    user = User(username="liquidator", hashed_password="hashed")
    db.add(user)
    db.flush()
    cred = BrokerCredential(user_id=user.id, broker_name='KIS', app_key='x', app_secret='x', account_no='x', verification_status='verified', verified_trade_mode='REAL')
    db.add(cred)
    db.add(UserSettings(
        user_id=user.id,
        trade_mode="MOCK",
        is_running=True,
        is_real_enabled=False,
    ))
    db.add(Holding(
        user_id=user.id,
        ticker="slot_AAPL",
        ticker_name="Apple",
        avg_price=100.0,
        quantity=3,
        highest_price=110.0,
        regime_mode="BULLISH",
        buy_stage=1,
    ))
    db.commit()
    db.refresh(user)

    class UnknownAckBroker:
        def get_order_metadata(self, ticker, session):
            return {"exchange_code": "NASD", "order_division": "00"}

        def sell_order(self, **kwargs):
            raise TimeoutError("broker response timeout")

    async def fail_price_lookup(*_args, **_kwargs):
        raise RuntimeError("market data unavailable")

    monkeypatch.setattr(
        account_router,
        "get_broker_client",
        lambda _settings: UnknownAckBroker(),
    )
    monkeypatch.setattr(account_router, "fetch_ohlcv", fail_price_lookup)
    monkeypatch.setattr(scheduler, "get_market_session", lambda: "REGULAR_MARKET")

    response = asyncio.run(account_router.force_liquidate(current_user=user, db=db))

    order = db.query(BrokerOrder).one()
    settings = db.query(UserSettings).filter_by(user_id=user.id).one()
    holding = db.query(Holding).filter_by(user_id=user.id).one()

    assert response["code"] == "SUCCESS"
    assert order.status == "ACK_UNKNOWN"
    assert order.source == "MANUAL_LIQUIDATION"
    assert order.resume_after_resolution is False
    assert settings.is_running is False
    assert holding.quantity == 3

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
