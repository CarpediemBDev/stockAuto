from apscheduler.schedulers.background import BackgroundScheduler
from app.bot.broker_factory import get_broker_client
from app.core.database import SessionLocal
from app.core.models import TradeLog, Holding, ActionLog, UserSettings, WatchList, User, AccountEquitySnapshot
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from zoneinfo import ZoneInfo
import asyncio
import threading
import socket
import httpx
from requests.exceptions import RequestException as RequestsRequestException
from app.core.logging import logger
from app.core.config import settings
from app.scanner.data_provider import fetch_ohlcv
from app.core.telegram import send_message_async, send_daily_report_to_all_users_sync
from app.bot.fx_cache import FXRateCache
from app.bot.market_session import (
    AFTER_HOURS_CLOSE,
    EARLY_CLOSE_AFTER_HOURS_END,
    PRE_MARKET_OPEN,
    REGULAR_MARKET_OPEN,
    MarketSession,
)
from app.trades.market_overview_cache import market_overview_cache_wrapper
from app.scanner.swing_prediction_cache import swing_prediction_cache_wrapper
from app.bot.us_market_calendar import nyse_regular_close
from app.bot.order_reconciler import (
    begin_order_submission,
    create_order_intent,
    finalize_order_submission,
    has_unresolved_orders,
    reconcile_open_orders_once,
)
from app.bot.order_discovery import discover_orphan_orders_once
import time
import math
from app.core.models import utc_now_aware
# 💡 네트워크 일시 장애에 따른 텔레그램 경고 도배 방지용 시간 기록 저장소
_user_network_alert_sent = {}

# 매수 실패(단가 초과, 예수금 부족) 알림 도배 방지용 쿨타임 캐시 (1시간)
WARNING_COOLDOWN_CACHE = {}
MARKET_CLOSED_LOG_CACHE = {}
SCANNER_CACHE_EMPTY_LOG_CACHE = {}
LOG_COOLDOWN_SECONDS = 1800.0

# 💡 동적 손절선 및 트레일링 스탑 이탈 연속 횟수 추적 캐시 (Whipsaw 방지용 연속 2회 확정 가드)
# 키: (user_id, ticker) -> 값: int (연속 이탈 횟수)
BREACH_COUNT_CACHE = {}

_scanner_refresh_lock = threading.Lock()
_scanner_refresh_in_progress = False


def should_log_with_cooldown(cache: dict, key, cooldown_seconds: float = LOG_COOLDOWN_SECONDS) -> bool:
    now = time.time()
    last_logged = cache.get(key, 0.0)
    if now - last_logged < cooldown_seconds:
        return False
    cache[key] = now
    return True


from app.scanner.scanner import scan_overseas_market, analyze_single_ticker, check_market_sentiment

scheduler = BackgroundScheduler()


is_processing = False # 중복 실행 방지용 플래그
is_manual_scanning = False # 💡 수동 스캔 실행 상태 추적용 전역 플래그
_processing_lock = threading.Lock()  # 💡 is_processing 레이스 컨디션 방지용 스레드 락
latest_scanned_signals = [] # 글로벌 실시간 마켓 스캔 시그널 캐시용
latest_watchlist_signals = {} # 사용자별 라우팅 전에만 사용하는 관심종목 분석 캐시

# 💡 KIS API 동시성 제어 세마포어 (초당 최대 15회 호출로 자동 제한 - 429 차단 철벽 방어)
kis_semaphore = asyncio.Semaphore(15)

async def safe_broker_call(func, *args, **kwargs):
    """
    KIS API의 초당 호출 제한(Rate Limit)을 철저히 준수하기 위해 동시성 세마포어 가드 하에
    동기식 브로커 함수를 비동기 스레드 풀(asyncio.to_thread)에서 안전하게 지연 호출합니다.
    """
    async with kis_semaphore:
        # 호출 사이에 아주 미세한 지연(40ms)을 주어 고르게 배분
        await asyncio.sleep(0.04)
        return await asyncio.to_thread(func, *args, **kwargs)

async def execute_and_poll_order(broker, func, *args, **kwargs):
    """
    주문을 비동기로 발송하고 즉시 반환(skip_poll=True)받은 뒤,
    비동기 타이머(await asyncio.sleep)를 활용하여 체결 상태를 폴링합니다.
    다른 유저들의 주문 처리를 전혀 블로킹하지 않습니다.
    """
    kwargs["skip_poll"] = True
    res = await safe_broker_call(func, *args, **kwargs)
    
    if res.get("status") == "PENDING" and res.get("order_no"):
        order_no = res["order_no"]
        quantity = kwargs.get("quantity")
        price = kwargs.get("price")
        
        # 최대 5회 x 2초 = 10초 대기 (비동기로 대기)
        for attempt in range(1, 6):
            await asyncio.sleep(2.0)
            status_res = await safe_broker_call(broker.check_order_status, order_no)
            
            status_code = status_res.get("status")
            if status_code == "FILLED":
                res["status"] = "FILLED"
                res["filled_qty"] = status_res.get("filled_qty", quantity)
                res["filled_price"] = status_res.get("filled_price", price)
                res["success"] = True
                res["fill_confirmed"] = True
                break
            elif status_code == "PARTIAL":
                filled_qty = status_res.get("filled_qty", 0)
                if filled_qty > 0:
                    res["status"] = "PARTIAL"
                    res["filled_qty"] = filled_qty
                    res["filled_price"] = status_res.get("filled_price", price)
                    res["success"] = True
                    res["fill_confirmed"] = False
                    break
            elif status_code == "ERROR":
                break
    return res

ET = ZoneInfo("America/New_York") # 미국 동부 표준시(ET)는 DST를 자동으로 반영합니다


def get_market_session(now_et: datetime | None = None) -> MarketSession:
    """
    현재 시각 기준 미국 주식시장 세션을 반환합니다.
    - PRE_MARKET: 04:00 ~ 09:30 ET
    - REGULAR_MARKET: 09:30 ~ 16:00 ET
    - AFTER_HOURS: 16:00 ~ 20:00 ET
    - CLOSED: 나머지 시간 및 주말
    """
    now_et = now_et or datetime.now(tz=ET)
    if now_et.tzinfo is None:
        now_et = now_et.replace(tzinfo=ET)
    else:
        now_et = now_et.astimezone(ET)

    regular_close = nyse_regular_close(now_et.date())
    if regular_close is None:
        return MarketSession.CLOSED

    current_time = now_et.time()
    after_hours_close = (
        EARLY_CLOSE_AFTER_HOURS_END
        if regular_close.hour == 13
        else AFTER_HOURS_CLOSE
    )

    if PRE_MARKET_OPEN <= current_time < REGULAR_MARKET_OPEN:
        return MarketSession.PRE_MARKET
    if REGULAR_MARKET_OPEN <= current_time < regular_close:
        return MarketSession.REGULAR
    if regular_close <= current_time < after_hours_close:
        return MarketSession.AFTER_HOURS
    return MarketSession.CLOSED

async def get_realtime_price(ticker: str) -> float | None:
    """
    매수 직전 해당 종목의 실시간 현재가를 새롭게 조회합니다.
    데이터 프로바이더 1분봉 활용 (Period: 1d, Interval: 1m)
    """
    try:
        df = await fetch_ohlcv(ticker, interval="1m", period="1d")
        if df.empty:
            return None
        return float(df['Close'].iloc[-1])
    except Exception as e:
        logger.exception(f"[RealTimePrice] Failed to fetch {ticker}")
        return None


