"""목표비중형 자율 슬롯 라이브 집행부 (canary_allocation).

흐름 (1분 루프마다 호출, 멱등):
  1. 정규장(REGULAR)에서만 동작. SIMULATED 외 모드는 경고 후 건너뛴다(기존 자율 경로와 같은 제약).
  2. 이번 달 판단 기록(autonomous_slot_states)이 DONE/HELD면 할 일 없음.
  3. 기록이 없으면 신호 데이터를 받아 전략 SSOT(canary_allocation)로 판단한다.
     - 데이터 결측 → 기록하지 않고 다음 사이클에 재시도(일시 장애로 한 달을 잃지 않기 위함).
       달이 바뀐 지 3영업일이 지나도 결측이면 텔레그램 경보(쿨다운).
     - 밴드 안 변화 → HELD(직전 목표 유지, 매매 없음).
     - 변화 → DECIDED.
  4. DECIDED/EXECUTING이면 실제 보유 기준으로 차이 수량을 다시 계산해 매도 먼저, 매수 나중으로 집행한다.
     주문이 하나라도 미체결·실패면 EXECUTING으로 남겨 다음 사이클에 남은 차이만 다시 계산한다.
     모든 주문이 체결되면 DONE + 텔레그램 요약.

수량 계산은 백테스트와 같은 trade_calculations.plan_target_weight_orders를 쓴다.
스케줄러 헬퍼(micro_session·log_action·브로커 호출 등)는 순환 참조를 피하려 함수 안에서 지연 임포트한다.
설계: docs/plans/canary_allocation_live_port.md
"""
from __future__ import annotations

import json
from datetime import datetime

import pandas as pd

from app.bot.market_session import ET, MarketSession
from app.bot.trade_calculations import calculate_realized_pnl, plan_target_weight_orders
from app.core.logging import logger
from app.core.models import AutonomousSlotState, Holding, TradeLog, UnfilledOrder

STATUS_DECIDED = "DECIDED"
STATUS_EXECUTING = "EXECUTING"
STATUS_DONE = "DONE"
STATUS_HELD = "HELD"
_FINAL = (STATUS_DONE, STATUS_HELD)
_ACTIVE = (STATUS_DECIDED, STATUS_EXECUTING)

DATA_MISSING_ALERT_BUSINESS_DAYS = 3
REGIME_LABEL = "CANARY"


# ---------------------------------------------------------------------------------------------
# 상태 테이블 (순수 DB 헬퍼)
# ---------------------------------------------------------------------------------------------
def month_key(day) -> str:
    return pd.Timestamp(day).strftime("%Y-%m")


def get_month_state(db, user_id: int, slot_key: str, decision_month: str):
    """판단일이 decision_month(YYYY-MM)에 속하는 상태 행. 없으면 None."""
    return (
        db.query(AutonomousSlotState)
        .filter(
            AutonomousSlotState.user_id == user_id,
            AutonomousSlotState.slot_key == slot_key,
            AutonomousSlotState.decision_date.like(f"{decision_month}-%"),
        )
        .order_by(AutonomousSlotState.decision_date.desc())
        .first()
    )


def get_last_target(db, user_id: int, slot_key: str) -> dict | None:
    """가장 최근 확정 목표(밴드 비교 기준)."""
    row = (
        db.query(AutonomousSlotState)
        .filter(AutonomousSlotState.user_id == user_id, AutonomousSlotState.slot_key == slot_key)
        .order_by(AutonomousSlotState.decision_date.desc())
        .first()
    )
    return json.loads(row.target_json) if row else None


def get_previous_target(db, user_id: int, slot_key: str, before_decision_date: str) -> dict | None:
    """before_decision_date 이전의 마지막 확정 목표(알림의 '이전 비중' 표시용)."""
    row = (
        db.query(AutonomousSlotState)
        .filter(
            AutonomousSlotState.user_id == user_id,
            AutonomousSlotState.slot_key == slot_key,
            AutonomousSlotState.decision_date < before_decision_date,
        )
        .order_by(AutonomousSlotState.decision_date.desc())
        .first()
    )
    return json.loads(row.target_json) if row else None


def previous_decision_month(today) -> str:
    """오늘이 속한 달의 직전 달(YYYY-MM). 판단일은 항상 직전 달의 마지막 거래일이다."""
    return (pd.Timestamp(today).to_period("M") - 1).strftime("%Y-%m")


