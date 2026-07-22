"""롤링 박스 트레일링 스탑(rolling box stop) 회귀 테스트.

핵심 불변식:
1. 래칫 단조 증가 — 윈도우 저점이 주가를 따라 내려가도 스탑은 절대 후퇴하지 않는다
   (제미나이 원안의 역주행 결함을 보정하는 설계 핵심).
2. 수익권 진입(최고가 > 평단) 전에는 발동하지 않는다 — 손실 방어는 동적 손절선 담당.
3. 미시드(0/None) 스탑은 발동하지 않는다.
4. 스캐너의 윈도우 저점 계산은 형성 중인 마지막 봉을 제외하고 완성 봉 N개를 요구한다.
"""

from decimal import Decimal

import pandas as pd
import pytest

from app.bot.trade_calculations import (
    DEFAULT_ROLLING_BOX_MINUTES,
    LIVE_BOX_BAR_MINUTES,
    MAX_ROLLING_BOX_MINUTES,
    MIN_ROLLING_BOX_BARS,
    bar_minutes_for_interval,
    compute_box_low,
    resolve_rolling_box_bars,
    check_rolling_box_breach,
    compute_rolling_box_stop,
)


class TestRatchet:
    def test_stop_rises_with_window_low(self):
        assert compute_rolling_box_stop(100.0, 105.0) == Decimal("105.0")

    def test_stop_never_retreats_when_window_low_falls(self):
        # 하락 중 윈도우 저점이 95 → 90으로 내려가도 스탑은 100 유지 (역주행 차단)
        assert compute_rolling_box_stop(100.0, 95.0) == Decimal("100.0")
        assert compute_rolling_box_stop(100.0, 90.0) == Decimal("100.0")

    def test_monotonic_over_declining_sequence(self):
        stop = Decimal("0")
        window_lows = [100, 102, 105, 103, 98, 95, 90]
        peaks = []
        for low in window_lows:
            stop = compute_rolling_box_stop(stop, low)
            peaks.append(stop)
        assert peaks == sorted(peaks)  # 단조 비감소
        assert stop == Decimal("105")

    def test_unseeded_stop_takes_window_low(self):
        assert compute_rolling_box_stop(None, 88.5) == Decimal("88.5")
        assert compute_rolling_box_stop(0.0, 88.5) == Decimal("88.5")

    def test_decimal_inputs_preserved(self):
        result = compute_rolling_box_stop(Decimal("100.1234"), Decimal("100.1235"))
        assert result == Decimal("100.1235")


class TestBreach:
    def test_breach_when_price_below_stop_and_profit_armed(self):
        assert check_rolling_box_breach(99.0, 100.0, highest_price=110.0, avg_price=95.0)

    def test_no_breach_before_profit_armed(self):
        # 최고가가 평단 이하 — 아직 수익권 미진입이면 박스 이탈해도 미발동
        assert not check_rolling_box_breach(99.0, 100.0, highest_price=95.0, avg_price=95.0)

    def test_no_breach_when_price_at_or_above_stop(self):
        assert not check_rolling_box_breach(100.0, 100.0, highest_price=110.0, avg_price=95.0)
        assert not check_rolling_box_breach(101.0, 100.0, highest_price=110.0, avg_price=95.0)

    def test_unseeded_stop_never_breaches(self):
        assert not check_rolling_box_breach(50.0, 0.0, highest_price=110.0, avg_price=95.0)
        assert not check_rolling_box_breach(50.0, None, highest_price=110.0, avg_price=95.0)


