"""고점 판단 방법론 평가 하네스의 회귀 테스트.

이 파일은 "어느 방법론이 더 낫다"를 검증하지 않는다. 그 판단은 과거 급등 사례를 돌려야
나오고 아직 실행하지 않았다. 여기서 고정하는 것은 **비교 장치 자체가 정직한가**다.

측정 도구가 틀리면 그 위에서 나온 모든 결론이 틀린다. 특히 이 도메인에서는 두 가지가
조용히 결론을 뒤집는다.

  1. 미래 훔쳐보기(look-ahead) - 현재 봉의 정보로 현재 봉을 판정하면 백테스트만 좋고
     라이브에서는 재현되지 않는다.
  2. 생존 편향 - 끝까지 청산 신호가 없는 사례를 비교에서 빼면, 늦게 파는 판정기일수록
     불리한 사례를 회피하게 된다.

각 판정기는 "반드시 발동하는 계열"과 "반드시 발동하지 않는 계열" 두 방향으로 확인한다.
한 방향만 보면 항상 True를 돌려주는 고장난 판정기도 통과한다.
"""

import pytest

from app.bot.peak_detectors import (
    Bar,
    ChandelierExit,
    DonchianBreak,
    EpisodeResult,
    MovingAverageBreak,
    ObservedPeakTrailing,
    ParabolicSAR,
    PivotSupportBreak,
    SwingHighFailure,
    VolumeDryUp,
    ZigZagReversal,
    compare,
    default_detectors,
    run_episode,
)


def _rising(count: int, start: float = 100.0, step: float = 2.0, atr: float = 1.0):
    """단조 상승 구간. 어떤 판정기도 여기서는 팔면 안 된다."""
    bars = []
    price = start
    for _ in range(count):
        bars.append(Bar(high=price + 1, low=price - 1, close=price, volume=1000.0, atr=atr))
        price += step
    return bars


