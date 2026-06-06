from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.bot.broker_factory import get_broker_client
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import logger
from app.core.models import ActionLog, BrokerOrder, Holding, TradeLog, UserSettings, utc_now_naive
from app.core.telegram import send_message_async


UNRESOLVED_ORDER_STATUSES = (
    "INTENT_CREATED",
    "SUBMITTING",
    "ACK_UNKNOWN",
    "AMBIGUOUS",
    "SUBMITTED",
    "PENDING",
    "PARTIAL",
    "ERROR",
)
TERMINAL_ORDER_STATUSES = ("FILLED", "CANCELED", "REJECTED", "ABORTED")
ET = ZoneInfo("America/New_York")
STALE_ALERT_AFTER_RETRIES = 60
ALERT_COOLDOWN = timedelta(minutes=30)


@dataclass
class FillApplication:
    order: BrokerOrder
    applied_qty: int = 0
    filled_price: float = 0.0
    created_holding: bool = False
    remaining_qty: int | None = None
    realized_pnl: float | None = None
    return_rate: float | None = None
    error: str | None = None

    @property
    def is_unresolved(self) -> bool:
        return self.order.status in UNRESOLVED_ORDER_STATUSES


def has_unresolved_orders(db, user_id: int) -> bool:
    return db.query(BrokerOrder.id).filter(
        BrokerOrder.user_id == user_id,
        BrokerOrder.status.in_(UNRESOLVED_ORDER_STATUSES),
    ).first() is not None


def disable_auto_resume_for_user(db, user_id: int) -> None:
    orders = db.query(BrokerOrder).filter(
        BrokerOrder.user_id == user_id,
        BrokerOrder.status.in_(UNRESOLVED_ORDER_STATUSES),
    ).all()
    for order in orders:
        order.resume_after_resolution = False


def _normalize_status(raw_status: str | None) -> str:
    status = (raw_status or "PENDING").upper()
    if status in {"SUBMITTED", "PENDING", "UNCONFIRMED", "UNFILLED"}:
        return "PENDING"
    if status == "CANCELLED":
        return "CANCELED"
    if status in {"PARTIAL", "FILLED", "CANCELED", "REJECTED", "ERROR"}:
        return status
    return "ERROR"


def _mark_integrity_error(order: BrokerOrder, message: str) -> FillApplication:
    order.status = "ERROR"
    order.last_error = message
    order.resolved_at = None
    return FillApplication(order=order, error=message)


def _apply_buy_delta(db, order: BrokerOrder, delta: int, filled_price: float) -> tuple[bool, int]:
    holding = db.query(Holding).filter(
        Holding.user_id == order.user_id,
        Holding.ticker == order.prefixed_ticker,
    ).first()
    if holding:
        old_qty = holding.quantity
        new_qty = old_qty + delta
        holding.avg_price = round(
            ((holding.avg_price * old_qty) + (filled_price * delta)) / new_qty,
            4,
        )
        holding.quantity = new_qty
        holding.buy_stage = order.buy_stage or holding.buy_stage
        holding.highest_price = max(holding.highest_price or filled_price, filled_price)
        return False, new_qty

    db.add(Holding(
        user_id=order.user_id,
        ticker=order.prefixed_ticker,
        ticker_name=order.ticker_name,
        avg_price=filled_price,
        quantity=delta,
        highest_price=filled_price,
        regime_mode=order.regime_mode,
        buy_stage=order.buy_stage or 1,
    ))
    return True, delta


def _apply_sell_delta(db, order: BrokerOrder, delta: int, filled_price: float) -> tuple[int, float, float]:
    holding = db.query(Holding).filter(
        Holding.user_id == order.user_id,
        Holding.ticker == order.prefixed_ticker,
    ).first()
    if not holding:
        raise ValueError(f"Holding {order.prefixed_ticker} does not exist for sell reconciliation.")
    if delta > holding.quantity:
        raise ValueError(
            f"Sell fill delta {delta} exceeds DB holding quantity {holding.quantity} "
            f"for {order.prefixed_ticker}."
        )

    buy_gross = holding.avg_price * delta
    buy_fee = buy_gross * settings.KIS_FEE_RATE
    sell_gross = filled_price * delta
    sell_fee = sell_gross * settings.KIS_FEE_RATE
    sec_fee = sell_gross * settings.SEC_FEE_RATE
    realized_pnl = sell_gross - buy_gross - buy_fee - sell_fee - sec_fee
    return_rate = (realized_pnl / buy_gross) * 100 if buy_gross > 0 else 0.0

    db.add(TradeLog(
        user_id=order.user_id,
        ticker=order.prefixed_ticker,
        ticker_name=order.ticker_name or holding.ticker_name,
        trade_type="SELL",
        price=filled_price,
        quantity=delta,
        order_no=order.broker_order_no,
        regime_mode=order.regime_mode,
        signal_score=order.signal_score,
        realized_pnl=round(realized_pnl, 2),
        return_rate=round(return_rate, 2),
    ))

    remaining_qty = holding.quantity - delta
    if remaining_qty == 0:
        db.delete(holding)
    else:
        holding.quantity = remaining_qty

    return remaining_qty, round(realized_pnl, 2), round(return_rate, 2)


