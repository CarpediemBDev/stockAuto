"""에쿼티 커브 게이트(equity_gate) 회귀 테스트.

핵심 불변식:
1. 콜드 스타트(표본 부족)·내부 오류·무손실 윈도우는 전부 무개입(1.0)이다.
2. 프로핏 팩터 경계값(1.2 / 1.0)에서 계수 매핑이 정확하다.
3. 게이트 계수는 calculate_entry_quantity의 제안 금액에 곱셈으로만 작용한다.
"""

from decimal import Decimal

import pytest

from app.bot.equity_gate import (
    FACTOR_HEALTHY,
    FACTOR_MARGINAL,
    FACTOR_UNHEALTHY,
    MIN_TRADES,
    compute_gate_factor,
    get_equity_gate_factor,
)


def _pnls(*values) -> list[Decimal]:
    return [Decimal(str(v)) for v in values]


class TestComputeGateFactor:
    def test_cold_start_below_min_trades_is_neutral(self):
        factor, meta = compute_gate_factor(_pnls(*([-10.0] * (MIN_TRADES - 1))))
        assert factor == FACTOR_HEALTHY
        assert "cold_start" in meta["reason"]

    def test_empty_window_is_neutral(self):
        factor, _ = compute_gate_factor([])
        assert factor == FACTOR_HEALTHY

    def test_healthy_profit_factor(self):
        # 이익 120, 손실 90 → PF 1.333... ≥ 1.2
        factor, meta = compute_gate_factor(_pnls(60, 60, -30, -30, -30, 0, 0, 0))
        assert factor == FACTOR_HEALTHY
        assert meta["reason"] == "healthy"

    def test_marginal_profit_factor(self):
        # 이익 100, 손실 90 → PF 1.111 (1.0 이상 1.2 미만)
        factor, meta = compute_gate_factor(_pnls(50, 50, -45, -45, 0, 0, 0, 0))
        assert factor == FACTOR_MARGINAL
        assert meta["reason"] == "marginal"

    def test_unhealthy_profit_factor(self):
        # 이익 50, 손실 100 → PF 0.5
        factor, meta = compute_gate_factor(_pnls(25, 25, -50, -50, 0, 0, 0, 0))
        assert factor == FACTOR_UNHEALTHY
        assert meta["reason"] == "unhealthy"

    def test_boundary_exactly_1_2_is_healthy(self):
        # 이익 120, 손실 100 → PF 정확히 1.2
        factor, _ = compute_gate_factor(_pnls(120, -100, 0, 0, 0, 0, 0, 0))
        assert factor == FACTOR_HEALTHY

    def test_boundary_exactly_1_0_is_marginal(self):
        factor, _ = compute_gate_factor(_pnls(100, -100, 0, 0, 0, 0, 0, 0))
        assert factor == FACTOR_MARGINAL

    def test_no_loss_window_is_neutral_despite_zero_denominator(self):
        factor, meta = compute_gate_factor(_pnls(*([10.0] * MIN_TRADES)))
        assert factor == FACTOR_HEALTHY
        assert meta["reason"] == "no_loss_window"

    def test_all_zero_pnl_window_is_neutral(self):
        factor, _ = compute_gate_factor(_pnls(*([0.0] * MIN_TRADES)))
        assert factor == FACTOR_HEALTHY

    def test_all_loss_window_is_unhealthy(self):
        factor, _ = compute_gate_factor(_pnls(*([-5.0] * MIN_TRADES)))
        assert factor == FACTOR_UNHEALTHY

    def test_decimal_precision_no_float_drift(self):
        # 부동소수점이면 0.1 합산 오차로 경계 판정이 흔들릴 수 있는 구성
        gains = [Decimal("0.1")] * 12   # 이익 1.2
        losses = [Decimal("-0.5"), Decimal("-0.5")]  # 손실 1.0 → PF 정확히 1.2
        factor, _ = compute_gate_factor(gains + losses)
        assert factor == FACTOR_HEALTHY


class TestGetEquityGateFactorFailOpen:
    def test_db_error_fails_open_to_neutral(self):
        class BrokenDb:
            def query(self, *args, **kwargs):
                raise RuntimeError("db unavailable")

        factor, meta = get_equity_gate_factor(BrokenDb(), user_id=1, strategy_type="complex", regime="BULLISH")
        assert factor == FACTOR_HEALTHY
        assert meta["reason"].startswith("error")


class TestEntryQuantityIntegration:
    def _run(self, gate_factor: float):
        from app.bot.scheduler import calculate_entry_quantity

        class StubStrategy:
            base_allocation_pct = 0.4
            min_allocation_usd = 0.0

        return calculate_entry_quantity(
            strategy_instance=StubStrategy(),
            signal={"details": {"atr": 0.0}},
            score=80.0,
            cutoff_score=80.0,
            slot_cash_usd=100_000.0,
            slot_total_asset_usd=10_000.0,
            current_price=10.0,
            proposed_alloc_factor=1.0,
            equity_gate_factor=gate_factor,
        )

    def test_gate_scales_proposed_value_multiplicatively(self):
        _, _, full_value = self._run(1.0)
        _, _, throttled_value = self._run(0.3)
        assert throttled_value == pytest.approx(full_value * 0.3)

    def test_default_gate_factor_preserves_legacy_behavior(self):
        from app.bot.scheduler import calculate_entry_quantity
        import inspect

        signature = inspect.signature(calculate_entry_quantity)
        assert signature.parameters["equity_gate_factor"].default == 1.0
