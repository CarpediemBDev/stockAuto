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
    DEFAULT_ROLLING_BOX_WINDOW,
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


class TestScannerRollingBoxLow:
    def _df(self, lows):
        return pd.DataFrame({
            "Low": lows,
            "High": [l + 2 for l in lows],
            "Close": [l + 1 for l in lows],
        })

    def test_excludes_forming_last_bar(self):
        from app.scanner.scanner import calculate_rolling_box_low

        # 마지막 봉 저점 1.0은 형성 중 — 제외되어야 함
        lows = [100.0] * DEFAULT_ROLLING_BOX_WINDOW + [1.0]
        assert calculate_rolling_box_low(self._df(lows)) == 100.0

    def test_requires_full_window_of_completed_bars(self):
        from app.scanner.scanner import calculate_rolling_box_low

        lows = [100.0] * (DEFAULT_ROLLING_BOX_WINDOW - 1) + [99.0]  # 완성 봉 N-1개뿐
        assert calculate_rolling_box_low(self._df(lows)) is None

    def test_returns_min_of_window(self):
        from app.scanner.scanner import calculate_rolling_box_low

        lows = [100.0, 97.5, 103.0, 99.0, 101.0, 98.0, 104.0, 102.0, 100.5, 99.5, 55.5]
        assert calculate_rolling_box_low(self._df(lows)) == 97.5

    def test_handles_empty_and_none(self):
        from app.scanner.scanner import calculate_rolling_box_low

        assert calculate_rolling_box_low(None) is None
        assert calculate_rolling_box_low(pd.DataFrame()) is None


class TestStrategyDefaults:
    def test_rolling_box_disabled_by_default(self):
        from app.strategies.base_strategy import BaseStrategy

        assert BaseStrategy.use_rolling_box_stop is False
        assert BaseStrategy.rolling_box_window == DEFAULT_ROLLING_BOX_WINDOW

    def test_holding_model_has_rolling_stop_column(self):
        from app.core import models

        assert hasattr(models.Holding, "rolling_stop_price")
