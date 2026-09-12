import concurrent.futures
from apscheduler.schedulers.background import BackgroundScheduler
from app.brokers.broker_factory import get_broker_client
from app.core.database import SessionLocal
from sqlalchemy.orm import selectinload
from app.watchlist.services import load_watchlist_tickers_by_user, load_all_watchlist_tickers_by_user
from app.core.locks import (
    RedisLockUnavailable,
    acquire_symbol_order_lock,
    acquire_user_operation_lock,
)
from app.core.holding_audit import delete_holding
from app.core.models import (
    TradeLog, Holding, ActionLog, UserSettings, WatchList, User, AccountEquitySnapshot, UnfilledOrder,
    MANAGEMENT_BOT_OWNED, MANAGEMENT_EXTERNAL, MANAGEMENT_DELEGATED, EXTERNAL_STRATEGY_TYPE,
    GUARD_ACTION_ALERT_ONLY, GUARD_ACTION_SHADOW, GUARD_ACTION_LIQUIDATE,
)
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from dataclasses import dataclass
import asyncio
import threading
import time
import socket
import weakref
import httpx
from requests.exceptions import RequestException as RequestsRequestException
from app.core.logging import logger
from app.core.config import settings
from app.scanner.data_provider import fetch_ohlcv
from app.core.telegram import send_message_async, send_daily_report_to_all_users_sync
from app.core.i18n import I18n, resolve_user_language
from app.bot.fx_cache import FXRateCache
from app.bot.market_session import (
    ET,
    AFTER_HOURS_CLOSE,
    EARLY_CLOSE_AFTER_HOURS_END,
    PRE_MARKET_OPEN,
    REGULAR_MARKET_OPEN,
    MarketSession,
    get_market_session,
)
from app.trades.market_overview_cache import market_overview_cache_wrapper
from app.trades.equity_snapshot import record_equity_snapshot
from app.scanner.swing_prediction_cache import swing_prediction_cache_wrapper
from app.scanner.score_calibration import swing_score_calibration_wrapper
from app.bot.order_reconciler import (
    begin_order_submission,
    create_order_intent,
    finalize_order_submission,
    has_unresolved_orders,
    has_unresolved_orders_for_ticker,
    reconcile_open_orders_once,
)
from app.bot.trade_calculations import (
    calculate_avg_price,
    calculate_buy_total,
    calculate_profit_rate,
    calculate_realized_pnl,
    DEFAULT_ROLLING_BOX_MINUTES,
    LIVE_BOX_BAR_MINUTES,
    check_rolling_box_breach,
    check_stop_loss_breach,
    check_trailing_stop_breach,
    compute_box_low,
    compute_rolling_box_stop,
    check_harvest_arm,
    check_harvest_breach,
    check_guard_breach,
    compute_guard_low,
    resolve_guard_sell_qty,
    GUARD_ACTION_COOLDOWN_HOURS,
    GUARD_SUSTAIN_CYCLES,
    GUARD_SUSTAIN_MINUTES,
    get_harvest_arm_pct,
    get_harvest_trailing_pct,
    EXIT_NOISE_BUFFER_CYCLES,
    EXIT_NOISE_BUFFER_MINUTES,
    HARVEST_SUSTAIN_CYCLES,
    HARVEST_SUSTAIN_MINUTES,
    GUARD_ALERT_COOLDOWN_HOURS,
    GUARD_GRACE_MINUTES,
    resolve_rolling_box_bars,
    fee_rate_for_trade_mode,
    to_decimal,
)
from app.bot.order_discovery import discover_orphan_orders_once
from app.bot.equity_gate import get_equity_gate_factor
import time
from uuid import uuid4
import math
from app.core.models import utc_now_aware
from contextlib import contextmanager
# 💡 네트워크 일시 장애에 따른 텔레그램 경고 도배 방지용 시간 기록 저장소
_user_network_alert_sent = {}


def _resolve_lang(user_id: int) -> str:
    """알림 발송 직전 사용자 언어를 독립 세션에서 해석한다(실패 시 ko 폴백)."""
    db = SessionLocal()
    try:
        return resolve_user_language(db, user_id)
    finally:
        db.close()


@dataclass
class SellReason:
    """매도 사유를 구조화한다. DB/로그에는 ko canonical, 텔레그램에는 사용자 언어로 렌더한다."""
    key: str
    args: dict
    confirmed: bool = False


def render_sell_reason(reason: "SellReason", lang: str) -> str:
    """SellReason을 주어진 언어의 텔레그램 사유 문구로 렌더한다."""
    text = I18n.get_msg(lang, f"telegram.sell_reason.{reason.key}", **reason.args)
    if reason.confirmed:
        text += I18n.get_msg(lang, "telegram.sell_reason.breach_confirmed_suffix")
    return text


def _send_sell_fill_message(
    user_id: int,
    strategy_name: str,
    ticker: str,
    ticker_name: str,
    filled_price: float,
    exchange_rate: float,
    filled_qty: int,
    sell_reason_obj: "SellReason",
    pnl_sign: str,
    pnl_emoji: str,
    return_rate: float,
    realized_pnl_abs: float,
    order_no: str,
) -> None:
    """자동매도 체결 알림을 사용자 언어로 발송한다(두 매도 실행 경로 공용)."""
    lang = _resolve_lang(user_id)
    total_amount_usd = filled_price * filled_qty
    send_message_async(
        user_id,
        I18n.get_msg(
            lang,
            "telegram.sell_filled",
            strategy_name=strategy_name,
            ticker=ticker,
            ticker_name=ticker_name,
            filled_price=filled_price,
            filled_price_krw=filled_price * exchange_rate,
            filled_qty=filled_qty,
            total_amount_usd=total_amount_usd,
            total_amount_krw=total_amount_usd * exchange_rate,
            sell_reason=render_sell_reason(sell_reason_obj, lang),
            pnl_emoji=pnl_emoji,
            pnl_sign=pnl_sign,
            return_rate=return_rate,
            realized_pnl_abs=realized_pnl_abs,
            order_no=order_no,
        ),
    )

# 매수 실패(단가 초과, 예수금 부족) 알림 도배 방지용 쿨타임 캐시 (1시간)
WARNING_COOLDOWN_CACHE = {}
MARKET_CLOSED_LOG_CACHE = {}
SCANNER_CACHE_EMPTY_LOG_CACHE = {}
LOG_COOLDOWN_SECONDS = 1800.0

# 💡 동적 손절선 및 트레일링 스탑 이탈 연속 횟수 추적 캐시 (Whipsaw 방지용 연속 2회 확정 가드)
# 키: (user_id, ticker) -> 값: int (연속 이탈 횟수)
BREACH_COUNT_CACHE = {}
_breach_count_lock = threading.Lock()


def _clear_exit_breach_clock(ctx, h) -> None:
    """봇 소유 손절 노이즈 버퍼의 이탈 시작 시각을 되돌린다.

    관측 횟수(BREACH_COUNT_CACHE)를 되돌리는 곳에서는 반드시 시각도 함께 되돌려야 한다.
    둘 중 하나만 지우면 다음 이탈이 남은 축을 이미 충족한 상태로 시작한다 - 방어 게이트에서
    실제로 겪은 결함이라 같은 실수를 반복하지 않도록 한 함수로 묶는다.

    version_id 낙관적 잠금을 건드리지 않도록 ORM flush가 아닌 Core UPDATE를 쓴다.
    """
    if not (isinstance(h, Holding) and getattr(h, "id", None) is not None):
        return
    if getattr(h, "exit_breach_started_at", None) is None:
        return
    with micro_session(ctx) as db:
        db.query(Holding).filter(Holding.id == h.id).update(
            {Holding.exit_breach_started_at: None}, synchronize_session=False,
        )
        db.commit()

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

# 매매 사이클의 실제 주기를 코드가 스스로 기록한다.
#
# main_trade_job은 interval 1분으로 등록되어 있으나 실제 간격은 그보다 길다. APScheduler의
# interval 트리거는 "직전 완료"가 아니라 "직전 예정 시각"에서 다음 시각을 뽑고, 잡 기본값이
# max_instances=1이라 사이클이 60초를 넘기면 그 사이에 낀 틱이 통째로 버려진다. 즉 사이클이
# 61초 걸리면 다음 실행은 60초 뒤가 아니라 120초 뒤다.
#
# 이 값을 추정이 아니라 관측으로 다루려고 사이클마다 직전 시작 시각과의 간격을 남긴다.
# 사이클 수를 시간처럼 쓰는 코드는 전부 이 간격만큼 조용히 늘어지므로, 그런 게이트를
# 벽시계로 바꿀지 판단하려면 실측값이 있어야 한다.
_last_cycle_started_at: float | None = None
latest_scanned_signals = [] # 글로벌 실시간 마켓 스캔 시그널 캐시용
latest_watchlist_signals = {} # 사용자별 라우팅 전에만 사용하는 관심종목 분석 캐시