def _crashing(count: int, start: float, step: float = 5.0, atr: float = 1.0):
    """계단식 하락 구간. 모든 판정기가 언젠가는 팔아야 한다.

    되돌림 없는 수직 낙하가 아니라 하락 4봉 + 반등 4봉을 반복한다. 스윙 판정기 때문이다.
    스윙 하이는 좌우 lookback봉보다 높은 국소 최고점을 요구하는데, 한 방향으로만 움직이는
    구간에는 그것이 아예 없어서 순수 단조 하락 표본으로는 그 판정기가 구조적으로 침묵한다
    (peak_detectors.SwingHighFailure 주석). 반등 폭이 얕아도 마찬가지다 - 3봉 전보다
    높아야 하므로 찔끔 반등으로는 국소 최고점이 서지 않는다.

    반등 폭을 하락 폭의 절반으로 두어 순추세는 아래를 향하고, 반등 구간의 마지막 봉이
    직전 반등보다 낮은 국소 최고점(lower high)이 되게 한다.

    ⚠️ 이 모양 선택 자체가 스윙 판정기에 유리하다. 실제 평가 표본에는 계단식과 수직 낙하가
    모두 들어가야 한 방법론의 한계가 성적에 정직하게 반영된다.
    """
    bars = []
    price = start
    leg = 4
    for index in range(count):
        price += -step if (index // leg) % 2 == 0 else step * 0.5
        bars.append(Bar(high=price + 1, low=price - 1, close=price, volume=1000.0, atr=atr))
    return bars


# ======================================================================================
# 1. 판정기별 양방향 확인
# ======================================================================================

@pytest.mark.parametrize("detector", default_detectors())
def test_no_detector_sells_during_a_monotonic_rally(detector):
    """상승만 하는 구간에서 파는 판정기는 고장난 것이다.

    거래량은 일정하고 가격은 계속 오른다. 어떤 근거로도 추세 종료로 볼 수 없다.
    """
    bars = _rising(120)
    result = run_episode(detector, bars)
    assert result.exit_index is None, (
        f"{detector.name}이(가) 상승 구간에서 청산했다 - 판정 기준이 뒤집혀 있다"
    )


@pytest.mark.parametrize("detector", default_detectors())
def test_every_detector_sells_after_a_sustained_crash(detector):
    """충분히 오래 급락하면 모든 판정기가 판다.

    이 테스트가 없으면 아무것도 하지 않는 판정기가 위 테스트를 통과해 버린다.
    거래량 판정기까지 걸리도록 급락 구간에서 거래량을 함께 말린다.
    """
    bars = _rising(60) + [
        Bar(high=b.high, low=b.low, close=b.close, volume=50.0, atr=b.atr)
        for b in _crashing(80, start=170.0)
    ]
    result = run_episode(detector, bars)
    assert result.exit_index is not None, (
        f"{detector.name}이(가) 급락 구간에서도 청산하지 않았다"
    )


# ======================================================================================
# 2. 개별 판정기의 계약
# ======================================================================================

def test_observed_peak_trailing_fires_at_the_configured_drop():
    """베이스라인의 기준선이 설정값과 정확히 일치한다."""
    detector = ObservedPeakTrailing(trailing_pct=5.0)
    detector.reset()
    assert detector.update(Bar(high=100.0, low=99.0, close=100.0)) is False
    # 고점 100에서 -4.9%는 아직 아니다
    assert detector.update(Bar(high=100.0, low=95.0, close=95.1)) is False
    # -5.0% 도달은 판다 (경계 포함)
    assert detector.update(Bar(high=100.0, low=94.0, close=95.0)) is True


def test_chandelier_does_not_fire_without_atr():
    """ATR을 못 구하면 발동하지 않는다.

    폭이 0이 되면 고점 직후 즉시 청산된다. 변동성을 모른다는 것이 폭이 없다는 뜻은 아니다.
    """
    detector = ChandelierExit(atr_mult=3.0)
    detector.reset()
    detector.update(Bar(high=100.0, low=99.0, close=100.0, atr=0.0))
    assert detector.update(Bar(high=100.0, low=50.0, close=50.0, atr=0.0)) is False
    # ATR이 있으면 같은 폭락에서 판다
    detector.reset()
    detector.update(Bar(high=100.0, low=99.0, close=100.0, atr=2.0))
    assert detector.update(Bar(high=100.0, low=50.0, close=50.0, atr=2.0)) is True


def test_moving_average_waits_for_a_full_window():
    """창이 다 차기 전에는 판정하지 않는다.

    짧은 평균은 가격을 그대로 따라가므로 이탈 판정이 사실상 무작위가 된다.
    """
    detector = MovingAverageBreak(window=20)
    detector.reset()
    for _ in range(19):
        assert detector.update(Bar(high=10.0, low=1.0, close=1.0)) is False


def test_donchian_does_not_judge_the_bar_it_just_recorded():
    """현재 봉의 저가를 채널에 넣고 그 채널로 현재 봉을 판정하면 절대 이탈하지 않는다.

    미래 훔쳐보기의 거울상이다. 자기 자신을 포함한 채널은 언제나 자기보다 낮거나 같다.
    """
    detector = DonchianBreak(window=5)
    detector.reset()
    for price in (100.0, 101.0, 102.0, 103.0, 104.0):
        assert detector.update(Bar(high=price, low=price - 1, close=price)) is False
    # 직전 5봉의 최저 저가는 99. 그 아래로 종가가 내려가면 판다.
    assert detector.update(Bar(high=105.0, low=90.0, close=98.0)) is True


def test_donchian_stop_ratchets_upward_only():
    """채널이 낮아져도 스탑은 내려가지 않는다.

    급등분을 지키는 것이 목적이라 스탑을 낮추면 반납분만 커진다.
    """
    detector = DonchianBreak(window=3)
    detector.reset()
    for price in (100.0, 110.0, 120.0, 130.0):
        detector.update(Bar(high=price, low=price - 1, close=price))
    # 스탑은 최소 109까지 올라와 있다. 종가 105는 그 아래다.
    assert detector.update(Bar(high=131.0, low=104.0, close=105.0)) is True


def test_swing_high_failure_needs_confirmed_swings():
    """확정되지 않은 스윙으로는 판정하지 않는다.

    좌우 lookback개 봉보다 높아야 스윙 하이로 인정하므로 판정이 그만큼 늦다.
    이는 착시가 아니라 이 방법론의 실제 비용이며, 여기서 그 비용을 고정한다.
    """
    detector = SwingHighFailure(lookback=3, max_lower_highs=2)
    detector.reset()
    # 창(7봉)이 차기 전에는 어떤 모양이어도 판정하지 않는다
    for price in (100.0, 90.0, 80.0, 70.0, 60.0, 50.0):
        assert detector.update(Bar(high=price, low=price - 1, close=price)) is False


def test_pivot_support_uses_only_the_previous_bar():
    """첫 봉에서는 판정하지 않는다 - 기준으로 삼을 전일이 없다."""
    detector = PivotSupportBreak()
    detector.reset()
    assert detector.update(Bar(high=100.0, low=90.0, close=95.0)) is False


def test_parabolic_sar_stop_never_exceeds_the_previous_low():
    """SAR이 직전 저가를 넘으면 추세 안인데도 즉시 청산된다."""
    detector = ParabolicSAR()
    detector.reset()
    detector.update(Bar(high=100.0, low=98.0, close=99.0))
    # 강한 상승이 이어지는 동안에는 팔지 않는다
    for price in (105.0, 112.0, 120.0, 129.0):
        assert detector.update(Bar(high=price, low=price - 3, close=price - 1)) is False


def test_volume_detector_is_inert_without_volume_data():
    """거래량이 확보되지 않으면(0) 아무 판정도 하지 않는다.

    데이터가 없는데 판정하면 없는 근거로 매도를 내는 셈이다.
    """
    detector = VolumeDryUp(window=5)
    detector.reset()
    for _ in range(10):
        assert detector.update(Bar(high=100.0, low=50.0, close=60.0, volume=0.0)) is False


def test_zigzag_confirms_only_at_the_threshold():
    """임계에 도달한 시점에만 전환을 인정한다.

    차트 위 전환점은 이미 확정된 과거다. 라이브에서 그것을 미리 알 수는 없다.
    """
    detector = ZigZagReversal(reversal_pct=8.0)
    detector.reset()
    detector.update(Bar(high=100.0, low=99.0, close=100.0))
    assert detector.update(Bar(high=100.0, low=93.0, close=93.0)) is False  # -7%
    assert detector.update(Bar(high=100.0, low=92.0, close=92.0)) is True   # -8%


# ======================================================================================
# 3. 비교 장치
# ======================================================================================

def test_comparison_is_measured_against_the_baseline_not_raw_return():
    """판단 기준이 원시 청산가가 아니라 베이스라인 대비 개선분이다.

    급등주 표본에서는 어떤 판정기든 큰 양의 수익을 낸다. 절대 숫자만 보면 전부 훌륭해
    보이므로, 그 함정(docs/strategy_alpha_verdict.md)을 비교 장치가 구조적으로 막아야 한다.
    """
    bars = _rising(60) + _crashing(40, start=170.0)
    table = compare(default_detectors(), bars)

    assert "improvement_pct_vs_baseline" in table["observed_peak_trailing"]
    # 베이스라인의 자기 자신 대비 개선분은 정의상 0이다.
    assert table["observed_peak_trailing"]["improvement_pct_vs_baseline"] == pytest.approx(0.0)
    # 모든 판정기가 같은 표본에서 같은 축으로 비교된다.
    assert len(table) == len(default_detectors())


def test_unsold_episodes_are_closed_at_the_last_bar():
    """끝까지 청산 신호가 없으면 마지막 종가로 청산한 것으로 본다.

    그 사례를 비교에서 빼면 늦게 파는 판정기일수록 불리한 사례를 회피하게 된다.
    """
    bars = _rising(30)
    result = run_episode(ObservedPeakTrailing(trailing_pct=50.0), bars)
    assert result.exit_index is None
    assert result.exit_price == bars[-1].close


def test_capture_rate_reports_how_much_of_the_peak_survived():
    """고점 대비 얼마나 건졌는지가 판정기의 본질적 성적이다."""
    result = EpisodeResult("x", exit_index=3, exit_price=95.0, peak_price=100.0)
    assert result.capture_rate == pytest.approx(0.95)
    # 고점을 모르면(0) 0으로 떨어뜨린다. 0으로 나누지 않는다.
    assert EpisodeResult("x", None, 95.0, 0.0).capture_rate == 0.0


def test_compare_tolerates_empty_input():
    """표본이 없으면 빈 결과를 낸다. 예외로 평가 전체를 멈추지 않는다."""
    assert compare([], []) == {}
    assert compare(default_detectors(), []) == {}
