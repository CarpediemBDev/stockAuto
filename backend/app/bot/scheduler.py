from apscheduler.schedulers.background import BackgroundScheduler
from app.bot.broker_factory import get_broker_client
from app.core.database import SessionLocal
from sqlalchemy.orm import selectinload
from app.watchlist.services import load_watchlist_tickers_by_user, load_all_watchlist_tickers_by_user
from app.core.locks import (
    RedisLockUnavailable,
    acquire_symbol_order_lock,
    acquire_user_operation_lock,
)
from app.core.models import TradeLog, Holding, ActionLog, UserSettings, WatchList, User, AccountEquitySnapshot, UnfilledOrder
from datetime import datetime, timezone, timedelta
from decimal import Decimal
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
from app.bot.trade_calculations import (
    calculate_avg_price,
    calculate_buy_total,
    calculate_profit_rate,
    calculate_realized_pnl,
    check_stop_loss_breach,
    check_trailing_stop_breach,
    fee_rate_for_trade_mode,
    to_decimal,
)
from app.bot.order_discovery import discover_orphan_orders_once
import time
from uuid import uuid4
import math
from app.core.models import utc_now_aware
from contextlib import contextmanager
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
_breach_count_lock = threading.Lock()

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


def _schedule_background_task(coro, task_name: str):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()

    def _log_task_result(done) -> None:
        try:
            done.result()
        except asyncio.CancelledError:
            logger.info("[Scheduler] Background task %s was cancelled.", task_name)
        except Exception:
            logger.exception("[Scheduler] Background task %s failed.", task_name)

    if loop.is_running():
        # 메인 루프 스레드 외의 동기 스레드에서 안전하게 전송
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        fut.add_done_callback(_log_task_result)
        return fut
    else:
        # 루프가 돌고 있지 않은 독립 스레드인 경우
        task = asyncio.ensure_future(coro, loop=loop)
        task.add_done_callback(_log_task_result)
        return task



async def execute_and_poll_order(broker, func, *args, lease=None, **kwargs):
    """
    주문을 비동기로 발송하고 즉시 반환(skip_poll=True)받은 뒤,
    비동기 타이머(await asyncio.sleep)를 활용하여 체결 상태를 폴링합니다.
    다른 유저들의 주문 처리를 전혀 블로킹하지 않습니다.
    """
    kwargs["skip_poll"] = True
    res = await safe_broker_call(func, *args, **kwargs)

    if res.get("status") == "PENDING" and res.get("order_no"):
        order_no = res["order_no"]
        original_order_no = order_no
        quantity = kwargs.get("quantity") or (args[1] if len(args) > 1 else 0)
        price = kwargs.get("price") or (args[2] if len(args) > 2 else 0.0)
        ticker = args[0] if len(args) > 0 else ""
        side = "BUY" if "buy" in func.__name__.lower() else "SELL"

        is_kis = type(broker).__name__ == "KISBroker"

        filled_qty = 0
        filled_price = 0.0
        fill_confirmed = False

        # KIS의 경우 30초(15회 x 2초) 동안 폴링 후 미체결 시 호가 정정
        max_attempts = 15 if is_kis else 5

        original_filled_qty = 0
        original_filled_val = 0.0
        order_modified = False

        attempt = 1
        while attempt <= max_attempts:
            if lease and getattr(lease, "lost_ownership", False):
                logger.error(f"[Order Guard] Lock lease {lease.key} ownership lost (CRITICAL_LOST) during order polling. Aborting.")
                res["status"] = "ERROR"
                res["message"] = "Lock lease ownership lost (CRITICAL_LOST) during order polling"
                res["success"] = False
                break

            await asyncio.sleep(2.0)
            status_res = await safe_broker_call(broker.check_order_status, order_no)
            status_code = status_res.get("status")
            curr_filled = status_res.get("filled_qty", 0)

            if status_code == "FILLED":
                filled_qty = curr_filled
                filled_price = status_res.get("filled_price", price)
                fill_confirmed = True
                break
            elif status_code == "PARTIAL":
                filled_qty = curr_filled
                filled_price = status_res.get("filled_price", price)
                fill_confirmed = False
            elif status_code == "ERROR":
                break

            # KIS이고 30초가 지났으며 정정한 적이 없고 아직 미체결 잔여 수량이 남았을 때 호가 정정
            if is_kis and attempt == max_attempts and not order_modified and filled_qty < quantity:
                unfilled_qty = quantity - filled_qty
                if unfilled_qty > 0:
                    live_price = None
                    try:
                        from app.scanner.data_provider import fetch_ohlcv
                        df = await asyncio.to_thread(fetch_ohlcv, ticker, "1m", "1d")
                        if df is not None and not df.empty:
                            close_column = "Close" if "Close" in df.columns else "close" if "close" in df.columns else None
                            if close_column:
                                live_price = float(df[close_column].iloc[-1])
                    except Exception as exc:
                        logger.warning(f"[Order Guard] Failed to fetch live price for KIS order modification: {exc}")

                    target_price = live_price if live_price else price
                    logger.info(f"[Order Guard] KIS order {order_no} ({side}) unfilled after 30s. Modifying remaining {unfilled_qty} shares to {target_price}")

                    modify_res = await safe_broker_call(
                        broker.modify_order,
                        ticker=ticker,
                        original_order_no=order_no,
                        quantity=unfilled_qty,
                        price=target_price,
                    )
                    if modify_res.get("success") and modify_res.get("order_no"):
                        original_filled_qty = filled_qty
                        original_filled_val = filled_qty * filled_price

                        order_no = modify_res["order_no"]
                        res["original_order_no"] = original_order_no
                        res["order_no"] = order_no
                        res["modified_order_no"] = order_no
                        order_modified = True
                        attempt = 1
                        max_attempts = 15
                        filled_qty = 0
                        filled_price = 0.0
                        continue

            attempt += 1

        if order_modified:
            total_filled_qty = original_filled_qty + filled_qty
            if total_filled_qty > 0:
                avg_filled_price = (original_filled_val + (filled_qty * filled_price)) / total_filled_qty
                res["filled_qty"] = total_filled_qty
                res["filled_price"] = avg_filled_price
                res["success"] = True
                res["fill_confirmed"] = fill_confirmed
                if total_filled_qty >= quantity:
                    res["status"] = "FILLED"
                    res["fill_confirmed"] = True
                else:
                    res["status"] = "PARTIAL"
                    res["fill_confirmed"] = False
            else:
                res["filled_qty"] = 0
                res["filled_price"] = 0.0
                res["success"] = False
                res["fill_confirmed"] = False
                res["status"] = "PENDING"
        else:
            if filled_qty > 0:
                res["filled_qty"] = filled_qty
                res["filled_price"] = filled_price
                res["success"] = True
                res["fill_confirmed"] = fill_confirmed
                if filled_qty >= quantity:
                    res["status"] = "FILLED"
                    res["fill_confirmed"] = True
                else:
                    res["status"] = "PARTIAL"
                    res["fill_confirmed"] = False
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
    status = order_result.get("status", "UNCONFIRMED")
    order_no = order_result.get("order_no", "")
    message = (
        f"[ORDER RECONCILIATION] {side} order for {ticker} is {status}. "
        f"New trading cycles are blocked while the order ledger retries reconciliation. "
        f"Order: {order_no or 'UNKNOWN'}"
    )
    with micro_session(ctx) as db:
        log_action(db, ctx.user_id, message, "ERROR")
    send_message_async(
        ctx.user_id,
        f"*Order Reconciliation Required*\n"
        f"Side: `{side}`\n"
        f"Ticker: `{ticker}`\n"
        f"Status: `{status}`\n"
        f"Order No: `{order_no or 'UNKNOWN'}`\n\n"
        "The system will keep checking the broker. Your bot start/stop preference will not be changed."
    )


@dataclass
class TradingFlowContext:
    db: object
    user_id: int
    db_settings: UserSettings
    trade_mode: str
    session: str
    sentiment: str
    exchange_rate: float
    holdings: list
    broker: object
    ms_manager: object
    first_slot_key: str
    signal_map: dict
    all_signals: list

