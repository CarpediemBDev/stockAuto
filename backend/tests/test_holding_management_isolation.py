"""봇 관할권(Holding.management) 격리 회귀 테스트.

2026-09-05 admin 계정 HCTI 실측에서, 봇이 사지 않은 보유분이 sync_broker_holdings로
첫 번째 전략 슬롯에 등록된 뒤 다음 사이클에 손절로 즉시 청산됐다. 실증권 API를 붙이면
사용자가 봇 도입 이전에 직접 매수한 종목 전체가 같은 경로를 탄다.

여기서 고정하는 계약은 두 가지다.
  1. 봇 매수 이력이 없는 계좌 보유분은 EXTERNAL로 등록된다 (기본값이 "봇이 안 건드림").
  2. EXTERNAL 보유분은 매도 판정 대상이 아니되, 관측(last_price/highest_price)은 계속된다.

설계 정본은 docs/plans/holding_management_modes.md.
"""

import asyncio
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.bot.scheduler as scheduler
import app.trades.router_account as account_router
from app.bot.multi_strategy_manager import MultiStrategyManager
from app.core.database import Base
from app.core.models import (
    EXTERNAL_STRATEGY_TYPE,
    MANAGEMENT_BOT_OWNED,
    MANAGEMENT_EXTERNAL,
    ActionLog,
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


def _make_user(db, username="holder"):
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


class _Broker:
    def __init__(self, holdings):
        self._holdings = holdings
        self.sell_calls = []

    def get_holdings(self, exchange_rate=None):
        return self._holdings

    def sell_order(self, ticker, quantity, **kwargs):
        self.sell_calls.append((ticker, quantity))
        return {
            "success": True,
            "order_no": "SIM-1",
            "filled_qty": quantity,
            "filled_price": kwargs.get("price", 1.0),
            "message": "Success",
            "status": "FILLED",
        }


def _make_ctx(db, user, broker, holdings, ms_manager=None, signal_map=None):
    settings_row = db.query(UserSettings).filter_by(user_id=user.id).one()
    return scheduler.TradingFlowContext(
        db=db,
        user_id=user.id,
        db_settings=settings_row,
        trade_mode="SIMULATED",
        session="REGULAR_MARKET",
        sentiment="BULLISH",
        exchange_rate=1350.0,
        holdings=holdings,
        broker=broker,
        ms_manager=ms_manager,
        first_slot_key="regime_switching",
        signal_map=signal_map or {},
        all_signals=[],
    )


# --------------------------------------------------------------------------------------
# 1. sync_broker_holdings - 기본값 반전
# --------------------------------------------------------------------------------------

def test_broker_position_without_buy_history_is_registered_as_external(monkeypatch):
    """봇 매수 이력이 없는 계좌 보유분은 첫 슬롯이 아니라 EXTERNAL로 등록된다."""
    db = _make_db()
    user = _make_user(db)
    broker = _Broker([
        {"ticker": "HCTI", "ticker_name": "Healthcare Triangle", "quantity": 4762, "avg_price": 1.48},
    ])
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)

    ctx = _make_ctx(db, user, broker, holdings=[])
    asyncio.run(scheduler.sync_broker_holdings(ctx))

    holding = db.query(Holding).filter_by(user_id=user.id).one()
    assert holding.management == MANAGEMENT_EXTERNAL
    assert holding.strategy_type == EXTERNAL_STRATEGY_TYPE
    # 첫 슬롯에 꽂히면 다음 사이클에 손절 판정 대상이 된다 - 그 경로로 돌아가지 않았음을 고정한다.
    assert holding.strategy_type != ctx.first_slot_key
    db.close()


def test_broker_position_with_buy_history_stays_bot_owned(monkeypatch):
    """봇 매수 이력이 있으면 기존 self-healing 그대로 봇 관할로 복원된다."""
    db = _make_db()
    user = _make_user(db)
    db.add(TradeLog(
        user_id=user.id,
        ticker="AAPL",
        ticker_name="Apple",
        strategy_type="episodic_pivot",
        trade_type="BUY",
        price=100.0,
        quantity=5,
    ))
    db.commit()

    broker = _Broker([
        {"ticker": "AAPL", "ticker_name": "Apple", "quantity": 5, "avg_price": 100.0},
    ])
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)

    ctx = _make_ctx(db, user, broker, holdings=[])
    asyncio.run(scheduler.sync_broker_holdings(ctx))

    holding = db.query(Holding).filter_by(user_id=user.id).one()
    assert holding.management == MANAGEMENT_BOT_OWNED
    assert holding.strategy_type == "episodic_pivot"
    db.close()