# 💡 KIS API 동시성 제어 세마포어 (초당 최대 15회 호출로 자동 제한 - 429 차단 철벽 방어)
# asyncio.Semaphore는 경합 시점의 이벤트 루프에 바인딩된다. 이 프로세스는 메인 uvicorn 루프 외에도
# APScheduler 잡들이 asyncio.run으로 만드는 단명 루프를 매 사이클 생성하므로, 단일 전역 인스턴스를
# 공유하면 "bound to a different event loop" RuntimeError로 유저 트레이딩 사이클이 통째로 중단된다.
# 루프별 인스턴스를 발급해 실제 동시성이 몰리는 동일 루프 내 gather 경합은 그대로 15로 제한한다.
# (scanner.get_sentiment_lock도 동일 패턴 — id 재사용 충돌과 누수를 막기 위해
#  WeakKeyDictionary로 루프 수명에 자동 연동한다. 루프 간 총합 상한은 브로커 rate limiter가 재차 방어)
KIS_MAX_CONCURRENT_CALLS = 15
_kis_semaphores: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = weakref.WeakKeyDictionary()
_kis_semaphores_lock = threading.Lock()


def get_kis_semaphore() -> asyncio.Semaphore:
    """현재 실행 중인 이벤트 루프 전용 KIS 동시성 세마포어를 반환합니다 (루프별 1개, 루프 소멸 시 자동 회수)."""
    loop = asyncio.get_running_loop()
    sem = _kis_semaphores.get(loop)
    if sem is None:
        with _kis_semaphores_lock:
            sem = _kis_semaphores.get(loop)
            if sem is None:
                sem = asyncio.Semaphore(KIS_MAX_CONCURRENT_CALLS)
                _kis_semaphores[loop] = sem
    return sem


async def safe_broker_call(func, *args, **kwargs):
    """
    KIS API의 초당 호출 제한(Rate Limit)을 철저히 준수하기 위해 동시성 세마포어 가드 하에
    동기식 브로커 함수를 비동기 스레드 풀(asyncio.to_thread)에서 안전하게 지연 호출합니다.
    """
    async with get_kis_semaphore():
        # 호출 사이에 아주 미세한 지연(40ms)을 주어 고르게 배분
        await asyncio.sleep(0.04)
        return await asyncio.to_thread(func, *args, **kwargs)


