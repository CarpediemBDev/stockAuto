"""개별 종목 수동 매도 회귀 테스트.

전량 청산(/force-liquidate)만 있고 종목을 지정해 파는 경로가 없어서, 봇 관할 밖(EXTERNAL)
보유분의 계약인 "봇이 안 건드림 = 사용자가 직접 관리"를 앱 안에서 이행할 수단이 없었다.

여기서 고정하는 계약은 세 가지다.
  1. confirm 없이는 절대 주문이 나가지 않는다 (되돌릴 수 없는 금융 액션의 기본값).
  2. 같은 티커를 여러 슬라이스로 보유하면 대상을 임의로 고르지 않고 거절한다.
  3. EXTERNAL 보유분도 사용자가 직접 지시하면 팔 수 있다 - 봇이 자율로 못 팔 뿐이다.

설계 정본은 docs/plans/holding_management_modes.md, 계약은 docs/API_STANDARD.md 6절.
"""

import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.trades.router_account as account_router
from app.core.database import Base
from app.core.models import (
    EXTERNAL_STRATEGY_TYPE,
    MANAGEMENT_BOT_OWNED,
    MANAGEMENT_EXTERNAL,
    BrokerOrder,
    Holding,
    TradeLog,
    User,
    UserSettings,
)


def _make_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _make_user(db, username="seller"):
    user = User(username=username, hashed_password="hashed")
    db.add(user)
    db.flush()
    db.add(UserSettings(
        user_id=user.id,
        strategy_type="regime_switching",
        trade_mode="SIMULATED",
        is_running=True,
    ))
    db.commit()
    db.refresh(user)
    return user


class _RecordingBroker:
    def __init__(self):
        self.sell_calls = []

    def sell_order(self, ticker, quantity, price=0.0, **kwargs):
        self.sell_calls.append((ticker, quantity, price))
        return {
            "success": True,
            "order_no": "SIM-SELL-1",
            "filled_qty": quantity,
            "filled_price": price,
            "message": "Success",
            "status": "FILLED",
        }

    def get_account_balance(self, *_args, **_kwargs):
        return {"total_asset": 0, "cash_balance": 0}


def _install(monkeypatch, broker, price=2.0):
    monkeypatch.setattr(account_router, "get_broker_client", lambda _s: broker)

    async def fake_price(_holding):
        return price

    monkeypatch.setattr(account_router, "_resolve_market_price", fake_price)


def _add_external(db, user, ticker="HCTI", qty=4762, avg=1.48):
    h = Holding(
        user_id=user.id, ticker=ticker, ticker_name="Healthcare Triangle",
        strategy_type=EXTERNAL_STRATEGY_TYPE, management=MANAGEMENT_EXTERNAL,
        avg_price=avg, quantity=qty, highest_price=avg,
    )
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


def _call(user, db, ticker, **kwargs):
    return asyncio.run(account_router.sell_holding(
        ticker=ticker,
        payload=account_router.SellHoldingRequest(**kwargs),
        current_user=user,
        db=db,
    ))


# --------------------------------------------------------------------------------------
# 1. confirm 게이트
# --------------------------------------------------------------------------------------

def test_preview_does_not_place_any_order(monkeypatch):
    """confirm 없이는 주문이 나가지 않고 예상치만 돌려준다."""
    db = _make_db()
    user = _make_user(db)
    _add_external(db, user)
    broker = _RecordingBroker()
    _install(monkeypatch, broker, price=2.0)

    result = _call(user, db, "HCTI")

    assert result["preview"] is True
    assert broker.sell_calls == []
    assert db.query(TradeLog).count() == 0
    assert db.query(Holding).filter_by(user_id=user.id).one().quantity == 4762
    assert result["sell_quantity"] == 4762
    assert result["estimated_price"] == 2.0
    assert result["management"] == MANAGEMENT_EXTERNAL
    db.close()


def test_confirm_true_executes_and_updates_ledger(monkeypatch):
    """confirm=true면 실제로 팔리고 보유·거래이력이 갱신된다."""
    db = _make_db()
    user = _make_user(db)
    _add_external(db, user, qty=100, avg=1.0)
    broker = _RecordingBroker()
    _install(monkeypatch, broker, price=2.0)

    result = _call(user, db, "HCTI", confirm=True)

    assert result["preview"] is False
    assert result["status"] == "filled"
    assert broker.sell_calls == [("HCTI", 100, 2.0)]
    assert result["sold_quantity"] == 100
    assert result["remaining_quantity"] == 0
    # 전량 매도된 슬라이스는 정리된다.
    assert db.query(Holding).filter_by(user_id=user.id).count() == 0
    log = db.query(TradeLog).one()
    assert log.trade_type == "SELL"
    assert log.quantity == 100
    assert log.regime_mode == "MANUAL_SELL"
    db.close()