# --------------------------------------------------------------------------------------
# 2. sync_broker_holdings - 수량 차분 배분 순서
# --------------------------------------------------------------------------------------

def _seed_two_slices(db, user, ticker="AAPL", bot_qty=5, ext_qty=10):
    bot = Holding(
        user_id=user.id, ticker=ticker, ticker_name="Apple",
        strategy_type="regime_switching", management=MANAGEMENT_BOT_OWNED,
        avg_price=100.0, quantity=bot_qty, highest_price=100.0,
    )
    ext = Holding(
        user_id=user.id, ticker=ticker, ticker_name="Apple",
        strategy_type=EXTERNAL_STRATEGY_TYPE, management=MANAGEMENT_EXTERNAL,
        avg_price=80.0, quantity=ext_qty, highest_price=80.0,
    )
    db.add_all([bot, ext])
    db.commit()
    return bot, ext


def test_quantity_decrease_without_pending_order_consumes_external_first(monkeypatch):
    """사용자가 앱 밖에서 판 물량이 봇 슬라이스를 갉아먹지 않는다."""
    db = _make_db()
    user = _make_user(db)
    _seed_two_slices(db, user)  # bot 5 + external 10 = 15
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)

    broker = _Broker([{"ticker": "AAPL", "ticker_name": "Apple", "quantity": 12, "avg_price": 90.0}])
    ctx = _make_ctx(db, user, broker, holdings=db.query(Holding).all())
    asyncio.run(scheduler.sync_broker_holdings(ctx))

    rows = {h.management: h.quantity for h in db.query(Holding).filter_by(user_id=user.id).all()}
    assert rows[MANAGEMENT_BOT_OWNED] == 5      # 봇 슬라이스는 그대로
    assert rows[MANAGEMENT_EXTERNAL] == 7       # 3주 차감은 전부 EXTERNAL에서
    db.close()


def test_quantity_decrease_with_pending_order_consumes_bot_slice_first(monkeypatch):
    """봇 매도 주문이 미해결이면 그 차감은 봇 슬라이스가 받는다."""
    db = _make_db()
    user = _make_user(db)
    _seed_two_slices(db, user)
    db.add(BrokerOrder(
        user_id=user.id, intent_id="intent-1", broker_order_date="20260906",
        trade_mode="SIMULATED", side="SELL", ticker="AAPL", prefixed_ticker="AAPL",
        strategy_type="regime_switching", status="PENDING",
        requested_qty=3, submitted_price=100.0,
    ))
    db.commit()
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)

    broker = _Broker([{"ticker": "AAPL", "ticker_name": "Apple", "quantity": 12, "avg_price": 90.0}])
    ctx = _make_ctx(db, user, broker, holdings=db.query(Holding).all())
    asyncio.run(scheduler.sync_broker_holdings(ctx))

    rows = {h.management: h.quantity for h in db.query(Holding).filter_by(user_id=user.id).all()}
    assert rows[MANAGEMENT_BOT_OWNED] == 2      # 봇 주문분이 봇 슬라이스에서 빠졌다
    assert rows[MANAGEMENT_EXTERNAL] == 10      # 사용자 보유분은 무사
    db.close()


def test_quantity_increase_without_pending_order_creates_external_slice(monkeypatch):
    """앱 밖 추가 매수는 봇 슬라이스를 부풀리지 않고 EXTERNAL로 잡힌다."""
    db = _make_db()
    user = _make_user(db)
    db.add(Holding(
        user_id=user.id, ticker="AAPL", ticker_name="Apple",
        strategy_type="regime_switching", management=MANAGEMENT_BOT_OWNED,
        avg_price=100.0, quantity=5, highest_price=100.0,
    ))
    db.commit()
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)

    broker = _Broker([{"ticker": "AAPL", "ticker_name": "Apple", "quantity": 9, "avg_price": 95.0}])
    ctx = _make_ctx(db, user, broker, holdings=db.query(Holding).all())
    asyncio.run(scheduler.sync_broker_holdings(ctx))

    rows = {h.management: h.quantity for h in db.query(Holding).filter_by(user_id=user.id).all()}
    assert rows[MANAGEMENT_BOT_OWNED] == 5
    assert rows[MANAGEMENT_EXTERNAL] == 4
    db.close()