class TestScannerRecentLows:
    def _df(self, lows):
        return pd.DataFrame({
            "Low": lows,
            "High": [l + 2 for l in lows],
            "Close": [l + 1 for l in lows],
        })

    def test_excludes_forming_last_bar(self):
        from app.scanner.scanner import collect_recent_lows_15m

        lows = [100.0] * 10 + [1.0]
        assert 1.0 not in collect_recent_lows_15m(self._df(lows))

    def test_caps_at_live_supply_ceiling(self):
        from app.scanner.scanner import collect_recent_lows_15m

        max_bars = resolve_rolling_box_bars(MAX_ROLLING_BOX_MINUTES, LIVE_BOX_BAR_MINUTES)
        lows = [100.0 + i for i in range(max_bars + 20)]
        assert len(collect_recent_lows_15m(self._df(lows))) == max_bars

    def test_preserves_order_for_downstream_window(self):
        from app.scanner.scanner import collect_recent_lows_15m

        lows = [100.0, 97.5, 103.0, 99.0, 101.0, 98.0, 104.0, 102.0, 100.5, 99.5, 55.5]
        result = collect_recent_lows_15m(self._df(lows))
        assert result[0] == 100.0 and result[-1] == 99.5

    def test_drops_nonpositive_and_nan(self):
        from app.scanner.scanner import collect_recent_lows_15m

        lows = [100.0, 0.0, float("nan"), 98.0, 99.0]
        assert collect_recent_lows_15m(self._df(lows)) == [100.0, 98.0]

    def test_handles_empty_and_none(self):
        from app.scanner.scanner import collect_recent_lows_15m

        assert collect_recent_lows_15m(None) == []
        assert collect_recent_lows_15m(pd.DataFrame()) == []


class TestResolveRollingBoxBars:
    def test_live_default_matches_legacy_ten_bars(self):
        assert resolve_rolling_box_bars(DEFAULT_ROLLING_BOX_MINUTES, LIVE_BOX_BAR_MINUTES) == 10

    def test_same_duration_across_timeframes(self):
        for interval, expected in [("15m", 10), ("5m", 30), ("1h", 3)]:
            assert resolve_rolling_box_bars(150, bar_minutes_for_interval(interval)) == expected

    def test_daily_interval_clamps_to_minimum_bars(self):
        assert resolve_rolling_box_bars(150, bar_minutes_for_interval("1d")) == MIN_ROLLING_BOX_BARS

    def test_clamps_above_live_supply_ceiling(self):
        capped = resolve_rolling_box_bars(MAX_ROLLING_BOX_MINUTES + 600, LIVE_BOX_BAR_MINUTES)
        assert capped == resolve_rolling_box_bars(MAX_ROLLING_BOX_MINUTES, LIVE_BOX_BAR_MINUTES)

    def test_zero_and_negative_minutes_clamp_to_minimum(self):
        assert resolve_rolling_box_bars(0, 15) == MIN_ROLLING_BOX_BARS
        assert resolve_rolling_box_bars(-100, 15) == MIN_ROLLING_BOX_BARS

    def test_invalid_bar_minutes_raises(self):
        with pytest.raises(ValueError):
            resolve_rolling_box_bars(150, 0)


class TestComputeBoxLow:
    def test_takes_min_of_last_bars(self):
        assert compute_box_low([10.0, 5.0, 9.0, 8.0], 3) == 5.0

    def test_ignores_older_bars_outside_window(self):
        assert compute_box_low([1.0, 10.0, 9.0, 8.0], 3) == 8.0

    def test_returns_none_when_not_enough_bars(self):
        assert compute_box_low([10.0, 9.0], 3) is None

    def test_returns_none_for_empty_or_invalid(self):
        assert compute_box_low([], 3) is None
        assert compute_box_low(None, 3) is None
        assert compute_box_low([10.0, 9.0, 8.0], 0) is None
        assert compute_box_low([10.0, 0.0, 8.0], 3) is None
        assert compute_box_low([10.0, "x", 8.0], 3) is None


class TestStrategyDefaults:
    def test_rolling_box_disabled_by_default(self):
        from app.strategies.base_strategy import BaseStrategy

        assert BaseStrategy.use_rolling_box_stop is False
        assert BaseStrategy.rolling_box_minutes == DEFAULT_ROLLING_BOX_MINUTES

    def test_holding_model_has_rolling_stop_column(self):
        from app.core import models

        assert hasattr(models.Holding, "rolling_stop_price")
