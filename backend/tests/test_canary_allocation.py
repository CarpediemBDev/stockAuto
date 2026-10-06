"""카나리아 배분 전략(순수 계산) 회귀 테스트.

핵심 계약:
1. 판단일 이후 데이터는 결과에 영향을 주지 않는다(룩어헤드 차단)
2. 신호 하나라도 계산 불가면 판단 보류(None) — 일부 신호로 비율을 내지 않는다
3. 목표비중 = 양호 비율 × QQQ, 나머지는 IEF/BIL 중 모멘텀 우위
4. 밴드: 직전 확정 목표와의 차이 합 < 0.10이면 유지
5. 판단일 = 이번 달 이전의 마지막 거래일
"""
import numpy as np
import pandas as pd
import pytest

from app.strategies import canary_allocation as ca
from app.strategies.canary_allocation import CanaryAllocation
from app.strategies.strategy_factory import get_strategy

CAL = pd.bdate_range("2024-01-01", periods=420)
AS_OF = CAL[399]


def _trend(slope, n=len(CAL), start=100.0):
    return pd.Series(start * np.exp(np.arange(n) * slope), index=CAL[:n])


def _closes(**overrides):
    base = {t: _trend(0.001) for t in ca.DATA_TICKERS}
    base["SPY"] = _trend(0.0008)  # 비율 신호(SMH/SPY, XLF/SPY)가 양(+)이 되도록 시장보다 약하게
    base["QQQ"] = _trend(0.001)
    base["BIL"] = _trend(0.0001)
    base["IEF"] = _trend(0.0002)
    base.update(overrides)
    return base


def _nfci(direction=-1.0):
    # 주간(금요일) 관측. direction<0이면 여건 개선(값 하락) → 마지막 값 ≤ 평균 → 양호
    weeks = pd.date_range(CAL[0] - pd.Timedelta(days=400), CAL[-1], freq="W-FRI")
    return pd.Series(direction * np.linspace(0, 1, len(weeks)), index=weeks)


class TestMomentum:
    def test_rising_is_positive_and_falling_negative(self):
        assert ca.momentum_13612u(_trend(0.001)) > 0
        assert ca.momentum_13612u(_trend(-0.001)) < 0

    def test_insufficient_bars_is_none(self):
        assert ca.momentum_13612u(_trend(0.001, n=ca.MIN_BARS - 1)) is None


class TestSignals:
    def test_all_good_gives_full_equity(self):
        sig = ca.compute_signals(_closes(), _nfci(-1), AS_OF)
        assert sig is not None and all(sig.values()) and set(sig) == set(ca.SIGNAL_KEYS)
        assert ca.compute_target(sig, _closes(), AS_OF) == {"QQQ": 1.0}

    def test_zero_momentum_is_warning(self):
        # 모멘텀이 정확히 0(분자·분모 동일 추세)이면 '양호'가 아니다 (> 0 엄격 비교)
        sig = ca.compute_signals(_closes(SPY=_trend(0.001)), _nfci(-1), AS_OF)
        assert sig["smh_spy"] is False and sig["xlf_spy"] is False

    def test_ratio_signal_uses_relative_strength(self):
        # SMH가 올라도 SPY보다 덜 오르면 비율 모멘텀은 경고
        sig = ca.compute_signals(_closes(SMH=_trend(0.0005), SPY=_trend(0.002)), _nfci(-1), AS_OF)
        assert sig["smh_spy"] is False and sig["vwo"] is True

    def test_future_bars_do_not_change_decision(self):
        closes = _closes()
        crashed = {t: s.copy() for t, s in closes.items()}
        for t in crashed:
            crashed[t].iloc[400:] = crashed[t].iloc[400:] * 0.3  # 판단일 이후 폭락
        nf = _nfci(-1)
        nf_future = nf.copy()
        nf_future[nf_future.index > AS_OF] = 99.0
        assert ca.compute_signals(closes, nf, AS_OF) == ca.compute_signals(crashed, nf_future, AS_OF)

    def test_missing_ticker_holds_decision(self):
        closes = _closes()
        del closes["XHB"]
        assert ca.compute_signals(closes, _nfci(-1), AS_OF) is None

    def test_missing_as_of_bar_holds_decision(self):
        closes = _closes()
        closes["VWO"] = closes["VWO"].drop(AS_OF)
        assert ca.compute_signals(closes, _nfci(-1), AS_OF) is None

    def test_missing_nfci_holds_decision(self):
        assert ca.compute_signals(_closes(), None, AS_OF) is None
        short = _nfci(-1)
        assert ca.compute_signals(_closes(), short[short.index > CAL[300]], AS_OF) is None

    def test_nfci_worsening_warns(self):
        sig = ca.compute_signals(_closes(), _nfci(+1), AS_OF)
        assert sig["nfci"] is False

    def test_nfci_lag_ignores_last_five_trading_days(self):
        # 판단일 직전 5거래일 안에만 있는 급등은 아직 발표 전 → 반영되지 않아야 한다
        nf = _nfci(-1)
        spiked = nf.copy()
        spiked[(spiked.index > CAL[395]) & (spiked.index <= AS_OF)] = 99.0
        assert ca.compute_signals(_closes(), spiked, AS_OF)["nfci"] is True