# --------------------------------------------------------------------------------------
# 3. 매도 판정 분기 (핵심) — 네거티브 컨트롤 포함
# --------------------------------------------------------------------------------------

class _CollapsedStrategy:
    """보유분을 무조건 청산 판정하는 전략 스텁."""
    name = "TestStrategy"
    is_autonomous = False
    min_smart_exit_profit = 999.0
    use_rolling_box_stop = False

    def calculate_score(self, *_args, **_kwargs):
        return 0.0

    def is_signal_collapsed(self, *_args, **_kwargs):
        return True

    def get_stop_loss_pct(self, *_args, **_kwargs):
        return 3.0

    def get_trailing_stop_pct(self, *_args, **_kwargs):
        return 2.0


def _run_exit_cycle(db, user, broker, holding, ms_manager):
    signal_map = {
        holding.ticker: {
            "price": 0.74,
            "details": {"atr": 0.05, "is_smart_exit": False},
        }
    }
    ctx = _make_ctx(
        db, user, broker,
        holdings=[holding],
        ms_manager=ms_manager,
        signal_map=signal_map,
    )
    asyncio.run(scheduler.process_exit_signals(ctx, signal_map))


def test_external_holding_is_not_sold_but_is_still_observed(monkeypatch):
    """EXTERNAL 보유분은 청산 판정에서 빠지되 관측은 계속된다.

    strategy_type을 일부러 살아 있는 슬롯 키로 둔다. EXTERNAL의 정상 strategy_type은
    "external"이고 그 값은 슬롯 조회에서 이미 걸러지므로, 그대로 쓰면 이 테스트는 관할권
    가드가 없어도 통과해 버린다(실제로 가드를 무력화한 네거티브 컨트롤에서 통과했다).
    관할권 판정의 권한이 strategy_type이 아니라 management에 있음을 고정한다.
    """
    db = _make_db()
    user = _make_user(db)
    holding = Holding(
        user_id=user.id, ticker="HCTI", ticker_name="Healthcare Triangle",
        strategy_type="regime_switching", management=MANAGEMENT_EXTERNAL,
        avg_price=1.48, quantity=4762, highest_price=0.50,
    )
    db.add(holding)
    db.commit()
    db.refresh(holding)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)

    broker = _Broker([])
    ms_manager = SimpleNamespace(strategies={"regime_switching": _CollapsedStrategy()})
    _run_exit_cycle(db, user, broker, holding, ms_manager)

    refreshed = db.query(Holding).filter_by(user_id=user.id).one()
    # 평가손익 -50%로 어떤 손절선도 뚫지만 매도 주문이 나가지 않는다.
    assert broker.sell_calls == []
    assert refreshed.quantity == 4762
    # 그럼에도 관측은 돌았다 - 잔고 평가금이 낡지 않고, 3단계 수확 모드가 쓸 고점이 남는다.
    assert float(refreshed.last_price) == 0.74
    assert float(refreshed.highest_price) == 0.74
    logs = [row.message for row in db.query(ActionLog).filter_by(user_id=user.id).all()]
    assert not any("EXIT SIGNAL" in msg for msg in logs)
    # 예외로 조용히 빠진 것이 아니라 정상 분기로 빠졌음을 확인한다.
    assert not any("Error processing holding" in msg for msg in logs)
    db.close()


def test_external_holding_with_external_strategy_type_is_also_observed(monkeypatch):
    """실제 등록 형태(strategy_type="external")에서도 관측이 멈추지 않는다.

    이 값은 어떤 슬롯 키와도 겹치지 않아 전략 조회가 None이 된다. 예전 구조는 루프 상단에서
    바로 continue 했으므로 관측조차 돌지 않았다.
    """
    db = _make_db()
    user = _make_user(db)
    holding = Holding(
        user_id=user.id, ticker="HCTI", ticker_name="Healthcare Triangle",
        strategy_type=EXTERNAL_STRATEGY_TYPE, management=MANAGEMENT_EXTERNAL,
        avg_price=1.48, quantity=4762, highest_price=0.50,
    )
    db.add(holding)
    db.commit()
    db.refresh(holding)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)

    broker = _Broker([])
    ms_manager = SimpleNamespace(strategies={"regime_switching": _CollapsedStrategy()})
    _run_exit_cycle(db, user, broker, holding, ms_manager)

    refreshed = db.query(Holding).filter_by(user_id=user.id).one()
    assert broker.sell_calls == []
    assert float(refreshed.last_price) == 0.74
    assert float(refreshed.highest_price) == 0.74
    db.close()