def log_action(db, user_id: int, message: str, level="INFO"):
    """활동 로그를 특정 사용자의 ID로 DB에 기록합니다."""
    db.add(ActionLog(user_id=user_id, message=message, level=level))
    db.commit()
    logger.info(f"[{level}] [User {user_id}] {message}")


def halt_trading_for_order_review(
    ctx: "TradingFlowContext",
    side: str,
    ticker: str,
    order_result: dict,
) -> None:
    ctx.db_settings.is_running = False
    ctx.db.commit()
    status = order_result.get("status", "UNCONFIRMED")
    order_no = order_result.get("order_no", "")
    message = (
        f"[ORDER RECONCILIATION] {side} order for {ticker} is {status}. "
        f"Automatic trading is paused while the order ledger retries broker reconciliation. "
        f"Order: {order_no or 'UNKNOWN'}"
    )
    log_action(ctx.db, ctx.user_id, message, "ERROR")
    send_message_async(
        ctx.user_id,
        f"*Automatic Trading Paused - Order Reconciliation*\n"
        f"Side: `{side}`\n"
        f"Ticker: `{ticker}`\n"
        f"Status: `{status}`\n"
        f"Order No: `{order_no or 'UNKNOWN'}`\n\n"
        "The system will keep checking the broker and resume automatically after all unresolved orders are terminal."
    )


@dataclass
class TradingFlowContext:
    db: object
    user_id: int
    db_settings: UserSettings
    session: str
    sentiment: str
    exchange_rate: float
    holdings: list
    broker: object
    ms_manager: object
    first_slot_key: str
    signal_map: dict
    all_signals: list


def load_watchlist_tickers_by_user(db, user_ids: list[int]) -> dict[int, set[str]]:
    watchlists = {user_id: set() for user_id in user_ids}
    if not user_ids:
        return watchlists

    rows = db.query(WatchList.user_id, WatchList.ticker).filter(
        WatchList.user_id.in_(user_ids)
    ).all()
    for user_id, raw_ticker in rows:
        ticker = (raw_ticker or "").strip().upper()
        if ticker and user_id in watchlists:
            watchlists[user_id].add(ticker)
    return watchlists


def build_user_signal_context(
    user_id: int,
    market_signals: list,
    watchlists_by_user: dict[int, set[str]],
    watchlist_signal_map: dict[str, dict],
) -> tuple[dict, list]:
    user_watchlist = watchlists_by_user.get(user_id, set())
    user_signals = []
    included_tickers = set()

    for market_signal in market_signals:
        ticker = market_signal.get("ticker")
        if not ticker:
            continue
        signal = dict(market_signal)
        sources = list(signal.get("source", []))
        if ticker in user_watchlist and "WATCHLIST" not in sources:
            sources.append("WATCHLIST")
        signal["source"] = sources
        user_signals.append(signal)
        included_tickers.add(ticker)

    for ticker in sorted(user_watchlist - included_tickers):
        cached_signal = watchlist_signal_map.get(ticker)
        if not cached_signal:
            continue
        signal = dict(cached_signal)
        signal["source"] = ["WATCHLIST"]
        user_signals.append(signal)

    return {signal["ticker"]: signal for signal in user_signals}, user_signals


def prepare_trading_flow_context(
    db,
    user_id: int,
    signal_map: dict,
    all_signals: list,
    exchange_rate: float,
    sentiment: str,
    session: str,
) -> TradingFlowContext | None:
    db_settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if not db_settings or not db_settings.is_running:
        return None
    if has_unresolved_orders(db, user_id):
        db_settings.is_running = False
        db.commit()
        log_action(
            db,
            user_id,
            "[ORDER GUARD] Trading was paused because an unresolved broker order exists.",
            "ERROR",
        )
        return None

    holdings = db.query(Holding).filter(Holding.user_id == user_id).all()
    if session == MarketSession.CLOSED and not holdings:
        if should_log_with_cooldown(MARKET_CLOSED_LOG_CACHE, ("closed_no_holdings", user_id)):
            log_action(
                db,
                user_id,
                "[MARKET CLOSED] US market is closed and no holdings exist. Skipping market data, balance, and buy analysis for this cycle.",
                "INFO"
            )
        return None

    log_action(db, user_id, f"Scan Cycle Started (Mode: {db_settings.trade_mode} | Market Regime: {sentiment})")

    broker = get_broker_client(db_settings)

    from app.bot.multi_strategy_manager import MultiStrategyManager
    strategy_type = getattr(db_settings, "strategy_type", "regime_switching")
    ms_manager = MultiStrategyManager(strategy_type=strategy_type)
    first_slot_key = list(ms_manager.SLOTS.keys())[0]

    return TradingFlowContext(
        db=db,
        user_id=user_id,
        db_settings=db_settings,
        session=session,
        sentiment=sentiment,
        exchange_rate=exchange_rate,
        holdings=holdings,
        broker=broker,
        ms_manager=ms_manager,
        first_slot_key=first_slot_key,
        signal_map=signal_map,
        all_signals=all_signals,
    )


async def sync_broker_holdings(ctx: TradingFlowContext) -> None:
    try:
        real_holdings = await safe_broker_call(ctx.broker.get_holdings, exchange_rate=ctx.exchange_rate)
        # 티커별 DB 보유 레코드 리스트 그룹화
        db_holdings_by_ticker = {}
        for db_h in ctx.holdings:
            db_holdings_by_ticker.setdefault(db_h.ticker, []).append(db_h)

        real_ticker_set = set()

        for rh in real_holdings:
            r_ticker = rh.get("ticker", "")
            r_qty = int(rh.get("quantity", 0))
            r_price = float(rh.get("avg_price", 0.0))
            r_name = rh.get("ticker_name", r_ticker)

            if r_qty <= 0:
                continue

            real_ticker_set.add(r_ticker)

            # 해당 티커의 DB 보유 리스트 및 총 수량 계산
            db_hs = db_holdings_by_ticker.get(r_ticker, [])
            db_total_qty = sum(h.quantity for h in db_hs)

            if db_total_qty == r_qty:
                # 수량이 완전히 일치하면 동기화할 필요가 없음
                continue

            if db_total_qty > 0:
                # 수량 불일치 발생 시, 첫 번째 전략의 수량을 차이만큼 가감하여 보정
                diff = r_qty - db_total_qty
                target_db_h = db_hs[0]
                old_qty = target_db_h.quantity
                target_db_h.quantity += diff
                ctx.db.commit()
                log_action(
                    ctx.db,
                    ctx.user_id,
                    f"[Sync Guard] Quantity discrepancy fixed for {r_ticker} ({target_db_h.strategy_type}): {old_qty} -> {target_db_h.quantity} (Total: {r_qty})",
                    "WARNING"
                )
            else:
                # DB에 아예 보유 정보가 없는 경우 (Phantom holding) -> 신규 복구
                last_buy = ctx.db.query(TradeLog).filter(
                    TradeLog.user_id == ctx.user_id,
                    TradeLog.ticker == r_ticker,
                    TradeLog.trade_type == "BUY"
                ).order_by(TradeLog.executed_at.desc()).first()

                target_strategy = last_buy.strategy_type if last_buy else ctx.first_slot_key
                log_action(
                    ctx.db,
                    ctx.user_id,
                    f"[Self-Healing] Phantom holding detected in account: {r_ticker} (Qty: {r_qty}). Restoring DB record under strategy {target_strategy}!",
                    "ERROR"
                )

                ctx.db.add(Holding(
                    user_id=ctx.user_id,
                    ticker=r_ticker,
                    strategy_type=target_strategy,
                    ticker_name=r_name,
                    avg_price=r_price,
                    quantity=r_qty,
                    highest_price=r_price,
                    regime_mode=ctx.sentiment,
                    buy_stage=1
                ))
                ctx.db.commit()

        for db_h in ctx.holdings:
            if db_h.ticker not in real_ticker_set:
                log_action(ctx.db, ctx.user_id, f"[Self-Healing] DB Holding {db_h.ticker} ({db_h.strategy_type}) does not exist in actual broker account. Sweeping legacy DB record.", "ERROR")
                ctx.db.delete(db_h)
                ctx.db.commit()

        ctx.holdings = ctx.db.query(Holding).filter(Holding.user_id == ctx.user_id).all()
    except Exception as sync_err:
        log_action(ctx.db, ctx.user_id, f"[Self-Healing] Failed to sync holding discrepancy: {sync_err}", "ERROR")


