"""회귀: 매매 사이클 DetachedInstanceError 제거 — trade_mode 스칼라 스냅샷.

PR #17(잔고 API 타임아웃 수정)이 매도 루프 중간에 커밋을 추가하면서, 공유
db_settings가 커밋으로 만료(expire)되고 micro_session의 expunge/close로 detach된 채
이후 trade_mode가 세션 밖에서 읽혀 DetachedInstanceError로 사이클이 침묵 실패했다.

핫픽스: prepare_trading_flow_context에서 세션이 살아있을 때 trade_mode를 평범한
문자열 값으로 ctx에 스냅샷하고, 세션 밖에서는 이 스냅샷만 읽는다. 세션 안에서 ORM이
실제 필요한 주문 경로는 micro_session의 merge로 다시 바인딩한다.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.bot.scheduler as scheduler
from app.core.database import Base
from app.core.models import Holding, User, UserSettings


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


def _seed_and_detach(factory):
    """준비 세션에서 값 스냅샷을 뜬 뒤, 세션을 닫아 ORM 객체를 detach 시킨다."""
    db = factory()
    user = User(username="detach-regression", hashed_password="x")
    db.add(user)
    db.flush()
    settings = UserSettings(user_id=user.id, trade_mode="MOCK", is_running=True)
    db.add(settings)
    holding = Holding(
        user_id=user.id,
        ticker="CPAY",
        ticker_name="Corpay",
        strategy_type="swing",
        quantity=10,
        avg_price=100.0,
    )
    db.add(holding)
    db.commit()
    db.refresh(settings)
    db.refresh(holding)
    # 세션이 살아있는 지금 스칼라 값으로 스냅샷 (prepare_trading_flow_context의 동작)
    trade_mode_snapshot = settings.trade_mode
    # 외부 준비 세션이 닫히는 상황 재현: expunge_all + close
    db.expunge_all()
    db.close()
    return settings, holding, trade_mode_snapshot


def _make_ctx(settings, holding, trade_mode_snapshot):
    return scheduler.TradingFlowContext(
        db=None,
        user_id=settings.user_id,
        db_settings=settings,
        trade_mode=trade_mode_snapshot,
        session="REGULAR_MARKET",
        sentiment="BULLISH",
        exchange_rate=1350.0,
        holdings=[holding],
        broker=object(),
        ms_manager=object(),
        first_slot_key="slot",
        signal_map={},
        all_signals=[],
    )


def test_trade_mode_snapshot_survives_committing_micro_session(session_factory, monkeypatch):
    settings, holding, trade_mode_snapshot = _seed_and_detach(session_factory)
    monkeypatch.setattr(scheduler, "SessionLocal", session_factory)
    ctx = _make_ctx(settings, holding, trade_mode_snapshot)

    # 앞 종목 처리 중의 커밋을 재현: micro_session 안에서 재바인딩 후 커밋.
    with scheduler.micro_session(ctx) as db:
        ctx.holdings[0].quantity += 1
        db.commit()

    # 세션 밖에서 trade_mode를 읽는 실제 코드 경로(is_kis_order 판정)는 ORM이 아니라 값 스냅샷만
    # 만지므로, micro_session의 expire_on_commit 정책과 무관하게 항상 안정적으로 읽힌다.
    # (원래 버그: 이 값을 ctx.db_settings.trade_mode로 세션 밖에서 읽어 DetachedInstanceError 발생.)
    assert (ctx.trade_mode or "").upper() == "MOCK"


def test_second_micro_session_remerges_expired_detached_settings(session_factory, monkeypatch):
    """주문 경로처럼, detach+expired 된 db_settings를 다음 micro_session이 다시
    merge할 때 StaleDataError/DetachedInstanceError 없이 재바인딩돼야 한다."""
    settings, holding, trade_mode_snapshot = _seed_and_detach(session_factory)
    monkeypatch.setattr(scheduler, "SessionLocal", session_factory)
    ctx = _make_ctx(settings, holding, trade_mode_snapshot)

    # 1차: 커밋을 일으켜 db_settings를 detach+expired 상태로 만든다.
    with scheduler.micro_session(ctx) as db:
        ctx.holdings[0].quantity += 1
        db.commit()

    # 2차: 앞선 커밋으로 만료된 db_settings를 다시 merge (create_order_intent 경로 모사).
    with scheduler.micro_session(ctx) as db:
        merged = db.merge(ctx.db_settings)
        assert (merged.trade_mode or "").upper() == "MOCK"
        merged.is_running = merged.is_running  # 낙관적 잠금 경로를 밟도록 flush 유발
        db.commit()

    # 스냅샷은 어떤 상황에서도 불변.
    assert (ctx.trade_mode or "").upper() == "MOCK"


# ---------------------------------------------------------------------------
# 원래 버그 시나리오 end-to-end 재현: process_exit_signals 매도 루프
#   앞 종목의 last_price UPDATE 커밋(PR #17)이 공유 db_settings를 만료/detach시키고,
#   뒤 종목이 trade_mode를 읽을 때 DetachedInstanceError → 종목별 except가 삼켜
#   "Error processing holding CPAY: ... not bound to a Session"로 침묵 실패했었다.
# ---------------------------------------------------------------------------


class _SellStrategy:
    name = "SellNow"
    min_smart_exit_profit = 999.0
    is_autonomous = False

    def calculate_score(self, _data, _sentiment, is_entry=False):
        return 10

    def get_stop_loss_pct(self, _atr, _price):
        return 50.0  # 수익 중이라 손절 미발동

    def get_trailing_stop_pct(self, _atr, _price):
        return 50.0

    def is_signal_collapsed(self, _score, _sentiment):
        return True  # 강세 시그널 붕괴 → 매도 신호 발생


class _SellBroker:
    def __init__(self):
        self.sell_calls = []

    def sell_order(self, ticker, quantity, price=None, session="REGULAR_MARKET", **kwargs):
        self.sell_calls.append((ticker, quantity, price))
        return {"success": True, "filled_price": 110.0, "filled_qty": quantity, "order_no": "SIM-1"}


class _FakeLease:
    async def release(self):
        pass


def _install_exit_fakes(monkeypatch):
    logs = []
    monkeypatch.setattr(scheduler, "log_action", lambda _db, _uid, msg, level="INFO": logs.append((level, msg)))
    monkeypatch.setattr(scheduler, "send_message_async", lambda *a, **k: None)

    async def fake_safe_broker_call(func, *a, **k):
        return func(*a, **k)

    async def fake_acquire(*a, **k):
        return _FakeLease()

    def fake_schedule(coro, name=None):
        if hasattr(coro, "close"):
            coro.close()  # 스냅샷 갱신 코루틴은 실행하지 않고 폐기

    monkeypatch.setattr(scheduler, "safe_broker_call", fake_safe_broker_call)
    monkeypatch.setattr(scheduler, "acquire_symbol_order_lock", fake_acquire)
    monkeypatch.setattr(scheduler, "_schedule_background_task", fake_schedule)
    return logs


@pytest.mark.asyncio
async def test_process_exit_signals_sells_both_holdings_with_trade_mode_and_holdings_fix(session_factory, monkeypatch):
    # 실 세션에 유저·설정·보유 2종목 시드 후 준비 세션을 닫아 detach 상태 재현
    db = session_factory()
    user = User(username="exit-loop-user", hashed_password="x")
    db.add(user)
    db.flush()
    settings = UserSettings(user_id=user.id, trade_mode="SIMULATED", is_running=True)
    db.add(settings)
    holdings = [
        Holding(user_id=user.id, ticker="AAA", ticker_name="Alpha", strategy_type="swing",
                quantity=5, avg_price=100.0, highest_price=120.0),
        Holding(user_id=user.id, ticker="CPAY", ticker_name="Corpay", strategy_type="swing",
                quantity=5, avg_price=100.0, highest_price=120.0),
    ]
    db.add_all(holdings)
    db.commit()
    for h in holdings:
        db.refresh(h)
    db.refresh(settings)
    trade_mode_snapshot = settings.trade_mode  # 세션 살아있을 때 값 스냅샷
    user_id = user.id  # 세션 살아있을 때 스칼라 캡처
    db.expunge_all()
    db.close()

    monkeypatch.setattr(scheduler, "SessionLocal", session_factory)
    logs = _install_exit_fakes(monkeypatch)

    broker = _SellBroker()
    ctx = scheduler.TradingFlowContext(
        db=None,
        user_id=user_id,
        db_settings=settings,
        trade_mode=trade_mode_snapshot,
        session=scheduler.MarketSession.REGULAR,
        sentiment="BULLISH",
        exchange_rate=1350.0,
        holdings=holdings,
        broker=broker,
        ms_manager=SimpleNamespace(strategies={"swing": _SellStrategy()}),
        first_slot_key="swing",
        signal_map={},
        all_signals=[],
    )
    target_signal_map = {
        "AAA": {"ticker": "AAA", "price": 110.0, "details": {"atr": 1.0, "is_smart_exit": False}},
        "CPAY": {"ticker": "CPAY", "price": 110.0, "details": {"atr": 1.0, "is_smart_exit": False}},
    }

    # 결합 검증: (A) trade_mode 값 스냅샷 + (B) holdings auto-merge load=False & 관측값 로컬화
    # 두 수정이 공존한 상태에서, 앞 종목 last_price 커밋에도 db_settings detach가 없고(A),
    # 매도 병합이 version 충돌 없이 전량 체결까지 완료돼야 한다(B).
    await scheduler.process_exit_signals(ctx, target_signal_map)

    # (1) trade_mode fix: db_settings(UserSettings)가 세션 밖에서 만료돼 "not bound to a Session"으로
    #     종목별 침묵 실패하던 로그가 없어야 한다.
    detach_failures = [
        m for lvl, m in logs
        if "Error processing holding" in m and "not bound to a Session" in m
    ]
    assert detach_failures == [], f"trade_mode 스냅샷이 db_settings detach를 못 막음: {detach_failures}"

    # (2) holdings fix: 어떤 종목도 StaleDataError로 침묵 실패하지 않아야 한다.
    stale_failures = [m for lvl, m in logs if "Error processing holding" in m]
    assert stale_failures == [], f"매도 처리 중 예외 발생: {stale_failures}"

    # (3) 두 종목 모두 실제 매도 주문 제출 + DB 전량 청산까지 완료.
    assert len(broker.sell_calls) == 2, f"매도 주문이 2건이 아님: {broker.sell_calls}"
    successes = [m for lvl, m in logs if m.startswith("SUCCESS:") and "sold" in m]
    assert len(successes) == 2, f"매도 성사 로그가 2건이 아님: {successes}"

    verify_db = session_factory()
    try:
        remaining = verify_db.query(Holding).filter(Holding.user_id == user_id).count()
    finally:
        verify_db.close()
    assert remaining == 0, f"전량 매도 후에도 holdings가 {remaining}건 잔존"