def test_bot_owned_holding_in_same_condition_is_sold(monkeypatch):
    """네거티브 컨트롤: 동일 조건에서 봇 관할 보유분은 실제로 청산된다.

    이 테스트가 없으면 위 테스트의 '안 팔림'이 관할권 가드 때문인지, 애초에 매도 경로가
    돌지 않아서인지 구분되지 않는다.
    """
    db = _make_db()
    user = _make_user(db)
    holding = Holding(
        user_id=user.id, ticker="HCTI", ticker_name="Healthcare Triangle",
        strategy_type="regime_switching", management=MANAGEMENT_BOT_OWNED,
        avg_price=1.48, quantity=4762, highest_price=0.50,
    )
    db.add(holding)
    db.commit()
    db.refresh(holding)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)

    broker = _Broker([])
    ms_manager = SimpleNamespace(strategies={"regime_switching": _CollapsedStrategy()})
    _run_exit_cycle(db, user, broker, holding, ms_manager)

    logs = [row.message for row in db.query(ActionLog).filter_by(user_id=user.id).all()]
    assert any("EXIT SIGNAL" in msg for msg in logs)
    assert broker.sell_calls and broker.sell_calls[0][0] == "HCTI"
    db.close()


# --------------------------------------------------------------------------------------
# 4. 슬롯 자본 산입 제외
# --------------------------------------------------------------------------------------

def test_external_holding_is_excluded_from_slot_capital():
    """EXTERNAL 평가액이 첫 슬롯 매수여력을 깎지 않는다."""
    manager = MultiStrategyManager(strategy_type="multi_slot")
    bot_only = [SimpleNamespace(
        quantity=10, current_price=None, last_price=50.0, highest_price=50.0,
        avg_price=50.0, strategy_type="episodic_pivot", management=MANAGEMENT_BOT_OWNED,
    )]
    with_external = bot_only + [SimpleNamespace(
        quantity=100, current_price=None, last_price=30.0, highest_price=30.0,
        avg_price=30.0, strategy_type=EXTERNAL_STRATEGY_TYPE, management=MANAGEMENT_EXTERNAL,
    )]

    baseline = manager.calculate_slots_allocation(10_000.0, 5_000.0, bot_only, "BULLISH")
    with_ext = manager.calculate_slots_allocation(10_000.0, 5_000.0, with_external, "BULLISH")

    for slot_key in baseline:
        assert baseline[slot_key]["stock_value"] == with_ext[slot_key]["stock_value"]
        assert baseline[slot_key]["cash_balance"] == with_ext[slot_key]["cash_balance"]


# --------------------------------------------------------------------------------------
# 5. force-liquidate 기본 제외
# --------------------------------------------------------------------------------------

def test_force_liquidate_excludes_external_by_default(monkeypatch):
    """전량 청산 버튼이 사용자의 외부 보유분까지 쓸어담지 않는다."""
    db = _make_db()
    user = _make_user(db, username="liquidator")
    db.add(Holding(
        user_id=user.id, ticker="HCTI", ticker_name="Healthcare Triangle",
        strategy_type=EXTERNAL_STRATEGY_TYPE, management=MANAGEMENT_EXTERNAL,
        avg_price=1.48, quantity=4762, highest_price=1.48,
    ))
    db.commit()
    db.refresh(user)

    monkeypatch.setattr(account_router, "get_broker_client", lambda _s: _Broker([]))

    response = asyncio.run(account_router.force_liquidate(current_user=user, db=db))

    assert response["excluded_external_count"] == 1
    assert response["liquidated_tickers"] == []
    assert db.query(Holding).filter_by(user_id=user.id).one().quantity == 4762
    db.close()