# ---------------------------------------------------------------------------------------------
# 판단 (네트워크 의존부 분리)
# ---------------------------------------------------------------------------------------------
async def load_signal_inputs(strategy, today) -> tuple[dict, pd.Series | None]:
    """신호 계산 입력: 데이터 티커 일봉 종가(오늘 미완결 봉 제외) + NFCI. 실패한 티커는 빠진다."""
    from app.scanner.data_provider import fetch_ohlcv
    from app.scanner.macro_data import fetch_fred_series
    from app.strategies.canary_allocation import NFCI_SERIES_ID

    closes: dict[str, pd.Series] = {}
    today_ts = pd.Timestamp(today)
    for ticker in strategy.data_tickers:
        try:
            df = await fetch_ohlcv(ticker, interval="1d", period="2y")
        except Exception:
            logger.exception(f"[Canary] {ticker} 일봉 수집 실패")
            continue
        if df is None or df.empty or "Close" not in df.columns:
            continue
        s = df["Close"].dropna()
        idx = pd.to_datetime(s.index)
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_localize(None)
        s = pd.Series(s.values, index=idx.normalize())
        closes[ticker] = s[s.index < today_ts.normalize()]
    nfci = fetch_fred_series(NFCI_SERIES_ID)
    return closes, nfci


def decide(strategy, closes: dict, nfci, today, last_target: dict | None):
    """(판단일, 상태, 목표, 신호). 판단 불가면 (판단일 또는 None, None, None, None)."""
    from app.strategies.canary_allocation import CALENDAR_TICKER, latest_decision_date

    if CALENDAR_TICKER not in closes or closes[CALENDAR_TICKER].empty:
        return None, None, None, None
    decision_date = latest_decision_date(closes[CALENDAR_TICKER].index, today)
    if decision_date is None:
        return None, None, None, None
    signals = strategy.compute_signals(closes, nfci, decision_date)
    target = strategy.compute_target(signals, closes, decision_date) if signals is not None else None
    if target is None:
        return decision_date, None, None, signals
    confirmed, changed = strategy.apply_band(target, last_target)
    return decision_date, (STATUS_DECIDED if changed else STATUS_HELD), confirmed, signals


def _fmt_weights(w: dict | None) -> str:
    if not w:
        return "-"
    return ", ".join(f"{k} {v * 100:.1f}%" for k, v in sorted(w.items(), key=lambda kv: -kv[1]) if v > 0)


