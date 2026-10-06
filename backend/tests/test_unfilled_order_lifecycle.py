# -*- coding: utf-8 -*-
"""모의(SIMULATED) 미체결 주문의 수명 관리 회귀 테스트.

2026-09 사이클 성능 회귀의 원인이 여기였다. 정규장 사이클 352초 중 241초(72%)가
미체결 주문 처리 구간이었고, 그 안에서 실제로 일어나던 일은 다음과 같다.

  1. 매도 지정가가 현재가보다 조금이라도 높으면 체결되지 않고 주문이 남는다. 다음 사이클에
     같은 보유분을 또 팔면서 주문이 겹쳤다(실측 최대 10건). 실제 증권사는 주문을 걸면 그
     수량을 묶어 두지만 이 시뮬레이터에는 그 예약이 없었다.
  2. 겹친 주문 중 하나가 체결되어 보유분이 사라지면 나머지는 전부 고아가 된다. 기존 정리
     코드가 "지정가 도달" 조건 안쪽에 있어, 가격이 닿지 않으면 삭제 기회조차 오지 않았다.
     그래서 매도 미체결 605건 중 595건이 두 달 가까이 쌓인 고아였다.
  3. 시세는 미체결 주문을 가진 유저마다 따로, 동기로, 이벤트 루프 위에서 받았다. 유저 54명이
     같은 티커를 중복해서 내려받았다.

여기서 고정하는 계약은 셋이다.
  - 매도 재시도는 주문을 쌓지 않고 기존 대기 주문을 갱신한다(한 보유분에 대기 주문 최대 1건).
  - 팔 물건이 없는 매도 주문은 시세를 받기 전에 지운다.
  - 시세는 주어지면 그대로 쓰고 네트워크를 타지 않는다(사이클이 한 번만 받아 나눠 준다).

막는 방향(대기 주문이 있으면 매도 금지)을 택하지 않은 이유도 함께 고정한다. 체결되지 않은
손절의 재시도 경로가 곧 다음 사이클의 매도이므로, 막으면 주문 하나가 걸린 동안 그 종목을
아무리 떨어져도 팔지 못한다.
"""

from types import SimpleNamespace

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.brokers.simulated_broker as simulated_broker_module
from app.brokers.simulated_broker import (
    LocalSimulatedBroker,
    collect_unfilled_tickers,
    fetch_unfilled_prices,
    purge_orphan_sell_orders,
)
from app.core.database import Base
from app.core.models import Holding, TradeLog, UnfilledOrder, User