def test_multi_slice_ticker_is_not_destroyed_by_per_slice_broker_rows(monkeypatch):
    """브로커가 슬라이스별로 행을 주더라도 수량이 유실되지 않는다.

    2026-09-06 stock-auto-mobile 세션이 실환경에서 발견한 결함의 재현이다. 같은 티커를
    봇 슬롯과 EXTERNAL로 나눠 들고 있을 때 MSFT 40주(25+15)가 15주로 줄고 EXTERNAL 행이
    체결 로그 없이 사라졌다.

    원인은 계약 불일치다. sync_broker_holdings는 브로커 응답이 티커당 1행이라고 가정하고
    db_total_qty(슬라이스 합계)와 비교하는데, 시뮬레이터의 get_holdings는 Holding 행마다
    1개씩 내보낸다. 그래서 40주 보유 상태에서 25짜리 행을 만나면 -15 차분으로 오인해
    차감하고, 이어서 15짜리 행을 만나면 다시 -10을 차감한다.

    하필 EXTERNAL부터 차감하는 순서 때문에 봇 관할 밖 보유분이 먼저 파괴된다 - 이 기능이
    보호하려는 바로 그 행이다.
    """
    db = _make_db()
    user = _make_user(db)
    db.add_all([
        Holding(
            user_id=user.id, ticker="MSFT", ticker_name="Microsoft",
            strategy_type="regime_switching", management=MANAGEMENT_BOT_OWNED,
            avg_price=410.0, quantity=25, highest_price=410.0,
        ),
        Holding(
            user_id=user.id, ticker="MSFT", ticker_name="Microsoft",
            strategy_type=EXTERNAL_STRATEGY_TYPE, management=MANAGEMENT_EXTERNAL,
            avg_price=395.0, quantity=15, highest_price=395.0,
        ),
    ])
    db.commit()
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)

    # 시뮬레이터와 동일하게 보유 행마다 1개씩 내보내는 브로커.
    broker = _Broker([
        {"ticker": "MSFT", "ticker_name": "Microsoft", "quantity": 25, "avg_price": 410.0},
        {"ticker": "MSFT", "ticker_name": "Microsoft", "quantity": 15, "avg_price": 395.0},
    ])
    ctx = _make_ctx(db, user, broker, holdings=db.query(Holding).all())
    asyncio.run(scheduler.sync_broker_holdings(ctx))

    rows = db.query(Holding).filter_by(user_id=user.id).all()
    by_mgmt = {r.management: r.quantity for r in rows}
    # 총량이 보존되어야 한다. 브로커가 어떻게 쪼개 보내든 40주다.
    assert sum(r.quantity for r in rows) == 40
    # EXTERNAL 행이 살아 있어야 한다 - 이 기능이 보호하려는 대상이다.
    assert by_mgmt.get(MANAGEMENT_EXTERNAL) == 15
    assert by_mgmt.get(MANAGEMENT_BOT_OWNED) == 25
    db.close()


def test_every_app_path_deletion_leaves_an_audit_log(monkeypatch):
    """앱이 보유 행을 지우면 예외 없이 ActionLog가 남는다.

    2026-09-06에 admin의 보유 행이 사라졌는데 삭제 경로가 8군데인 데다 로깅이 제각각이라
    "앱이 지웠는지 누가 DB를 직접 건드렸는지"조차 가릴 수 없었다. 이 불변식이 서면 소거법이
    선다 - 로그 없이 사라진 행은 앱이 지운 것이 아니다.

    이 가드는 DB 직접 조작을 막지 못한다. SQL로 지우면 애플리케이션을 거치지 않기 때문이다.
    여기서 얻는 것은 "앱 경로는 전부 기록된다"는 사실 하나다.
    """
    db = _make_db()
    user = _make_user(db)
    # 브로커 계좌에 없는 보유분 - 동기화 sweep이 지우는 경로.
    db.add(Holding(
        user_id=user.id, ticker="GONE", ticker_name="Vanished Inc",
        strategy_type=EXTERNAL_STRATEGY_TYPE, management=MANAGEMENT_EXTERNAL,
        avg_price=10.0, quantity=7, highest_price=10.0,
    ))
    db.commit()
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)

    ctx = _make_ctx(db, user, _Broker([]), holdings=db.query(Holding).all())
    asyncio.run(scheduler.sync_broker_holdings(ctx))

    assert db.query(Holding).filter_by(user_id=user.id).count() == 0
    logs = [r.message for r in db.query(ActionLog).filter_by(user_id=user.id).all()]
    audit = [m for m in logs if "[Holding Deleted]" in m]
    assert len(audit) == 1
    body = audit[0]
    # 나중에 원인을 좁힐 수 있도록 무엇이·왜·어느 경로가 지웠는지가 모두 담긴다.
    assert "GONE" in body and "qty=7" in body
    assert f"management={MANAGEMENT_EXTERNAL}" in body
    assert "actor=scheduler.sync_broker_holdings" in body
    assert "reason=" in body
    db.close()