def test_partial_quantity_leaves_remainder(monkeypatch):
    """수량을 지정하면 그만큼만 팔리고 잔량이 남는다."""
    db = _make_db()
    user = _make_user(db)
    _add_external(db, user, qty=100, avg=1.0)
    broker = _RecordingBroker()
    _install(monkeypatch, broker, price=2.0)

    result = _call(user, db, "HCTI", quantity=30, confirm=True)

    assert broker.sell_calls == [("HCTI", 30, 2.0)]
    assert result["sold_quantity"] == 30
    assert result["remaining_quantity"] == 70
    assert db.query(Holding).filter_by(user_id=user.id).one().quantity == 70
    db.close()


# --------------------------------------------------------------------------------------
# 2. 입력 검증
# --------------------------------------------------------------------------------------

def test_selling_more_than_held_is_rejected(monkeypatch):
    db = _make_db()
    user = _make_user(db)
    _add_external(db, user, qty=10)
    broker = _RecordingBroker()
    _install(monkeypatch, broker)

    with pytest.raises(HTTPException) as exc:
        _call(user, db, "HCTI", quantity=11, confirm=True)

    assert exc.value.status_code == 400
    assert broker.sell_calls == []
    db.close()


def test_unheld_ticker_is_rejected(monkeypatch):
    db = _make_db()
    user = _make_user(db)
    broker = _RecordingBroker()
    _install(monkeypatch, broker)

    with pytest.raises(HTTPException) as exc:
        _call(user, db, "NOPE", confirm=True)

    assert exc.value.status_code == 404
    assert broker.sell_calls == []
    db.close()


def test_ambiguous_ticker_requires_explicit_slice(monkeypatch):
    """같은 티커를 봇 슬롯과 EXTERNAL로 동시에 보유하면 임의로 고르지 않는다."""
    db = _make_db()
    user = _make_user(db)
    db.add_all([
        Holding(
            user_id=user.id, ticker="AAPL", ticker_name="Apple",
            strategy_type="regime_switching", management=MANAGEMENT_BOT_OWNED,
            avg_price=100.0, quantity=5, highest_price=100.0,
        ),
        Holding(
            user_id=user.id, ticker="AAPL", ticker_name="Apple",
            strategy_type=EXTERNAL_STRATEGY_TYPE, management=MANAGEMENT_EXTERNAL,
            avg_price=80.0, quantity=10, highest_price=80.0,
        ),
    ])
    db.commit()
    broker = _RecordingBroker()
    _install(monkeypatch, broker, price=120.0)

    with pytest.raises(HTTPException) as exc:
        _call(user, db, "AAPL", confirm=True)
    assert exc.value.status_code == 400
    assert "strategy_type" in exc.value.detail
    assert broker.sell_calls == []

    # 슬라이스를 지정하면 그 슬라이스만 팔린다.
    result = _call(user, db, "AAPL", strategy_type=EXTERNAL_STRATEGY_TYPE, confirm=True)
    assert result["sold_quantity"] == 10
    remaining = db.query(Holding).filter_by(user_id=user.id).one()
    assert remaining.strategy_type == "regime_switching"
    assert remaining.quantity == 5
    db.close()


# --------------------------------------------------------------------------------------
# 3. 동시성 가드
# --------------------------------------------------------------------------------------

def test_pending_broker_order_blocks_execution_but_not_preview(monkeypatch):
    """미해결 주문이 있으면 실행은 막되 프리뷰는 계속 볼 수 있어야 한다."""
    db = _make_db()
    user = _make_user(db)
    _add_external(db, user, qty=10)
    db.add(BrokerOrder(
        user_id=user.id, intent_id="intent-x", broker_order_date="20260906",
        trade_mode="SIMULATED", side="SELL", ticker="HCTI", prefixed_ticker="HCTI",
        strategy_type=EXTERNAL_STRATEGY_TYPE, status="PENDING",
        requested_qty=3, submitted_price=1.0,
    ))
    db.commit()
    broker = _RecordingBroker()
    _install(monkeypatch, broker)

    # 프리뷰는 통과한다 - 주문을 내지 않으므로 경합이 없다.
    assert _call(user, db, "HCTI")["preview"] is True

    with pytest.raises(HTTPException) as exc:
        _call(user, db, "HCTI", confirm=True)
    assert exc.value.status_code == 409
    assert broker.sell_calls == []
    db.close()


