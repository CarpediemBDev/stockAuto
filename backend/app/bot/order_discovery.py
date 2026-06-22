from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.bot.broker_factory import get_broker_client
from app.bot.order_reconciler import apply_broker_report
from app.core.database import SessionLocal
from app.core.logging import logger
from app.core.models import ActionLog, BrokerOrder, UserSettings, utc_now_aware
from app.core.telegram import send_message_async


DISCOVERABLE_STATUSES = ("SUBMITTING", "ACK_UNKNOWN", "AMBIGUOUS")
INTENT_ABORT_GRACE = timedelta(seconds=60)
PRICE_TOLERANCE = 0.011
ORDER_TIME_TOLERANCE = timedelta(minutes=10)
ET = ZoneInfo("America/New_York")


def _broker_order_timestamp_utc(broker_order: dict) -> datetime | None:
    order_date = str(broker_order.get("order_date") or "")
    order_time = str(broker_order.get("order_time") or "").zfill(6)
    if len(order_date) != 8 or len(order_time) != 6:
        return None
    try:
        local_timestamp = datetime.strptime(
            f"{order_date}{order_time}",
            "%Y%m%d%H%M%S",
        ).replace(tzinfo=ET)
    except ValueError:
        return None
    return local_timestamp.astimezone(UTC)


def _matches_intent(order: BrokerOrder, broker_order: dict) -> bool:
    if broker_order.get("side") != order.side:
        return False
    if str(broker_order.get("ticker") or "").upper() != order.ticker.upper():
        return False
    if int(broker_order.get("ordered_qty") or 0) != order.requested_qty:
        return False

    broker_price = float(broker_order.get("order_price") or 0.0)
    if abs(broker_price - order.submitted_price) > PRICE_TOLERANCE:
        return False

    broker_exchange = str(broker_order.get("exchange_code") or "").upper()
    intent_exchange = str(order.exchange_code or "").upper()
    if broker_exchange and intent_exchange and broker_exchange != intent_exchange:
        return False
    broker_timestamp = _broker_order_timestamp_utc(broker_order)
    if broker_timestamp is None or order.submission_started_at is None:
        return False
    if abs(broker_timestamp - order.submission_started_at) > ORDER_TIME_TOLERANCE:
        return False
    return bool(broker_order.get("order_no"))


def _abort_stale_unsubmitted_intents(db) -> int:
    cutoff = utc_now_aware() - INTENT_ABORT_GRACE
    orders = db.query(BrokerOrder).filter(
        BrokerOrder.status == "INTENT_CREATED",
        BrokerOrder.submitted_at <= cutoff,
    ).all()
    aborted = 0
    for order in orders:
        order.status = "ABORTED"
        order.last_error = "The process stopped before broker submission began."
        order.resolved_at = utc_now_aware()
        db.add(ActionLog(
            user_id=order.user_id,
            level="WARNING",
            message=(
                f"[ORDER INTENT ABORTED] {order.side} {order.ticker} was never submitted "
                "to the broker and was closed during startup recovery."
            ),
        ))
        aborted += 1
    if aborted:
        db.commit()
    return aborted


def discover_orphan_orders_once(session_factory=SessionLocal) -> int:
    db = session_factory()
    matched_count = 0
    notifications = []
    try:
        _abort_stale_unsubmitted_intents(db)
        orders = db.query(BrokerOrder).filter(
            BrokerOrder.status.in_(DISCOVERABLE_STATUSES),
            BrokerOrder.broker_order_no.is_(None),
        ).order_by(BrokerOrder.submitted_at.asc()).all()
        if not orders:
            return 0

        linked_order_numbers = {
            row[0]
            for row in db.query(BrokerOrder.broker_order_no)
            .filter(BrokerOrder.broker_order_no.isnot(None))
            .all()
        }
        history_cache = {}

        for order in orders:
            db_settings = db.query(UserSettings).filter(
                UserSettings.user_id == order.user_id
            ).first()
            if not db_settings:
                order.status = "ERROR"
                order.last_error = "User settings no longer exist."
                continue

            current_mode = (db_settings.trade_mode or "SIMULATED").upper()
            if current_mode != order.trade_mode:
                order.status = "ERROR"
                order.last_error = (
                    f"Trade mode changed from {order.trade_mode} to {current_mode} "
                    "during orphan order discovery."
                )
                continue

            cache_key = (order.user_id, order.broker_order_date)
            if cache_key not in history_cache:
                broker = get_broker_client(db_settings)
                try:
                    history_cache[cache_key] = broker.list_order_history(
                        order.broker_order_date,
                        order.broker_order_date,
                    )
                except Exception as exc:
                    logger.exception(
                        "[OrderDiscovery] Failed to load order history for user=%s date=%s",
                        order.user_id,
                        order.broker_order_date,
                    )
                    history_cache[cache_key] = None
                    order.discovery_attempts += 1
                    order.last_discovery_at = utc_now_aware()
                    order.status = "ACK_UNKNOWN"
                    order.last_error = f"Order history lookup failed: {exc}"
                    continue

            history = history_cache[cache_key]
            if history is None:
                continue

            candidates = [
                item
                for item in history
                if item.get("order_no") not in linked_order_numbers
                and _matches_intent(order, item)
            ]
            order.discovery_attempts += 1
            order.last_discovery_at = utc_now_aware()

            if len(candidates) == 0:
                order.status = "ACK_UNKNOWN"
                order.last_error = "No matching broker order was found yet."
                continue

            if len(candidates) > 1:
                order.status = "AMBIGUOUS"
                order.last_error = (
                    f"{len(candidates)} broker orders match this intent; automatic linking was refused."
                )
                db.add(ActionLog(
                    user_id=order.user_id,
                    level="ERROR",
                    message=(
                        f"[ORDER DISCOVERY AMBIGUOUS] {order.side} {order.ticker} has "
                        f"{len(candidates)} matching KIS orders. "
                        "New trading cycles remain blocked by the order ledger."
                    ),
                ))
                notifications.append((
                    order.user_id,
                    f"*Order Recovery Ambiguous*\n"
                    f"Side: `{order.side}`\nTicker: `{order.ticker}`\n"
                    f"Candidates: `{len(candidates)}`\n\n"
                    "Automatic linking was refused; the user's bot preference was preserved.",
                ))
                continue

            candidate = candidates[0]
            order.broker_order_no = candidate["order_no"]
            order.response_received_at = utc_now_aware()
            order.last_error = None
            linked_order_numbers.add(candidate["order_no"])
            application = apply_broker_report(db, order, candidate)
            matched_count += 1
            db.add(ActionLog(
                user_id=order.user_id,
                level="INFO",
                message=(
                    f"[ORDER DISCOVERED] Linked intent {order.intent_id} to KIS order "
                    f"{order.broker_order_no}; status={order.status}, "
                    f"applied={application.applied_qty}."
                ),
            ))
            notifications.append((
                order.user_id,
                f"*Orphan Order Recovered*\n"
                f"Side: `{order.side}`\nTicker: `{order.ticker}`\n"
                f"Order No: `{order.broker_order_no}`\nStatus: `{order.status}`\n"
                "Bot preference unchanged.",
            ))

        db.commit()
    except Exception:
        db.rollback()
        logger.exception("[OrderDiscovery] Orphan order discovery failed")
    finally:
        db.close()

    for user_id, message in notifications:
        send_message_async(user_id, message)
    return matched_count