async def calculate_slot_allocations(ctx: TradingFlowContext) -> dict:
    balance_data = await safe_broker_call(ctx.broker.get_account_balance, exchange_rate=ctx.exchange_rate)
    total_asset_krw = balance_data.get(
        "total_asset",
        settings.SIMULATED_INITIAL_CASH_KRW,
    )
    cash_balance_krw = balance_data.get(
        "cash_balance",
        settings.SIMULATED_INITIAL_CASH_KRW,
    )
    total_asset_usd = total_asset_krw / ctx.exchange_rate
    cash_balance_usd = cash_balance_krw / ctx.exchange_rate
    return ctx.ms_manager.calculate_slots_allocation(total_asset_usd, cash_balance_usd, ctx.holdings, ctx.sentiment, ctx.session)


async def build_target_signals(ctx: TradingFlowContext) -> list | None:
    target_signals = []
    focused_tickers = ctx.ms_manager.get_focused_tickers(ctx.all_signals)
    for ticker in focused_tickers:
        sig = ctx.signal_map.get(ticker)
        if sig:
            target_signals.append(sig)

    if not target_signals and not ctx.holdings:
        if ctx.session != MarketSession.CLOSED and should_log_with_cooldown(SCANNER_CACHE_EMPTY_LOG_CACHE, ("empty_signals", ctx.user_id), 600.0):
            log_action(
                ctx.db,
                ctx.user_id,
                "[Scanner Cache] No cached signals are available yet. Skipping per-user fallback analysis to prevent duplicate Yahoo Finance calls.",
                "WARNING"
            )
        return None

    return target_signals