def _env(tmp_path, monkeypatch, db_name="unfilled.db", usernames=("sim_user",)):
    engine = create_engine(f"sqlite:///{tmp_path / db_name}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(simulated_broker_module, "SessionLocal", session_factory)

    db = session_factory()
    try:
        ids = []
        for name in usernames:
            user = User(username=name, hashed_password="hash")
            db.add(user)
            db.commit()
            db.refresh(user)
            ids.append(user.id)
    finally:
        db.close()
    return session_factory, ids


def _add_holding(db, user_id, ticker="TEST", strategy_type="darvas_box", qty=87, avg=40.0):
    h = Holding(
        user_id=user_id, ticker=ticker, ticker_name=ticker, avg_price=avg,
        quantity=qty, highest_price=avg, strategy_type=strategy_type,
    )
    db.add(h)
    db.commit()
    return h


def _add_unfilled(db, user_id, ticker="TEST", strategy_type="darvas_box",
                  trade_type="SELL", qty=87, price=44.02, order_no=None):
    order = UnfilledOrder(
        user_id=user_id, ticker=ticker, ticker_name=ticker, trade_type=trade_type,
        price=price, quantity=qty, strategy_type=strategy_type,
        # order_no는 유니크 제약이 있다. 유저까지 넣어야 여러 유저에 같은 주문을 심을 수 있다.
        order_no=order_no or f"SIM-{trade_type}-{ticker}-{price}-u{user_id}",
    )
    db.add(order)
    db.commit()
    return order


def _no_network(monkeypatch):
    """네트워크 호출이 일어나면 즉시 실패시킨다."""
    def boom(*args, **kwargs):
        raise AssertionError("시세를 네트워크로 받았다 - 이 경로는 조회가 없어야 한다")
    monkeypatch.setattr(simulated_broker_module, "fetch_bulk_ohlcv_sync", boom)


# ======================================================================================
# 1. 매도 재시도는 주문을 쌓지 않고 갱신한다
# ======================================================================================

def test_sell_retry_replaces_the_pending_order_instead_of_stacking(tmp_path, monkeypatch):
    """같은 보유분에 대기 주문은 최대 한 건만 남는다 - 이중 매도 여지를 없애는 불변식이다."""
    session_factory, (user_id,) = _env(tmp_path, monkeypatch, "replace.db")
    db = session_factory()
    try:
        _add_holding(db, user_id)
    finally:
        db.close()

    # 현재가(43.0)가 지정가보다 낮아 계속 체결되지 않는 상황에서 세 사이클 연속 매도 시도
    monkeypatch.setattr(LocalSimulatedBroker, "_get_live_price", lambda self, t: 43.0)
    broker = LocalSimulatedBroker(db_settings=SimpleNamespace(user_id=user_id))
    for limit in (44.02, 43.90, 43.50):
        res = broker.sell_order("TEST", 87, limit, strategy_type="darvas_box")
        assert res["success"] and res["fill_confirmed"] is False

    db = session_factory()
    try:
        orders = db.query(UnfilledOrder).filter_by(user_id=user_id, trade_type="SELL").all()
        assert len(orders) == 1, f"대기 주문이 쌓였다: {[float(o.price) for o in orders]}"
        # 남은 한 건은 가장 최근 가격이어야 한다 - 갱신이지 방치가 아니다.
        assert float(orders[0].price) == pytest.approx(43.50)
    finally:
        db.close()


def test_sell_retry_still_fills_when_price_comes_back(tmp_path, monkeypatch):
    """갱신이 재시도를 막지 않는다 - 가격이 닿으면 그 사이클에 체결된다.

    '대기 주문이 있으면 매도 금지'로 막았다면 이 체결이 일어나지 않는다. 손절이 얼어붙는
    그 설계를 택하지 않았음을 행위로 고정한다.
    """
    session_factory, (user_id,) = _env(tmp_path, monkeypatch, "retry_fill.db")
    db = session_factory()
    try:
        _add_holding(db, user_id)
    finally:
        db.close()

    broker = LocalSimulatedBroker(db_settings=SimpleNamespace(user_id=user_id))
    monkeypatch.setattr(LocalSimulatedBroker, "_get_live_price", lambda self, t: 43.0)
    broker.sell_order("TEST", 87, 44.02, strategy_type="darvas_box")

    monkeypatch.setattr(LocalSimulatedBroker, "_get_live_price", lambda self, t: 44.10)
    res = broker.sell_order("TEST", 87, 44.00, strategy_type="darvas_box")

    assert res["fill_confirmed"] is True
    db = session_factory()
    try:
        assert db.query(UnfilledOrder).filter_by(user_id=user_id).count() == 0, (
            "체결됐는데 직전 대기 주문이 남았다 - 다음 사이클에 고아가 된다"
        )
    finally:
        db.close()


def test_sell_still_rejects_more_than_held(tmp_path, monkeypatch):
    """보유 수량을 넘는 매도는 여전히 거절된다 - 갱신이 수량 가드를 무르게 하지 않는다."""
    session_factory, (user_id,) = _env(tmp_path, monkeypatch, "oversell.db")
    db = session_factory()
    try:
        _add_holding(db, user_id, qty=10)
    finally:
        db.close()

    monkeypatch.setattr(LocalSimulatedBroker, "_get_live_price", lambda self, t: 50.0)
    broker = LocalSimulatedBroker(db_settings=SimpleNamespace(user_id=user_id))
    res = broker.sell_order("TEST", 87, 44.0, strategy_type="darvas_box")
    assert res["success"] is False and res["status"] == "REJECTED"


# ======================================================================================
# 2. 팔 물건이 없는 주문은 시세를 받기 전에 지운다
# ======================================================================================

def test_orphan_sell_orders_are_purged_without_any_price_lookup(tmp_path, monkeypatch):
    """보유분이 사라진 매도 주문은 시세 조회 없이 정리된다.

    기존 구현은 삭제가 '지정가 도달' 조건 안쪽에 있어, 가격이 닿지 않는 한 영원히 남고
    매 사이클 그 티커의 시세를 받았다.
    """
    session_factory, (user_id,) = _env(tmp_path, monkeypatch, "orphan.db")
    db = session_factory()
    try:
        _add_unfilled(db, user_id, ticker="NKE")          # 보유분 없음 = 고아
        _no_network(monkeypatch)
        broker = LocalSimulatedBroker(db_settings=SimpleNamespace(user_id=user_id))
        broker.process_unfilled_orders(db)
        assert db.query(UnfilledOrder).count() == 0, "고아 매도 주문이 남았다"
    finally:
        db.close()


def test_purge_keeps_orders_that_still_have_a_holding(tmp_path, monkeypatch):
    """살아 있는 주문은 지우지 않는다 - 정리가 정상 주문까지 쓸어가면 청산이 사라진다."""
    session_factory, (user_id,) = _env(tmp_path, monkeypatch, "keep.db")
    db = session_factory()
    try:
        _add_holding(db, user_id, ticker="NKE")
        _add_unfilled(db, user_id, ticker="NKE")
        assert purge_orphan_sell_orders(db, [user_id]) == 0
        assert db.query(UnfilledOrder).count() == 1
    finally:
        db.close()


def test_purge_leaves_buy_orders_alone(tmp_path, monkeypatch):
    """매수 미체결은 대상이 아니다 - 체결되어야 보유분이 생기므로 보유분이 없는 것이 정상이다."""
    session_factory, (user_id,) = _env(tmp_path, monkeypatch, "buy.db")
    db = session_factory()
    try:
        _add_unfilled(db, user_id, ticker="AAPL", trade_type="BUY", qty=5, price=100.0)
        assert purge_orphan_sell_orders(db, [user_id]) == 0
        assert db.query(UnfilledOrder).count() == 1
    finally:
        db.close()


def test_purge_treats_zero_quantity_holding_as_no_holding(tmp_path, monkeypatch):
    """수량 0인 보유분은 팔 물건이 없는 것과 같다."""
    session_factory, (user_id,) = _env(tmp_path, monkeypatch, "zero.db")
    db = session_factory()
    try:
        _add_holding(db, user_id, ticker="NKE", qty=0)
        _add_unfilled(db, user_id, ticker="NKE")
        assert purge_orphan_sell_orders(db, [user_id]) == 1
    finally:
        db.close()


# ======================================================================================
# 3. 시세는 사이클이 한 번만 받아 나눠 준다
# ======================================================================================

def test_given_prices_are_used_without_network(tmp_path, monkeypatch):
    """prices를 받으면 네트워크를 타지 않고 그대로 체결 판정에 쓴다."""
    session_factory, (user_id,) = _env(tmp_path, monkeypatch, "given.db")
    db = session_factory()
    try:
        _add_holding(db, user_id, ticker="NKE", qty=87)
        _add_unfilled(db, user_id, ticker="NKE", price=44.02)
        _no_network(monkeypatch)

        broker = LocalSimulatedBroker(db_settings=SimpleNamespace(user_id=user_id))
        broker.process_unfilled_orders(db, prices={"NKE": 44.50})   # 지정가 도달

        assert db.query(UnfilledOrder).count() == 0
        log = db.query(TradeLog).filter_by(user_id=user_id, trade_type="SELL").one()
        # 체결가는 지정가다(시뮬레이터 계약). 수량은 보유분을 넘지 않는다.
        assert float(log.price) == pytest.approx(44.02)
        assert log.quantity == 87
    finally:
        db.close()


def test_collect_tickers_deduplicates_across_users(tmp_path, monkeypatch):
    """유저가 달라도 같은 티커는 한 번만 담는다 - 조회 수가 유저 수와 무관해지는 근거다."""
    session_factory, ids = _env(tmp_path, monkeypatch, "dedup.db", usernames=("a", "b", "c"))
    db = session_factory()
    try:
        for uid in ids:
            _add_holding(db, uid, ticker="NKE")
            _add_unfilled(db, uid, ticker="NKE")
        _add_holding(db, ids[0], ticker="AAPL")
        _add_unfilled(db, ids[0], ticker="AAPL")

        tickers = collect_unfilled_tickers(db, ids)
        assert sorted(tickers) == ["AAPL", "NKE"], tickers
    finally:
        db.close()


def test_bulk_fetch_asks_for_each_ticker_once(monkeypatch):
    """일괄 조회는 티커 목록 그대로 한 번만 호출한다."""
    calls = []

    def fake_bulk(tickers, **kwargs):
        calls.append(list(tickers))
        return pd.DataFrame({"Close": [44.5]})

    monkeypatch.setattr(simulated_broker_module, "fetch_bulk_ohlcv_sync", fake_bulk)
    prices = fetch_unfilled_prices(["NKE"])

    assert calls == [["NKE"]], calls
    assert float(prices["NKE"]) == pytest.approx(44.5)


def test_bulk_fetch_failure_is_not_fatal(monkeypatch):
    """조회가 실패해도 예외를 밖으로 던지지 않는다 - 사이클 전체가 멈추면 안 된다."""
    def boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(simulated_broker_module, "fetch_bulk_ohlcv_sync", boom)
    assert fetch_unfilled_prices(["NKE"]) == {}
