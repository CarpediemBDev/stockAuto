"""지수 레버리지 레짐(자율 슬롯) 전략 회귀 테스트.

핵심 계약:
1. 레짐 상태기계 — SMA 위/아래 confirm_days '연속' 마감 시에만 상태 전환 (휩쏘 가드)
2. 데이터 부족 시 안전측(OUT=현금) 판정
3. 벤치마크 변형은 필터 없이 항상 IN
4. core_satellite 슬롯 모드 가중치(70/30) 및 자율 플래그 배선
"""
import numpy as np
import pandas as pd
import pytest

from app.strategies.leveraged_regime import LeveragedRegime, BenchmarkQqqHold
from app.strategies.strategy_factory import get_strategy


def _series(values):
    return pd.Series([float(v) for v in values])


def _rising(n=260, start=100.0, step=0.5):
    return _series(np.arange(n) * step + start)


class TestComputeTargetState:
    def test_uptrend_confirms_in(self):
        strat = LeveragedRegime(sma_period=50, confirm_days=3)
        assert strat.compute_target_state(_rising()) == "IN"

    def test_downtrend_stays_out(self):
        strat = LeveragedRegime(sma_period=50, confirm_days=3)
        falling = _series(np.linspace(200, 100, 260))
        assert strat.compute_target_state(falling) == "OUT"

    def test_insufficient_data_is_out(self):
        strat = LeveragedRegime(sma_period=200, confirm_days=3)
        assert strat.compute_target_state(_rising(n=100)) == "OUT"

    def test_two_day_whipsaw_does_not_exit(self):
        # 상승 추세 확립 후 SMA 아래 2일(확정 미달) → IN 유지
        strat = LeveragedRegime(sma_period=50, confirm_days=3)
        values = list(np.arange(240) * 0.5 + 100)
        values += [50.0, 50.0]           # SMA 하향 이탈 2일 (3일 미만)
        values += [250.0] * 5            # 즉시 복귀
        assert strat.compute_target_state(_series(values)) == "IN"

    def test_three_day_breakdown_exits(self):
        # SMA 아래 3일 연속 마감 → OUT 확정
        strat = LeveragedRegime(sma_period=50, confirm_days=3)
        values = list(np.arange(240) * 0.5 + 100)
        values += [50.0] * 3
        assert strat.compute_target_state(_series(values)) == "OUT"

    def test_two_day_rally_does_not_enter(self):
        # 하락 추세에서 SMA 위 2일 반등(확정 미달) → OUT 유지
        strat = LeveragedRegime(sma_period=50, confirm_days=3)
        values = list(np.linspace(200, 100, 240))
        values += [300.0, 300.0]
        values += [10.0] * 5
        assert strat.compute_target_state(_series(values)) == "OUT"

    def test_benchmark_always_in(self):
        bench = BenchmarkQqqHold()
        assert bench.compute_target_state(_series([1.0])) == "IN"
        assert bench.asset_ticker == "QQQ"

    def test_scanner_score_never_fires(self):
        strat = LeveragedRegime()
        assert strat.calculate_score({"Close": 100.0, "Volume": 1e9}, "BULLISH") == 0.0


class TestFactoryAndSlots:
    def test_factory_registration(self):
        core = get_strategy("leveraged_regime")
        bench = get_strategy("benchmark_qqq_hold")
        assert isinstance(core, LeveragedRegime)
        assert isinstance(bench, BenchmarkQqqHold)
        assert core.is_autonomous is True
        assert core.asset_ticker == "QLD"
        assert core.signal_ticker == "QQQ"
        assert core.sma_period == 200
        assert core.confirm_days == 3

    def test_core_satellite_slot_mode(self):
        from app.bot.multi_strategy_manager import MultiStrategyManager

        manager = MultiStrategyManager(strategy_type="core_satellite")
        assert set(manager.SLOTS.keys()) == {"leveraged_regime", "strategy_c"}
        assert manager.SLOTS["leveraged_regime"]["weight"] == pytest.approx(0.70)
        assert manager.SLOTS["strategy_c"]["weight"] == pytest.approx(0.30)
        assert manager.strategies["leveraged_regime"].is_autonomous is True
        assert getattr(manager.strategies["strategy_c"], "is_autonomous", False) is False

    def test_non_autonomous_strategies_unaffected(self):
        regime = get_strategy("regime_switching")
        assert getattr(regime, "is_autonomous", False) is False
