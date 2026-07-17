# -*- coding: utf-8 -*-
"""SIMULATED 주문 경로의 전략(strategy_type) 태깅 회귀 테스트.

배경(2026-07-16): 스케줄러 메인 매수/매도 SIMULATED 분기가 broker 호출 시
strategy_type을 전달하지 않아 미체결 주문이 기본값(regime_switching)으로
오태깅됐다. 그 결과 (1) 미체결 매수가 체결되면 보유가 유저의 실제 전략 슬롯
밖으로 오귀속되고, (2) 미체결 매도는 (ticker, strategy_type) 불일치로 보유를
찾지 못해 청산이 무기한 누락됐다. 이 테스트는 태그 전파의 행위 보증과
호출부 소스 가드(AST) 두 층으로 재발을 방지한다.
"""

import ast
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.bot.simulated_broker as simulated_broker_module
from app.bot.simulated_broker import LocalSimulatedBroker
from app.core.database import Base
from app.core.models import Holding, TradeLog, UnfilledOrder, User

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _make_broker_env(tmp_path, monkeypatch, db_name):
    engine = create_engine(f"sqlite:///{tmp_path / db_name}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(simulated_broker_module, "SessionLocal", session_factory)

    db = session_factory()
    try:
        user = User(username="tagging_user", hashed_password="hash")
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
    finally:
        db.close()

    broker = LocalSimulatedBroker(db_settings=SimpleNamespace(user_id=user_id))
    return engine, session_factory, broker, user_id


def _mock_live_price(monkeypatch, price):
    monkeypatch.setattr(
        LocalSimulatedBroker, "_get_live_price", lambda self, ticker: price
    )


def _mock_bulk_price(monkeypatch, price):
    df = pd.DataFrame({"Close": [price]})
    monkeypatch.setattr(
        simulated_broker_module,
        "fetch_bulk_ohlcv_sync",
        lambda tickers, **kwargs: df,
    )


def test_unfilled_buy_preserves_strategy_type_through_fill(tmp_path, monkeypatch):
    """미체결 매수의 strategy_type이 체결 후 Holding/TradeLog까지 보존되어야 한다."""
    engine, session_factory, broker, user_id = _make_broker_env(
        tmp_path, monkeypatch, "tagging_buy.db"
    )

    # 시세(200) > 지정가(100) → 미체결 주문 생성
    _mock_live_price(monkeypatch, 200.0)
    res = broker.buy_order(
        "TEST", 5, 100.0,
        strategy_type="exploded_c", buy_stage=1,
        regime_mode="BULLISH", signal_score=80,
    )
    assert res["success"] and res["fill_confirmed"] is False

    db = session_factory()
    try:
        order = db.query(UnfilledOrder).filter_by(user_id=user_id).one()
        assert order.strategy_type == "exploded_c"

        # 시세(90) <= 지정가(100) → 체결. 태그가 Holding/TradeLog로 전파되어야 함
        _mock_bulk_price(monkeypatch, 90.0)
        broker.process_unfilled_orders(db)

        holding = db.query(Holding).filter_by(user_id=user_id, ticker="TEST").one()
        assert holding.strategy_type == "exploded_c"
        log = db.query(TradeLog).filter_by(user_id=user_id, ticker="TEST").one()
        assert log.strategy_type == "exploded_c"
        assert db.query(UnfilledOrder).filter_by(user_id=user_id).count() == 0
    finally:
        db.close()
    engine.dispose()


def test_unfilled_sell_with_matching_tag_liquidates_holding(tmp_path, monkeypatch):
    """전략 태그가 일치하는 미체결 매도는 체결 시 해당 슬롯 보유를 감소시켜야 한다.

    (버그 상황에서는 주문이 regime_switching으로 오태깅되어 보유를 못 찾고
    주문만 삭제된 채 청산이 누락됐다.)
    """
    engine, session_factory, broker, user_id = _make_broker_env(
        tmp_path, monkeypatch, "tagging_sell.db"
    )

    db = session_factory()
    try:
        db.add(Holding(
            user_id=user_id, ticker="TEST", ticker_name="Test",
            avg_price=100.0, quantity=5, highest_price=110.0,
            strategy_type="exploded_c",
        ))
        db.commit()
    finally:
        db.close()

    # 시세(90) < 지정가(120) → 미체결 매도 생성
    _mock_live_price(monkeypatch, 90.0)
    res = broker.sell_order("TEST", 5, 120.0, strategy_type="exploded_c")
    assert res["success"] and res["fill_confirmed"] is False

    db = session_factory()
    try:
        order = db.query(UnfilledOrder).filter_by(user_id=user_id).one()
        assert order.strategy_type == "exploded_c"

        # 시세(125) >= 지정가(120) → 체결. 같은 태그의 보유가 전량 청산되어야 함
        _mock_bulk_price(monkeypatch, 125.0)
        broker.process_unfilled_orders(db)
        db.expire_all()

        holding = db.query(Holding).filter_by(user_id=user_id, ticker="TEST").first()
        assert holding is None or holding.quantity == 0
        assert db.query(UnfilledOrder).filter_by(user_id=user_id).count() == 0
    finally:
        db.close()
    engine.dispose()


def _iter_calls(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node


def _first_arg_broker_method(call):
    """호출의 첫 위치 인자가 *.buy_order / *.sell_order 속성이면 그 이름을 반환."""
    if not call.args:
        return None
    first = call.args[0]
    if isinstance(first, ast.Attribute) and first.attr in ("buy_order", "sell_order"):
        return first.attr
    return None


def test_scheduler_simulated_order_call_sites_pass_strategy_type():
    """스케줄러의 SIMULATED 주문 호출(safe_broker_call 경유)은 반드시
    strategy_type 키워드를 전달해야 한다. (KIS 경로 execute_and_poll_order는
    broker 시그니처가 달라 검사 대상에서 제외)"""
    source = (BACKEND_ROOT / "app" / "bot" / "scheduler.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    violations = []
    for call in _iter_calls(tree):
        func = call.func
        if not (isinstance(func, ast.Name) and func.id == "safe_broker_call"):
            continue
        method = _first_arg_broker_method(call)
        if method is None:
            continue
        keywords = {kw.arg for kw in call.keywords if kw.arg is not None}
        if "strategy_type" not in keywords:
            violations.append(f"scheduler.py:{call.lineno} safe_broker_call({method}) — strategy_type 누락")

    assert not violations, (
        "SIMULATED 주문 호출부에 strategy_type 키워드가 누락되면 미체결 주문이 "
        "기본값(regime_switching)으로 오태깅됩니다:\n" + "\n".join(violations)
    )


def test_manual_liquidation_simulated_call_passes_strategy_type():
    """router_account.py의 수동 청산 SIMULATED 분기(run_in_threadpool 경유,
    client_order_id 없는 호출)도 strategy_type을 전달해야 한다."""
    source = (BACKEND_ROOT / "app" / "trades" / "router_account.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    violations = []
    for call in _iter_calls(tree):
        func = call.func
        if not (isinstance(func, ast.Name) and func.id == "run_in_threadpool"):
            continue
        method = _first_arg_broker_method(call)
        if method is None:
            continue
        keywords = {kw.arg for kw in call.keywords if kw.arg is not None}
        # client_order_id를 넘기는 호출은 KIS(주문 인텐트) 경로 — broker 시그니처가 달라 제외
        if "client_order_id" in keywords:
            continue
        if "strategy_type" not in keywords:
            violations.append(f"router_account.py:{call.lineno} run_in_threadpool({method}) — strategy_type 누락")

    assert not violations, (
        "수동 청산 SIMULATED 호출부에 strategy_type 키워드가 누락되면 미체결 주문이 "
        "기본값(regime_switching)으로 오태깅됩니다:\n" + "\n".join(violations)
    )