async def process_exit_signals(ctx: TradingFlowContext, target_signal_map: dict) -> None:
    if ctx.session == MarketSession.CLOSED:
        if should_log_with_cooldown(MARKET_CLOSED_LOG_CACHE, ("closed_sell", ctx.user_id)):
            log_action(
                ctx.db,
                ctx.user_id,
                "[SELL SKIP] US market is closed. Exit signals will be reevaluated in the next active session.",
                "INFO",
            )
        return

    db = ctx.db
    user_id = ctx.user_id
    holdings = ctx.holdings
    ms_manager = ctx.ms_manager
    broker = ctx.broker
    sentiment = ctx.sentiment
    exchange_rate = ctx.exchange_rate

    sell_tasks_args = []

    # ------------------ (Part A) 매도 조건 판별 및 인텐트 생성 (순차) ------------------
    for h in holdings:
        try:
            slot_key = h.strategy_type
            clean_ticker = h.ticker
            if slot_key not in ms_manager.strategies:
                continue
            strategy_instance = ms_manager.strategies[slot_key]

            current_data = target_signal_map.get(clean_ticker) or ctx.signal_map.get(clean_ticker)
            if not current_data:
                current_data = await analyze_single_ticker(clean_ticker)

            if not current_data:
                log_action(db, user_id, f"No technical data available for owned ticker {clean_ticker}. Skipping monitoring in this cycle.", "WARNING")
                continue

            current_price = current_data['price']
            h.current_price = current_price
            profit_rate = ((current_price - h.avg_price) / h.avg_price) * 100

            current_score = strategy_instance.calculate_score(current_data['details'] or current_data, sentiment, is_entry=False)
            is_smart_exit = current_data.get('details', {}).get('is_smart_exit', False)

            if current_price > h.highest_price:
                h.highest_price = current_price
                log_action(db, user_id, f"[{strategy_instance.name}] New Peak for {clean_ticker}: ${current_price}", "SIGNAL")
                db.commit()

            atr = current_data.get('details', {}).get('atr', 0.0)
            stop_loss_pct = strategy_instance.get_stop_loss_pct(atr, current_price)
            trailing_stop_pct = strategy_instance.get_trailing_stop_pct(atr, current_price)

            sell_reason = None
            is_breached = False
            breach_reason = ""

            if profit_rate <= -stop_loss_pct:
                is_breached = True
                breach_reason = f"동적 손절선 이탈 (손절 기준 -{stop_loss_pct:.2f}% 돌파 | 현재 수익률: {profit_rate:.2f}%)"
            elif current_price <= h.highest_price * (1 - trailing_stop_pct / 100) and h.highest_price > h.avg_price:
                is_breached = True
                breach_reason = f"동적 트레일링 스탑 이탈 (최고가 ${h.highest_price:.2f} 대비 {trailing_stop_pct:.2f}% 하락 | 현재 수익률: {profit_rate:.2f}%)"

            if is_breached:
                cache_key = (user_id, h.ticker, h.strategy_type)
                BREACH_COUNT_CACHE[cache_key] = BREACH_COUNT_CACHE.get(cache_key, 0) + 1
                count = BREACH_COUNT_CACHE[cache_key]

                if count >= 2:
                    sell_reason = breach_reason + " [2회 연속 이탈 확정]"
                else:
                    log_action(db, user_id, f"[Noise Buffer] {h.ticker} ({h.strategy_type}) first breach detected ({breach_reason}). Delaying sell for noise protection (Count: {count}/2).", "INFO")
            else:
                BREACH_COUNT_CACHE.pop((user_id, h.ticker, h.strategy_type), None)

            if not sell_reason and profit_rate >= strategy_instance.min_smart_exit_profit and is_smart_exit:
                sell_reason = f"스마트 조기 익절 (RSI-MACD 조건 충족 | 수익률: {profit_rate:.2f}%)"

            elif not sell_reason and strategy_instance.is_signal_collapsed(current_score, sentiment):
                sell_reason = f"강세 시그널 붕괴 ({current_score}점 도달)"

            if sell_reason:
                log_action(db, user_id, f"[{strategy_instance.name}] EXIT SIGNAL: {h.ticker} | Reason: {sell_reason}", "SIGNAL")

                is_kis_order = (ctx.db_settings.trade_mode or "").upper() in {"MOCK", "REAL"}
                order_intent = None
                if is_kis_order:
                    metadata = await safe_broker_call(broker.get_order_metadata, clean_ticker, ctx.session)
                    order_intent = create_order_intent(
                        db, ctx.db_settings, side="SELL", ticker=clean_ticker,
                        prefixed_ticker=clean_ticker, strategy_type=slot_key, ticker_name=h.ticker_name,
                        requested_qty=h.quantity, submitted_price=current_price,
                        exchange_code=metadata.get("exchange_code"), order_division=metadata.get("order_division"),
                        regime_mode=sentiment, signal_score=current_score, sell_reason=sell_reason,
                    )
                    begin_order_submission(db, order_intent, ctx.db_settings)
                    
                sell_tasks_args.append((h, order_intent, current_price, sell_reason, clean_ticker, strategy_instance, current_score))

        except Exception as item_err:
            log_action(db, user_id, f"Error processing holding {h.ticker}: {item_err}", "ERROR")

    if not sell_tasks_args:
        return

    # ------------------ (Part B) 브로커 비동기 병렬 주문 및 체결 처리 ------------------
    async def _execute_single_sell(h, order_intent, current_price, sell_reason, clean_ticker, strategy_instance, current_score):
        try:
            is_kis_order = (ctx.db_settings.trade_mode or "").upper() in {"MOCK", "REAL"}
            if is_kis_order:
                res = await execute_and_poll_order(
                    broker, broker.sell_order, clean_ticker, h.quantity,
                    price=current_price, session=ctx.session,
                    **({"client_order_id": order_intent.intent_id} if order_intent else {}),
                )
            else:
                res = await safe_broker_call(
                    broker.sell_order, clean_ticker, h.quantity,
                    price=current_price, session=ctx.session,
                    **({"client_order_id": order_intent.intent_id} if order_intent else {}),
                )
        except Exception as exc:
            if not order_intent:
                log_action(db, user_id, f"Error during sell order for {h.ticker}: {exc}", "ERROR")
                return
            res = {
                "success": False, "order_submitted": True, "submission_unknown": True,
                "status": "ACK_UNKNOWN", "order_no": "", "filled_qty": 0, "filled_price": 0.0,
                "fill_confirmed": False, "message": f"Broker acknowledgement unknown: {exc}",
            }

        if order_intent:
            application = finalize_order_submission(db, order_intent, ctx.db_settings, res)
            if application.applied_qty > 0:
                filled_price = application.filled_price
                filled_qty = application.applied_qty
                realized_pnl = application.realized_pnl or 0.0
                calc_return_rate = application.return_rate or 0.0
                remaining_qty = application.remaining_qty or 0
                BREACH_COUNT_CACHE.pop((user_id, h.ticker), None)
                fill_label = "sold" if remaining_qty == 0 else f"partially sold ({filled_qty} filled, {remaining_qty} remaining)"
                log_action(db, user_id, f"SUCCESS: {h.ticker} {fill_label} via {sell_reason} | Order: {res['order_no']}", "INFO")

                filled_price_krw = filled_price * exchange_rate
                total_amount_usd = filled_price * filled_qty
                total_amount_krw = total_amount_usd * exchange_rate
                pnl_sign = "+" if realized_pnl >= 0 else "-"
                pnl_emoji = "📈" if realized_pnl >= 0 else "📉"
                send_message_async(
                    user_id,
                    f"🔴 *[{strategy_instance.name} 자동매도 체결]*\n"
                    f"종목: {clean_ticker} ({h.ticker_name})\n"
                    f"• *체결 단가:* `${filled_price:,.2f}` (약 {filled_price_krw:,.0f}원)\n"
                    f"• *체결 수량:* `{filled_qty}주`\n"
                    f"• *체결 금액:* `${total_amount_usd:,.2f}` (약 {total_amount_krw:,.0f}원)\n"
                    f"• *매도 사유:* {sell_reason}\n\n"
                    f"{pnl_emoji} *실수익률:* `{pnl_sign}{calc_return_rate:.2f}%`\n"
                    f"💰 *실현 실수익:* `{pnl_sign}${abs(realized_pnl):,.2f}`\n"
                    f"• *주문 번호:* `{res['order_no']}`",
                )
            if application.is_unresolved:
                halt_trading_for_order_review(ctx, "SELL", clean_ticker, res)
                return
            if application.applied_qty == 0 and not res.get("success"):
                log_action(db, user_id, f"SELL FAILED: {h.ticker} | {res['message']}", "ERROR")
            return

        requires_review = bool(res.get("order_submitted")) and not bool(res.get("fill_confirmed"))
        if requires_review and res.get("status") != "PARTIAL":
            halt_trading_for_order_review(ctx, "SELL", clean_ticker, res)
            return

        if res["success"]:
            filled_price = res["filled_price"]
            filled_qty = res["filled_qty"]
            if filled_qty <= 0 or filled_qty > h.quantity:
                log_action(db, user_id, f"SELL INVALID FILL: {h.ticker} | {res}", "ERROR")
                halt_trading_for_order_review(ctx, "SELL", clean_ticker, res)
                return

            buy_gross = h.avg_price * filled_qty
            buy_fee = buy_gross * settings.KIS_FEE_RATE
            sell_gross = filled_price * filled_qty
            sell_fee = sell_gross * settings.KIS_FEE_RATE
            sec_fee = sell_gross * settings.SEC_FEE_RATE

            realized_pnl = sell_gross - buy_gross - buy_fee - sell_fee - sec_fee
            calc_return_rate = (realized_pnl / buy_gross) * 100 if buy_gross > 0 else 0.0

            db.add(TradeLog(
                user_id=user_id, ticker=h.ticker, strategy_type=h.strategy_type, ticker_name=h.ticker_name,
                trade_type="SELL", price=filled_price, quantity=filled_qty,
                order_no=res["order_no"], regime_mode=sentiment, signal_score=current_score,
                realized_pnl=round(realized_pnl, 2), return_rate=round(calc_return_rate, 2)
            ))
            is_full_fill = filled_qty >= h.quantity
            if is_full_fill:
                db.delete(h)
            else:
                h.quantity -= filled_qty
            db.commit()
            BREACH_COUNT_CACHE.pop((user_id, h.ticker, h.strategy_type), None)
            fill_label = "sold" if is_full_fill else f"partially sold ({filled_qty} filled, {h.quantity} remaining)"
            log_action(db, user_id, f"SUCCESS: {h.ticker} ({h.strategy_type}) {fill_label} via {sell_reason} | Order: {res['order_no']}", "INFO")

            filled_price_krw = filled_price * exchange_rate
            total_amount_usd = filled_price * filled_qty
            total_amount_krw = total_amount_usd * exchange_rate

            pnl_sign = "+" if realized_pnl >= 0 else "-"
            pnl_emoji = "📈" if realized_pnl >= 0 else "📉"
            realized_pnl_abs = abs(realized_pnl)

            send_message_async(
                user_id,
                f"🔴 *[{strategy_instance.name} 자동매도 체결]*\n"
                f"종목: {clean_ticker} ({h.ticker_name})\n"
                f"• *체결 단가:* `${filled_price:,.2f}` (약 {filled_price_krw:,.0f}원)\n"
                f"• *체결 수량:* `{filled_qty}주`\n"
                f"• *체결 금액:* `${total_amount_usd:,.2f}` (약 {total_amount_krw:,.0f}원)\n"
                f"• *매도 사유:* {sell_reason}\n\n"
                f"{pnl_emoji} *실수익률:* `{pnl_sign}{calc_return_rate:.2f}%`\n"
                f"💰 *실현 실수익:* `{pnl_sign}${realized_pnl_abs:,.2f}`\n"
                f"• *주문 번호:* `{res['order_no']}`"
            )
            if requires_review:
                halt_trading_for_order_review(ctx, "SELL", clean_ticker, res)
                return
        else:
            log_action(db, user_id, f"SELL FAILED: {h.ticker} | {res['message']}", "ERROR")

    # 병렬 대기 및 실행
    tasks = [_execute_single_sell(*args) for args in sell_tasks_args]
    await asyncio.gather(*tasks)