def apply_broker_report(db, order: BrokerOrder, report: dict) -> FillApplication:
    status = _normalize_status(report.get("status"))
    if status == "ERROR":
        message = report.get("message") or "Broker order status lookup failed."
        order.status = "ERROR"
        order.last_error = message
        order.resolved_at = None
        return FillApplication(order=order, error=message)

    try:
        broker_filled_qty = int(report.get("filled_qty") or 0)
        cumulative_filled_price = float(report.get("filled_price") or order.filled_price or 0.0)
    except (TypeError, ValueError):
        return _mark_integrity_error(order, f"Invalid broker fill report: {report}")

    if (
        (report.get("status") or "").upper() == "UNFILLED"
        and int(report.get("ordered_qty") or 0) == 0
        and order.applied_filled_qty > 0
    ):
        broker_filled_qty = order.applied_filled_qty
        status = "PARTIAL"

    if broker_filled_qty < order.applied_filled_qty:
        return _mark_integrity_error(
            order,
            f"Broker cumulative fill regressed from {order.applied_filled_qty} to {broker_filled_qty}.",
        )
    if broker_filled_qty > order.requested_qty:
        return _mark_integrity_error(
            order,
            f"Broker cumulative fill {broker_filled_qty} exceeds requested quantity {order.requested_qty}.",
        )

    delta = broker_filled_qty - order.applied_filled_qty
    incremental_filled_price = cumulative_filled_price
    if delta > 0 and order.applied_filled_qty > 0 and order.filled_price:
        incremental_filled_price = (
            (broker_filled_qty * cumulative_filled_price)
            - (order.applied_filled_qty * order.filled_price)
        ) / delta

    application = FillApplication(
        order=order,
        applied_qty=delta,
        filled_price=incremental_filled_price,
    )
    if delta > 0 and incremental_filled_price <= 0:
        return _mark_integrity_error(order, "Positive fill quantity was returned without a valid fill price.")

    if delta > 0:
        try:
            if order.side == "BUY":
                application.created_holding, application.remaining_qty = _apply_buy_delta(
                    db,
                    order,
                    delta,
                    incremental_filled_price,
                )
            elif order.side == "SELL":
                (
                    application.remaining_qty,
                    application.realized_pnl,
                    application.return_rate,
                ) = _apply_sell_delta(db, order, delta, incremental_filled_price)
            else:
                return _mark_integrity_error(order, f"Unsupported order side: {order.side}")
        except ValueError as exc:
            return _mark_integrity_error(order, str(exc))

        order.applied_filled_qty = broker_filled_qty
        order.broker_filled_qty = broker_filled_qty
        order.filled_price = cumulative_filled_price
    else:
        order.broker_filled_qty = broker_filled_qty

    if broker_filled_qty >= order.requested_qty:
        status = "FILLED"
    elif status == "FILLED":
        status = "PARTIAL" if broker_filled_qty > 0 else "ERROR"
    elif status == "PARTIAL" and broker_filled_qty == 0:
        status = "PENDING"

    order.status = status
    order.last_error = report.get("message") if status == "ERROR" else None
    if status in TERMINAL_ORDER_STATUSES:
        order.resolved_at = utc_now_naive()
    else:
        order.resolved_at = None

    return application


def _resume_user_if_safe(db, order: BrokerOrder, db_settings: UserSettings) -> bool:
    if order.status not in TERMINAL_ORDER_STATUSES or not order.resume_after_resolution:
        return False
    db.flush()
    if has_unresolved_orders(db, order.user_id):
        return False
    current_mode = (db_settings.trade_mode or "SIMULATED").upper()
    if current_mode == "REAL" and not bool(db_settings.is_real_enabled):
        return False
    db_settings.is_running = True
    order.resume_after_resolution = False
    return True


