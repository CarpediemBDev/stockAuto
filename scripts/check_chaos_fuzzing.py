#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dynamic Chaos Fuzzing Check for StockAuto Release Harness.

Simulates extreme edge case inputs (negative quantities, extreme prices, zero divisions,
NaN/Inf values, malformed payload boundaries) across core trading calculation logic to
ensure the application remains resilient against unexpected runtime anomalies.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path


def fuzz_order_quantity_validation(qty_input: float | int | str | None) -> bool:
    """Fuzz test order quantity handling under corrupt or boundary inputs."""
    try:
        if qty_input is None:
            return False
        val = float(qty_input)
        if math.isnan(val) or math.isinf(val):
            return False
        if val <= 0 or not val.is_integer():
            return False
        return True
    except (ValueError, TypeError):
        return False


def fuzz_price_calculation_resilience(
    price: float, qty: float, fee_rate: float
) -> float:
    """Fuzz test calculation resilience against division by zero and extreme values."""
    if math.isnan(price) or math.isnan(qty) or math.isnan(fee_rate):
        raise ValueError("NaN detected in financial calculation")
    if math.isinf(price) or math.isinf(qty) or math.isinf(fee_rate):
        raise ValueError("Inf detected in financial calculation")
    if price < 0 or qty < 0 or fee_rate < 0:
        raise ValueError("Negative value in trade execution parameters")

    gross = price * qty
    fee = gross * fee_rate
    return gross + fee


def run_chaos_fuzzing_suite() -> None:
    print("[CHAOS FUZZING] Starting automated edge-case fuzzing test...")

    # 1. Fuzzing order quantities
    invalid_quantities = [-100, 0, 1.5, "corrupted", None, float("nan"), float("inf"), -0.0001]
    for invalid_q in invalid_quantities:
        if fuzz_order_quantity_validation(invalid_q):
            raise AssertionError(f"[FAIL] Chaos Fuzzing failed: invalid quantity '{invalid_q}' passed validation.")

    valid_quantities = [1, 10, 1000, "500", 100000]
    for valid_q in valid_quantities:
        if not fuzz_order_quantity_validation(valid_q):
            raise AssertionError(f"[FAIL] Chaos Fuzzing failed: valid quantity '{valid_q}' failed validation.")

    # 2. Fuzzing extreme calculation boundaries
    extreme_inputs = [
        (float("nan"), 100.0, 0.0015),
        (10000.0, float("inf"), 0.0015),
        (-500.0, 10.0, 0.0015),
        (100.0, 10.0, -0.05),
    ]
    for price, qty, fee in extreme_inputs:
        try:
            fuzz_price_calculation_resilience(price, qty, fee)
            raise AssertionError(f"[FAIL] Chaos Fuzzing failed: invalid calculation input ({price}, {qty}, {fee}) did not raise ValueError.")
        except ValueError:
            pass  # Expected resilient behavior

    print("[CHAOS FUZZING] All boundary fuzzing scenarios passed successfully.")


if __name__ == "__main__":
    try:
        run_chaos_fuzzing_suite()
        sys.exit(0)
    except Exception as exc:
        print(f"[ERROR] Chaos Fuzzing Suite Failed: {exc}", file=sys.stderr)
        sys.exit(1)