def resolve_entry_stage(ctx: TradingFlowContext, strategy_instance, clean_ticker: str, signal: dict, existing_holding):
    proposed_alloc_factor = 1.0
    next_stage = 3

    if existing_holding:
        pyramid_trigger_1 = strategy_instance.get_pyramid_trigger(1)
        if pyramid_trigger_1 > 100.0 or ctx.sentiment != "BULLISH":
            return None

        buy_stage = existing_holding.buy_stage
        current_price = signal['price']
        profit_rate = ((current_price - existing_holding.avg_price) / existing_holding.avg_price) * 100
        pyramid_trigger_2 = strategy_instance.get_pyramid_trigger(2)

        if buy_stage == 1:
            if profit_rate < pyramid_trigger_1:
                return None
            proposed_alloc_factor = 0.35
            next_stage = 2
            log_action(ctx.db, ctx.user_id, f"[{strategy_instance.name}] [Pyramiding] {clean_ticker} meets 2nd Buy Condition (+{profit_rate:.2f}% profit). Placing 35% confirm order.", "SIGNAL")
        elif buy_stage == 2:
            if profit_rate < pyramid_trigger_2:
                return None
            proposed_alloc_factor = 0.50
            next_stage = 3
            log_action(ctx.db, ctx.user_id, f"[{strategy_instance.name}] [Pyramiding] {clean_ticker} meets 3rd Buy Condition (+{profit_rate:.2f}% profit). Placing 50% ultimate order.", "SIGNAL")
        else:
            return None
    else:
        proposed_alloc_factor = strategy_instance.get_initial_entry_factor(ctx.sentiment)
        if ctx.sentiment == "BULLISH" and proposed_alloc_factor < 1.0:
            next_stage = 1
            log_action(ctx.db, ctx.user_id, f"[{strategy_instance.name}] [New Entry] {clean_ticker} scanned. Placing 15% scout order.", "INFO")
        else:
            next_stage = 3
            log_action(ctx.db, ctx.user_id, f"[{strategy_instance.name}] [New Entry] {clean_ticker} scanned. Placing {proposed_alloc_factor*100:.0f}% single defensive order.", "INFO")

    return proposed_alloc_factor, next_stage


def has_recent_sell(db, user_id: int, ticker: str, strategy_type: str) -> bool:
    cooldown_cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.REENTRY_COOLDOWN_MINUTES)
    recent_sell = db.query(TradeLog).filter(
        TradeLog.user_id == user_id,
        TradeLog.ticker == ticker,
        TradeLog.strategy_type == strategy_type,
        TradeLog.trade_type == "SELL",
        TradeLog.executed_at >= cooldown_cutoff
    ).first()
    return recent_sell is not None


def calculate_entry_quantity(
    strategy_instance,
    signal: dict,
    score: float,
    cutoff_score: float,
    slot_cash_usd: float,
    slot_total_asset_usd: float,
    current_price: float,
    proposed_alloc_factor: float,
) -> tuple[int, float, float]:
    base_alloc_usd = slot_total_asset_usd * strategy_instance.base_allocation_pct
    if strategy_instance.min_allocation_usd > 0.0:
        base_alloc_usd = max(strategy_instance.min_allocation_usd, base_alloc_usd)

    atr = signal.get('details', {}).get('atr', 0.0)
    vol_factor = 1.0
    if atr > 0:
        atr_pct = (atr / current_price) * 100
        if atr_pct > 0:
            vol_factor = max(0.5, min(1.5, 2.0 / atr_pct))

    score_factor = 1.0 + (score - cutoff_score) * 0.05
    proposed_value_usd = base_alloc_usd * vol_factor * score_factor * proposed_alloc_factor
    proposed_qty = proposed_value_usd / current_price

    max_order_budget_usd = slot_cash_usd * 0.95
    final_qty = int(min(proposed_qty, max_order_budget_usd / current_price))

    if final_qty == 0 and max_order_budget_usd >= current_price:
        final_qty = 1

    return final_qty, proposed_qty, proposed_value_usd


def send_entry_budget_warning(
    ctx: TradingFlowContext,
    strategy_instance,
    clean_ticker: str,
    signal: dict,
    strategy_type: str,
    reason_title: str,
    reason_desc: str,
    current_price: float,
    proposed_value_usd: float,
    slot_cash_usd: float,
) -> None:
    log_action(ctx.db, ctx.user_id, f"[{strategy_instance.name}] SKIP PURCHASE ({reason_title}): {clean_ticker}.", "WARNING")

    cache_key = (ctx.user_id, clean_ticker, strategy_type, reason_title)
    now = time.time()
    last_sent = WARNING_COOLDOWN_CACHE.get(cache_key, 0.0)

    if now - last_sent < 3600.0:
        return

    current_price_krw = current_price * ctx.exchange_rate
    send_message_async(
        ctx.user_id,
        f"*[{strategy_instance.name} Auto Buy Skipped - {reason_title}]*\n"
        f"Ticker: {clean_ticker} ({signal['name']})\n\n"
        f"*Current Price:* `${current_price:,.2f}` (KRW {current_price_krw:,.0f})\n"
        f"*Attempted Amount:* `${proposed_value_usd:,.2f}`\n"
        f"*Slot Cash:* `${slot_cash_usd:,.2f}`\n\n"
        f"{reason_desc}"
    )
    WARNING_COOLDOWN_CACHE[cache_key] = now


def record_successful_buy(
    ctx: TradingFlowContext,
    strategy_instance,
    existing_holding,
    ticker: str,
    strategy_type: str,
    signal: dict,
    filled_price: float,
    filled_qty: int,
    next_stage: int,
) -> bool:
    if existing_holding:
        old_qty = existing_holding.quantity
        old_avg = existing_holding.avg_price

        new_qty = old_qty + filled_qty
        new_avg = ((old_avg * old_qty) + (filled_price * filled_qty)) / new_qty

        existing_holding.avg_price = round(new_avg, 4)
        existing_holding.quantity = new_qty
        existing_holding.buy_stage = next_stage
        existing_holding.highest_price = max(existing_holding.highest_price, filled_price)
        ctx.db.commit()
        log_action(ctx.db, ctx.user_id, f"SUCCESS: {ticker} ({strategy_type}) Pyramiding Stage {next_stage} Add-on. New Avg: ${new_avg:.2f}", "INFO")
        return False

    ctx.db.add(Holding(
        user_id=ctx.user_id,
        ticker=ticker,
        strategy_type=strategy_type,
        ticker_name=signal['name'],
        avg_price=filled_price,
        quantity=filled_qty,
        highest_price=filled_price,
        regime_mode=ctx.sentiment,
        buy_stage=next_stage
    ))
    ctx.db.commit()
    log_action(ctx.db, ctx.user_id, f"SUCCESS: {ticker} ({strategy_type}) purchased ({filled_qty} shares)", "INFO")
    return True


def send_successful_buy_message(
    ctx: TradingFlowContext,
    strategy_instance,
    clean_ticker: str,
    signal: dict,
    filled_price: float,
    filled_qty: int,
    next_stage: int,
    order_no: str,
) -> None:
    current_price_krw = filled_price * ctx.exchange_rate
    total_amount_usd = filled_price * filled_qty
    total_amount_krw = total_amount_usd * ctx.exchange_rate

    send_message_async(
        ctx.user_id,
        f"*[{strategy_instance.name} Auto Buy Filled]*\n"
        f"Ticker: {clean_ticker} ({signal['name']})\n\n"
        f"*Filled Price:* `${filled_price:,.2f}` (KRW {current_price_krw:,.0f})\n"
        f"*Filled Qty:* `{filled_qty}` (Pyramiding Stage {next_stage})\n"
        f"*Filled Amount:* `${total_amount_usd:,.2f}` (KRW {total_amount_krw:,.0f})\n"
        f"*Market Regime:* `{ctx.sentiment}`\n"
        f"*Order No:* `{order_no}`"
    )