# ---------------------------------------------------------------------------------------------
# 집행
# ---------------------------------------------------------------------------------------------
async def process_target_weight_slots(ctx, slot_allocations: dict) -> None:
    from app.bot import scheduler as sch
    from app.core.locks import RedisLockUnavailable
    from app.core.holding_audit import delete_holding
    from app.bot.trade_calculations import fee_rate_for_trade_mode

    user_id = ctx.user_id
    targets = [
        (k, info) for k, info in slot_allocations.items()
        if getattr(ctx.ms_manager.strategies.get(k), "is_target_weight", False)
    ]
    if not targets:
        return

    def _log(msg, level="INFO"):
        with sch.micro_session(ctx) as db:
            sch.log_action(db, user_id, msg, level)

    trade_mode = ((ctx.db_settings.trade_mode if ctx.db_settings else None) or "SIMULATED").upper()
    now_et = datetime.now(tz=ET)
    today = now_et.date()

    for slot_key, slot_info in targets:
        strategy = ctx.ms_manager.strategies[slot_key]
        if trade_mode != "SIMULATED":
            if sch.should_log_with_cooldown(sch.MARKET_CLOSED_LOG_CACHE, ("tw_mode_guard", user_id, slot_key)):
                _log(f"[{strategy.name}] Target-weight slot is SIMULATED-only. Skipping in {trade_mode} mode.", "WARNING")
            continue
        if ctx.session != MarketSession.REGULAR:
            continue

        decision_month = previous_decision_month(today)
        with sch.micro_session(ctx) as db:
            state = get_month_state(db, user_id, slot_key, decision_month)
            state_snapshot = None if state is None else {
                "id": state.id, "status": state.status, "decision_date": state.decision_date,
                "target": json.loads(state.target_json),
            }
            last_target = get_last_target(db, user_id, slot_key)

        if state_snapshot and state_snapshot["status"] in _FINAL:
            continue

        # 1) 이번 달 판단 (아직 기록 없음)
        if state_snapshot is None:
            closes, nfci = await load_signal_inputs(strategy, today)
            decision_date, status, target, signals = decide(strategy, closes, nfci, today, last_target)
            if status is None:
                business_days = len(pd.bdate_range(pd.Timestamp(today).replace(day=1), pd.Timestamp(today)))
                if business_days > DATA_MISSING_ALERT_BUSINESS_DAYS and sch.should_log_with_cooldown(
                    sch.WARNING_COOLDOWN_CACHE, ("tw_data_missing", user_id, slot_key), 6 * 3600.0
                ):
                    _log(f"[{strategy.name}] {decision_month} decision held: signal data missing (keeping previous target).", "WARNING")
                    sch.send_message_async(user_id, sch.I18n.get_msg(
                        sch._resolve_lang(user_id), "telegram.canary_data_missing",
                        strategy_name=strategy.name, decision_date=decision_month,
                    ))
                continue
            with sch.micro_session(ctx) as db:
                if get_month_state(db, user_id, slot_key, decision_month) is not None:
                    continue  # 다른 사이클이 먼저 기록 (경합 방지)
                row = AutonomousSlotState(
                    user_id=user_id, slot_key=slot_key, decision_date=decision_date.strftime("%Y-%m-%d"),
                    target_json=json.dumps(target), signals_json=json.dumps(signals), status=status,
                )
                db.add(row)
                db.commit()
                state_snapshot = {"id": row.id, "status": status, "decision_date": row.decision_date, "target": target}
            good = sum(1 for v in signals.values() if v)
            _log(
                f"[{strategy.name}] {state_snapshot['decision_date']} decision {status}: signals {good}/{len(signals)} "
                f"({', '.join(k for k, v in signals.items() if v) or 'none'} clear) → target [{_fmt_weights(target)}] "
                f"(previous [{_fmt_weights(last_target)}])",
                "SIGNAL",
            )
            if status == STATUS_HELD:
                continue

        # 2) 집행 (DECIDED / EXECUTING)
        target = state_snapshot["target"]
        with sch.micro_session(ctx) as db:
            slot_holdings = {
                h.ticker: {"id": h.id, "quantity": int(h.quantity or 0), "avg_price": h.avg_price, "ticker_name": h.ticker_name}
                for h in db.query(Holding).filter(Holding.user_id == user_id, Holding.strategy_type == slot_key).all()
            }
            tickers = sorted(set(target) | set(slot_holdings))
            pending = db.query(UnfilledOrder).filter(
                UnfilledOrder.user_id == user_id,
                UnfilledOrder.strategy_type == slot_key,
                UnfilledOrder.ticker.in_(tickers),
            ).first() is not None
        if pending:
            continue

        prices = {}
        for t in tickers:
            p = await sch.get_realtime_price(t)
            if p is None or p <= 0:
                break
            prices[t] = float(p)
        if len(prices) != len(tickers):
            if sch.should_log_with_cooldown(sch.WARNING_COOLDOWN_CACHE, ("tw_price", user_id, slot_key), 600.0):
                _log(f"[{strategy.name}] Live price unavailable for rebalance. Retrying next cycle.", "WARNING")
            continue

        cash = float(slot_info.get("cash_balance", 0.0))
        current_qty = {t: h["quantity"] for t, h in slot_holdings.items()}
        total = cash + sum(q * prices[t] for t, q in current_qty.items())
        plan = plan_target_weight_orders(total, target, prices, current_qty)
        if plan is None:
            continue

        with sch.micro_session(ctx) as db:
            row = db.query(AutonomousSlotState).filter(AutonomousSlotState.id == state_snapshot["id"]).first()
            if row is not None and row.status != STATUS_EXECUTING:
                row.status = STATUS_EXECUTING
                db.commit()

        fee_rate = fee_rate_for_trade_mode(trade_mode)
        all_filled = True
        for ticker, delta in sorted(plan.items(), key=lambda kv: kv[1]):  # 매도(음수) 먼저
            price = prices[ticker]
            if delta > 0:
                affordable = int(cash / (price * 1.001 * (1.0 + float(fee_rate))))
                qty = min(delta, affordable)
                if qty < 1:
                    continue  # 현금 부족 잔여 차이는 이번 달 목표 오차로 남긴다
            else:
                qty = -delta
            try:
                lease = await sch.acquire_symbol_order_lock(user_id, ticker, f"tw-{state_snapshot['id']}-{ticker}")
            except RedisLockUnavailable:
                _log(f"[{strategy.name}] ORDER BLOCKED: Redis order lock unavailable for {ticker}.", "ERROR")
                all_filled = False
                break
            if lease is None:
                all_filled = False
                break
            try:
                if delta < 0:
                    res = await sch.safe_broker_call(
                        ctx.broker.sell_order, ticker, qty, price=price * 0.999, session=ctx.session,
                        strategy_type=slot_key, regime_mode=REGIME_LABEL,
                    )
                    if not (res.get("success") and res.get("filled_qty", 0) > 0):
                        _log(f"[{strategy.name}] Rebalance SELL not filled: {ticker} x{qty} | {res.get('message', '')}", "WARNING")
                        all_filled = False
                        break
                    filled_qty, filled_price = int(res["filled_qty"]), float(res["filled_price"])
                    h = slot_holdings[ticker]
                    pnl = calculate_realized_pnl(avg_price=h["avg_price"], filled_price=filled_price,
                                                 quantity=filled_qty, fee_rate=fee_rate)
                    with sch.micro_session(ctx) as db:
                        h_db = db.query(Holding).filter(Holding.id == h["id"]).first()
                        db.add(TradeLog(
                            user_id=user_id, ticker=ticker, strategy_type=slot_key,
                            ticker_name=h["ticker_name"] or ticker, trade_type="SELL",
                            price=filled_price, quantity=filled_qty, order_no=res["order_no"],
                            regime_mode=REGIME_LABEL, signal_score=0,
                            realized_pnl=pnl.realized_pnl, return_rate=pnl.return_rate,
                        ))
                        if h_db is not None:
                            if filled_qty >= (h_db.quantity or 0):
                                delete_holding(db, h_db, actor="target_weight_executor", reason="target-weight rebalance sell")
                            else:
                                h_db.quantity -= filled_qty
                        db.commit()
                    cash += float(pnl.net_revenue)
                    if filled_qty < qty:
                        all_filled = False
                        break
                else:
                    res = await sch.safe_broker_call(
                        ctx.broker.buy_order, ticker, qty, price=price * 1.001, session=ctx.session,
                        strategy_type=slot_key, regime_mode=REGIME_LABEL,
                    )
                    if not (res.get("success") and res.get("filled_qty", 0) > 0):
                        _log(f"[{strategy.name}] Rebalance BUY not filled: {ticker} x{qty} | {res.get('message', '')}", "WARNING")
                        all_filled = False
                        break
                    filled_qty, filled_price = int(res["filled_qty"]), float(res["filled_price"])
                    with sch.micro_session(ctx) as db:
                        existing = db.query(Holding).filter(
                            Holding.user_id == user_id, Holding.strategy_type == slot_key, Holding.ticker == ticker,
                        ).first()
                        if existing is not None:
                            db.expunge(existing)
                    sch.record_successful_buy(
                        ctx=ctx, strategy_instance=strategy, existing_holding=existing, ticker=ticker,
                        strategy_type=slot_key, signal={"name": ticker}, filled_price=filled_price,
                        filled_qty=filled_qty, next_stage=3, order_no=res["order_no"], current_score=0,
                    )
                    cash -= filled_qty * filled_price * (1.0 + float(fee_rate))
                    if filled_qty < qty:
                        all_filled = False
                        break
            finally:
                await lease.release()

        if not all_filled:
            continue

        with sch.micro_session(ctx) as db:
            row = db.query(AutonomousSlotState).filter(AutonomousSlotState.id == state_snapshot["id"]).first()
            if row is not None:
                row.status = STATUS_DONE
                db.commit()
                signals = json.loads(row.signals_json) if row.signals_json else {}
            else:
                signals = {}
            previous = get_previous_target(db, user_id, slot_key, state_snapshot["decision_date"])
        good = sum(1 for v in signals.values() if v)
        _log(f"[{strategy.name}] Rebalance DONE for {state_snapshot['decision_date']}: [{_fmt_weights(target)}]", "INFO")
        sch.send_message_async(user_id, sch.I18n.get_msg(
            sch._resolve_lang(user_id), "telegram.canary_rebalance",
            strategy_name=strategy.name, decision_date=state_snapshot["decision_date"],
            good_count=good, total_count=len(signals),
            signal_summary=", ".join(f"{k}{'✅' if v else '⚠️'}" for k, v in signals.items()),
            target_summary=_fmt_weights(target),
            previous_summary=_fmt_weights(previous),
        ))
