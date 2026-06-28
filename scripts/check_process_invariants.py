#!/usr/bin/env python3
"""Static process invariant checks for StockAuto release verification."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def require_file(root: Path, relative: str, errors: list[str]) -> str:
    path = root / relative
    if not path.exists():
        errors.append(f"{relative} is missing")
        return ""
    return path.read_text(encoding="utf-8")


def require_markers(
    text: str,
    markers: tuple[str, ...],
    label: str,
    errors: list[str],
) -> None:
    for marker in markers:
        if marker not in text:
            errors.append(f"{label} missing required marker: {marker}")


def require_order_intents_after_symbol_locks(
    scheduler_text: str,
    errors: list[str],
) -> None:
    intent_pattern = re.compile(r"order_intent\s*=\s*create_order_intent\(")
    for match in intent_pattern.finditer(scheduler_text):
        window = scheduler_text[max(0, match.start() - 2500) : match.start()]
        if "await acquire_symbol_order_lock" not in window:
            errors.append(
                "scheduler creates an order intent without an immediately preceding "
                "symbol order lock acquisition"
            )


def require_user_lock_before_session(
    scheduler_text: str,
    errors: list[str],
) -> None:
    flow_start = scheduler_text.find("async def run_user_trading_flow")
    if flow_start == -1:
        errors.append("run_user_trading_flow is missing from backend/app/bot/scheduler.py")
        return

    flow_text = scheduler_text[flow_start:]
    lock_index = flow_text.find("await acquire_user_operation_lock")
    session_index = flow_text.find("SessionLocal()")
    if lock_index == -1:
        errors.append("run_user_trading_flow must acquire the user operation lock")
        return
    if session_index == -1:
        errors.append("run_user_trading_flow must open an explicit DB session")
        return
    if session_index < lock_index:
        errors.append(
            "run_user_trading_flow opens a DB session before acquiring the user "
            "operation lock"
        )


def check_required_process_tests(root: Path, errors: list[str]) -> None:
    requirements = (
        (
            "backend/tests/test_admin_settings_safety.py",
            "admin mode safety tests",
            (
                "test_mock_settings_save_is_blocked_when_credentials_are_missing",
                "test_broker_factory_mock_real_mode_raises_value_error_if_provider_is_null",
                "test_settings_save_rejects_unregistered_broker",
                "verified_trade_mode",
            ),
        ),
        (
            "backend/tests/test_trading_catalog.py",
            "broker mode catalog tests",
            (
                "test_trade_mode_catalog_is_the_validation_source",
                "test_toss_mock_and_real_modes_are_rejected_before_broker_creation",
                'for mode in ("MOCK", "REAL")',
            ),
        ),
        (
            "backend/tests/test_trading_flow_scenarios.py",
            "trading flow lifecycle tests",
            (
                "test_run_user_trading_flow_preserves_bot_preference_when_buy_fill_is_unconfirmed",
                "test_run_user_trading_flow_records_partial_buy_and_preserves_bot_preference",
                "test_run_user_trading_flow_preserves_bot_preference_without_deleting_unconfirmed_sell",
                "test_run_user_trading_flow_keeps_remaining_quantity_after_partial_sell",
                "test_symbol_lock_contention_does_not_create_broker_order_intent",
                "test_redis_unavailable_fails_closed_before_opening_user_session",
            ),
        ),
        (
            "backend/tests/test_order_reconciler.py",
            "order reconciler lifecycle tests",
            (
                "test_partial_buy_is_applied_idempotently_and_preserves_running_preference",
                "test_partial_sell_uses_only_fill_delta_and_preserves_manual_stop",
                "test_unresolved_order_guard_detects_pending_order",
                "test_multiple_order_intents_preserve_running_preference_until_terminal",
            ),
        ),
        (
            "backend/tests/test_order_locks.py",
            "order lock unit tests",
            (
                "test_symbol_lock_keys_are_isolated_by_user",
                "test_lock_acquisition_returns_none_when_key_is_busy",
                "lock:order_submit:1:AAPL",
                "lock:order_submit:2:AAPL",
            ),
        ),
        (
            "backend/tests/test_redis_integration.py",
            "Redis duplicate-order integration test",
            (
                "test_redis_locks_integration",
                "acquire_user_operation_lock",
                "acquire_symbol_order_lock",
                "pytest.skip",
            ),
        ),
        (
            "backend/tests/test_scanner_multitenancy.py",
            "scanner multi-user API tests",
            (
                "test_scanner_and_account_radar_isolate_two_users_and_follow_deletion",
                "tenant_a",
                "tenant_b",
                "test_swing_prediction_is_authenticated_global_market_data",
            ),
        ),
        (
            "backend/tests/test_scanner_tenant_isolation.py",
            "scanner tenant isolation unit tests",
            (
                "test_public_seed_discovery_never_reads_or_tags_user_watchlists",
                "test_user_signal_context_routes_only_the_owners_watchlist",
                '"WATCHLIST" not in user_two_map["AAPL"]["source"]',
            ),
        ),
    )

    for relative, label, markers in requirements:
        text = require_file(root, relative, errors)
        if text:
            require_markers(text, markers, label, errors)


def check_source_process_boundaries(root: Path, errors: list[str]) -> None:
    locks_text = require_file(root, "backend/app/core/locks.py", errors)
    if locks_text:
        require_markers(
            locks_text,
            (
                "class RedisLockUnavailable",
                'f"lock:trading_user:{user_id}"',
                'f"lock:order_submit:{user_id}:{normalized_symbol}"',
                "nx=True",
            ),
            "Redis lock source",
            errors,
        )

    scheduler_text = require_file(root, "backend/app/bot/scheduler.py", errors)
    if scheduler_text:
        require_markers(
            scheduler_text,
            (
                "except RedisLockUnavailable",
                "[TradingLock] Redis unavailable; failing closed",
                "await user_lease.release()",
                "await symbol_lease.release()",
            ),
            "scheduler lock source",
            errors,
        )
        require_order_intents_after_symbol_locks(scheduler_text, errors)
        require_user_lock_before_session(scheduler_text, errors)

    broker_factory_text = require_file(root, "backend/app/bot/broker_factory.py", errors)
    if broker_factory_text:
        require_markers(
            broker_factory_text,
            (
                "BROKER_REGISTRY",
                "ensure_broker_supports_trade_mode",
                'raise ValueError(f"{normalized} 증권사는 {mode} 모드를 지원하지 않습니다.")',
                'raise ValueError("MOCK 또는 REAL 모드에서는 증권사(broker_provider)가 반드시 지정되어야 합니다.")',
            ),
            "broker capability source",
            errors,
        )

    admin_text = require_file(root, "backend/app/admin/router.py", errors)
    if admin_text:
        require_markers(
            admin_text,
            (
                "has_unresolved_orders(db, current_user.id)",
                'trade_mode in {"MOCK", "REAL"}',
                'cred.verified_trade_mode != trade_mode',
                "_ensure_broker_mode_supported",
            ),
            "admin mode-change source",
            errors,
        )

    reconciler_text = require_file(root, "backend/app/bot/order_reconciler.py", errors)
    if reconciler_text:
        require_markers(
            reconciler_text,
            (
                "def has_unresolved_orders",
                "current_mode != order.trade_mode",
                "Trade mode changed",
                "calculate_realized_pnl",
            ),
            "order reconciler source",
            errors,
        )


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
    errors: list[str] = []

    check_required_process_tests(root, errors)
    check_source_process_boundaries(root, errors)

    if errors:
        print("Process invariant check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Process invariant check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