async def process_entry_signals(ctx: TradingFlowContext, target_signals: list, slot_allocations: dict) -> bool:
    db = ctx.db
    user_id = ctx.user_id
    ms_manager = ctx.ms_manager

    if ctx.session == MarketSession.CLOSED:
        if should_log_with_cooldown(MARKET_CLOSED_LOG_CACHE, ("closed_buy", user_id)):
            log_action(db, user_id, "[BUY SKIP] US market is currently closed. No new buy orders placed.", "INFO")
        return False

    focused_tickers = ms_manager.get_focused_tickers(ctx.all_signals)
    log_action(db, user_id, f"[Focusing Filter] Selected {len(focused_tickers)} elite tickers for compressed investment: {', '.join(focused_tickers)}", "INFO")

    buy_tasks_args = []

    # ------------------ (Part A) 매수 조건 판별 및 인텐트 생성 (순차) ------------------
    for slot_key, slot_info in slot_allocations.items():
        if slot_key == "regime_switching" and ctx.sentiment != "BULLISH":
            log_action(db, user_id, f"[Regime Sluice] Regime Switching V2 slot DEACTIVATED in {ctx.sentiment} market to protect 100% cash.", "INFO")
            continue

        strategy_instance = ms_manager.strategies[slot_key]
        slot_cash_usd = slot_info["cash_balance"]
        slot_total_asset_usd = slot_info["total_asset"]
        slot_holdings_count = db.query(Holding).filter(
            Holding.user_id == user_id,
            Holding.strategy_type == slot_key
        ).count()
        cutoff_score = strategy_instance.get_cutoff_score(ctx.sentiment)

        for signal in target_signals:
            clean_ticker = signal['ticker']
            if clean_ticker not in focused_tickers:
                continue

            score = strategy_instance.calculate_score(signal.get('details') or signal, ctx.sentiment, is_entry=True)
            if score < cutoff_score:
                continue

            if slot_holdings_count >= 3:
                continue

            existing_holding = db.query(Holding).filter(
                Holding.user_id == user_id,
                Holding.ticker == clean_ticker,
                Holding.strategy_type == slot_key
            ).first()

            entry_stage = resolve_entry_stage(ctx, strategy_instance, clean_ticker, signal, existing_holding)
            if entry_stage is None:
                continue
            proposed_alloc_factor, next_stage = entry_stage

            if has_recent_sell(db, user_id, clean_ticker, slot_key):
                continue

            realtime_price = await get_realtime_price(clean_ticker)
            if realtime_price is None:
                continue

            cached_price = signal['price']
            price_drift_pct = (realtime_price - cached_price) / cached_price * 100 if cached_price > 0 else 0
            if price_drift_pct > 20.0:
                log_action(db, user_id, f"[Surge Guard] {clean_ticker} has surged +{price_drift_pct:.1f}% since signal cached. Aborting purchase.", "WARNING")
                continue

            current_price = realtime_price
            if slot_cash_usd < settings.MIN_CASH_BALANCE_USD:
                continue

            final_qty, proposed_qty, proposed_value_usd = calculate_entry_quantity(
                strategy_instance=strategy_instance,
                signal=signal,
                score=score,
                cutoff_score=cutoff_score,
                slot_cash_usd=slot_cash_usd,
                slot_total_asset_usd=slot_total_asset_usd,
                current_price=current_price,
                proposed_alloc_factor=proposed_alloc_factor,
            )

            if final_qty < 1:
                is_budget_exceeded = proposed_qty < 1.0
                reason_title = "Budget exceeded - below minimum quantity" if is_budget_exceeded else "Insufficient cash"
                reason_desc = "Slot cash is not enough for this order." if not is_budget_exceeded else "One share costs more than the slot allocation allows."
                send_entry_budget_warning(
                    ctx=ctx, strategy_instance=strategy_instance, clean_ticker=clean_ticker,
                    signal=signal, strategy_type=slot_key, reason_title=reason_title,
                    reason_desc=reason_desc, current_price=current_price, proposed_value_usd=proposed_value_usd,
                    slot_cash_usd=slot_cash_usd,
                )
                continue

            is_kis_order = (ctx.db_settings.trade_mode or "").upper() in {"MOCK", "REAL"}
            order_intent = None
            if is_kis_order:
                metadata = await safe_broker_call(ctx.broker.get_order_metadata, clean_ticker, ctx.session)
                order_intent = create_order_intent(
                    db, ctx.db_settings, side="BUY", ticker=clean_ticker,
                    prefixed_ticker=clean_ticker, strategy_type=slot_key, ticker_name=signal["name"],
                    requested_qty=final_qty, submitted_price=current_price,
                    exchange_code=metadata.get("exchange_code"), order_division=metadata.get("order_division"),
                    buy_stage=next_stage, regime_mode=ctx.sentiment, signal_score=score,
                )
                begin_order_submission(db, order_intent, ctx.db_settings)

            buy_tasks_args.append((
                clean_ticker, strategy_instance, signal, score, next_stage,
                current_price, final_qty, existing_holding, order_intent, slot_key
            ))
            slot_cash_usd -= (current_price * final_qty) * (1 + settings.KIS_FEE_RATE)
            if not existing_holding:
                slot_holdings_count += 1

    if not buy_tasks_args:
        return True

    # ------------------ (Part B) 브로커 비동기 병렬 주문 및 체결 처리 ------------------
    async def _execute_single_buy(clean_ticker, strategy_instance, signal, score, next_stage, current_price, final_qty, existing_holding, order_intent, slot_key):
        try:
            is_kis_order = (ctx.db_settings.trade_mode or "").upper() in {"MOCK", "REAL"}
            if is_kis_order:
                res = await execute_and_poll_order(
                    ctx.broker, ctx.broker.buy_order, clean_ticker, final_qty,
                    price=current_price, session=ctx.session,
                    **({"client_order_id": order_intent.intent_id} if order_intent else {}),
                )
            else:
                res = await safe_broker_call(
                    ctx.broker.buy_order, clean_ticker, final_qty,
                    price=current_price, session=ctx.session,
                    **({"client_order_id": order_intent.intent_id} if order_intent else {}),
                )
        except Exception as exc:
            if not order_intent:
                log_action(db, user_id, f"Error during buy order for {clean_ticker}: {exc}", "ERROR")
                return False
            res = {
                "success": False, "order_submitted": True, "submission_unknown": True,
                "status": "ACK_UNKNOWN", "order_no": "", "filled_qty": 0, "filled_price": 0.0,
                "fill_confirmed": False, "message": f"Broker acknowledgement unknown: {exc}",
            }

        if order_intent:
            application = finalize_order_submission(db, order_intent, ctx.db_settings, res)
            if application.applied_qty > 0:
                filled_price = application.filled_price
                filled_qty = application.applied_qty
                log_action(db, user_id, f"SUCCESS: {clean_ticker} ({slot_key}) broker fill applied ({filled_qty} shares)", "INFO")
                send_successful_buy_message(
                    ctx=ctx, strategy_instance=strategy_instance, clean_ticker=clean_ticker,
                    signal=signal, filled_price=filled_price, filled_qty=filled_qty,
                    next_stage=next_stage, order_no=res["order_no"],
                )
            if application.is_unresolved:
                halt_trading_for_order_review(ctx, "BUY", clean_ticker, res)
                return False
            if application.applied_qty == 0 and not res.get("success"):
                log_action(db, user_id, f"BUY FAILED: {clean_ticker} ({slot_key}) | {res['message']}", "ERROR")
            return True

        requires_review = bool(res.get("order_submitted")) and not bool(res.get("fill_confirmed"))
        if requires_review and res.get("status") != "PARTIAL":
            halt_trading_for_order_review(ctx, "BUY", clean_ticker, res)
            return False

        if not res["success"]:
            log_action(db, user_id, f"BUY FAILED: {clean_ticker} ({slot_key}) | {res['message']}", "ERROR")
            return True

        filled_price = res["filled_price"]
        filled_qty = res["filled_qty"]

        record_successful_buy(
            ctx=ctx, strategy_instance=strategy_instance, existing_holding=existing_holding,
            ticker=clean_ticker, strategy_type=slot_key, signal=signal, filled_price=filled_price,
            filled_qty=filled_qty, next_stage=next_stage,
        )

        send_successful_buy_message(
            ctx=ctx, strategy_instance=strategy_instance, clean_ticker=clean_ticker,
            signal=signal, filled_price=filled_price, filled_qty=filled_qty,
            next_stage=next_stage, order_no=res["order_no"],
        )
        if requires_review:
            halt_trading_for_order_review(ctx, "BUY", clean_ticker, res)
            return False
            
        return True

    tasks = [_execute_single_buy(*args) for args in buy_tasks_args]
    results = await asyncio.gather(*tasks)

    return all(results)