from contextlib import contextmanager
@contextmanager
def micro_session(ctx: TradingFlowContext):
    """
    Micro-Session Pattern:
    증권사 API 네트워크 대기 시간 동안 DB 커넥션을 점유하지 않도록,
    DB 접근이 필요한 찰나의 순간(0.01초)에만 커넥션을 풀에서 빌려오고 즉시 반납합니다.
    """
    db = SessionLocal()
    # 커밋 후에도 ctx.db_settings/holdings의 속성값을 세션 밖(Detached)에서 계속 읽어야 한다.
    # 기본값(expire_on_commit=True)이면 커밋 시 병합 인스턴스가 만료되고, expunge/close 이후
    # 접근 시 refresh를 시도하다 DetachedInstanceError로 사이클이 침묵 실패한다.
    # ※ 과거 이 옵션이 version_id 낙관적 잠금과 겹쳐 StaleDataError를 유발했던 원인(재진입 auto-merge가
    #   dirty holding을 flush하며 version을 올림)은 아래 load=False 병합과 process_exit_signals의 관측값
    #   로컬화로 제거됐다. 따라서 expire_on_commit=False를 안전하게 유지한다.
    #   추가 방어: 세션 밖에서 읽는 스칼라(trade_mode)는 ctx에 값 스냅샷으로도 떠 둔다.
    db.expire_on_commit = False
    old_db = getattr(ctx, "db", None)
    ctx.db = db
    try:
        if not hasattr(db, "commit_count"):
            if hasattr(ctx, "db_settings") and ctx.db_settings:
                ctx.db_settings = db.merge(ctx.db_settings)
            if hasattr(ctx, "holdings") and ctx.holdings:
                # load=False로 병합한다: DB를 다시 읽지 않고 detached holding을 그대로 "영속(clean)"으로
                # 세션에 붙인다. 기본값(load=True)은 재진입마다 DB를 읽어 재조정하는데, process_exit_signals가
                # last_price/highest_price를 version 비간섭 Core UPDATE로 DB에만 반영해 두면 세션 밖 holding의
                # 매핑 컬럼값이 DB와 어긋난 상태가 되고, 다음 auto-merge가 이 diff를 flush하며 (1) Core UPDATE로
                # 쓴 값을 되돌리고 (2) version_id를 1→2로 올려 Part B 매도의 db.merge(h)를 StaleDataError로
                # 죽인다. load=False는 이 재조정 flush를 원천 제거한다. 병합 이후 객체에 가한 실제 변경
                # (sync guard의 quantity 증감·delete 등)은 그대로 dirty 추적·flush되어 정상 영속된다.
                ctx.holdings = [db.merge(h, load=False) for h in ctx.holdings]
        yield db
    except Exception as e:
        db.rollback()  # 💡 예외 발생 시 트랜잭션 롤백 및 커넥션 오염 방지
        raise e
    finally:
        if hasattr(db, "expunge_all"):
            db.expunge_all()
        db.close()
        ctx.db = old_db


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
        log_action(
            db,
            user_id,
            "[ORDER GUARD] This cycle was skipped because an unresolved broker order exists.",
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

    # 세션이 살아있는 지금 trade_mode를 평범한 문자열 값으로 스냅샷한다.
    # (log_action 커밋으로 만료됐어도 이 접근이 전체 행을 refresh시켜 이후 merge 경로도 안전해진다.)
    trade_mode = (db_settings.trade_mode or "SIMULATED")

    broker = get_broker_client(db_settings)

    from app.bot.multi_strategy_manager import MultiStrategyManager
    strategy_type = getattr(db_settings, "strategy_type", "regime_switching")
    ms_manager = MultiStrategyManager(strategy_type=strategy_type)
    first_slot_key = list(ms_manager.SLOTS.keys())[0]

    return TradingFlowContext(
        db=db,
        user_id=user_id,
        db_settings=db_settings,
        trade_mode=trade_mode,
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
    request_id = str(uuid4())
    lease = await acquire_user_operation_lock(ctx.user_id, request_id, ttl_seconds=60)
    if lease is None:
        with micro_session(ctx) as db:
            log_action(db, ctx.user_id, "[Sync Guard] Skipped sync due to lock unavailability.", "WARNING")
        return

    try:
        real_holdings = await safe_broker_call(ctx.broker.get_holdings, exchange_rate=ctx.exchange_rate)

        with micro_session(ctx) as db:
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

                db_hs = db_holdings_by_ticker.get(r_ticker, [])
                db_total_qty = sum(h.quantity for h in db_hs)

                if db_total_qty == r_qty:
                    continue

                if db_total_qty > 0:
                    diff = r_qty - db_total_qty
                    if diff > 0:
                        target_db_h = db_hs[0]
                        old_qty = target_db_h.quantity
                        target_db_h.quantity += diff
                        db.commit()
                        log_action(
                            db,
                            ctx.user_id,
                            f"[Sync Guard] Quantity increased for {r_ticker} ({target_db_h.strategy_type}): {old_qty} -> {target_db_h.quantity} (Total: {r_qty})",
                            "WARNING"
                        )
                    elif diff < 0:
                        remaining_deduction = abs(diff)
                        for h in db_hs:
                            if remaining_deduction <= 0:
                                break
                            deduct = min(h.quantity, remaining_deduction)
                            if deduct > 0:
                                old_qty = h.quantity
                                h.quantity -= deduct
                                remaining_deduction -= deduct
                                log_action(
                                    db,
                                    ctx.user_id,
                                    f"[Sync Guard] Quantity deducted for {r_ticker} ({h.strategy_type}): {old_qty} -> {h.quantity} (Deducted: {deduct})",
                                    "WARNING"
                                )
                                if h.quantity == 0:
                                    db.delete(h)
                        db.commit()
                else:
                    last_buy = db.query(TradeLog).filter(
                        TradeLog.user_id == ctx.user_id,
                        TradeLog.ticker == r_ticker,
                        TradeLog.trade_type == "BUY"
                    ).order_by(TradeLog.executed_at.desc()).first()

                    target_strategy = last_buy.strategy_type if last_buy else ctx.first_slot_key
                    log_action(
                        db,
                        ctx.user_id,
                        f"[Self-Healing] Phantom holding detected in account: {r_ticker} (Qty: {r_qty}). Restoring DB record under strategy {target_strategy}!",
                        "ERROR"
                    )

                    db.add(Holding(
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
                    db.commit()

            for db_h in ctx.holdings:
                if db_h.ticker not in real_ticker_set:
                    log_action(db, ctx.user_id, f"[Self-Healing] DB Holding {db_h.ticker} ({db_h.strategy_type}) does not exist in actual broker account. Sweeping legacy DB record.", "ERROR")
                    db.delete(db_h)
                    db.commit()

            ctx.holdings = db.query(Holding).filter(Holding.user_id == ctx.user_id).all()
    except Exception as sync_err:
        with micro_session(ctx) as db:
            log_action(db, ctx.user_id, f"[Self-Healing] Failed to sync holding discrepancy: {sync_err}", "ERROR")
    finally:
        await lease.release()


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
            with micro_session(ctx) as db:
                log_action(
                    db,
                    ctx.user_id,
                    "[Scanner Cache] No cached signals are available yet. Skipping per-user fallback analysis to prevent duplicate Yahoo Finance calls.",
                    "WARNING"
                )
        return None

    return target_signals


async def process_autonomous_slots(ctx: TradingFlowContext, slot_allocations: dict) -> None:
    """자율 슬롯(지수 레버리지 레짐 계열) 전용 집행 경로.

    스캐너 시그널·손절/트레일링 파이프라인과 무관하게, 신호 지수(QQQ)의 '완결 일봉'
    레짐(SMA 위/아래 N일 연속 확정)으로 목표 상태(IN=보유/OUT=현금)를 판정하고
    현재 보유 상태와 다를 때만 정규장에서 슬롯 현금 전액 매수 또는 전량 매도합니다.
    상태가 일치하면 무매매(멱등)이므로 1분 주기 호출에도 과매매가 발생하지 않습니다.
    주문 인텐트 원장(KIS 경로)이 배선되지 않았으므로 SIMULATED 모드에서만 집행합니다.
    """
    user_id = ctx.user_id

    def _log(msg, level="INFO"):
        with micro_session(ctx) as db:
            log_action(db, user_id, msg, level)

    if not any(
        getattr(s, "is_autonomous", False)
        for s in ctx.ms_manager.strategies.values()
    ):
        return

    # 선행 단계의 micro_session 커밋으로 ORM 객체 속성이 만료(Detached)될 수 있으므로,
    # 필요한 상태를 세션 안에서 평범한 값(스냅샷)으로 떠서 세션 밖에서는 ORM을 만지지 않는다.
    with micro_session(ctx) as db:
        trade_mode = ((ctx.db_settings.trade_mode if ctx.db_settings else None) or "SIMULATED").upper()
        holdings_snapshot = [
            {
                "id": h.id,
                "ticker": h.ticker,
                "strategy_type": h.strategy_type,
                "quantity": int(h.quantity or 0),
                "avg_price": h.avg_price,
                "ticker_name": h.ticker_name,
            }
            for h in db.query(Holding).filter(Holding.user_id == user_id).all()
        ]

    for slot_key, slot_info in slot_allocations.items():
        strategy = ctx.ms_manager.strategies.get(slot_key)
        if not strategy or not getattr(strategy, "is_autonomous", False):
            continue

        if trade_mode != "SIMULATED":
            if should_log_with_cooldown(MARKET_CLOSED_LOG_CACHE, ("autonomous_mode_guard", user_id, slot_key)):
                _log(
                    f"[{strategy.name}] Autonomous slot is SIMULATED-only (order-intent ledger not wired). "
                    f"Skipping in {trade_mode} mode.",
                    "WARNING",
                )
            continue

        asset = strategy.asset_ticker
        holding = next(
            (h for h in holdings_snapshot if h["strategy_type"] == slot_key and h["ticker"] == asset),
            None,
        )

        # 1) 레짐 판정 — 완결 일봉만 사용 (당일 미완결 봉 제거로 룩어헤드 차단)
        try:
            df = await fetch_ohlcv(strategy.signal_ticker, interval="1d", period="2y")
        except Exception as fetch_err:
            _log(f"[{strategy.name}] Failed to fetch daily bars for {strategy.signal_ticker}: {fetch_err}", "WARNING")
            continue
        if df is None or df.empty or "Close" not in df.columns:
            _log(f"[{strategy.name}] Daily bars unavailable for {strategy.signal_ticker}. Skipping this cycle.", "WARNING")
            continue

        closes = df["Close"].dropna()
        try:
            last_bar_date = closes.index[-1].date()
            if ctx.session != MarketSession.CLOSED and last_bar_date >= datetime.now(tz=ET).date():
                closes = closes.iloc[:-1]
        except (AttributeError, TypeError):
            pass

        target = strategy.compute_target_state(closes)
        regime_label = "BULLISH" if target == "IN" else "BEARISH"

        # 상태 정합 → 무매매 (멱등 가드)
        if (target == "IN") == (holding is not None):
            continue

        # 2) 체결은 정규장에서만 — 백테스트(신호 익일 체결)와 등가 규율
        if ctx.session != MarketSession.REGULAR:
            if should_log_with_cooldown(MARKET_CLOSED_LOG_CACHE, ("autonomous_wait_regular", user_id, slot_key)):
                _log(f"[{strategy.name}] Regime target={target} pending. Awaiting REGULAR session to execute.", "INFO")
            continue

        # 3) 동일 슬롯 미체결 가상 주문이 남아 있으면 중복 발주 금지
        with micro_session(ctx) as db:
            pending_order = db.query(UnfilledOrder).filter(
                UnfilledOrder.user_id == user_id,
                UnfilledOrder.ticker == asset,
                UnfilledOrder.strategy_type == slot_key,
            ).first()
            if pending_order is not None:
                db.expunge(pending_order)
        if pending_order is not None:
            continue

        live_price = await get_realtime_price(asset)
        if live_price is None or live_price <= 0:
            _log(f"[{strategy.name}] Live price unavailable for {asset}. Skipping this cycle.", "WARNING")
            continue

        request_id = str(uuid4())
        try:
            symbol_lease = await acquire_symbol_order_lock(user_id, asset, request_id)
        except RedisLockUnavailable:
            _log(f"[{strategy.name}] ORDER BLOCKED: Redis order lock unavailable for {asset}.", "ERROR")
            continue
        if symbol_lease is None:
            continue

        try:
            fee_rate = fee_rate_for_trade_mode(trade_mode)
            if target == "IN":
                slot_cash_usd = float(slot_info.get("cash_balance", 0.0))
                budget_usd = slot_cash_usd * 0.98
                qty = int(budget_usd / (live_price * (1.0 + float(fee_rate))))
                if qty < 1:
                    if should_log_with_cooldown(WARNING_COOLDOWN_CACHE, ("autonomous_budget", user_id, slot_key), 3600.0):
                        _log(
                            f"[{strategy.name}] Slot cash ${slot_cash_usd:,.2f} cannot afford 1 share of {asset} (${live_price:,.2f}).",
                            "WARNING",
                        )
                    continue

                _log(f"[{strategy.name}] REGIME ENTRY: {asset} x{qty} @ ~${live_price:,.2f} (target={target})", "SIGNAL")
                res = await safe_broker_call(
                    ctx.broker.buy_order, asset, qty,
                    price=live_price * 1.001, session=ctx.session,
                    strategy_type=slot_key, regime_mode=regime_label,
                )
                if res.get("success") and res.get("filled_qty", 0) > 0:
                    record_successful_buy(
                        ctx=ctx, strategy_instance=strategy, existing_holding=None,
                        ticker=asset, strategy_type=slot_key,
                        signal={"name": asset}, filled_price=res["filled_price"],
                        filled_qty=res["filled_qty"], next_stage=3,
                        order_no=res["order_no"], current_score=0,
                    )
                    send_successful_buy_message(
                        ctx=ctx, strategy_instance=strategy, clean_ticker=asset,
                        signal={"name": asset}, filled_price=res["filled_price"],
                        filled_qty=res["filled_qty"], next_stage=3, order_no=res["order_no"],
                    )
                elif res.get("success"):
                    _log(f"[{strategy.name}] BUY order submitted (pending fill): {asset} x{qty} | {res.get('order_no', '')}", "INFO")
                else:
                    _log(f"[{strategy.name}] BUY FAILED: {asset} | {res.get('message', '')}", "ERROR")
            else:
                sell_qty = int(holding["quantity"] or 0)
                if sell_qty <= 0:
                    continue

                _log(f"[{strategy.name}] REGIME EXIT: {asset} x{sell_qty} @ ~${live_price:,.2f} → 현금 대피 (target={target})", "SIGNAL")
                res = await safe_broker_call(
                    ctx.broker.sell_order, asset, sell_qty,
                    price=live_price * 0.999, session=ctx.session,
                    strategy_type=slot_key, regime_mode=regime_label,
                )
                if res.get("success") and res.get("filled_qty", 0) > 0:
                    filled_qty = res["filled_qty"]
                    filled_price = res["filled_price"]
                    pnl = calculate_realized_pnl(
                        avg_price=holding["avg_price"],
                        filled_price=filled_price,
                        quantity=filled_qty,
                        fee_rate=fee_rate,
                    )
                    with micro_session(ctx) as db:
                        h_db = db.query(Holding).filter(Holding.id == holding["id"]).first()
                        db.add(TradeLog(
                            user_id=user_id, ticker=asset, strategy_type=slot_key,
                            ticker_name=holding["ticker_name"] or asset,
                            trade_type="SELL", price=filled_price, quantity=filled_qty,
                            order_no=res["order_no"], regime_mode=regime_label, signal_score=0,
                            realized_pnl=pnl.realized_pnl, return_rate=pnl.return_rate,
                        ))
                        if h_db is not None:
                            if filled_qty >= (h_db.quantity or 0):
                                db.delete(h_db)
                            else:
                                h_db.quantity -= filled_qty
                        db.commit()
                        log_action(db, user_id, f"[{strategy.name}] SUCCESS: {asset} regime exit ({filled_qty} shares) | Order: {res['order_no']}", "INFO")

                    realized_pnl = float(pnl.realized_pnl)
                    pnl_sign = "+" if realized_pnl >= 0 else "-"
                    pnl_emoji = "📈" if realized_pnl >= 0 else "📉"
                    send_message_async(
                        user_id,
                        f"🔴 *[{strategy.name} 레짐 이탈 자동매도]*\n"
                        f"종목: {asset}\n"
                        f"• *체결 단가:* `${filled_price:,.2f}`\n"
                        f"• *체결 수량:* `{filled_qty}주`\n"
                        f"• *매도 사유:* SMA{strategy.sma_period} 하향 이탈 {strategy.confirm_days}일 연속 확정 → 현금 대피\n\n"
                        f"{pnl_emoji} *실수익률:* `{pnl_sign}{abs(float(pnl.return_rate)):.2f}%`\n"
                        f"💰 *실현 실수익:* `{pnl_sign}${abs(realized_pnl):,.2f}`\n"
                        f"• *주문 번호:* `{res['order_no']}`",
                    )
                elif res.get("success"):
                    _log(f"[{strategy.name}] SELL order submitted (pending fill): {asset} x{sell_qty} | {res.get('order_no', '')}", "INFO")
                else:
                    _log(f"[{strategy.name}] SELL FAILED: {asset} | {res.get('message', '')}", "ERROR")
        finally:
            await symbol_lease.release()


async def process_exit_signals(ctx: TradingFlowContext, target_signal_map: dict) -> None:
    user_id = ctx.user_id
    broker = ctx.broker

    def _log(msg, level="INFO"):
        with micro_session(ctx) as db:
            log_action(db, user_id, msg, level)

    if ctx.session == MarketSession.CLOSED:
        if should_log_with_cooldown(MARKET_CLOSED_LOG_CACHE, ("closed_sell", ctx.user_id)):
            _log("장이 닫혀 있어 매도 신호 처리를 생략합니다.", "INFO")
        return

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
            if getattr(strategy_instance, "is_autonomous", False):
                # 자율 슬롯 보유분은 손절/트레일링 대상이 아님 — 레짐 이탈 시에만 process_autonomous_slots가 청산
                continue

            current_data = target_signal_map.get(clean_ticker) or ctx.signal_map.get(clean_ticker)
            if not current_data:
                current_data = await analyze_single_ticker(clean_ticker)

            if not current_data:
                _log(f"No technical data available for owned ticker {clean_ticker}. Skipping monitoring in this cycle.", "WARNING")
                continue

            current_price_dec = to_decimal(current_data['price'])
            current_price = float(current_price_dec)
            h.current_price = current_price  # 비영속(transient) 속성 — version_id 간섭 없음
            # 관측 현재가를 DB에 영속화 — 유저 대면 잔고 API가 외부 호출 없이 평가금을 계산하는 원천.
            # version_id 낙관적 잠금과 간섭하지 않도록 ORM merge 대신 컬럼 단위 UPDATE를 사용하고,
            # 실제 ORM Holding일 때만 기록한다 (테스트 더블 등 비영속 객체 보호).
            # ⚠️ 매핑 컬럼(last_price/last_price_updated_at)을 공유 detached holding(ctx.holdings 원소)에
            #    세팅하면 h가 dirty가 되고, 다음 micro_session 진입 시 auto-merge(scheduler.py:388)가 이
            #    dirty 상태를 flush하며 version_id를 올린다. 그러면 Part B 매도의 db.merge(h)가 stale 원본을
            #    병합하다 StaleDataError로 사이클을 통째 중단시킨다. 따라서 관측값은 로컬 변수로만 다루고
            #    h의 매핑 컬럼은 절대 건드리지 않는다.
            observed_at = utc_now_aware()
            if isinstance(h, Holding) and h.id is not None:
                with micro_session(ctx) as db:
                    db.query(Holding).filter(Holding.id == h.id).update(
                        {
                            Holding.last_price: current_price_dec,
                            Holding.last_price_updated_at: observed_at,
                        },
                        # version_id를 건드리지 않도록 ORM flush가 아닌 Core UPDATE를 쓴다. 세션 내 병합본과
                        # 동기화(evaluate/fetch)하면 그 병합본이 dirty가 되어 오히려 version이 오르므로 False를
                        # 유지하고, 대신 micro_session의 holdings auto-merge를 load=False로 두어(scheduler.py:389)
                        # 이 Core UPDATE 값이 재병합 때 되돌려지거나 version이 오르지 않게 한다.
                        synchronize_session=False,
                    )
                    db.commit()
            profit_rate = calculate_profit_rate(current_price_dec, h.avg_price)

            current_score = strategy_instance.calculate_score(current_data['details'] or current_data, sentiment, is_entry=False)
            is_smart_exit = current_data.get('details', {}).get('is_smart_exit', False)

            dec_highest_price = to_decimal(h.highest_price or current_price_dec)
            if current_price_dec > dec_highest_price:
                dec_highest_price = current_price_dec
                _log(f"[{strategy_instance.name}] New Peak for {clean_ticker}: ${current_price}", "SIGNAL")
                # last_price와 동일 사유(위 주석 참조): 공유 detached holding에 highest_price(매핑 컬럼)를
                # 세팅해 merge로 영속화하면 version_id가 올라 Part B 매도의 db.merge(h)가 StaleData로 실패한다.
                # 트레일링 기준점은 로컬 dec_highest_price로만 계산하고, DB에는 version 비간섭 컬럼 UPDATE로 반영.
                if isinstance(h, Holding) and h.id is not None:
                    with micro_session(ctx) as db:
                        db.query(Holding).filter(Holding.id == h.id).update(
                            {Holding.highest_price: current_price_dec},
                            # last_price와 동일 사유: Core UPDATE(version 비간섭) + auto-merge load=False 조합.
                            synchronize_session=False,
                        )
                        db.commit()

            atr = current_data.get('details', {}).get('atr', 0.0)
            stop_loss_pct = strategy_instance.get_stop_loss_pct(atr, current_price)
            trailing_stop_pct = strategy_instance.get_trailing_stop_pct(atr, current_price)

            sell_reason = None
            is_breached = False
            breach_reason = ""

            if check_stop_loss_breach(profit_rate, stop_loss_pct):
                is_breached = True
                breach_reason = f"동적 손절선 이탈 (손절 기준 -{stop_loss_pct:.2f}% 돌파 | 현재 수익률: {profit_rate:.2f}%)"
            elif check_trailing_stop_breach(current_price_dec, dec_highest_price, trailing_stop_pct, h.avg_price):
                is_breached = True
                breach_reason = f"동적 트레일링 스탑 이탈 (최고가 ${float(dec_highest_price):.2f} 대비 {trailing_stop_pct:.2f}% 하락 | 현재 수익률: {profit_rate:.2f}%)"

            if is_breached:
                cache_key = (user_id, h.ticker, h.strategy_type)
                with _breach_count_lock:
                    BREACH_COUNT_CACHE[cache_key] = BREACH_COUNT_CACHE.get(cache_key, 0) + 1
                    count = BREACH_COUNT_CACHE[cache_key]

                if count >= 2:
                    sell_reason = breach_reason + " [2회 연속 이탈 확정]"
                else:
                    _log(f"[Noise Buffer] {h.ticker} ({h.strategy_type}) first breach detected ({breach_reason}). Delaying sell for noise protection (Count: {count}/2).", "INFO")
            else:
                with _breach_count_lock:
                    BREACH_COUNT_CACHE.pop((user_id, h.ticker, h.strategy_type), None)

            if not sell_reason and profit_rate >= strategy_instance.min_smart_exit_profit and is_smart_exit:
                sell_reason = f"스마트 조기 익절 (RSI-MACD 조건 충족 | 수익률: {profit_rate:.2f}%)"

            elif not sell_reason and strategy_instance.is_signal_collapsed(current_score, sentiment):
                sell_reason = f"강세 시그널 붕괴 ({current_score}점 도달)"

            if sell_reason:
                _log(f"[{strategy_instance.name}] EXIT SIGNAL: {h.ticker} | Reason: {sell_reason}", "SIGNAL")

                is_kis_order = (ctx.trade_mode or "").upper() in {"MOCK", "REAL"}
                metadata = None
                if is_kis_order:
                    metadata = await safe_broker_call(broker.get_order_metadata, clean_ticker, ctx.session)

                sell_tasks_args.append((
                    h,
                    current_price,
                    sell_reason,
                    clean_ticker,
                    strategy_instance,
                    current_score,
                    slot_key,
                    metadata,
                ))

        except Exception as item_err:
            _log(f"Error processing holding {h.ticker}: {item_err}", "ERROR")

    if not sell_tasks_args:
        return

    # ------------------ (Part B) 브로커 비동기 병렬 주문 및 체결 처리 ------------------
    async def _execute_single_sell(
        h,
        current_price,
        sell_reason,
        clean_ticker,
        strategy_instance,
        current_score,
        slot_key,
        metadata,
    ):
        request_id = str(uuid4())
        try:
            symbol_lease = await acquire_symbol_order_lock(user_id, clean_ticker, request_id)
        except RedisLockUnavailable:
            _log(f"SELL BLOCKED: Redis order lock is unavailable for {clean_ticker}.", "ERROR")
            return
        if symbol_lease is None:
            _log(f"SELL SKIP: Another order is in progress for {clean_ticker}.", "WARNING")
            return

        try:
            is_kis_order = (ctx.trade_mode or "").upper() in {"MOCK", "REAL"}
            order_intent = None
            if is_kis_order:
                with micro_session(ctx) as db:
                    order_intent = create_order_intent(
                        db,
                        db.merge(ctx.db_settings),
                        side="SELL",
                        ticker=clean_ticker,
                        prefixed_ticker=clean_ticker,
                        strategy_type=slot_key,
                        ticker_name=h.ticker_name,
                        requested_qty=h.quantity,
                        submitted_price=current_price,
                        exchange_code=metadata.get("exchange_code"),
                        order_division=metadata.get("order_division"),
                        regime_mode=sentiment,
                        signal_score=current_score,
                        sell_reason=sell_reason,
                    )
                    begin_order_submission(db, order_intent, db.merge(ctx.db_settings))
                    db.commit()

            try:
                if is_kis_order:
                    res = await execute_and_poll_order(
                        broker, broker.sell_order, clean_ticker, h.quantity,
                        price=current_price, session=ctx.session,
                        lease=symbol_lease,
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
                    _log(f"Error during sell order for {h.ticker}: {exc}", "ERROR")
                    return
                res = {
                    "success": False, "order_submitted": True, "submission_unknown": True,
                    "status": "ACK_UNKNOWN", "order_no": "", "filled_qty": 0, "filled_price": 0.0,
                    "fill_confirmed": False, "message": f"Broker acknowledgement unknown: {exc}",
                }

            if order_intent:
                with micro_session(ctx) as db:
                    application = finalize_order_submission(db, order_intent, db.merge(ctx.db_settings), res)
                    db.commit()

                if application.applied_qty > 0:
                    filled_price = application.filled_price
                    filled_qty = application.applied_qty
                    realized_pnl = application.realized_pnl or 0.0
                    calc_return_rate = application.return_rate or 0.0
                    remaining_qty = application.remaining_qty or 0
                    BREACH_COUNT_CACHE.pop((user_id, h.ticker, h.strategy_type), None)
                    fill_label = "sold" if remaining_qty == 0 else f"partially sold ({filled_qty} filled, {remaining_qty} remaining)"
                    _log(f"SUCCESS: {h.ticker} {fill_label} via {sell_reason} | Order: {res['order_no']}", "INFO")

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
                    # 체결 직후 잔고 스냅샷 즉시 갱신 (60초 dedup 우회) — 대시보드 낡은 잔고 방지
                    _schedule_background_task(
                        refresh_user_equity_snapshot(user_id),
                        f"equity-snapshot-refresh-{user_id}",
                    )
                if application.is_unresolved:
                    halt_trading_for_order_review(ctx, "SELL", clean_ticker, res)
                    return
                if application.applied_qty == 0 and not res.get("success"):
                    with micro_session(ctx) as db:
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
                    with micro_session(ctx) as db:
                        log_action(db, user_id, f"SELL INVALID FILL: {h.ticker} | {res}", "ERROR")
                    halt_trading_for_order_review(ctx, "SELL", clean_ticker, res)
                    return

                pnl = calculate_realized_pnl(
                    avg_price=h.avg_price,
                    filled_price=filled_price,
                    quantity=filled_qty,
                    fee_rate=settings.KIS_FEE_RATE,
                )
                realized_pnl = pnl.realized_pnl
                calc_return_rate = pnl.return_rate

                with micro_session(ctx) as db:
                    h_db = db.merge(h)
                    db.add(TradeLog(
                        user_id=user_id, ticker=h.ticker, strategy_type=h.strategy_type, ticker_name=h.ticker_name,
                        trade_type="SELL", price=filled_price, quantity=filled_qty,
                        order_no=res["order_no"], regime_mode=sentiment, signal_score=current_score,
                        realized_pnl=round(realized_pnl, 2), return_rate=round(calc_return_rate, 2)
                    ))
                    is_full_fill = filled_qty >= h.quantity
                    if is_full_fill:
                        db.delete(h_db)
                    else:
                        h_db.quantity -= filled_qty
                    db.commit()
                    fill_label = "sold" if is_full_fill else f"partially sold ({filled_qty} filled, {h.quantity} remaining)"
                    log_action(db, user_id, f"SUCCESS: {h.ticker} ({h.strategy_type}) {fill_label} via {sell_reason} | Order: {res['order_no']}", "INFO")

                # 전량 매도된 holding을 ctx.holdings에서 제거한다. 같은 사이클에서 다른 종목이 이어서 매도될 때,
                # 다음 micro_session의 holdings auto-merge(scheduler.py:388)가 이미 삭제된 detached holding을
                # 다시 병합하려다 실패하거나 유령 재삽입하는 것을 막는다.
                if is_full_fill:
                    holding_id = getattr(h, "id", None)
                    if holding_id is not None and getattr(ctx, "holdings", None):
                        ctx.holdings = [x for x in ctx.holdings if getattr(x, "id", None) != holding_id]

                BREACH_COUNT_CACHE.pop((user_id, h.ticker, h.strategy_type), None)

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
                # 체결 직후 잔고 스냅샷 즉시 갱신 (60초 dedup 우회) — 대시보드 낡은 잔고 방지
                _schedule_background_task(
                    refresh_user_equity_snapshot(user_id),
                    f"equity-snapshot-refresh-{user_id}",
                )
                if requires_review:
                    halt_trading_for_order_review(ctx, "SELL", clean_ticker, res)
                    return
            else:
                with micro_session(ctx) as db:
                    log_action(db, user_id, f"SELL FAILED: {h.ticker} | {res['message']}", "ERROR")

        finally:
            await symbol_lease.release()

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
        current_price_dec = to_decimal(signal['price'])
        current_price = float(current_price_dec)
        profit_rate = calculate_profit_rate(current_price_dec, existing_holding.avg_price)
        pyramid_trigger_2 = strategy_instance.get_pyramid_trigger(2)

        if buy_stage == 1:
            if profit_rate < pyramid_trigger_1:
                return None
            proposed_alloc_factor = 0.35
            next_stage = 2
            with micro_session(ctx) as db:
                log_action(db, ctx.user_id, f"[{strategy_instance.name}] [Pyramiding] {clean_ticker} meets 2nd Buy Condition (+{profit_rate:.2f}% profit). Placing 35% confirm order.", "SIGNAL")
        elif buy_stage == 2:
            if profit_rate < pyramid_trigger_2:
                return None
            proposed_alloc_factor = 0.50
            next_stage = 3
            with micro_session(ctx) as db:
                log_action(db, ctx.user_id, f"[{strategy_instance.name}] [Pyramiding] {clean_ticker} meets 3rd Buy Condition (+{profit_rate:.2f}% profit). Placing 50% ultimate order.", "SIGNAL")
        else:
            return None
    else:
        proposed_alloc_factor = strategy_instance.get_initial_entry_factor(ctx.sentiment)
        if ctx.sentiment == "BULLISH" and proposed_alloc_factor < 1.0:
            next_stage = 1
            with micro_session(ctx) as db:
                log_action(db, ctx.user_id, f"[{strategy_instance.name}] [New Entry] {clean_ticker} scanned. Placing 15% scout order.", "INFO")
        else:
            next_stage = 3
            with micro_session(ctx) as db:
                log_action(db, ctx.user_id, f"[{strategy_instance.name}] [New Entry] {clean_ticker} scanned. Placing {proposed_alloc_factor*100:.0f}% single defensive order.", "INFO")

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
    with micro_session(ctx) as db:
        log_action(db, ctx.user_id, f"[{strategy_instance.name}] SKIP PURCHASE ({reason_title}): {clean_ticker}.", "WARNING")

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
    order_no: str,
    current_score: int,
) -> bool:
    with micro_session(ctx) as db:
        dec_filled_price = to_decimal(filled_price)
        if existing_holding:
            existing_holding = db.merge(existing_holding)
            old_qty = existing_holding.quantity
            old_avg = existing_holding.avg_price

            new_qty = old_qty + filled_qty
            new_avg = calculate_avg_price(old_avg, old_qty, dec_filled_price, filled_qty)

            existing_holding.avg_price = new_avg
            existing_holding.quantity = new_qty
            existing_holding.buy_stage = next_stage
            existing_holding.highest_price = max(to_decimal(existing_holding.highest_price or dec_filled_price), dec_filled_price)

            db.add(TradeLog(
                user_id=ctx.user_id,
                ticker=ticker,
                strategy_type=strategy_type,
                ticker_name=signal['name'],
                trade_type="BUY",
                price=dec_filled_price,
                quantity=filled_qty,
                order_no=order_no,
                regime_mode=ctx.sentiment,
                signal_score=current_score,
                realized_pnl=Decimal('0.0000'),
                return_rate=Decimal('0.0000')
            ))

            db.commit()
            log_action(db, ctx.user_id, f"SUCCESS: {ticker} ({strategy_type}) Pyramiding Stage {next_stage} Add-on. New Avg: ${float(new_avg):.2f}", "INFO")
            return False

        db.add(Holding(
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

        db.add(TradeLog(
            user_id=ctx.user_id,
            ticker=ticker,
            strategy_type=strategy_type,
            ticker_name=signal['name'],
            trade_type="BUY",
            price=filled_price,
            quantity=filled_qty,
            order_no=order_no,
            regime_mode=ctx.sentiment,
            signal_score=current_score,
            realized_pnl=0.0,
            return_rate=0.0
        ))

        db.commit()
        log_action(db, ctx.user_id, f"SUCCESS: {ticker} ({strategy_type}) purchased ({filled_qty} shares)", "INFO")
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
    user_id = ctx.user_id
    ms_manager = ctx.ms_manager

    def _log(msg, level="INFO"):
        with micro_session(ctx) as db:
            log_action(db, user_id, msg, level)

    if ctx.session == MarketSession.CLOSED:
        if should_log_with_cooldown(MARKET_CLOSED_LOG_CACHE, ("closed_buy", user_id)):
            _log("[BUY SKIP] US market is currently closed. No new buy orders placed.", "INFO")
        return False

    focused_tickers = ms_manager.get_focused_tickers(ctx.all_signals)
    _log(f"[Focusing Filter] Selected {len(focused_tickers)} elite tickers for compressed investment: {', '.join(focused_tickers)}", "INFO")

    buy_tasks_args = []

    # ------------------ (Part A) 매수 조건 판별 및 인텐트 생성 (순차) ------------------
    for slot_key, slot_info in slot_allocations.items():
        if slot_key == "regime_switching" and ctx.sentiment != "BULLISH":
            _log(f"[Regime Sluice] Regime Switching V2 slot DEACTIVATED in {ctx.sentiment} market to protect 100% cash.", "INFO")
            continue

        strategy_instance = ms_manager.strategies[slot_key]
        if getattr(strategy_instance, "is_autonomous", False):
            # 자율 슬롯은 스캐너 시그널 기반 신규 진입 대상이 아님 — process_autonomous_slots 전담
            continue
        slot_cash_usd = slot_info["cash_balance"]
        slot_total_asset_usd = slot_info["total_asset"]

        with micro_session(ctx) as db:
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

            with micro_session(ctx) as db:
                existing_holding = db.query(Holding).filter(
                    Holding.user_id == user_id,
                    Holding.ticker == clean_ticker,
                    Holding.strategy_type == slot_key
                ).first()
                if existing_holding:
                    db.expunge(existing_holding)

            entry_stage = resolve_entry_stage(ctx, strategy_instance, clean_ticker, signal, existing_holding)
            if entry_stage is None:
                continue
            proposed_alloc_factor, next_stage = entry_stage

            with micro_session(ctx) as db:
                recent_sell = has_recent_sell(db, user_id, clean_ticker, slot_key)

            if recent_sell:
                continue

            realtime_price = await get_realtime_price(clean_ticker)
            if realtime_price is None:
                continue

            cached_price = signal['price']
            price_drift_pct = (realtime_price - cached_price) / cached_price * 100 if cached_price > 0 else 0
            if price_drift_pct > 20.0:
                _log(f"[Surge Guard] {clean_ticker} has surged +{price_drift_pct:.1f}% since signal cached. Aborting purchase.", "WARNING")
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

            is_kis_order = (ctx.trade_mode or "").upper() in {"MOCK", "REAL"}
            metadata = None
            if is_kis_order:
                metadata = await safe_broker_call(ctx.broker.get_order_metadata, clean_ticker, ctx.session)

            buy_tasks_args.append((
                clean_ticker, strategy_instance, signal, score, next_stage,
                current_price, final_qty, existing_holding, slot_key, metadata
            ))
            _, _, reserved_order_total = calculate_buy_total(
                current_price,
                final_qty,
                fee_rate_for_trade_mode(ctx.trade_mode),
            )
            slot_cash_usd -= float(reserved_order_total)
            if not existing_holding:
                slot_holdings_count += 1

    if not buy_tasks_args:
        return True

    # ------------------ (Part B) 브로커 비동기 병렬 주문 및 체결 처리 ------------------
    async def _execute_single_buy(
        clean_ticker,
        strategy_instance,
        signal,
        score,
        next_stage,
        current_price,
        final_qty,
        existing_holding,
        slot_key,
        metadata,
    ):
        request_id = str(uuid4())
        try:
            symbol_lease = await acquire_symbol_order_lock(user_id, clean_ticker, request_id)
        except RedisLockUnavailable:
            _log(f"BUY BLOCKED: Redis order lock is unavailable for {clean_ticker}.", "ERROR")
            return False
        if symbol_lease is None:
            _log(f"BUY SKIP: Another order is in progress for {clean_ticker}.", "WARNING")
            return False

        try:
            is_kis_order = (ctx.trade_mode or "").upper() in {"MOCK", "REAL"}
            order_intent = None
            if is_kis_order:
                with micro_session(ctx) as db:
                    order_intent = create_order_intent(
                        db,
                        db.merge(ctx.db_settings),
                        side="BUY",
                        ticker=clean_ticker,
                        prefixed_ticker=clean_ticker,
                        strategy_type=slot_key,
                        ticker_name=signal["name"],
                        requested_qty=final_qty,
                        submitted_price=current_price,
                        exchange_code=metadata.get("exchange_code"),
                        order_division=metadata.get("order_division"),
                        buy_stage=next_stage,
                        regime_mode=ctx.sentiment,
                        signal_score=score,
                    )
                    begin_order_submission(db, order_intent, db.merge(ctx.db_settings))
                    db.commit()

            try:
                if is_kis_order:
                    res = await execute_and_poll_order(
                        ctx.broker, ctx.broker.buy_order, clean_ticker, final_qty,
                        price=current_price, session=ctx.session,
                        lease=symbol_lease,
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
                    _log(f"Error during buy order for {clean_ticker}: {exc}", "ERROR")
                    return False
                res = {
                    "success": False, "order_submitted": True, "submission_unknown": True,
                    "status": "ACK_UNKNOWN", "order_no": "", "filled_qty": 0, "filled_price": 0.0,
                    "fill_confirmed": False, "message": f"Broker acknowledgement unknown: {exc}",
                }

            if order_intent:
                with micro_session(ctx) as db:
                    application = finalize_order_submission(db, order_intent, db.merge(ctx.db_settings), res)
                    db.commit()

                if application.applied_qty > 0:
                    filled_price = application.filled_price
                    filled_qty = application.applied_qty
                    _log(f"SUCCESS: {clean_ticker} ({slot_key}) broker fill applied ({filled_qty} shares)", "INFO")
                    send_successful_buy_message(
                        ctx=ctx, strategy_instance=strategy_instance, clean_ticker=clean_ticker,
                        signal=signal, filled_price=filled_price, filled_qty=filled_qty,
                        next_stage=next_stage, order_no=res["order_no"],
                    )
                    # 체결 직후 잔고 스냅샷 즉시 갱신 (60초 dedup 우회) — 대시보드 낡은 잔고 방지
                    _schedule_background_task(
                        refresh_user_equity_snapshot(user_id),
                        f"equity-snapshot-refresh-{user_id}",
                    )
                if application.is_unresolved:
                    halt_trading_for_order_review(ctx, "BUY", clean_ticker, res)
                    return False
                if application.applied_qty == 0 and not res.get("success"):
                    with micro_session(ctx) as db:
                        log_action(db, user_id, f"BUY FAILED: {clean_ticker} ({slot_key}) | {res['message']}", "ERROR")
                return True

            requires_review = bool(res.get("order_submitted")) and not bool(res.get("fill_confirmed"))
            if requires_review and res.get("status") != "PARTIAL":
                halt_trading_for_order_review(ctx, "BUY", clean_ticker, res)
                return False

            if not res["success"]:
                with micro_session(ctx) as db:
                    log_action(db, user_id, f"BUY FAILED: {clean_ticker} ({slot_key}) | {res['message']}", "ERROR")
                return True

            filled_price = res["filled_price"]
            filled_qty = res["filled_qty"]

            record_successful_buy(
                ctx=ctx, strategy_instance=strategy_instance, existing_holding=existing_holding,
                ticker=clean_ticker, strategy_type=slot_key, signal=signal, filled_price=filled_price,
                filled_qty=filled_qty, next_stage=next_stage,
                order_no=res["order_no"], current_score=score,
            )
            # 체결 직후 잔고 스냅샷 즉시 갱신 (60초 dedup 우회) — 대시보드 낡은 잔고 방지
            _schedule_background_task(
                refresh_user_equity_snapshot(user_id),
                f"equity-snapshot-refresh-{user_id}",
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

        finally:
            await symbol_lease.release()

    tasks = [_execute_single_buy(*args) for args in buy_tasks_args]
    results = await asyncio.gather(*tasks)

    return all(results)

async def run_user_trading_flow(user_id: int, signal_map: dict, all_signals: list, exchange_rate: float, sentiment: str, session: str):
    """Runs one user's automated trading flow using cycle-level market context."""
    operation_id = str(uuid4())
    try:
        user_lease = await acquire_user_operation_lock(user_id, operation_id)
    except RedisLockUnavailable:
        logger.exception(
            "[TradingLock] Redis unavailable; failing closed for user=%s",
            user_id,
        )
        return
    if user_lease is None:
        logger.info(
            "[TradingLock] Another trading operation is active for user=%s; skipping cycle",
            user_id,
        )
        return

    try:
        db = SessionLocal()
        # prepare_trading_flow_context 내 log_action 커밋이 db_settings 속성을 만료시키는데,
        # 이후 expunge_all로 Detached된 상태에서 속성을 읽으면 refresh 실패한다. 만료를 끈다.
        # (micro_session과 동일 정책 — 상세 근거는 micro_session 주석 참조.)
        db.expire_on_commit = False
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

            # 찰나의 세션이 닫힌 뒤에도 ctx.db_settings, ctx.holdings 속성을 읽고 수정할 수 있도록 분리
            db.expunge_all()
        finally:
            db.close()

        try:
            await sync_broker_holdings(ctx)

            # 선행 micro_session 커밋으로 만료(Detached-expired)된 보유 ORM을 신선한 로드 상태로 교체.
            # 이 재적재가 없으면 보유가 생긴 뒤 calculate_slots_allocation의 세션 밖 속성 접근이
            # DetachedInstanceError로 사이클 전체를 침묵 실패시킨다.
            refresh_db = SessionLocal()
            try:
                ctx.holdings = refresh_db.query(Holding).filter(Holding.user_id == user_id).all()
                refresh_db.expunge_all()
            finally:
                refresh_db.close()

            slot_allocations = await calculate_slot_allocations(ctx)
            await process_autonomous_slots(ctx, slot_allocations)
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
            # Micro-Session 에서는 이미 DB 커넥션이 반납된 상태이므로 rollback 불필요
            logger.warning(f"[Scheduler Auto-Recovery] Network disruption detected for User {user_id}. Error: {ne}")

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
            logger.exception(f"[run_user_trading_flow] Error for user {user_id}")
    finally:
        await user_lease.release()


def is_scanner_refresh_in_progress() -> bool:
    with _scanner_refresh_lock:
        return _scanner_refresh_in_progress


async def refresh_scanner_cache(force: bool = False) -> bool:
    """
    마켓 스캐너 캐시를 독립적으로 갱신하는 전용 비동기 함수 (10분 주기).
    자동매매 루프와 완전히 분리되어 Rate Limit 위험 없이 안전하게 동작합니다.
    """
    global latest_scanned_signals, latest_watchlist_signals, _scanner_refresh_in_progress

    with _scanner_refresh_lock:
        if _scanner_refresh_in_progress:
            logger.info("[Scanner Cache] Previous refresh still running. Skipping duplicate refresh.")
            return False
        _scanner_refresh_in_progress = True

    try:
        # 장 외 시간 API 비용/호출 낭비 방지 가드
        session = get_market_session()
        if session == MarketSession.CLOSED and not force:
            logger.info("[Scanner Cache] Market is closed. Skipping scan to save API quotas.")
            return False

        logger.info("[Scanner Cache] Starting 10-min market scan refresh cycle...")
        signals = await scan_overseas_market()
        latest_scanned_signals = signals
        market_signal_map = {signal["ticker"]: signal for signal in signals}

        db = SessionLocal()
        try:
            watchlists_by_user = load_all_watchlist_tickers_by_user(db)
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
        # SSE(Phase 2): 공용 스캐너 결과가 갱신됐음을 브로드캐스트(invalidate) → 구독자 일괄 재조회.
        from app.core import sse
        await sse.publish(sse.CHANNEL_PUBLIC, sse.EVENT_SCANNER_LATEST, None)
        return True
    except Exception as e:
        logger.exception("[Scanner Cache] ERROR during market scan")
        return False
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
            _schedule_background_task(refresh_scanner_cache(), "scanner_cache")
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
            return

        # SIMULATED 모드인 유저들의 미체결 지정가 주문(UnfilledOrder)을 주기적으로 평가/체결 처리합니다.
        for u in active_users:
            trade_mode = getattr(u, "trade_mode", "SIMULATED") or "SIMULATED"
            if trade_mode.upper() == "SIMULATED":
                from app.bot.simulated_broker import LocalSimulatedBroker
                sim_broker = LocalSimulatedBroker(db_settings=u)
                sim_broker.process_unfilled_orders(db)

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

        watchlists_by_user = load_watchlist_tickers_by_user(db, active_user_ids)

        # Eagerly close db session before starting remote / async calls
        db.close()
        db = None

        sentiment = await check_market_sentiment()
        market_signals = latest_scanned_signals

        # 3. 각 활성 유저별 자동매매 시나리오 병렬 실행
        tasks = []
        for user_id in active_user_ids:
            signal_map, all_signals = build_user_signal_context(
                user_id,
                market_signals,
                watchlists_by_user,
                latest_watchlist_signals,
            )
            tasks.append(
                run_user_trading_flow(
                    user_id,
                    signal_map,
                    all_signals,
                    exchange_rate,
                    sentiment,
                    session,
                )
            )
        await asyncio.gather(*tasks)

    except Exception:
        logger.exception("[Scheduler] CRITICAL ERROR in trading loop")
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
        is_processing = False

def trading_loop_wrapper():
    try:
        asyncio.run(async_trading_loop())
    except RuntimeError:
        # 💡 이미 실행 중인 이벤트 루프가 있는 경우 (FastAPI/uvicorn 내부 등)
        loop = asyncio.get_event_loop()
        if loop.is_running():
            _schedule_background_task(async_trading_loop(), "trading_loop")
        else:
            loop.run_until_complete(async_trading_loop())


def reconcile_open_orders_wrapper():
    try:
        asyncio.run(reconcile_open_orders_once())
    except RuntimeError:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            _schedule_background_task(reconcile_open_orders_once(), "broker_order_reconciliation")
        else:
            loop.run_until_complete(reconcile_open_orders_once())


def discover_orphan_orders_wrapper():
    discover_orphan_orders_once()

# last_price가 이 시간 이상 낡으면 백그라운드 벌크 시세 조회로 재갱신한다.
LAST_PRICE_STALE_SECONDS = 600


def _refresh_stale_holding_prices() -> None:
    """
    봇이 꺼진 유저의 보유종목도 평가금이 동결되지 않도록,
    낡은 Holding.last_price를 벌크 시세 1회로 갱신합니다.
    (백그라운드 전용 — 유저 대면 경로에서는 절대 호출 금지)
    """
    from app.scanner.data_provider import fetch_bulk_ohlcv_sync
    import pandas as pd

    db = SessionLocal()
    try:
        holdings = db.query(Holding).all()
        now = utc_now_aware()
        stale = [
            h for h in holdings
            if h.last_price_updated_at is None
            or (now - h.last_price_updated_at).total_seconds() >= LAST_PRICE_STALE_SECONDS
        ]
        if not stale:
            return

        tickers = sorted({h.ticker for h in stale})
        data = fetch_bulk_ohlcv_sync(tickers, interval="1m", period="1d", group_by="ticker")
        if data is None or data.empty:
            return

        prices = {}
        for ticker in tickers:
            try:
                if isinstance(data.columns, pd.MultiIndex):
                    df = data[ticker].dropna() if ticker in data.columns.levels[0] else pd.DataFrame()
                else:
                    df = data.dropna()
                if not df.empty:
                    prices[ticker] = to_decimal(df['Close'].iloc[-1])
            except Exception as exc:
                logger.warning(f"[Equity Snapshot] Failed to parse bulk price for {ticker}: {exc}")

        refreshed_at = utc_now_aware()
        for h in stale:
            price = prices.get(h.ticker)
            if price is None:
                continue
            db.query(Holding).filter(Holding.id == h.id).update(
                {Holding.last_price: price, Holding.last_price_updated_at: refreshed_at},
                synchronize_session=False,
            )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("[Equity Snapshot] Stale holding price refresh failed")
    finally:
        db.close()


def record_equity_snapshot(
    user_id: int,
    trade_mode: str,
    balance: dict,
    exchange_rate: float | None = None,
    force: bool = False,
) -> bool:
    """
    잔고 dict를 AccountEquitySnapshot으로 영속화합니다.
    force=True면 60초 dedup을 우회합니다(체결 직후 즉시 갱신용).
    """
    total_asset = balance.get("total_asset")
    if total_asset is None or not math.isfinite(float(total_asset)):
        return False

    captured_at = utc_now_aware()
    snapshot_db = SessionLocal()
    try:
        latest_snapshot = (
            snapshot_db.query(AccountEquitySnapshot)
            .filter(
                AccountEquitySnapshot.user_id == user_id,
                AccountEquitySnapshot.trade_mode == trade_mode,
            )
            .order_by(AccountEquitySnapshot.captured_at.desc())
            .first()
        )
        should_record = (
            force
            or latest_snapshot is None
            or (captured_at - latest_snapshot.captured_at).total_seconds() >= 60
        )
        if not should_record:
            return False

        snapshot_db.add(AccountEquitySnapshot(
            user_id=user_id,
            total_asset=float(total_asset),
            cash_balance=balance.get("cash_balance"),
            stock_balance=balance.get("stock_balance"),
            profit_rate=float(balance.get("profit_rate", 0.0)),
            profit_loss=balance.get("profit_loss"),
            fx_rate=balance.get("fx_rate", exchange_rate),
            trade_mode=trade_mode,
            captured_at=captured_at,
        ))
        snapshot_db.flush()

        expired_snapshots = (
            snapshot_db.query(AccountEquitySnapshot)
            .filter(
                AccountEquitySnapshot.user_id == user_id,
                AccountEquitySnapshot.trade_mode == trade_mode,
            )
            .order_by(AccountEquitySnapshot.captured_at.desc())
            .offset(500)
            .all()
        )
        for expired_snapshot in expired_snapshots:
            snapshot_db.delete(expired_snapshot)
        snapshot_db.commit()

        # SSE: 스냅샷이 실제로 기록됐을 때만 유저 채널로 잔고/보유 invalidate 발행(best-effort).
        from app.core import sse
        sse.notify_user_equity(user_id)
        return True
    except Exception:
        snapshot_db.rollback()
        raise
    finally:
        snapshot_db.close()


async def refresh_user_equity_snapshot(user_id: int) -> None:
    """
    체결·계좌 초기화 등 잔고 변동 직후 스냅샷을 dedup 없이 즉시 갱신합니다.
    실패해도 다음 admin_balance_cache_sync 주기가 자연 복구하므로 경고만 남깁니다.
    """
    try:
        db = SessionLocal()
        try:
            user = (
                db.query(User)
                .options(selectinload(User.settings).selectinload(UserSettings.credentials))
                .filter(User.id == user_id)
                .first()
            )
            if not user or not user.settings:
                return
            trade_mode = user.settings.trade_mode
            broker = get_broker_client(user.settings)
        finally:
            db.expunge_all()
            db.close()

        balance = await safe_broker_call(broker.get_account_balance)
        if not isinstance(balance, dict):
            return
        await asyncio.to_thread(record_equity_snapshot, user_id, trade_mode, balance, None, True)
    except Exception as exc:
        logger.warning(f"[Equity Snapshot] Immediate refresh failed for user {user_id}: {exc}")


async def admin_balance_cache_sync():
    """
    Refresh admin account-equity snapshots without holding a DB connection
    during broker/network balance calls.
    """
    targets = []
    db = SessionLocal()
    try:
        users = (
            db.query(User)
            .options(selectinload(User.settings).selectinload(UserSettings.credentials))
            .all()
        )
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

            if not (is_simulated or has_verified_cred):
                continue

            try:
                broker = get_broker_client(settings)
            except Exception as exc:
                logger.warning(f"[Admin Cache Sync] Broker creation failed for user {user.username}: {exc}")
                continue

            targets.append({
                "user_id": user.id,
                "username": user.username,
                "trade_mode": settings.trade_mode,
                "broker": broker,
            })
    except Exception:
        logger.exception("[Admin Cache Sync] CRITICAL ERROR while loading users")
        return
    finally:
        db.expunge_all()
        db.close()

    # 봇 미가동 유저의 보유종목 평가금이 동결되지 않도록 낡은 last_price를 먼저 벌크 갱신
    await asyncio.to_thread(_refresh_stale_holding_prices)

    exchange_rate = await asyncio.to_thread(FXRateCache.get_rate)

    for target in targets:
        try:
            balance = await safe_broker_call(target["broker"].get_account_balance)
            if not isinstance(balance, dict):
                continue
            record_equity_snapshot(target["user_id"], target["trade_mode"], balance, exchange_rate)
        except Exception as exc:
            logger.warning(f"[Admin Cache Sync] Error for user {target['username']}: {exc}")

    # SSE: 1분 벌크 동기 후 관리자 랭킹을 한 번만 무효화(유저별 발행과 분리해 과다 refetch 방지).
    from app.core import sse
    await sse.publish(sse.CHANNEL_ADMIN, sse.EVENT_ADMIN_USERS, None)

def admin_balance_cache_wrapper():
    try:
        asyncio.run(admin_balance_cache_sync())
    except RuntimeError:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            _schedule_background_task(admin_balance_cache_sync(), "admin_balance_cache")
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
        logger.info("Background scheduler started (Multi-tenant 3-Mode Unified Engine).")

def stop_scheduler():
    """앱 종료 시 백그라운드 스레드를 깔끔하게 종료하여 좀비 폴링 방지"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped.")
