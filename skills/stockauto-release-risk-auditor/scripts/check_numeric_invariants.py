#!/usr/bin/env python3
from __future__ import annotations

import math
import re
import sys
from pathlib import Path


def approx(actual: float, expected: float, tolerance: float = 1e-9) -> None:
    if not math.isclose(actual, expected, rel_tol=tolerance, abs_tol=tolerance):
        raise AssertionError(f"expected {expected}, got {actual}")


def pct(new_value: float, old_value: float) -> float:
    if old_value <= 0:
        return 0.0
    return (new_value / old_value - 1.0) * 100.0


def weighted_average(old_qty: float, old_avg: float, fill_qty: float, fill_price: float) -> float:
    total_qty = old_qty + fill_qty
    if total_qty <= 0:
        raise ValueError("total quantity must be positive")
    return (old_qty * old_avg + fill_qty * fill_price) / total_qty


def realized_pnl(sell_qty: float, avg_buy: float, sell_price: float, fee_rate: float, sec_fee_rate: float) -> float:
    gross = sell_qty * (sell_price - avg_buy)
    sell_notional = sell_qty * sell_price
    return gross - sell_notional * fee_rate - sell_notional * sec_fee_rate


def read_constant(config_text: str, name: str) -> float:
    match = re.search(rf"^\s*{re.escape(name)}\s*=\s*([0-9_]+(?:\.[0-9_]+)?)", config_text, re.MULTILINE)
    if not match:
        raise AssertionError(f"missing {name} in backend/app/core/config.py")
    return float(match.group(1).replace("_", ""))


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
    config_path = root / "backend" / "app" / "core" / "config.py"
    config_text = config_path.read_text(encoding="utf-8")

    simulated_fee = read_constant(config_text, "SIMULATED_FEE_RATE")
    kis_fee = read_constant(config_text, "KIS_FEE_RATE")
    sec_fee = read_constant(config_text, "SEC_FEE_RATE")

    assert 0 <= kis_fee < 0.01, "KIS_FEE_RATE should be a fraction, not a percent"
    assert 0 <= simulated_fee < 0.02, "SIMULATED_FEE_RATE should be a fraction, not a percent"
    assert 0 <= sec_fee < 0.001, "SEC_FEE_RATE should be sell-side fraction"

    approx(pct(110.0, 100.0), 10.0)
    approx(pct(95.0, 100.0), -5.0)
    approx(pct(100.0, 0.0), 0.0)
    approx(weighted_average(10, 100, 5, 130), 110.0)
    approx(realized_pnl(10, 100, 110, 0.001, 0.0000278), 98.86942)

    print("Numeric invariant smoke check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