def _schedule_background_task(coro, task_name: str):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()

    def _log_task_result(done) -> None:
        # 취소 예외는 어느 쪽 Future냐에 따라 클래스가 다르다. run_coroutine_threadsafe가 주는
        # concurrent.futures.Future는 concurrent.futures.CancelledError를, asyncio Task는
        # asyncio.CancelledError를 던지며 이 둘은 서로 다른 클래스다(전자만 Exception 하위).
        # asyncio 쪽만 잡으면 스레드세이프 경로의 취소가 전부 ERROR+스택트레이스로 둔갑한다.
        try:
            done.result()
        except (asyncio.CancelledError, concurrent.futures.CancelledError):
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

    lang = _resolve_lang(ctx.user_id)
    side_label = I18n.get_msg(lang, "telegram.side.sell" if side == "SELL" else "telegram.side.buy")
    status_key = {"SUBMITTED": "submitted", "FILLED": "filled", "PARTIAL": "partial", "REJECTED": "rejected"}.get(status)
    status_label = I18n.get_msg(lang, f"telegram.order_status.{status_key}", default=status) if status_key else status

    send_message_async(
        ctx.user_id,
        I18n.get_msg(
            lang,
            "telegram.order_pending_wait",
            ticker=ticker,
            side=side_label,
            status_label=status_label,
            status=status,
            order_no=order_no or "UNKNOWN",
        ),
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
    try:
        real_holdings = await safe_broker_call(ctx.broker.get_holdings, exchange_rate=ctx.exchange_rate)

        # ⚠️ 브로커 응답을 티커 단위로 먼저 합산한다. 아래 비교는 db_total_qty(그 티커의 모든
        #    슬라이스 합계)를 상대로 하므로, 브로커가 슬라이스·로트별로 여러 행을 주면 한 행의
        #    수량이 전체 합계와 대조되어 없는 차분을 만들어낸다. 실제로 시뮬레이터의
        #    get_holdings는 Holding 행마다 1개씩 내보내며, 같은 티커를 봇 슬롯과 EXTERNAL로
        #    나눠 든 상태에서 40주(25+15)가 15주로 줄고 EXTERNAL 행이 체결 로그 없이 사라졌다
        #    (2026-09-06 stock-auto-mobile 세션 실환경 보고). 차감이 EXTERNAL부터 이뤄지므로
        #    하필 이 기능이 보호하려는 행이 먼저 파괴된다.
        #    브로커 어댑터마다 응답 형태가 다를 수 있으므로 소비 측에서 정규화한다.
        aggregated: dict[str, dict] = {}
        for rh in real_holdings or []:
            t = rh.get("ticker", "")
            q = int(rh.get("quantity", 0) or 0)
            if not t or q <= 0:
                continue
            entry = aggregated.setdefault(
                t, {"ticker": t, "quantity": 0, "cost": 0.0, "ticker_name": rh.get("ticker_name", t)}
            )
            entry["quantity"] += q
            entry["cost"] += float(rh.get("avg_price", 0.0) or 0.0) * q
        for entry in aggregated.values():
            # 평단은 수량 가중평균으로 되돌린다. 유령 보유 복원 시 avg_price로 쓰인다.
            entry["avg_price"] = entry["cost"] / entry["quantity"] if entry["quantity"] else 0.0

        with micro_session(ctx) as db:
            db_holdings_by_ticker = {}
            for db_h in ctx.holdings:
                db_holdings_by_ticker.setdefault(db_h.ticker, []).append(db_h)

            real_ticker_set = set()

            for rh in aggregated.values():
                r_ticker = rh["ticker"]
                r_qty = int(rh["quantity"])
                r_price = float(rh["avg_price"])
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
                    # 차분을 어느 슬라이스에 배분할지는 임의로 정하면 안 된다. 봇 주문이 아직
                    # 원장에 반영되지 않은 상태에서 EXTERNAL부터 건드리면 사용자의 외부 보유분이
                    # 봇 주문 때문에 늘거나 줄어든다. 미해결 주문 유무로 원인을 갈라 우선순위를 뒤집는다.
                    bot_order_pending = has_unresolved_orders_for_ticker(db, ctx.user_id, r_ticker)
                    if diff > 0:
                        # 증가분의 기본 해석은 "사용자가 앱 밖에서 추가 매수했다"이므로 EXTERNAL이 받는다.
                        # 봇 주문이 미해결이면 체결 반영 지연일 수 있어 기존처럼 봇 슬라이스가 받는다.
                        target_db_h = None
                        if not bot_order_pending:
                            target_db_h = next(
                                (h for h in db_hs if h.management == MANAGEMENT_EXTERNAL), None
                            )
                        if target_db_h is None and not bot_order_pending:
                            target_db_h = Holding(
                                user_id=ctx.user_id,
                                ticker=r_ticker,
                                strategy_type=EXTERNAL_STRATEGY_TYPE,
                                management=MANAGEMENT_EXTERNAL,
                                ticker_name=r_name,
                                avg_price=r_price,
                                quantity=0,
                                highest_price=r_price,
                                regime_mode=ctx.sentiment,
                                buy_stage=1,
                            )
                            db.add(target_db_h)
                        if target_db_h is None:
                            target_db_h = db_hs[0]
                        old_qty = target_db_h.quantity or 0
                        target_db_h.quantity = old_qty + diff
                        db.commit()
                        log_action(
                            db,
                            ctx.user_id,
                            f"[Sync Guard] Quantity increased for {r_ticker} "
                            f"({target_db_h.strategy_type}/{target_db_h.management}): "
                            f"{old_qty} -> {target_db_h.quantity} (Total: {r_qty})",
                            "WARNING"
                        )
                    elif diff < 0:
                        # 감소분의 기본 해석은 "사용자가 앱 밖에서 매도했다"이므로 EXTERNAL부터 깎는다.
                        # 봇 주문이 미해결이면 봇 매도의 반영 지연이므로 봇 슬라이스부터 깎는다.
                        # 차감 순서는 EXTERNAL -> DELEGATED -> BOT_OWNED다.
                        # 사용자가 앱 밖에서 판 물량은 사용자가 직접 관리하는 슬라이스에서
                        # 나갔다고 보는 것이 가장 그럴듯하고, 봇이 산 슬라이스를 먼저 깎으면
                        # 봇의 성과 원장이 실제로 하지 않은 매도로 오염된다.
                        # 위임분이 가운데인 이유는 소유는 사용자, 관할은 봇이기 때문이다.
                        #
                        # 봇 주문이 미해결이면 해석이 뒤집힌다. 그 감소는 봇 매도의 반영 지연일
                        # 가능성이 높으므로 봇 슬라이스부터 깎는다.
                        _deduction_rank = {
                            MANAGEMENT_EXTERNAL: 0,
                            MANAGEMENT_DELEGATED: 1,
                            MANAGEMENT_BOT_OWNED: 2,
                        }

                        def _deduction_key(h):
                            rank = _deduction_rank.get(
                                h.management or MANAGEMENT_BOT_OWNED,
                                _deduction_rank[MANAGEMENT_BOT_OWNED],
                            )
                            return -rank if bot_order_pending else rank

                        deduction_order = sorted(db_hs, key=_deduction_key)
                        remaining_deduction = abs(diff)
                        for h in deduction_order:
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
                                    f"[Sync Guard] Quantity deducted for {r_ticker} "
                                    f"({h.strategy_type}/{h.management}): "
                                    f"{old_qty} -> {h.quantity} (Deducted: {deduct})",
                                    "WARNING"
                                )
                                if h.quantity == 0:
                                    delete_holding(db, h, actor="scheduler.sync_broker_holdings",
                                                   reason="quantity deducted to zero by sync guard")
                        db.commit()
                else:
                    last_buy = db.query(TradeLog).filter(
                        TradeLog.user_id == ctx.user_id,
                        TradeLog.ticker == r_ticker,
                        TradeLog.trade_type == "BUY"
                    ).order_by(TradeLog.executed_at.desc()).first()

                    # 기본값은 EXTERNAL이다. 봇 매수 이력이 없는 계좌 보유분은 사용자가 직접 산
                    # 종목이며, 이것을 첫 번째 전략 슬롯에 꽂으면 다음 사이클에 손절·시그널 붕괴
                    # 판정 대상이 되어 그대로 청산된다(2026-09-05 HCTI 실측). 봇 관할 밖으로 둔다.
                    if last_buy is not None:
                        target_strategy = last_buy.strategy_type
                        target_management = MANAGEMENT_BOT_OWNED
                        log_action(
                            db,
                            ctx.user_id,
                            f"[Self-Healing] Phantom holding detected in account: {r_ticker} (Qty: {r_qty}). "
                            f"Restoring DB record under strategy {target_strategy}!",
                            "ERROR"
                        )
                    else:
                        target_strategy = EXTERNAL_STRATEGY_TYPE
                        target_management = MANAGEMENT_EXTERNAL
                        log_action(
                            db,
                            ctx.user_id,
                            f"[External Holding] Registered broker position without bot buy history: "
                            f"{r_ticker} (Qty: {r_qty}). Bot will not trade this position.",
                            "INFO"
                        )

                    db.add(Holding(
                        user_id=ctx.user_id,
                        ticker=r_ticker,
                        strategy_type=target_strategy,
                        management=target_management,
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
                    delete_holding(db, db_h, actor="scheduler.sync_broker_holdings",
                                   reason="sweep: ticker absent from broker account")
                    db.commit()

            ctx.holdings = db.query(Holding).filter(Holding.user_id == ctx.user_id).all()
    except Exception as sync_err:
        with micro_session(ctx) as db:
            log_action(db, ctx.user_id, f"[Self-Healing] Failed to sync holding discrepancy: {sync_err}", "ERROR")


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
                                delete_holding(db, h_db, actor="scheduler.process_autonomous_slots",
                                               reason="regime exit fully filled")
                            else:
                                h_db.quantity -= filled_qty
                        db.commit()
                        log_action(db, user_id, f"[{strategy.name}] SUCCESS: {asset} regime exit ({filled_qty} shares) | Order: {res['order_no']}", "INFO")

                    realized_pnl = float(pnl.realized_pnl)
                    pnl_sign = "+" if realized_pnl >= 0 else "-"
                    pnl_emoji = "📈" if realized_pnl >= 0 else "📉"
                    send_message_async(
                        user_id,
                        I18n.get_msg(
                            _resolve_lang(user_id),
                            "telegram.regime_exit",
                            strategy_name=strategy.name,
                            asset=asset,
                            filled_price=filled_price,
                            filled_qty=filled_qty,
                            sma_period=strategy.sma_period,
                            confirm_days=strategy.confirm_days,
                            pnl_emoji=pnl_emoji,
                            pnl_sign=pnl_sign,
                            return_rate=abs(float(pnl.return_rate)),
                            realized_pnl_abs=abs(realized_pnl),
                            order_no=res["order_no"],
                        ),
                    )
                elif res.get("success"):
                    _log(f"[{strategy.name}] SELL order submitted (pending fill): {asset} x{sell_qty} | {res.get('order_no', '')}", "INFO")
                else:
                    _log(f"[{strategy.name}] SELL FAILED: {asset} | {res.get('message', '')}", "ERROR")
        finally:
            await symbol_lease.release()


class _HarvestPseudoStrategy:
    """수확 모드 매도가 Part B의 공통 실행부를 그대로 타기 위한 최소 스텁.

    EXTERNAL 보유분에는 전략 인스턴스가 없다(strategy_type이 'external'이라 슬롯 조회가
    비어 있다). Part B가 strategy_instance에서 쓰는 것은 표시용 name 하나뿐이므로,
    매도 경로를 복제하는 대신 이름만 갖는 스텁을 넘긴다.
    """
    name = "수확 모드"
    is_autonomous = False


HARVEST_PSEUDO_STRATEGY = _HarvestPseudoStrategy()


# 방어 경보의 고정 평가자. 사용자가 어떤 전략을 쓰든 외부 보유 경보는 같은 잣대로 판정한다.
# 전략별 평가자를 쓰면 (1) 외부 보유는 어떤 전략으로도 진입한 적이 없어 그 잣대를 들이댈
# 근거가 없고, (2) 사용자가 전략을 바꿨다고 기존 보유 종목의 경보 기준이 흔들린다.
# 점수는 절대값이 아니라 켠 시점 대비 변화량으로만 쓰이므로 평가자 선택이 판정을 좌우하지는
# 않지만, 기준이 사이에서 바뀌면 변화량 자체가 무의미해지므로 고정이 필요하다.
GUARD_EVALUATOR_STRATEGY = "regime_switching"
_guard_evaluator = None


def _get_guard_evaluator():
    global _guard_evaluator
    if _guard_evaluator is None:
        from app.strategies.strategy_factory import get_strategy
        _guard_evaluator = get_strategy(GUARD_EVALUATOR_STRATEGY)
    return _guard_evaluator


class _GuardPseudoStrategy:
    """방어 청산이 Part B의 공통 실행부를 타기 위한 최소 스텁(수확과 같은 사유)."""
    name = "방어 청산"
    is_autonomous = False


GUARD_PSEUDO_STRATEGY = _GuardPseudoStrategy()


async def _evaluate_guard(
    ctx: TradingFlowContext,
    h,
    current_data: dict,
    current_price_dec: Decimal,
    _log,
):
    """EXTERNAL 보유분의 방어 판정. 조치가 필요하면 Part B 인자 튜플을, 아니면 None을 반환한다.

    판정은 상태가 아니라 전이를 본다. -50% 물린 종목은 십중팔구 이미 점수가 붕괴선
    아래이므로, 절대선으로 판정하면 켜는 순간 즉시 경보가 되어 이 프로젝트가 처음에
    문제 삼았던 '관측 시작 즉시 청산'이 이름만 바꿔 재현된다.

    이 함수는 직접 주문을 내지 않는다. 청산이 필요하다고 판단해도 Part B가 집행하도록
    인자만 돌려준다 - 판정과 집행을 섞으면 되돌릴 수 없는 주문이 판정 로직 안에 숨는다.
    """
    if not getattr(h, "guard_enabled", False):
        return None
    if not isinstance(h, Holding) or h.id is None:
        return None

    clean_ticker = h.ticker
    try:
        evaluator = _get_guard_evaluator()
        current_score = float(
            evaluator.calculate_score(
                current_data.get("details") or current_data, ctx.sentiment, is_entry=False
            )
        )
    except Exception as score_err:
        _log(f"[Guard] Score evaluation failed for {clean_ticker}: {score_err}", "WARNING")
        return None

    now = utc_now_aware()

    with micro_session(ctx) as db:
        row = db.query(
            Holding.guard_baseline_score,
            Holding.guard_baseline_low,
            Holding.guard_enabled_at,
            Holding.guard_last_alert_at,
            Holding.guard_action,
            Holding.guard_sell_ratio,
            Holding.guard_streak,
            Holding.guard_last_action_at,
            Holding.guard_streak_started_at,
        ).filter(Holding.id == h.id).first()
        if row is None:
            return None
        (
            baseline_score, baseline_low, enabled_at, last_alert_at,
            guard_action, sell_ratio, streak, last_action_at, streak_started_at,
        ) = row

        # 켠 직후 첫 사이클에 기준선을 박는다. API가 켤 때는 시세를 모르므로 여기서 채운다.
        if baseline_score is None or baseline_low is None:
            db.query(Holding).filter(Holding.id == h.id).update(
                {
                    Holding.guard_baseline_score: current_score,
                    Holding.guard_baseline_low: current_price_dec,
                    Holding.guard_enabled_at: enabled_at or now,
                    Holding.guard_streak: 0,
                },
                synchronize_session=False,
            )
            db.commit()
            _log(
                f"[Guard] Baseline set for {clean_ticker}: score {current_score:.1f}, "
                f"low ${float(current_price_dec):.2f}. mode={(guard_action or 'ALERT_ONLY').lower()}.",
                "INFO",
            )
            return None

        # 저가 래칫은 매 사이클 갱신한다(단조 감소). 반등해도 기준선은 따라 올라가지 않는다.
        new_low = compute_guard_low(baseline_low, current_price_dec)
        if new_low < to_decimal(baseline_low):
            db.query(Holding).filter(Holding.id == h.id).update(
                {Holding.guard_baseline_low: new_low}, synchronize_session=False,
            )
            db.commit()

    # 유예기간 - 켜자마자 울리는 오발동을 막는다.
    if enabled_at is not None:
        elapsed_min = (now - enabled_at).total_seconds() / 60.0
        if elapsed_min < GUARD_GRACE_MINUTES:
            return None

    # 판정에는 갱신 전 기준선을 쓴다. 방금 내린 저가로 자기 자신을 비교하면 영원히 거짓이다.
    breached = check_guard_breach(
        current_score, baseline_score, current_price_dec, baseline_low
    )

    # 연속 충족 카운터. 조치(청산)는 경보보다 훨씬 엄격한 지속성을 요구하므로 DB에 누적한다.
    # 인메모리 캐시로 두면 재기동이 카운터를 리셋해 조치가 영영 안 나거나, 반대로 조건이
    # 끊겼다가 이어진 것을 연속으로 오인한다.
    new_streak = (streak or 0) + 1 if breached else 0
    # 연속이 처음 시작되는 순간의 시각을 박아둔다. 사이클 주기가 흔들려도 이 값 덕에
    # 실제 지속 시간을 알 수 있고, 알림에도 참값을 적을 수 있다.
    new_started_at = None if not breached else (streak_started_at or now)
    if new_streak != (streak or 0):
        with micro_session(ctx) as db:
            db.query(Holding).filter(Holding.id == h.id).update(
                {
                    Holding.guard_streak: new_streak,
                    Holding.guard_streak_started_at: new_started_at,
                },
                synchronize_session=False,
            )
            db.commit()

    if not breached:
        return None

    action = (guard_action or GUARD_ACTION_ALERT_ONLY).upper()

    # --- 경보: 조치 모드와 무관하게 동일한 쿨다운으로 보낸다 ---
    alert_due = (
        last_alert_at is None
        or (now - last_alert_at).total_seconds() / 3600.0 >= GUARD_ALERT_COOLDOWN_HOURS
    )
    if alert_due:
        with micro_session(ctx) as db:
            db.query(Holding).filter(Holding.id == h.id).update(
                {Holding.guard_last_alert_at: now}, synchronize_session=False,
            )
            db.commit()
        _log(
            f"[Guard] ALERT {clean_ticker}: score {baseline_score:.1f} -> {current_score:.1f}, "
            f"new low ${float(current_price_dec):.2f} (was ${float(baseline_low):.2f}). "
            f"mode={action.lower()}.",
            "WARNING",
        )
        send_message_async(
            ctx.user_id,
            I18n.get_msg(
                _resolve_lang(ctx.user_id),
                "telegram.guard_alert",
                ticker=clean_ticker,
                ticker_name=h.ticker_name or clean_ticker,
                baseline_score=float(baseline_score),
                current_score=current_score,
                baseline_low=float(baseline_low),
                current_price=float(current_price_dec),
            ),
        )

    # --- 조치: 알림만 모드는 여기서 끝난다 ---
    if action == GUARD_ACTION_ALERT_ONLY:
        return None

    # 지속 요구 - 수확의 2사이클보다 훨씬 엄격하다. 조치의 최악은 되돌릴 수 없는 손실 확정이다.
    # 사이클 수와 실제 경과 시간을 모두 요구한다. 사이클만 쓰면 주기 변동(실측 104~846초)에
    # 따라 같은 10사이클이 20분일 수도 두 시간일 수도 있고, 시간만 쓰면 관측이 성긴 구간에서
    # 한두 번의 판정으로 조치가 나간다.
    if new_streak < GUARD_SUSTAIN_CYCLES:
        return None
    sustained_minutes = (
        (now - new_started_at).total_seconds() / 60.0 if new_started_at else 0.0
    )
    if sustained_minutes < GUARD_SUSTAIN_MINUTES:
        return None

    # 일일 캡 - 무너지는 날 같은 보유분을 반복 청산하지 않는다.
    if last_action_at is not None:
        if (now - last_action_at).total_seconds() / 3600.0 < GUARD_ACTION_COOLDOWN_HOURS:
            return None

    sell_qty = resolve_guard_sell_qty(h.quantity or 0, sell_ratio)
    if sell_qty <= 0:
        return None

    with micro_session(ctx) as db:
        db.query(Holding).filter(Holding.id == h.id).update(
            {
                Holding.guard_last_action_at: now,
                Holding.guard_streak: 0,
                Holding.guard_streak_started_at: None,
            },
            synchronize_session=False,
        )
        db.commit()

    # --- 섀도: 팔았다면 어땠을지만 남기고 주문은 내지 않는다 ---
    # 이 로그가 5단계 착수 근거를 만드는 측정 원천이다. 사람이 경보 로그를 눈으로
    # 상관분석하는 대신, 조치 시점의 가격·점수·수량을 기계 판독 가능한 형식으로 남긴다.
    if action == GUARD_ACTION_SHADOW:
        _log(
            f"[Guard][SHADOW] {clean_ticker} would_sell_qty={sell_qty} "
            f"price={float(current_price_dec):.4f} score={current_score:.1f} "
            f"baseline_score={baseline_score:.1f} baseline_low={float(baseline_low):.4f} "
            f"streak={new_streak} sustained_min={sustained_minutes:.1f} | no order placed",
            "WARNING",
        )
        # 기록을 로그에만 남기면 사용자가 볼 방법이 없다 - 이 모드를 볼 수 있는 화면이
        # 저장소에 없기 때문이다(ActionLog는 관리자 패널에만 노출된다). 측정 결과가
        # 손에 들어와야 모드가 쓸모를 갖는다. 조치 시점은 10사이클 지속 + 일일 1회로
        # 이미 좁혀져 있으므로 알림이 잦아지지 않는다.
        send_message_async(
            ctx.user_id,
            I18n.get_msg(
                _resolve_lang(ctx.user_id),
                "telegram.guard_shadow",
                ticker=clean_ticker,
                ticker_name=h.ticker_name or clean_ticker,
                # 사이클 수가 아니라 실제 경과 시간을 적는다. 주기가 흔들리므로
                # 사이클을 분으로 환산하면 거짓이 된다(실측 104~846초).
                minutes=int(sustained_minutes),
                current_price=float(current_price_dec),
                sell_qty=sell_qty,
                total_qty=int(h.quantity or 0),
                proceeds=float(current_price_dec) * sell_qty,
            ),
        )
        return None

    # --- 실제 부분 청산 ---
    sell_reason_obj = SellReason(
        "guard_liquidate",
        {
            "baseline_score": float(baseline_score),
            "current_score": float(current_score),
            "baseline_low": float(baseline_low),
            "sell_qty": sell_qty,
        },
    )
    sell_reason = "방어 청산 (추가 악화 + 신저가 지속)"
    _log(
        f"[Guard] LIQUIDATE {clean_ticker}: selling {sell_qty}/{h.quantity} shares "
        f"(streak {new_streak}, score {baseline_score:.1f} -> {current_score:.1f})",
        "WARNING",
    )

    is_kis_order = (ctx.trade_mode or "").upper() in {"MOCK", "REAL"}
    metadata = None
    if is_kis_order:
        metadata = await safe_broker_call(ctx.broker.get_order_metadata, clean_ticker, ctx.session)

    return (
        h,
        float(current_price_dec),
        sell_reason,
        sell_reason_obj,
        clean_ticker,
        GUARD_PSEUDO_STRATEGY,
        int(current_score),
        h.strategy_type,
        metadata,
        sell_qty,
    )


def _persist_harvest_thresholds(
    ctx: TradingFlowContext,
    h,
    current_data: dict,
    current_price_dec: Decimal,
) -> None:
    """EXTERNAL 보유분의 수확 임계값을 화면 표시용으로 DB에 남긴다.

    판정에는 관여하지 않는다. _evaluate_harvest는 종전대로 자기 사이클의 값을 다시 계산해
    쓰며, 여기 저장된 값이 낡거나 NULL이어도 판정 결과는 달라지지 않는다. 표시 전용이므로
    실패해도 사이클을 중단시키지 않는다.

    version_id를 건드리지 않는 Core UPDATE를 쓰는 이유는 last_price·highest_price와 같다 -
    공유 detached holding의 매핑 컬럼을 세팅하면 다음 micro_session의 auto-merge가 이를
    flush하며 version을 올리고, Part B 매도의 db.merge(h)가 StaleDataError로 사이클을 깬다.
    """
    if not isinstance(h, Holding) or h.id is None:
        return

    atr = current_data.get("details", {}).get("atr", 0.0)
    current_price = float(current_price_dec)
    arm_pct = round(get_harvest_arm_pct(atr, current_price), 2)
    trailing_pct = round(get_harvest_trailing_pct(atr, current_price), 2)

    # 값이 그대로면 쓰지 않는다. ATR은 사이클마다 미세하게 흔들리므로 소수점 2자리로 끊어
    # 비교해야 의미 없는 UPDATE가 매 사이클 쌓이지 않는다.
    def _same(stored, computed) -> bool:
        return stored is not None and round(float(stored), 2) == computed

    if _same(getattr(h, "harvest_arm_pct", None), arm_pct) and _same(
        getattr(h, "harvest_trailing_pct", None), trailing_pct
    ):
        return

    try:
        with micro_session(ctx) as db:
            db.query(Holding).filter(Holding.id == h.id).update(
                {
                    Holding.harvest_arm_pct: arm_pct,
                    Holding.harvest_trailing_pct: trailing_pct,
                },
                synchronize_session=False,
            )
            db.commit()
    except Exception as exc:  # noqa: BLE001 - 표시용 값이므로 사이클을 깨뜨리지 않는다
        logger.warning(f"[Harvest] 임계값 기록 실패 {h.ticker}: {exc}")
        return

    # 여기서 h.harvest_arm_pct에 같은 값을 덧쓰지 않는다. 매핑 컬럼을 세팅하면 공유 detached
    # holding이 dirty가 되어 위 독스트링이 경고한 경로(auto-merge의 version 상승)로 들어간다.
    # 덧쓸 이득도 없다 - 위의 중복 쓰기 방지 비교는 사이클마다 DB에서 새로 읽은 값을 보고,
    # 한 사이클 안에서 같은 보유분을 두 번 처리하지 않는다.


async def _evaluate_harvest(
    ctx: TradingFlowContext,
    h,
    current_data: dict,
    current_price_dec: Decimal,
    dec_highest_price: Decimal,
    _log,
):
    """EXTERNAL 보유분의 수확 판정. 매도해야 하면 Part B 인자 튜플을, 아니면 None을 반환한다.

    이 함수는 급등 후 꺾임만 본다. 손절도 시그널 붕괴 청산도 하지 않는다 - 그것들은
    봇이 진입 근거를 가진 포지션에만 적용되는 규칙이고, 사용자가 산 종목에 적용하면
    관측 시작 즉시 청산이 된다(2026-09-05 HCTI 실측).
    """
    if not getattr(h, "harvest_enabled", False):
        return None

    # 스냅샷 우선. 매핑 컬럼은 detached 상태에서 Core UPDATE 결과를 반영하지 않는다.
    observed_base = to_decimal(
        getattr(h, "observed_base_snapshot", None)
        or getattr(h, "observed_base_price", None)
    )
    if observed_base <= 0:
        return None

    armed = getattr(h, "harvest_armed_snapshot", None)
    if armed is None:
        armed = bool(getattr(h, "harvest_armed", False))

    clean_ticker = h.ticker
    atr = current_data.get("details", {}).get("atr", 0.0)
    current_price = float(current_price_dec)

    # --- 무장: 급등해야 감시가 시작된다. 그 전에는 아무것도 하지 않는다 ---
    if not armed:
        arm_pct = get_harvest_arm_pct(atr, current_price)
        if not check_harvest_arm(current_price_dec, observed_base, arm_pct):
            return None

        gain_pct = float(
            (current_price_dec - observed_base) / observed_base * Decimal("100")
        )
        trailing_pct = get_harvest_trailing_pct(atr, current_price)
        stop_price = float(current_price_dec * (Decimal("1") - to_decimal(trailing_pct) / Decimal("100")))
        # 무장 시점부터 새로 추적한다. 무장 전 고점을 물려받으면 무장 직후 이미 이탈 상태일 수 있다.
        if isinstance(h, Holding) and h.id is not None:
            with micro_session(ctx) as db:
                db.query(Holding).filter(Holding.id == h.id).update(
                    {Holding.harvest_armed: True, Holding.highest_price: current_price_dec},
                    synchronize_session=False,
                )
                db.commit()
        h.harvest_armed_snapshot = True
        _log(
            f"[Harvest] ARMED {clean_ticker}: +{gain_pct:.1f}% from observed base "
            f"${float(observed_base):.2f}. Trailing {trailing_pct:.1f}% (stop ~${stop_price:.2f}).",
            "SIGNAL",
        )
        send_message_async(
            ctx.user_id,
            I18n.get_msg(
                _resolve_lang(ctx.user_id),
                "telegram.harvest_armed",
                ticker=clean_ticker,
                ticker_name=h.ticker_name or clean_ticker,
                gain_pct=gain_pct,
                base_price=float(observed_base),
                current_price=current_price,
                trailing_pct=trailing_pct,
                stop_price=stop_price,
            ),
        )
        return None

    # --- 추적: 무장 뒤에는 고점 대비 이탈만 본다 ---
    trailing_pct = get_harvest_trailing_pct(atr, current_price)
    now = utc_now_aware()
    cache_key = (ctx.user_id, h.ticker, h.strategy_type)

    def _clear_breach_clock() -> None:
        if getattr(h, "harvest_breach_started_at", None) is None:
            return
        with micro_session(ctx) as db:
            db.query(Holding).filter(Holding.id == h.id).update(
                {Holding.harvest_breach_started_at: None}, synchronize_session=False,
            )
            db.commit()
        h.harvest_breach_started_at = None

    if not check_harvest_breach(current_price_dec, dec_highest_price, trailing_pct, observed_base):
        # 회복하면 관측 횟수와 시각을 함께 되돌린다. 둘 중 하나만 지우면 다음 이탈에서
        # 남은 축이 이미 충족된 상태로 시작한다(방어 게이트에서 실제로 겪은 결함이다).
        with _breach_count_lock:
            BREACH_COUNT_CACHE.pop(cache_key, None)
        _clear_breach_clock()
        return None

    # 노이즈 버퍼 - 순간적으로 찔렀다 돌아오는 꼬리에 털리지 않는다.
    #
    # 관측 횟수와 실제 경과 시간을 모두 요구한다. 사이클 수만 쓰면 주기 변동(실측 104~846초)에
    # 따라 같은 2사이클이 3분일 수도 30분일 수도 있다. 횟수는 표본이 성긴 구간에서 한 번에
    # 파는 것을 막고, 시간은 주기가 빨라졌을 때의 하한을 준다.
    #
    # 횟수는 인메모리로 센다 - 재기동하면 두 번을 다시 관측해야 하지만 그것은 무해하다.
    # 반면 시각은 DB에 둔다. 재기동이 대기를 0으로 되돌리면 급등이 꺾인 뒤에도 매도가 계속 미뤄진다.
    breach_started_at = getattr(h, "harvest_breach_started_at", None) or now
    if getattr(h, "harvest_breach_started_at", None) is None:
        with micro_session(ctx) as db:
            db.query(Holding).filter(Holding.id == h.id).update(
                {Holding.harvest_breach_started_at: breach_started_at}, synchronize_session=False,
            )
            db.commit()
        h.harvest_breach_started_at = breach_started_at

    with _breach_count_lock:
        BREACH_COUNT_CACHE[cache_key] = BREACH_COUNT_CACHE.get(cache_key, 0) + 1
        count = BREACH_COUNT_CACHE[cache_key]
    breach_minutes = (now - breach_started_at).total_seconds() / 60.0

    if count < HARVEST_SUSTAIN_CYCLES or breach_minutes < HARVEST_SUSTAIN_MINUTES:
        _log(
            f"[Harvest] {clean_ticker} breach below trailing stop "
            f"(peak ${float(dec_highest_price):.2f}, -{trailing_pct:.1f}%). "
            f"Delaying sell ({count}/{HARVEST_SUSTAIN_CYCLES} checks, "
            f"{breach_minutes:.1f}/{HARVEST_SUSTAIN_MINUTES}min).",
            "INFO",
        )
        return None

    _clear_breach_clock()

    sell_reason_obj = SellReason(
        "harvest",
        {
            "highest_price": float(dec_highest_price),
            "trailing_stop_pct": trailing_pct,
            "observed_base_price": float(observed_base),
        },
    )
    sell_reason = "수확 (급등 후 고점 이탈)"
    _log(
        f"[Harvest] EXIT SIGNAL: {clean_ticker} | peak ${float(dec_highest_price):.2f} "
        f"-> ${current_price:.2f} (-{trailing_pct:.1f}% trailing)",
        "SIGNAL",
    )

    is_kis_order = (ctx.trade_mode or "").upper() in {"MOCK", "REAL"}
    metadata = None
    if is_kis_order:
        metadata = await safe_broker_call(ctx.broker.get_order_metadata, clean_ticker, ctx.session)

    return (
        h,
        current_price,
        sell_reason,
        sell_reason_obj,
        clean_ticker,
        HARVEST_PSEUDO_STRATEGY,
        0,
        h.strategy_type,
        metadata,
    )


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
            # 봇이 사지 않은 외부 보유분은 매도 판정 대상이 아니다. 다만 루프 상단에서 통째로
            # 건너뛰면 관측(last_price·highest_price 갱신)까지 멈춰 잔고 평가금이 낡고, 3단계
            # 수확 모드가 붙을 때 고점 기록이 비어 눈이 먼다. 배제가 아니라 분기로 처리한다 —
            # 아래 공통 관측 구간까지는 함께 돌고 전략 판정 직전에 빠진다.
            is_external = getattr(h, "management", MANAGEMENT_BOT_OWNED) == MANAGEMENT_EXTERNAL
            strategy_instance = ms_manager.strategies.get(slot_key)
            if not is_external:
                if strategy_instance is None:
                    continue
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

            # 봇이 이 종목을 처음 본 가격을 한 번만 기록한다. 수확 모드의 무장 판정과 매도
            # 하한이 모두 이 값을 앵커로 쓴다. 등록 시점의 브로커 평단(사용자 매수가)이 아니라
            # 실제 관측가여야 한다 - 반토막 종목에서 본전을 앵커로 쓰면 무장이 영원히 안 된다.
            # ⚠️ h는 사이클 간 공유되는 detached 객체이고, 매핑 컬럼을 세팅하면 dirty가 되어
            #    auto-merge가 version_id를 올리고 Part B의 db.merge(h)가 StaleDataError로 죽는다
            #    (last_price·highest_price와 동일한 사유). 따라서 수확 상태도 매핑 컬럼을 직접
            #    건드리지 않고 version 비간섭 Core UPDATE + 비영속 스냅샷으로만 다룬다.
            #    스냅샷은 DB에서 되읽어 채운다 - 로컬 값으로 덮어쓰면 다음 사이클에 관측 시작가가
            #    현재가로 갱신되어 무장이 영원히 안 된다.
            if is_external and getattr(h, "observed_base_snapshot", None) is None:
                base_value = getattr(h, "observed_base_price", None)
                if isinstance(h, Holding) and h.id is not None:
                    with micro_session(ctx) as db:
                        db.query(Holding).filter(
                            Holding.id == h.id, Holding.observed_base_price.is_(None)
                        ).update(
                            {Holding.observed_base_price: current_price_dec},
                            synchronize_session=False,
                        )
                        db.commit()
                        row = db.query(
                            Holding.observed_base_price, Holding.harvest_armed
                        ).filter(Holding.id == h.id).first()
                        if row is not None:
                            base_value = row[0]
                            h.harvest_armed_snapshot = bool(row[1])
                h.observed_base_snapshot = to_decimal(base_value or current_price_dec)

            # 고점 갱신은 전략과 무관한 순수 관측이므로 판정 구간보다 앞에 둔다. 외부 보유분도
            # 이 지점까지는 함께 돌아 고점이 기록된다(수확 모드의 추적 기준점).
            dec_highest_price = to_decimal(h.highest_price or current_price_dec)
            if current_price_dec > dec_highest_price:
                dec_highest_price = current_price_dec
                peak_owner = strategy_instance.name if strategy_instance is not None else "External"
                _log(f"[{peak_owner}] New Peak for {clean_ticker}: ${current_price}", "SIGNAL")
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

            # ---- 공통 관측 구간 끝. 아래부터는 전략 판정이므로 봇 관할 보유분만 진입한다 ----
            if is_external:
                # 수확 임계값을 화면이 읽을 수 있도록 남긴다. 판정에는 쓰지 않는다 - 각 판정은
                # 종전대로 그 사이클에 계산한 값을 쓰고, 여기 저장하는 것은 관측 기록일 뿐이다.
                #
                # 잔고 API가 직접 계산하지 않는 이유는 ATR을 얻으려면 외부 시세 호출이 필요해서다
                # ("유저 대면 경로 외부 호출 0건" 원칙). 스케줄러는 어차피 매 사이클 이 값을
                # 계산하므로 결과만 옮겨 담는다.
                #
                # harvest_enabled와 무관하게 채우는 이유 - 켜기 전에 기준을 볼 수 있어야 켤지
                # 말지 판단할 수 있다. 켰을 때만 채우면 화면이 "켜봐야 알 수 있다"가 된다.
                _persist_harvest_thresholds(ctx, h, current_data, current_price_dec)

                # 두 스위치는 독립이다. 같이 켜면 위로 갔다 꺾이면 수확, 아래로 무너지면 방어다.
                # 방어가 먼저인 이유는 하락 국면에서 수확 조건이 성립할 수 없어 순서가 무해하고,
                # 반대로 상승 국면에서는 방어 조건이 성립할 수 없기 때문이다(둘은 배타적으로 발동한다).
                guard_args = await _evaluate_guard(
                    ctx, h, current_data, current_price_dec, _log,
                )
                if guard_args is not None:
                    sell_tasks_args.append(guard_args)
                    continue
                harvest_args = await _evaluate_harvest(
                    ctx, h, current_data, current_price_dec, dec_highest_price, _log,
                )
                if harvest_args is not None:
                    sell_tasks_args.append(harvest_args)
                continue

            profit_rate = calculate_profit_rate(current_price_dec, h.avg_price)

            # 리스크 판정의 앵커는 실제 매수가가 아니라 리스크 기준가다.
            #
            # 위임(DELEGATED) 포지션은 사용자가 이미 물려 있던 것을 봇이 넘겨받은 것이라
            # avg_price 기준으로 손절을 재면 인수 즉시 청산된다. 반토막 종목을 맡겼는데
            # 손절선 -8%가 이미 -50%로 뚫려 있기 때문이다. 트레일링·롤링박스의 하한 가드
            # (highest_price > 기준가)도 같은 이유로 영원히 거짓이 되어 발화하지 않는다.
            # 수확 모드가 observed_base_price를 앵커로 삼은 것과 정확히 같은 구조다.
            #
            # 반대로 실현손익·스마트이그짓은 avg_price를 그대로 쓴다. 사용자가 실제로 얼마에
            # 샀는지를 바꿔 기록하면 원장이 거짓말을 한다. 리스크만 분리하고 손익은 손대지 않는다.
            # risk_basis_price가 NULL인 기존 BOT_OWNED 레코드는 avg_price로 폴백하므로
            # 동작이 바뀌지 않는다.
            risk_basis_price = getattr(h, "risk_basis_price", None) or h.avg_price
            risk_profit_rate = calculate_profit_rate(current_price_dec, risk_basis_price)

            current_score = strategy_instance.calculate_score(current_data['details'] or current_data, sentiment, is_entry=False)
            is_smart_exit = current_data.get('details', {}).get('is_smart_exit', False)

            atr = current_data.get('details', {}).get('atr', 0.0)
            stop_loss_pct = strategy_instance.get_stop_loss_pct(atr, current_price)
            trailing_stop_pct = strategy_instance.get_trailing_stop_pct(atr, current_price)

            # 롤링 박스 스탑 래칫 갱신 (opt-in 전략 한정). highest_price와 동일 사유로
            # detached holding의 매핑 컬럼은 건드리지 않고 로컬 변수 + version 비간섭 Core UPDATE만 사용.
            use_rolling_box = bool(getattr(strategy_instance, "use_rolling_box_stop", False))
            dec_rolling_stop = to_decimal(getattr(h, "rolling_stop_price", None))
            if use_rolling_box:
                # 박스 길이는 전략이 '분' 단위로 선언하고, 라이브 15분봉 기준 봉 수로 환산한다.
                # 백테스트와 동일한 환산 함수를 써서 두 경로의 박스가 같은 실시간 길이를 갖는다.
                box_bars = resolve_rolling_box_bars(
                    getattr(strategy_instance, "rolling_box_minutes", DEFAULT_ROLLING_BOX_MINUTES),
                    LIVE_BOX_BAR_MINUTES,
                )
                window_low = compute_box_low(
                    current_data.get('details', {}).get('recent_lows_15m'),
                    box_bars,
                )
                if window_low:
                    new_rolling_stop = compute_rolling_box_stop(dec_rolling_stop, window_low)
                    if new_rolling_stop > dec_rolling_stop:
                        dec_rolling_stop = new_rolling_stop
                        if isinstance(h, Holding) and h.id is not None:
                            with micro_session(ctx) as db:
                                db.query(Holding).filter(Holding.id == h.id).update(
                                    {Holding.rolling_stop_price: dec_rolling_stop},
                                    synchronize_session=False,
                                )
                                db.commit()

            sell_reason_obj = None
            is_breached = False
            breach_obj = None

            # 판정에는 risk_profit_rate/risk_basis_price를, 표시에는 profit_rate를 쓴다.
            # 사용자가 보는 손익률은 언제나 자기 매수가 기준이어야 한다.
            if check_stop_loss_breach(risk_profit_rate, stop_loss_pct):
                is_breached = True
                breach_obj = SellReason("stop_loss", {"stop_loss_pct": stop_loss_pct, "profit_rate": profit_rate})
            elif check_trailing_stop_breach(current_price_dec, dec_highest_price, trailing_stop_pct, risk_basis_price):
                is_breached = True
                breach_obj = SellReason("trailing_stop", {"highest_price": float(dec_highest_price), "trailing_stop_pct": trailing_stop_pct, "profit_rate": profit_rate})
            elif use_rolling_box and check_rolling_box_breach(current_price_dec, dec_rolling_stop, dec_highest_price, risk_basis_price):
                is_breached = True
                breach_obj = SellReason("rolling_box", {"rolling_stop": float(dec_rolling_stop), "profit_rate": profit_rate})

            cache_key = (user_id, h.ticker, h.strategy_type)

            def _write_exit_breach_clock(value):
                """이탈 시작 시각을 DB에 기록한다.

                version_id 낙관적 잠금을 건드리지 않도록 ORM flush가 아닌 Core UPDATE를 쓴다.
                이 경로의 holding은 Part B 매도에서 db.merge(h)(load=True)로 다시 병합되므로,
                매핑 컬럼을 detached 객체에 직접 세팅하면 version이 올라 StaleDataError로
                사이클이 통째로 죽는다(last_price·highest_price와 동일한 사유).
                """
                if not (isinstance(h, Holding) and h.id is not None):
                    return
                with micro_session(ctx) as db:
                    db.query(Holding).filter(Holding.id == h.id).update(
                        {Holding.exit_breach_started_at: value}, synchronize_session=False,
                    )
                    db.commit()

            if is_breached:
                # 노이즈 버퍼 - 손절선을 순간적으로 찔렀다 돌아오는 꼬리에 털리지 않는다.
                #
                # 관측 횟수와 경과 시간을 모두 요구한다. 사이클 수만 쓰면 주기 변동(실측 104~846초)에
                # 따라 같은 2사이클이 3분일 수도 28분일 수도 있다. 횟수는 표본이 성긴 구간에서
                # 한 번에 파는 것을 막고, 시간은 주기가 빨라졌을 때의 하한을 준다.
                #
                # 시각을 DB에 두는 이유는 재기동 때문이다. 카운터만 인메모리로 두면 재기동 후
                # 한 사이클을 더 관측하는 비용으로 끝나지만, 시각까지 인메모리면 진행 중이던
                # 대기가 통째로 0이 되어 손절이 처음부터 다시 미뤄진다.
                with _breach_count_lock:
                    BREACH_COUNT_CACHE[cache_key] = BREACH_COUNT_CACHE.get(cache_key, 0) + 1
                    count = BREACH_COUNT_CACHE[cache_key]

                now = utc_now_aware()
                breach_started_at = getattr(h, "exit_breach_started_at", None) or now
                if getattr(h, "exit_breach_started_at", None) is None:
                    _write_exit_breach_clock(breach_started_at)
                breach_minutes = (now - breach_started_at).total_seconds() / 60.0

                if count >= EXIT_NOISE_BUFFER_CYCLES and breach_minutes >= EXIT_NOISE_BUFFER_MINUTES:
                    breach_obj.confirmed = True
                    sell_reason_obj = breach_obj
                else:
                    _log(
                        f"[Noise Buffer] {h.ticker} ({h.strategy_type}) breach detected "
                        f"({render_sell_reason(breach_obj, 'ko')}). Delaying sell for noise protection "
                        f"({count}/{EXIT_NOISE_BUFFER_CYCLES} checks, "
                        f"{breach_minutes:.1f}/{EXIT_NOISE_BUFFER_MINUTES}min).",
                        "INFO",
                    )
            else:
                # 회복하면 관측 횟수와 시각을 함께 되돌린다. 둘 중 하나만 지우면 다음 이탈에서
                # 남은 축이 이미 충족된 상태로 시작한다(방어 게이트에서 실제로 겪은 결함이다).
                with _breach_count_lock:
                    BREACH_COUNT_CACHE.pop(cache_key, None)
                _clear_exit_breach_clock(ctx, h)

            if not sell_reason_obj and profit_rate >= strategy_instance.min_smart_exit_profit and is_smart_exit:
                sell_reason_obj = SellReason("smart_exit", {"profit_rate": profit_rate})

            elif not sell_reason_obj and strategy_instance.is_signal_collapsed(current_score, sentiment):
                sell_reason_obj = SellReason("signal_collapse", {"current_score": current_score})

            if sell_reason_obj:
                # DB(order_intent)·로그에는 기존과 동일한 한국어 canonical을 유지하고, 텔레그램만 사용자 언어로 렌더한다.
                sell_reason = render_sell_reason(sell_reason_obj, "ko")
                _log(f"[{strategy_instance.name}] EXIT SIGNAL: {h.ticker} | Reason: {sell_reason}", "SIGNAL")

                is_kis_order = (ctx.trade_mode or "").upper() in {"MOCK", "REAL"}
                metadata = None
                if is_kis_order:
                    metadata = await safe_broker_call(broker.get_order_metadata, clean_ticker, ctx.session)

                sell_tasks_args.append((
                    h,
                    current_price,
                    sell_reason,
                    sell_reason_obj,
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
        sell_reason_obj,
        clean_ticker,
        strategy_instance,
        current_score,
        slot_key,
        metadata,
        sell_qty=None,
    ):
        # sell_qty가 None이면 전량 매도(기존 모든 경로). 방어 청산만 부분 수량을 넘긴다 -
        # 신호 품질이 검증되지 않은 판정으로 포지션 전체를 확정하지 않기 위해서다.
        sell_qty = int(sell_qty) if sell_qty else int(h.quantity or 0)
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
                        requested_qty=sell_qty,
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
                        broker, broker.sell_order, clean_ticker, sell_qty,
                        price=current_price, session=ctx.session,
                        lease=symbol_lease,
                        **({"client_order_id": order_intent.intent_id} if order_intent else {}),
                    )
                else:
                    res = await safe_broker_call(
                        broker.sell_order, clean_ticker, sell_qty,
                        price=current_price, session=ctx.session,
                        strategy_type=slot_key,
                        regime_mode=sentiment, signal_score=current_score,
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
                    _clear_exit_breach_clock(ctx, h)
                    fill_label = "sold" if remaining_qty == 0 else f"partially sold ({filled_qty} filled, {remaining_qty} remaining)"
                    _log(f"SUCCESS: {h.ticker} {fill_label} via {sell_reason} | Order: {res['order_no']}", "INFO")

                    pnl_sign = "+" if realized_pnl >= 0 else "-"
                    pnl_emoji = "📈" if realized_pnl >= 0 else "📉"
                    _send_sell_fill_message(
                        user_id,
                        strategy_instance.name,
                        clean_ticker,
                        h.ticker_name,
                        filled_price,
                        exchange_rate,
                        filled_qty,
                        sell_reason_obj,
                        pnl_sign,
                        pnl_emoji,
                        calc_return_rate,
                        abs(realized_pnl),
                        res["order_no"],
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
                if filled_qty <= 0 or filled_qty > sell_qty:
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
                    is_full_fill = filled_qty >= (h.quantity or 0)
                    if is_full_fill:
                        delete_holding(db, h_db, actor="scheduler.process_exit_signals",
                                       reason=f"sell fully filled via {sell_reason}")
                    else:
                        h_db.quantity -= filled_qty
                    db.commit()
                    fill_label = "sold" if is_full_fill else f"partially sold ({filled_qty} filled, {(h.quantity or 0) - filled_qty} remaining)"
                    log_action(db, user_id, f"SUCCESS: {h.ticker} ({h.strategy_type}) {fill_label} via {sell_reason} | Order: {res['order_no']}", "INFO")

                # 전량 매도된 holding을 ctx.holdings에서 제거한다. 같은 사이클에서 다른 종목이 이어서 매도될 때,
                # 다음 micro_session의 holdings auto-merge(scheduler.py:388)가 이미 삭제된 detached holding을
                # 다시 병합하려다 실패하거나 유령 재삽입하는 것을 막는다.
                if is_full_fill:
                    holding_id = getattr(h, "id", None)
                    if holding_id is not None and getattr(ctx, "holdings", None):
                        ctx.holdings = [x for x in ctx.holdings if getattr(x, "id", None) != holding_id]

                BREACH_COUNT_CACHE.pop((user_id, h.ticker, h.strategy_type), None)
                if not is_full_fill:
                    # 전량 매도면 holding 자체가 사라지므로 시각을 지울 대상이 없다.
                    # 부분 체결로 잔량이 남은 경우에만 다음 이탈을 처음부터 세게 한다.
                    _clear_exit_breach_clock(ctx, h)

                pnl_sign = "+" if realized_pnl >= 0 else "-"
                pnl_emoji = "📈" if realized_pnl >= 0 else "📉"

                _send_sell_fill_message(
                    user_id,
                    strategy_instance.name,
                    clean_ticker,
                    h.ticker_name,
                    filled_price,
                    exchange_rate,
                    filled_qty,
                    sell_reason_obj,
                    pnl_sign,
                    pnl_emoji,
                    calc_return_rate,
                    abs(realized_pnl),
                    res["order_no"],
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
    equity_gate_factor: float = 1.0,
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
    proposed_value_usd = base_alloc_usd * vol_factor * score_factor * proposed_alloc_factor * equity_gate_factor
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
    reason_key: str,
    current_price: float,
    proposed_value_usd: float,
    slot_cash_usd: float,
) -> None:
    with micro_session(ctx) as db:
        log_action(db, ctx.user_id, f"[{strategy_instance.name}] SKIP PURCHASE ({reason_key}): {clean_ticker}.", "WARNING")

    cache_key = (ctx.user_id, clean_ticker, strategy_type, reason_key)
    now = time.time()
    last_sent = WARNING_COOLDOWN_CACHE.get(cache_key, 0.0)

    if now - last_sent < 3600.0:
        return

    lang = _resolve_lang(ctx.user_id)
    send_message_async(
        ctx.user_id,
        I18n.get_msg(
            lang,
            "telegram.buy_skipped",
            strategy_name=strategy_instance.name,
            reason_title=I18n.get_msg(lang, f"telegram.buy_skip_reason.{reason_key}.title"),
            ticker=clean_ticker,
            name=signal["name"],
            current_price=current_price,
            current_price_krw=current_price * ctx.exchange_rate,
            proposed_value_usd=proposed_value_usd,
            slot_cash_usd=slot_cash_usd,
            reason_desc=I18n.get_msg(lang, f"telegram.buy_skip_reason.{reason_key}.desc"),
        ),
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
    total_amount_usd = filled_price * filled_qty

    send_message_async(
        ctx.user_id,
        I18n.get_msg(
            _resolve_lang(ctx.user_id),
            "telegram.buy_filled",
            strategy_name=strategy_instance.name,
            ticker=clean_ticker,
            name=signal["name"],
            filled_price=filled_price,
            filled_price_krw=filled_price * ctx.exchange_rate,
            filled_qty=filled_qty,
            next_stage=next_stage,
            total_amount_usd=total_amount_usd,
            total_amount_krw=total_amount_usd * ctx.exchange_rate,
            sentiment=ctx.sentiment,
            order_no=order_no,
        ),
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

        # 에쿼티 커브 게이트: (슬롯×레짐) 최근 청산 성적이 부진하면 신규 매수 배분을 스로틀
        with micro_session(ctx) as db:
            equity_gate_factor, gate_meta = get_equity_gate_factor(db, user_id, slot_key, ctx.sentiment)
        if equity_gate_factor < 1.0:
            _log(
                f"[Equity Gate] {strategy_instance.name} slot throttled to {equity_gate_factor:.0%} "
                f"(PF {gate_meta.get('profit_factor'):.2f} over {gate_meta.get('sample_count')} recent {ctx.sentiment} trades)",
                "WARNING",
            )

        for signal in target_signals:
            clean_ticker = signal['ticker']
            if clean_ticker not in focused_tickers:
                continue

            score = strategy_instance.calculate_score(signal.get('details') or signal, ctx.sentiment, is_entry=True)
            if score < cutoff_score:
                continue

            if slot_holdings_count >= 3:
                continue

            # 사용자가 이미 갖고 있는(봇 관할 밖) 종목은 봇이 새로 사지 않는다. 중복 조회가
            # strategy_type 단위라서 이 가드가 없으면 EXTERNAL로 보유 중인 티커를 다른 슬롯에서
            # 그대로 또 매수한다 — 사용자 입장에선 "안 건드린다더니 물량이 늘었다"가 되고,
            # 브로커 계좌에서 두 슬라이스가 한 덩어리로 섞여 청산 회계도 모호해진다.
            with micro_session(ctx) as db:
                external_holding_exists = db.query(Holding.id).filter(
                    Holding.user_id == user_id,
                    Holding.ticker == clean_ticker,
                    Holding.management == MANAGEMENT_EXTERNAL,
                ).first() is not None
            if external_holding_exists:
                _log(
                    f"[{strategy_instance.name}] BUY SKIPPED: {clean_ticker} is held outside bot management (EXTERNAL).",
                    "INFO",
                )
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
                equity_gate_factor=equity_gate_factor,
            )

            if final_qty < 1:
                is_budget_exceeded = proposed_qty < 1.0
                reason_key = "budget_exceeded" if is_budget_exceeded else "insufficient_cash"
                send_entry_budget_warning(
                    ctx=ctx, strategy_instance=strategy_instance, clean_ticker=clean_ticker,
                    signal=signal, strategy_type=slot_key, reason_key=reason_key,
                    current_price=current_price, proposed_value_usd=proposed_value_usd,
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
                        strategy_type=slot_key, buy_stage=next_stage,
                        regime_mode=ctx.sentiment, signal_score=score,
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
                    I18n.get_msg(_resolve_lang(user_id), "telegram.network_fault"),
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
        # SSE: 공용 스캐너 결과가 갱신됐음을 브로드캐스트(invalidate) → 구독자 일괄 재조회.
        # publish_sync 고정 — 이 함수는 asyncio.run 일회용 루프에서도 돌므로 async 클라이언트 금지.
        from app.core import sse
        sse.publish_sync(sse.CHANNEL_PUBLIC, sse.EVENT_SCANNER_LATEST, None)
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
    global is_processing, _last_cycle_started_at
    with _processing_lock:
        if is_processing:
            logger.info("[Scheduler] Previous loop still running. Skipping this cycle.")
            return
        is_processing = True

    cycle_started_at = time.monotonic()
    previous_started_at = _last_cycle_started_at
    _last_cycle_started_at = cycle_started_at
    if previous_started_at is not None:
        gap_seconds = cycle_started_at - previous_started_at
        # 등록값 60초를 크게 벗어나면 사이클이 자기 주기를 잡아먹고 있다는 뜻이다.
        # 이 한 줄이 없으면 게이트가 늘어지는 것을 사후에 알 방법이 없다.
        level = logger.warning if gap_seconds >= 90 else logger.info
        level(f"[Cycle] Interval since previous start: {gap_seconds:.1f}s (registered 60s)")

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
                from app.brokers.simulated_broker import LocalSimulatedBroker
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
        duration_seconds = time.monotonic() - cycle_started_at
        # 60초를 넘긴 사이클은 다음 틱을 스킵시킨다. 주기가 늘어나는 원인이 바로 여기다.
        level = logger.warning if duration_seconds >= 60 else logger.info
        level(f"[Cycle] Duration: {duration_seconds:.1f}s")

CYCLE_DRAIN_TIMEOUT_SECONDS = 10.0


async def _run_cycle_with_drain(coro, label: str):
    """전용 루프에서 한 사이클을 돌린 뒤, 그 사이클이 띄운 후속 태스크를 마저 흘려보낸다.

    asyncio.run은 본문 코루틴이 끝나는 즉시 남아 있는 태스크를 전부 취소하고 루프를 닫는다.
    체결 직후 띄우는 잔고 스냅샷 갱신처럼 사이클보다 오래 걸리는 작업은 그대로 CancelledError로
    죽어서(로그의 equity-snapshot-refresh 실패가 이 경우다) 대시보드 잔고가 낡은 채로 남는다.
    루프를 닫기 전에 짧은 상한을 두고 완료를 기다린다.

    all_tasks()를 그대로 훑어도 되는 이유는 이 루프가 asyncio.run이 이 호출만을 위해 새로 만든
    것이기 때문이다. 다른 주체의 태스크가 섞여 들어올 수 없다. 이미 돌고 있는 루프에 얹는
    경로(아래 except RuntimeError 분기)에는 절대 쓰면 안 된다.
    """
    try:
        return await coro
    finally:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + CYCLE_DRAIN_TIMEOUT_SECONDS
        while True:
            # run_coroutine_threadsafe는 call_soon_threadsafe로 태스크 생성을 예약만 한다.
            # 한 번 양보해 줘야 그 태스크들이 all_tasks()에 잡힌다.
            await asyncio.sleep(0)
            pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            if not pending:
                return
            remaining = deadline - loop.time()
            if remaining <= 0:
                logger.warning(
                    "[Scheduler] %s: %d background task(s) unfinished after %.0fs drain; loop teardown will cancel them.",
                    label,
                    len(pending),
                    CYCLE_DRAIN_TIMEOUT_SECONDS,
                )
                return
            await asyncio.wait(pending, timeout=remaining)


def trading_loop_wrapper():
    try:
        asyncio.run(_run_cycle_with_drain(async_trading_loop(), "trading_loop"))
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
    sse.notify_admin_users()

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
        # 스윙 예측 점수 캘리브레이션: 당일 예측 갱신 직후, 지난 예측들의 익일 실제 등락을 누적한다.
        # 매매에 관여하지 않는 관측 잡이라 실패해도 트레이딩 사이클에 영향이 없다.
        scheduler.add_job(
            swing_score_calibration_wrapper,
            'cron',
            hour=8,
            minute=30,
            id='swing_score_calibration_job',
            max_instances=1,
            coalesce=True,
        )
        # ③ 스캐너 캐시 갱신: 10분 주기 (yfinance 대규모 API 호출 - Rate Limit 안전)
        scheduler.add_job(scanner_cache_wrapper, 'interval', minutes=10, id='scanner_cache_job', next_run_time=datetime.now())
        # ④ 자동매매 루프: 1분 주기 (캐시된 시그널로 봇 실행 사용자 처리)
        #
        # max_instances=1과 coalesce=True는 APScheduler 기본값과 같지만 일부러 명시한다.
        # 이 잡은 주문을 낸다. 기본값에 기대고 있다가 job_defaults가 바뀌면 매매 사이클이
        # 동시에 두 개 도는 상황이 조용히 열린다(애플리케이션 쪽 is_processing 가드가
        # 2차 방어로 남아 있긴 하다). 의도는 상속이 아니라 선언으로 남긴다.
        #
        # 실제 실행 간격은 등록값 1분이 아니다. interval 트리거는 다음 시각을 직전 예정
        # 시각에서 뽑고, 사이클이 60초를 넘기면 그 사이에 낀 틱은 뒤로 밀리는 것이 아니라
        # 버려진다. 그래서 실측 중앙값이 124초였다(재현: tests/test_scheduler_cycle_interval.py).
        # 사이클 수를 시간 단위로 쓰면 안 되는 이유가 이것이며, 방어·수확 게이트는 그래서
        # 벽시계 기준이다.
        scheduler.add_job(
            trading_loop_wrapper,
            'interval',
            minutes=1,
            id='main_trade_job',
            next_run_time=datetime.now() + timedelta(seconds=20),
            max_instances=1,
            coalesce=True,
        )
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