class TestTarget:
    def test_four_of_seven_and_defensive_choice(self):
        sig = {k: (i < 4) for i, k in enumerate(ca.SIGNAL_KEYS)}
        t = ca.compute_target(sig, _closes(), AS_OF)
        assert t["QQQ"] == pytest.approx(4 / 7, abs=1e-6)
        assert t["IEF"] == pytest.approx(3 / 7, abs=1e-6) and "BIL" not in t
        t2 = ca.compute_target(sig, _closes(IEF=_trend(-0.0005)), AS_OF)
        assert "BIL" in t2 and "IEF" not in t2

    def test_all_warn_goes_fully_defensive(self):
        sig = {k: False for k in ca.SIGNAL_KEYS}
        assert ca.compute_target(sig, _closes(), AS_OF) == {"QQQ": 0.0, "IEF": 1.0}

    def test_incomplete_signals_rejected(self):
        assert ca.compute_target({"vwo": True}, _closes(), AS_OF) is None


class TestBand:
    def test_first_decision_always_applies(self):
        assert ca.apply_band({"QQQ": 0.5, "BIL": 0.5}, None) == ({"QQQ": 0.5, "BIL": 0.5}, True)

    def test_small_change_keeps_last(self):
        last = {"QQQ": 0.5, "BIL": 0.5}
        new = {"QQQ": 0.54, "BIL": 0.46}  # 차이 합 0.08
        assert ca.apply_band(new, last) == (last, False)

    def test_one_signal_flip_exceeds_band(self):
        last = {"QQQ": 4 / 7, "BIL": 3 / 7}
        new = {"QQQ": 5 / 7, "BIL": 2 / 7}  # 차이 합 0.2857
        assert ca.apply_band(new, last) == (new, True)

    def test_defensive_swap_exceeds_band(self):
        last = {"QQQ": 0.5, "BIL": 0.5}
        new = {"QQQ": 0.5, "IEF": 0.5}
        assert ca.apply_band(new, last)[1] is True


class TestDecisionDates:
    def test_latest_decision_is_previous_month_last_trading_day(self):
        cal = pd.bdate_range("2026-08-01", "2026-10-05")
        assert ca.latest_decision_date(cal, pd.Timestamp("2026-10-05")) == pd.Timestamp("2026-09-30")
        assert ca.latest_decision_date(cal, pd.Timestamp("2026-09-30")) == pd.Timestamp("2026-08-31")

    def test_target_series_carries_last_on_missing_month(self):
        closes = _closes()
        dates = ca.month_end_dates(CAL)
        dates = dates[dates >= CAL[260]]
        full = ca.compute_target_series(closes, _nfci(-1), dates)
        assert len(full) == len(dates) and (full["QQQ"] == 1.0).all()
        # 마지막 판단일 봉을 지우면 그 달은 보류 → 직전 목표 유지
        gap = {t: s.drop(dates[-1], errors="ignore") for t, s in closes.items()}
        held = ca.compute_target_series(gap, _nfci(-1), dates)
        assert held.loc[dates[-1]].to_dict() == held.loc[dates[-2]].to_dict()


class TestStrategyClass:
    def test_flags_and_factory(self):
        s = get_strategy("canary_allocation")
        assert isinstance(s, CanaryAllocation)
        assert s.is_autonomous and s.is_target_weight
        assert s.calculate_score({}, "BULLISH") == 0.0
        assert set(s.hold_tickers) == {"QQQ", "IEF", "BIL"}
