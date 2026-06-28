#!/usr/bin/env python3
"""Fast numeric invariant checks for StockAuto release verification.

The goal is not to replace domain tests. This script keeps the release harness
from silently losing the golden tests and constants that protect trading math.
It intentionally avoids importing app modules because config imports may require
runtime services such as Redis.
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path


def approx(actual: float, expected: float, tolerance: float = 1e-9) -> None:
    if not math.isclose(actual, expected, rel_tol=tolerance, abs_tol=tolerance):
        raise AssertionError(f"expected {expected}, got {actual}")


def pct_change(new_value: float, old_value: float) -> float:
    if old_value <= 0:
        return 0.0
    return (new_value / old_value - 1.0) * 100.0


def weighted_average(
    old_qty: float,
    old_avg: float,
    fill_qty: float,
    fill_price: float,
) -> float:
    total_qty = old_qty + fill_qty
    if total_qty <= 0:
        raise ValueError("total quantity must be positive")
    return (old_qty * old_avg + fill_qty * fill_price) / total_qty


def realized_pnl(
    sell_qty: float,
    avg_buy_price: float,
    sell_price: float,
    allocated_buy_fee: float,
    sell_fee_rate: float,
    sec_fee_rate: float,
) -> float:
    gross = sell_qty * (sell_price - avg_buy_price)
    sell_notional = sell_qty * sell_price
    return gross - allocated_buy_fee - (sell_notional * sell_fee_rate) - (
        sell_notional * sec_fee_rate
    )


def return_rate_pct(realized_profit_loss: float, cost_basis: float) -> float:
    if cost_basis <= 0:
        raise ValueError("cost basis must be positive")
    return realized_profit_loss / cost_basis * 100.0


def bounded_score(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("score must be finite")
    return max(0.0, min(100.0, value))


def read_number_assignment(config_text: str, name: str) -> float:
    match = re.search(
        rf"^\s*{re.escape(name)}\s*=\s*([0-9_]+(?:\.[0-9_]+)?)",
        config_text,
        re.MULTILINE,
    )
    if not match:
        raise AssertionError(f"missing {name} in backend/app/core/config.py")
    return float(match.group(1).replace("_", ""))


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


def check_formula_smoke(root: Path, errors: list[str]) -> None:
    config_text = require_file(root, "backend/app/core/config.py", errors)
    if not config_text:
        return

    simulated_fee = read_number_assignment(config_text, "SIMULATED_FEE_RATE")
    kis_fee = read_number_assignment(config_text, "KIS_FEE_RATE")
    sec_fee = read_number_assignment(config_text, "SEC_FEE_RATE")

    if not 0 <= kis_fee < 0.01:
        errors.append("KIS_FEE_RATE must be a fractional rate below 1%.")
    if not 0 <= simulated_fee < 0.02:
        errors.append("SIMULATED_FEE_RATE must be a fractional rate below 2%.")
    if not 0 <= sec_fee < 0.001:
        errors.append("SEC_FEE_RATE must be a sell-side fractional rate below 0.1%.")

    approx(pct_change(110.0, 100.0), 10.0)
    approx(pct_change(95.0, 100.0), -5.0)
    approx(pct_change(100.0, 0.0), 0.0)
    approx(weighted_average(10, 100, 5, 130), 110.0)
    approx(realized_pnl(10, 100, 110, 1.0, 0.001, 0.0000278), 97.86942)
    approx(return_rate_pct(97.86942, 1000.0), 9.786942)
    approx(bounded_score(140.0), 100.0)
    approx(bounded_score(-5.0), 0.0)


def check_golden_test_coverage(root: Path, errors: list[str]) -> None:
    requirements = (
        (
            "backend/tests/test_backtest_metrics.py",
            "backtest drawdown golden tests",
            (
                'metrics["max_drawdown"] == -6.8627',
                'metrics["mdd_recovered"] is True',
                'metrics["max_underwater_days"] == 3',
            ),
        ),
        (
            "backend/tests/test_scanner_scoring.py",
            "scanner score golden tests",
            (
                'result["signal_score"] == 100.0',
                "score_bb_buy == 100.0",
                "score_bb_normal == 0.0",
            ),
        ),
        (
            "backend/tests/test_partial_fill_edge_cases.py",
            "partial-fill accounting golden tests",
            (
                "application.applied_qty == 30",
                'balance["cash_balance"] == 9_800_000',
                "duplicate.applied_qty == 0",
            ),
        ),
        (
            "backend/tests/test_simulated_broker_balance.py",
            "simulated account valuation golden tests",
            (
                'active_balance["cash_balance"] == 8_650_000',
                'active_balance["stock_balance"] == 1_620_000',
                'active_balance["profit_rate"] == 2.7',
                "active_balance_high_fx",
            ),
        ),
        (
            "backend/tests/test_fx_cache.py",
            "FX cache golden tests",
            (
                "1517.56",
                "call_count == 1",
                "cached FX rate should not fetch live data inside TTL",
            ),
        ),
    )

    for relative, label, markers in requirements:
        text = require_file(root, relative, errors)
        if text:
            require_markers(text, markers, label, errors)


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
    errors: list[str] = []

    try:
        check_formula_smoke(root, errors)
    except Exception as exc:  # noqa: BLE001 - report all invariant failures.
        errors.append(f"formula smoke check failed: {exc}")

    check_golden_test_coverage(root, errors)

    if errors:
        print("Numeric invariant check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Numeric invariant check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