def create_order_intent(
    db,
    db_settings: UserSettings,
    *,
    side: str,
    ticker: str,
    prefixed_ticker: str,
    ticker_name: str | None,
    requested_qty: int,
    submitted_price: float,
    exchange_code: str | None,
    order_division: str | None,
    buy_stage: int | None = None,
    regime_mode: str | None = None,
    signal_score: int | None = None,
    sell_reason: str | None = None,
    source: str = "STRATEGY",
    resume_after_resolution: bool | None = None,
) -> BrokerOrder:
    order = BrokerOrder(
        user_id=db_settings.user_id,
        intent_id=str(uuid4()),
        broker_order_no=None,
        broker_order_date=datetime.now(ET).strftime("%Y%m%d"),
        trade_mode=(db_settings.trade_mode or "SIMULATED").upper(),
        side=side.upper(),
        ticker=ticker,
        prefixed_ticker=prefixed_ticker,
        ticker_name=ticker_name,
        exchange_code=exchange_code,
        order_division=order_division,
        source=source,
        status="INTENT_CREATED",
        requested_qty=requested_qty,
        submitted_price=submitted_price,
        buy_stage=buy_stage,
        regime_mode=regime_mode,
        signal_score=signal_score,
        sell_reason=sell_reason,
        resume_after_resolution=(
            bool(db_settings.is_running)
            if resume_after_resolution is None
            else resume_after_resolution
        ),
        submitted_at=utc_now_naive(),
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def begin_order_submission(db, order: BrokerOrder, db_settings: UserSettings) -> None:
    if order.status != "INTENT_CREATED":
        raise ValueError(f"Order intent {order.intent_id} cannot be submitted from {order.status}.")
    order.status = "SUBMITTING"
    order.submission_attempts += 1
    order.submission_started_at = utc_now_naive()
    db_settings.is_running = False
    db.commit()


def finalize_order_submission(
    db,
    order: BrokerOrder,
    db_settings: UserSettings,
    order_result: dict,
) -> FillApplication:
    order.response_received_at = utc_now_naive()
    order_no = str(order_result.get("order_no") or "").strip()
    if order_no:
        order.broker_order_no = order_no

    acknowledgement_unknown = bool(order_result.get("submission_unknown")) or (
        bool(order_result.get("order_submitted")) and not order_no
    )
    if acknowledgement_unknown:
        order.status = "ACK_UNKNOWN"
        order.last_error = order_result.get("message") or "Broker acknowledgement is unknown."
        db_settings.is_running = False
        db.commit()
        return FillApplication(order=order, error=order.last_error)

    if not order_result.get("order_submitted"):
        order.status = "REJECTED"
        order.last_error = order_result.get("message")
        order.resolved_at = utc_now_naive()
        application = FillApplication(order=order)
        _resume_user_if_safe(db, order, db_settings)
        db.commit()
        return application

    application = apply_broker_report(db, order, order_result)
    if application.is_unresolved:
        db_settings.is_running = False
    else:
        _resume_user_if_safe(db, order, db_settings)
    db.commit()
    return application


def record_submitted_order(
    db,
    db_settings: UserSettings,
    *,
    side: str,
    ticker: str,
    prefixed_ticker: str,
    ticker_name: str | None,
    requested_qty: int,
    submitted_price: float,
    order_result: dict,
    buy_stage: int | None = None,
    regime_mode: str | None = None,
    signal_score: int | None = None,
    sell_reason: str | None = None,
) -> FillApplication:
    order_no = str(order_result.get("order_no") or "").strip()
    untrackable = not order_no
    if untrackable:
        order_no = f"UNTRACKABLE-{uuid4().hex}"

    order = db.query(BrokerOrder).filter(
        BrokerOrder.user_id == db_settings.user_id,
        BrokerOrder.broker_order_no == order_no,
    ).first()
    if not order:
        order = BrokerOrder(
            user_id=db_settings.user_id,
            intent_id=str(uuid4()),
            broker_order_no=order_no,
            broker_order_date=datetime.now(ET).strftime("%Y%m%d"),
            trade_mode=(db_settings.trade_mode or "SIMULATED").upper(),
            side=side.upper(),
            ticker=ticker,
            prefixed_ticker=prefixed_ticker,
            ticker_name=ticker_name,
            source="LEGACY_POST_SUBMIT",
            status="SUBMITTED",
            requested_qty=requested_qty,
            submitted_price=submitted_price,
            buy_stage=buy_stage,
            regime_mode=regime_mode,
            signal_score=signal_score,
            sell_reason=sell_reason,
            resume_after_resolution=False,
            submitted_at=utc_now_naive(),
        )
        db.add(order)
        db.flush()

    if untrackable:
        application = _mark_integrity_error(
            order,
            "Broker accepted the order without returning an order number; automatic lookup is impossible.",
        )
    else:
        application = apply_broker_report(db, order, order_result)

    if application.is_unresolved:
        order.resume_after_resolution = order.resume_after_resolution or bool(db_settings.is_running)
        db_settings.is_running = False

    db.commit()
    return application


def _should_send_stale_alert(order: BrokerOrder) -> bool:
    if order.retry_count < STALE_ALERT_AFTER_RETRIES and order.status != "ERROR":
        return False
    now = utc_now_naive()
    return not order.last_alerted_at or now - order.last_alerted_at >= ALERT_COOLDOWN


def _append_action(db, order: BrokerOrder, message: str, level: str) -> None:
    db.add(ActionLog(user_id=order.user_id, message=message, level=level))


def _reconcile_one_order(db, order: BrokerOrder) -> tuple[FillApplication, bool, bool]:
    db_settings = db.query(UserSettings).filter(UserSettings.user_id == order.user_id).first()
    if not db_settings:
        return _mark_integrity_error(order, "User settings no longer exist."), False, False

    current_mode = (db_settings.trade_mode or "SIMULATED").upper()
    if current_mode != order.trade_mode:
        application = _mark_integrity_error(
            order,
            f"Trade mode changed from {order.trade_mode} to {current_mode} while the order was unresolved.",
        )
    elif order.broker_order_no.startswith("UNTRACKABLE-"):
        application = _mark_integrity_error(order, order.last_error or "Order number is unavailable.")
    else:
        broker = get_broker_client(db_settings)
        order.retry_count += 1
        order.last_checked_at = utc_now_naive()
        try:
            report = broker.check_order_status(order.broker_order_no, order.broker_order_date)
        except Exception as exc:
            logger.exception(
                "[OrderReconciler] Broker lookup failed for order %s",
                order.broker_order_no,
            )
            report = {"status": "ERROR", "message": str(exc)}
        application = apply_broker_report(db, order, report)

    resumed = _resume_user_if_safe(db, order, db_settings)

    stale_alert = _should_send_stale_alert(order)
    if stale_alert:
        order.last_alerted_at = utc_now_naive()

    if application.applied_qty > 0:
        _append_action(
            db,
            order,
            f"[ORDER RECONCILED] {order.side} {order.ticker} applied "
            f"{application.applied_qty} additional shares; cumulative "
            f"{order.applied_filled_qty}/{order.requested_qty}.",
            "INFO",
        )
    if resumed:
        _append_action(
            db,
            order,
            f"[ORDER RESOLVED] {order.side} {order.ticker} {order.status}; automatic trading resumed.",
            "INFO",
        )
    elif stale_alert:
        _append_action(
            db,
            order,
            f"[ORDER STILL UNRESOLVED] {order.side} {order.ticker} {order.status}; "
            f"retry={order.retry_count}, error={order.last_error or 'none'}.",
            "ERROR",
        )

    return application, resumed, stale_alert


def reconcile_open_orders_once(session_factory=SessionLocal) -> int:
    lookup_db = session_factory()
    try:
        order_ids = [
            row[0]
            for row in lookup_db.query(BrokerOrder.id)
            .filter(
                BrokerOrder.status.in_(UNRESOLVED_ORDER_STATUSES),
                BrokerOrder.broker_order_no.isnot(None),
            )
            .order_by(BrokerOrder.submitted_at.asc())
            .all()
        ]
    finally:
        lookup_db.close()

    processed = 0
    for order_id in order_ids:
        db = session_factory()
        try:
            order = db.query(BrokerOrder).filter(BrokerOrder.id == order_id).first()
            if not order or order.status not in UNRESOLVED_ORDER_STATUSES:
                continue

            application, resumed, stale_alert = _reconcile_one_order(db, order)
            user_id = order.user_id
            side = order.side
            ticker = order.ticker
            status = order.status
            cumulative = order.applied_filled_qty
            requested = order.requested_qty
            last_error = order.last_error
            db.commit()
            processed += 1

            if application.applied_qty > 0 or resumed:
                resume_text = "\nAutomatic trading resumed." if resumed else ""
                send_message_async(
                    user_id,
                    f"*Order Reconciliation Updated*\n"
                    f"Side: `{side}`\nTicker: `{ticker}`\nStatus: `{status}`\n"
                    f"Applied: `{cumulative}/{requested}`{resume_text}",
                )
            elif stale_alert:
                send_message_async(
                    user_id,
                    f"*Order Reconciliation Still Pending*\n"
                    f"Side: `{side}`\nTicker: `{ticker}`\nStatus: `{status}`\n"
                    f"Error: `{last_error or 'none'}`\n\n"
                    "The bot remains stopped and will continue retrying automatically.",
                )
        except Exception:
            db.rollback()
            logger.exception("[OrderReconciler] Failed to reconcile broker order id=%s", order_id)
        finally:
            db.close()

    return processed