async def run_user_trading_flow(user_id: int, signal_map: dict, all_signals: list, exchange_rate: float, sentiment: str, session: str):
    """Runs one user's automated trading flow using cycle-level market context."""
    db = SessionLocal()
    try:
        ctx = prepare_trading_flow_context(
            db=db,
            user_id=user_id,
            signal_map=signal_map,
            all_signals=all_signals,
            exchange_rate=exchange_rate,
            sentiment=sentiment,
            session=session,
        )
        if not ctx:
            return

        await sync_broker_holdings(ctx)
        slot_allocations = await calculate_slot_allocations(ctx)
        target_signals = await build_target_signals(ctx)
        if target_signals is None:
            return

        target_signal_map = {s['ticker']: s for s in target_signals}
        await process_exit_signals(ctx, target_signal_map)
        entries_processed = await process_entry_signals(ctx, target_signals, slot_allocations)
        if not entries_processed:
            return

        _user_network_alert_sent.pop(user_id, None)

    except (RequestsRequestException, httpx.RequestError, ConnectionError, socket.gaierror, socket.timeout, TimeoutError, OSError) as ne:
        db.rollback()
        logger.warning(f"[Scheduler Auto-Recovery] Network disruption detected for User {user_id}. DB rolled back. Error: {ne}")

        now = datetime.now()
        last_sent = _user_network_alert_sent.get(user_id)
        if not last_sent or (now - last_sent) > timedelta(minutes=30):
            _user_network_alert_sent[user_id] = now
            send_message_async(
                user_id,
                "⚠️ *[시스템 접속 장애 알림]*\n\n"
                "증권사(KIS) 또는 외부 네트워크 통신에 일시적인 장애가 감지되었습니다.\n"
                "시스템은 자동으로 자가 복구를 시도하며, 연결이 정상화되는 즉시 매매를 재개합니다."
            )
    except Exception as e:
        db.rollback()
        logger.exception(f"[run_user_trading_flow] Error for user {user_id}")
    finally:
        db.close()


async def refresh_scanner_cache():
    """
    마켓 스캐너 캐시를 독립적으로 갱신하는 전용 비동기 함수 (10분 주기).
    자동매매 루프와 완전히 분리되어 Rate Limit 위험 없이 안전하게 동작합니다.
    """
    global latest_scanned_signals, latest_watchlist_signals, _scanner_refresh_in_progress

    with _scanner_refresh_lock:
        if _scanner_refresh_in_progress:
            logger.info("[Scanner Cache] Previous refresh still running. Skipping duplicate refresh.")
            return
        _scanner_refresh_in_progress = True

    try:
        # 장 외 시간 API 비용/호출 낭비 방지 가드
        session = get_market_session()
        if session == MarketSession.CLOSED:
            logger.info("[Scanner Cache] Market is closed. Skipping scan to save API quotas.")
            return

        logger.info("[Scanner Cache] Starting 10-min market scan refresh cycle...")
        signals = await scan_overseas_market()
        latest_scanned_signals = signals
        market_signal_map = {signal["ticker"]: signal for signal in signals}

        db = SessionLocal()
        try:
            active_user_ids = [
                row[0]
                for row in db.query(UserSettings.user_id)
                .filter(UserSettings.is_running == True)
                .all()
            ]
            watchlists_by_user = load_watchlist_tickers_by_user(db, active_user_ids)
        finally:
            db.close()

        watchlist_tickers = set().union(*watchlists_by_user.values()) if watchlists_by_user else set()
        missing_watchlist_tickers = sorted(watchlist_tickers - market_signal_map.keys())
        analyzed = await asyncio.gather(
            *(
                analyze_single_ticker(ticker, bypass_fundamental=True)
                for ticker in missing_watchlist_tickers
            ),
            return_exceptions=True,
        )
        latest_watchlist_signals = {
            ticker: signal
            for ticker, signal in zip(missing_watchlist_tickers, analyzed)
            if isinstance(signal, dict)
        }
        logger.info(
            "[Scanner Cache] Refresh complete. Cached %s market signals and %s isolated watchlist signals.",
            len(signals),
            len(latest_watchlist_signals),
        )
    except Exception as e:
        logger.exception("[Scanner Cache] ERROR during market scan")
    finally:
        with _scanner_refresh_lock:
            _scanner_refresh_in_progress = False

def scanner_cache_wrapper():
    """스캐너 캐시 갱신용 동기 래퍼 (APScheduler 호출용)"""
    try:
        asyncio.run(refresh_scanner_cache())
    except RuntimeError:
        # 💡 이미 실행 중인 이벤트 루프가 있는 경우 (FastAPI/uvicorn 내부 등)
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(refresh_scanner_cache())
        else:
            loop.run_until_complete(refresh_scanner_cache())