def test_symbol_lock_contention_blocks_sell(monkeypatch):
    """봇이 같은 종목 주문 중이면 매도를 시작하지 않는다."""
    db = _make_db()
    user = _make_user(db)
    _add_external(db, user, qty=10)
    broker = _RecordingBroker()
    _install(monkeypatch, broker)

    async def busy_symbol_lock(*_args, **_kwargs):
        return None

    monkeypatch.setattr(account_router, "acquire_symbol_order_lock", busy_symbol_lock)

    with pytest.raises(HTTPException) as exc:
        _call(user, db, "HCTI", confirm=True)

    assert exc.value.status_code == 409
    assert broker.sell_calls == []
    db.close()


# --------------------------------------------------------------------------------------
# 4. 관할권과의 관계
# --------------------------------------------------------------------------------------

def test_bot_owned_holding_can_also_be_sold_manually(monkeypatch):
    """관할권은 봇의 자율 매도를 가르는 것이지 사용자의 수동 매도를 막지 않는다."""
    db = _make_db()
    user = _make_user(db)
    db.add(Holding(
        user_id=user.id, ticker="AAPL", ticker_name="Apple",
        strategy_type="regime_switching", management=MANAGEMENT_BOT_OWNED,
        avg_price=100.0, quantity=5, highest_price=100.0,
    ))
    db.commit()
    broker = _RecordingBroker()
    _install(monkeypatch, broker, price=120.0)

    result = _call(user, db, "AAPL", confirm=True)

    assert result["status"] == "filled"
    assert result["management"] == MANAGEMENT_BOT_OWNED
    assert broker.sell_calls == [("AAPL", 5, 120.0)]
    db.close()


# --------------------------------------------------------------------------------------
# 5. 매도 대상 키의 안정성
# --------------------------------------------------------------------------------------

def test_holdings_expose_slices_for_target_selection(monkeypatch):
    """매도 대상을 지정할 키는 (ticker, strategy_type)이고, 그 후보가 응답에 실린다.

    응답의 id는 매도 키로 쓸 수 없다 - KIS 경로는 목록 순번(idx+1000)을 발급해 청산 한 번에
    나머지 행의 id가 전부 밀리고 Toss 경로는 id 자체가 없다. 폴링 사이에 목록이 바뀌면
    순번 id로 보낸 요청이 엉뚱한 종목을 지정한다.
    """
    db = _make_db()
    user = _make_user(db)
    db.add_all([
        Holding(
            user_id=user.id, ticker="AAPL", ticker_name="Apple",
            strategy_type="regime_switching", management=MANAGEMENT_BOT_OWNED,
            avg_price=100.0, quantity=5, highest_price=100.0,
        ),
        Holding(
            user_id=user.id, ticker="AAPL", ticker_name="Apple",
            strategy_type=EXTERNAL_STRATEGY_TYPE, management=MANAGEMENT_EXTERNAL,
            avg_price=80.0, quantity=10, highest_price=80.0,
        ),
    ])
    db.commit()

    class _BrokerWithUnstableIds:
        """KIS 경로를 모사한다 - id가 목록 순번이라 사이클마다 달라질 수 있다."""

        def get_holdings(self, exchange_rate=None):
            return [{
                "id": 1000, "ticker": "AAPL", "ticker_name": "Apple",
                "avg_price": 93.3, "quantity": 15, "highest_price": 100.0,
                "current_price": 120.0, "fx_rate": 1350.0, "provider": "KIS Mock",
            }]

    monkeypatch.setattr(account_router, "get_broker_client", lambda _s: _BrokerWithUnstableIds())

    rows = account_router.get_holdings(current_user=user, db=db)

    assert len(rows) == 1
    slices = rows[0]["slices"]
    keys = {(s["strategy_type"], s["management"], s["quantity"]) for s in slices}
    assert keys == {
        ("regime_switching", MANAGEMENT_BOT_OWNED, 5),
        (EXTERNAL_STRATEGY_TYPE, MANAGEMENT_EXTERNAL, 10),
    }
    # 슬라이스가 둘이므로 클라이언트는 strategy_type을 지정해야 한다는 것을 미리 알 수 있다.
    assert len(slices) > 1
    db.close()