async def async_trading_loop():
    """
    3-Mode 통합 자율 트레이딩 루프 (멀티유저 동시 기동 지원).
    스캔은 별도 10분 주기 잡에서 수행되며, 여기서는 캐시된 시그널만 사용합니다.
    """
    global is_processing
    with _processing_lock:
        if is_processing:
            logger.info("[Scheduler] Previous loop still running. Skipping this cycle.")
            return
        is_processing = True
    db = SessionLocal()
    try:
        # 1. 자동매매 기동 중인 활성 유저 리스트 로드
        active_users = db.query(UserSettings).filter(UserSettings.is_running == True).all()
        if not active_users:
            is_processing = False
            return

        active_user_ids = [u.user_id for u in active_users]
        holding_user_ids = {
            row[0]
            for row in db.query(Holding.user_id)
            .filter(Holding.user_id.in_(active_user_ids))
            .distinct()
            .all()
        }

        session = get_market_session()
        if session == MarketSession.CLOSED:
            if not holding_user_ids:
                if should_log_with_cooldown(MARKET_CLOSED_LOG_CACHE, "scheduler_closed_no_holdings"):
                    logger.info("[Scheduler] Market is closed and no active users have holdings. Skipping all user flows.")
                return
        exchange_rate = FXRateCache.get_rate()

        sentiment = await check_market_sentiment()
        market_signals = latest_scanned_signals
        watchlists_by_user = load_watchlist_tickers_by_user(db, active_user_ids)

        # 3. 각 활성 유저별 자동매매 시나리오 병렬 실행
        tasks = []
        for user in active_users:
            signal_map, all_signals = build_user_signal_context(
                user.user_id,
                market_signals,
                watchlists_by_user,
                latest_watchlist_signals,
            )
            tasks.append(
                run_user_trading_flow(
                    user.user_id,
                    signal_map,
                    all_signals,
                    exchange_rate,
                    sentiment,
                    session,
                )
            )
        await asyncio.gather(*tasks)

    except Exception as e:
        db.rollback()
        logger.exception("[Scheduler] CRITICAL ERROR in trading loop")
    finally:
        is_processing = False
        db.close()

def trading_loop_wrapper():
    try:
        asyncio.run(async_trading_loop())
    except RuntimeError:
        # 💡 이미 실행 중인 이벤트 루프가 있는 경우 (FastAPI/uvicorn 내부 등)
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(async_trading_loop())
        else:
            loop.run_until_complete(async_trading_loop())


def reconcile_open_orders_wrapper():
    reconcile_open_orders_once()


def discover_orphan_orders_wrapper():
    discover_orphan_orders_once()

async def admin_balance_cache_sync():
    """
    1분 단위로 모든 관리대상 유저의 잔고를 백그라운드에서 조회하여 
    AccountEquitySnapshot을 갱신합니다. 
    """
    db = SessionLocal()
    try:
        users = db.query(User).all()
        exchange_rate = FXRateCache.get_rate()
        
        for user in users:
            settings = user.settings
            if not settings:
                continue
            is_simulated = settings.trade_mode == "SIMULATED"
            has_verified_cred = False
            if not is_simulated and settings.broker_provider:
                for cred in settings.credentials:
                    if cred.broker_name == settings.broker_provider and cred.verification_status == "verified":
                        has_verified_cred = True
                        break
            
            if is_simulated or has_verified_cred:
                broker = get_broker_client(settings)
                try:
                    balance = await safe_broker_call(broker.get_account_balance)
                    if not isinstance(balance, dict):
                        continue
                    total_asset = balance.get("total_asset")
                    if total_asset is None or not math.isfinite(float(total_asset)):
                        continue
                    profit_rate = float(balance.get("profit_rate", 0.0))
                    
                    captured_at = utc_now_aware()
                    latest_snapshot = (
                        db.query(AccountEquitySnapshot)
                        .filter(
                            AccountEquitySnapshot.user_id == user.id,
                            AccountEquitySnapshot.trade_mode == settings.trade_mode,
                        )
                        .order_by(AccountEquitySnapshot.captured_at.desc())
                        .first()
                    )
                    should_record = (
                        latest_snapshot is None
                        or (captured_at - latest_snapshot.captured_at).total_seconds() >= 60
                    )
                    if should_record:
                        db.add(AccountEquitySnapshot(
                            user_id=user.id,
                            total_asset=float(total_asset),
                            cash_balance=balance.get("cash_balance"),
                            stock_balance=balance.get("stock_balance"),
                            profit_rate=profit_rate,
                            fx_rate=balance.get("fx_rate", exchange_rate),
                            trade_mode=settings.trade_mode,
                            captured_at=captured_at,
                        ))
                        db.flush()
                        
                        expired_snapshots = (
                            db.query(AccountEquitySnapshot)
                            .filter(
                                AccountEquitySnapshot.user_id == user.id,
                                AccountEquitySnapshot.trade_mode == settings.trade_mode,
                            )
                            .order_by(AccountEquitySnapshot.captured_at.desc())
                            .offset(500)
                            .all()
                        )
                        for expired_snapshot in expired_snapshots:
                            db.delete(expired_snapshot)
                        db.commit()
                except Exception as e:
                    logger.warning(f"[Admin Cache Sync] Error for user {user.username}: {e}")
                    db.rollback()
    except Exception as e:
        logger.exception("[Admin Cache Sync] CRITICAL ERROR")
    finally:
        db.close()

def admin_balance_cache_wrapper():
    try:
        asyncio.run(admin_balance_cache_sync())
    except RuntimeError:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(admin_balance_cache_sync())
        else:
            loop.run_until_complete(admin_balance_cache_sync())

def start_scheduler():
    if not scheduler.running:
        # ① 시장 개요 캐시 갱신: 1분 주기 (헤더 API는 캐시만 즉시 반환)
        scheduler.add_job(market_overview_cache_wrapper, 'interval', minutes=1, id='market_overview_cache_job', next_run_time=datetime.now())
        # ② 스윙 예측 캐시 갱신: 서버 시작 시 1회 + 매일 08:00 KST 1회
        scheduler.add_job(swing_prediction_cache_wrapper, 'date', id='swing_prediction_startup_job', run_date=datetime.now())
        scheduler.add_job(swing_prediction_cache_wrapper, 'cron', hour=8, minute=0, id='swing_prediction_daily_job')
        # ③ 스캐너 캐시 갱신: 10분 주기 (yfinance 대규모 API 호출 - Rate Limit 안전)
        scheduler.add_job(scanner_cache_wrapper, 'interval', minutes=10, id='scanner_cache_job', next_run_time=datetime.now())
        # ④ 자동매매 루프: 1분 주기 (캐시된 시그널로 봇 실행 사용자 처리)
        scheduler.add_job(trading_loop_wrapper, 'interval', minutes=1, id='main_trade_job', next_run_time=datetime.now() + timedelta(seconds=20))
        # ⑤ 주문 응답 저장 전 장애로 남은 고아 주문 탐색: 1분 주기
        scheduler.add_job(
            discover_orphan_orders_wrapper,
            'interval',
            minutes=1,
            id='orphan_order_discovery_job',
            next_run_time=datetime.now() + timedelta(seconds=2),
            max_instances=1,
            coalesce=True,
        )
        # ⑥ 미해결 증권사 주문 재조정: 30초 주기, 중복 실행 금지
        scheduler.add_job(
            reconcile_open_orders_wrapper,
            'interval',
            seconds=30,
            id='broker_order_reconciliation_job',
            next_run_time=datetime.now() + timedelta(seconds=5),
            max_instances=1,
            coalesce=True,
        )
        # ⑦ 텔레그램 일일 리포트 발송: 매일 한국시간 17:10 (미국장 마감 직후)
        scheduler.add_job(send_daily_report_to_all_users_sync, 'cron', hour=17, minute=10, id='daily_telegram_report_job')
        # ⑧ 관리자용 1분 단위 모든 유저 잔고 스냅샷 캐싱: 1분 주기
        scheduler.add_job(admin_balance_cache_wrapper, 'interval', minutes=1, id='admin_balance_cache_job', next_run_time=datetime.now() + timedelta(seconds=10))
        scheduler.start()
        print("[Scheduler] APScheduler Background Trading Engine Started.")
        logger.info("Background scheduler started (Multi-tenant 3-Mode Unified Engine).")

def stop_scheduler():
    """앱 종료 시 백그라운드 스레드를 깔끔하게 종료하여 좀비 폴링 방지"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        print("[Scheduler] APScheduler Background Trading Engine Stopped.")
