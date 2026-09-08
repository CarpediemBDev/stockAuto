"""고점 판단 방법론 비교용 순수 판정기 모음.

수확 모드가 현재 쓰는 "관측 최고가 기록 + 고정 비율 트레일링"은 가장 단순한 방식이며
구조적 한계가 분명하다. 절대 고점에서는 팔 수 없어 항상 트레일링 폭만큼 반납하고,
고점의 구조적 의미(직전 스윙 하이, 저항선)를 전혀 보지 않는다.

이 파일은 대안 방법론들을 **같은 인터페이스로** 구현해 동일 조건에서 비교할 수 있게 한다.
docs/plans/holding_management_modes.md 6절의 검토 대상 8종이 여기 들어 있다.

## 이 파일이 하지 않는 것

여기에는 어떤 방법론이 더 낫다는 판단이 없다. 판단하려면 과거 급등 사례를 표본으로
돌려 봐야 하고, 그 실행은 별도 결정이다(scripts/evaluate_peak_detectors.py).

docs/strategy_alpha_verdict.md의 교훈이 여기에도 그대로 적용된다. 원시 수익률이 아니라
**동일 조건 대비 개선분**으로 판정해야 한다. 어떤 판정기든 급등주 표본에서는 큰 양의
수익을 내므로, 그 숫자만 보면 전부 훌륭해 보인다. 비교 대상은 언제나 베이스라인이다.

## 라이브에 바로 넣지 않는 이유

수확 모드는 되돌릴 수 없는 매도를 낸다. 검증되지 않은 판정기를 넣으면 사용자의 급등분을
잘못된 시점에 확정한다. 이 파일의 판정기들은 평가 하네스에서만 쓰이며, 실증 후에 하나가
채택되면 그때 trade_calculations로 옮긴다.

## 공통 인터페이스

각 판정기는 봉을 하나씩 받아 "지금 팔아라"를 bool로 돌려준다. 라이브 사이클이 봉 하나씩
관측하는 구조와 같게 맞춘 것이다 - 전체 시계열을 한 번에 보고 판정하면 미래를 훔쳐보는
착시(look-ahead bias)가 생기고, 백테스트만 좋고 라이브에서는 재현되지 않는다.

ZigZag처럼 본질적으로 후행 확정(repaint)인 방법론도 같은 인터페이스에 맞춰 두되,
그 한계를 각 클래스 주석에 명시한다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Bar:
    """평가에 쓰는 최소 봉 단위.

    atr은 봉 단위로 미리 계산해 넣는다. 판정기 안에서 계산하면 판정기마다 다른 ATR
    산출식을 쓰게 되어 비교가 오염된다.
    """
    high: float
    low: float
    close: float
    volume: float = 0.0
    atr: float = 0.0


class PeakDetector:
    """모든 판정기의 공통 계약.

    update()가 True를 돌려주면 그 봉의 종가에 청산한 것으로 본다. 한 번 True를 돌려준
    뒤의 호출 결과는 평가에서 무시되므로 상태를 되돌릴 필요가 없다.
    """

    name = "base"

    def reset(self) -> None:
        raise NotImplementedError

    def update(self, bar: Bar) -> bool:
        raise NotImplementedError


@dataclass
class ObservedPeakTrailing(PeakDetector):
    """베이스라인 - 관측 최고가 대비 고정 비율 이탈.

    수확 모드가 현재 쓰는 방식이다. 다른 모든 판정기는 이것과 비교된다.
    """

    trailing_pct: float = 5.0
    name: str = "observed_peak_trailing"
    _peak: float = field(default=0.0, init=False)

    def reset(self) -> None:
        self._peak = 0.0

    def update(self, bar: Bar) -> bool:
        self._peak = max(self._peak, bar.high)
        if self._peak <= 0:
            return False
        return bar.close <= self._peak * (1.0 - self.trailing_pct / 100.0)


@dataclass
class ChandelierExit(PeakDetector):
    """최고가 - ATR x k.

    현재 방식의 자연스러운 확장이며 가장 먼저 비교해볼 후보다. 고정 비율 대신 변동성으로
    폭을 정하므로, 잔잔한 구간에서는 타이트하고 급등 구간에서는 넓어진다.

    ATR을 못 구하면(0) 발동하지 않는다. 폭이 0이 되어 고점 직후 즉시 청산되는 것을
    막기 위함이다 - 변동성을 모른다는 것이 "폭이 없다"는 뜻은 아니다.
    """

    atr_mult: float = 3.0
    name: str = "chandelier_exit"
    _peak: float = field(default=0.0, init=False)

    def reset(self) -> None:
        self._peak = 0.0

    def update(self, bar: Bar) -> bool:
        self._peak = max(self._peak, bar.high)
        if self._peak <= 0 or bar.atr <= 0:
            return False
        return bar.close <= self._peak - bar.atr * self.atr_mult


@dataclass
class MovingAverageBreak(PeakDetector):
    """종가가 이동평균 아래로 이탈하면 추세 종료로 본다.

    급등 후 눌림에 관대해 일찍 털리지 않는 대신 반응이 느려 반납분이 크다. 이 맞바꿈이
    실제로 유리한지가 평가의 핵심 질문 중 하나다.

    창이 다 차기 전에는 판정하지 않는다. 짧은 평균은 가격을 그대로 따라가므로 이탈
    판정이 사실상 무작위가 된다.
    """

    window: int = 20
    name: str = ""
    _closes: list[float] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        # 창 길이가 이름에 들어가야 한다. 20일선과 50일선을 함께 비교하는데 이름이 같으면
        # 비교표(dict)에서 하나가 조용히 덮어써져 판정기 하나가 통째로 사라진다.
        if not self.name:
            self.name = f"ma_break_{self.window}"

    def reset(self) -> None:
        self._closes = []

    def update(self, bar: Bar) -> bool:
        self._closes.append(bar.close)
        if len(self._closes) < self.window:
            return False
        window = self._closes[-self.window:]
        return bar.close < sum(window) / len(window)


@dataclass
class SwingHighFailure(PeakDetector):
    """고점 갱신 실패(lower high)가 연속되면 추세 전환으로 본다.

    구조적 의미가 가장 명확한 방식이다. 다만 "무엇을 스윙 하이로 볼 것인가"의 파라미터
    민감도가 커서, lookback을 바꾸면 결과가 크게 달라질 수 있다. 평가에서 이 민감도를
    함께 재야 한다.

    확정된 스윙 하이만 쓴다. 좌우 lookback개 봉보다 높아야 스윙 하이로 인정하므로
    판정이 lookback개 봉만큼 늦다 - 이는 착시가 아니라 이 방법론의 실제 비용이다.

    ⚠️ 구조적 한계: 단조 하락에서는 발동하지 않는다. 스윙 하이가 형성되려면 국소 최고점이
    필요한데 한 방향으로만 움직이는 구간에는 그것이 없다. 즉 되돌림 없이 수직 낙하하는
    급락에서 이 판정기는 침묵한다. 계단식 하락(lower high가 반복되는 모양)에서만 작동하며,
    평가 시 표본에 그 두 모양이 모두 들어가야 이 한계가 성적에 정직하게 반영된다.
    """

    lookback: int = 3
    max_lower_highs: int = 2
    name: str = "swing_high_failure"
    _highs: list[float] = field(default_factory=list, init=False)
    _last_swing_high: float | None = field(default=None, init=False)
    _lower_high_count: int = field(default=0, init=False)

    def reset(self) -> None:
        self._highs = []
        self._last_swing_high = None
        self._lower_high_count = 0

    def update(self, bar: Bar) -> bool:
        self._highs.append(bar.high)
        span = self.lookback * 2 + 1
        if len(self._highs) < span:
            return False

        center_index = len(self._highs) - self.lookback - 1
        center = self._highs[center_index]
        window = self._highs[center_index - self.lookback: center_index + self.lookback + 1]
        if center < max(window):
            return False  # 중앙봉이 창의 최고가가 아니면 스윙 하이가 아니다

        if self._last_swing_high is not None and center < self._last_swing_high:
            self._lower_high_count += 1
        else:
            self._lower_high_count = 0
        self._last_swing_high = center
        return self._lower_high_count >= self.max_lower_highs


@dataclass
class DonchianBreak(PeakDetector):
    """N봉 최저가 채널 이탈.

    저장소에 이미 롤링 박스 스탑(compute_box_low / compute_rolling_box_stop /
    check_rolling_box_breach)으로 사실상 같은 구현이 있고, 래칫 불변식과 백테스트·라이브
    박스 길이 환산까지 갖추고 있다. 신규 구현 전에 그것을 수확 모드에 그대로 쓸 수 있는지
    먼저 보라는 것이 백로그의 지시다.

    여기서는 비교 가능한 최소 형태로만 재현한다. 채택이 결정되면 기존 구현을 쓰고
    이 클래스는 버린다 - SSOT를 둘로 쪼개지 않기 위함이다.
    """

    window: int = 20
    name: str = "donchian_break"
    _lows: list[float] = field(default_factory=list, init=False)
    _stop: float = field(default=0.0, init=False)

    def reset(self) -> None:
        self._lows = []
        self._stop = 0.0

    def update(self, bar: Bar) -> bool:
        # 판정은 직전까지의 완성 봉으로만 한다. 현재 봉의 저가를 채널에 넣고 그 채널로
        # 현재 봉을 판정하면 절대 이탈하지 않는다.
        breached = False
        if len(self._lows) >= self.window:
            window_low = min(self._lows[-self.window:])
            # 래칫 - 스탑은 내려가지 않는다. 급등분을 지키는 것이 목적이므로
            # 채널이 다시 낮아졌다고 스탑을 낮추면 반납분만 커진다.
            self._stop = max(self._stop, window_low)
            breached = self._stop > 0 and bar.close < self._stop
        self._lows.append(bar.low)
        return breached


@dataclass
class ZigZagReversal(PeakDetector):
    """임계 변동폭 이상의 전환만 고점으로 인정한다.

    ⚠️ 후행 확정(repaint) 위험이 가장 큰 방법론이다. 차트 위에서는 전환점이 깔끔하게
    보이지만 그것은 이미 확정된 과거이기 때문이다. 라이브에서는 임계를 넘긴 시점에야
    전환을 알 수 있으므로, 여기서도 임계 도달 시점에만 True를 돌려준다.

    백테스트에서 이 판정기가 유독 좋아 보인다면 구현이 미래를 훔쳐보고 있는지 먼저
    의심해야 한다.
    """

    reversal_pct: float = 8.0
    name: str = "zigzag_reversal"
    _peak: float = field(default=0.0, init=False)

    def reset(self) -> None:
        self._peak = 0.0

    def update(self, bar: Bar) -> bool:
        self._peak = max(self._peak, bar.high)
        if self._peak <= 0:
            return False
        drop_pct = (self._peak - bar.close) / self._peak * 100.0
        return drop_pct >= self.reversal_pct


@dataclass
class PivotSupportBreak(PeakDetector):
    """전일 고저종 기반 피벗 지지선 이탈.

    일봉 기준이라 분 단위 급등에는 부적합할 수 있다는 것이 백로그의 지적이다. 그 지적을
    확인하는 것 자체가 평가의 목적이므로 그대로 구현해 둔다.

    피벗 = (고 + 저 + 종) / 3, 1차 지지선 S1 = 2 x 피벗 - 고.
    """

    name: str = "pivot_support_break"
    _prev: Bar | None = field(default=None, init=False)

    def reset(self) -> None:
        self._prev = None

    def update(self, bar: Bar) -> bool:
        prev = self._prev
        self._prev = bar
        if prev is None:
            return False
        pivot = (prev.high + prev.low + prev.close) / 3.0
        support = 2.0 * pivot - prev.high
        return bar.close < support


@dataclass
class ParabolicSAR(PeakDetector):
    """가속 계수 기반 추적 스탑.

    급등장에서 트레일링보다 타이트해 조기 청산이 우려된다는 것이 백로그의 지적이다.
    가속 계수가 상승이 이어질수록 커져 스탑이 가격에 바싹 붙기 때문이다.

    상승 추세만 다룬다. 수확 모드는 이미 급등해 무장된 포지션에만 적용되므로 하락
    추세로의 전환은 곧 청산이고, 전환 후를 추적할 이유가 없다.
    """

    step: float = 0.02
    max_step: float = 0.20
    name: str = "parabolic_sar"
    _sar: float | None = field(default=None, init=False)
    _extreme: float = field(default=0.0, init=False)
    _accel: float = field(default=0.0, init=False)
    _prev_low: float | None = field(default=None, init=False)
    _prev_prev_low: float | None = field(default=None, init=False)

    def reset(self) -> None:
        self._sar = None
        self._extreme = 0.0
        self._accel = 0.0
        self._prev_low = None
        self._prev_prev_low = None

    def update(self, bar: Bar) -> bool:
        if self._sar is None:
            self._sar = bar.low
            self._extreme = bar.high
            self._accel = self.step
            self._prev_low = bar.low
            return False

        sar = self._sar + self._accel * (self._extreme - self._sar)

        # SAR은 직전 두 봉의 저가를 넘지 못한다(표준 규칙).
        #
        # 여기서 현재 봉의 저가로 누르면 안 된다. close < sar가 성립하려면 close < low여야
        # 하는데 그것은 정의상 불가능하므로, 판정기가 영원히 발동하지 않는 채로 조용히
        # 죽는다. 실제로 이 파일의 첫 구현이 그랬고 급락 표본에서 청산하지 않아 걸렸다.
        prior_lows = [low for low in (self._prev_low, self._prev_prev_low) if low is not None]
        if prior_lows:
            sar = min(sar, min(prior_lows))
        self._sar = sar

        breached = bar.close < sar

        if bar.high > self._extreme:
            self._extreme = bar.high
            self._accel = min(self._accel + self.step, self.max_step)
        self._prev_prev_low, self._prev_low = self._prev_low, bar.low

        return breached


@dataclass
class VolumeDryUp(PeakDetector):
    """거래량 급감으로 매수세 소진을 판정한다.

    ⚠️ 거래량 시계열이 확보되는지부터 확인이 필요하다는 것이 백로그의 지적이다.
    거래량이 0으로 들어오면(미확보) 이 판정기는 아무것도 하지 않는다 - 데이터가 없는데
    판정하면 없는 근거로 매도를 내는 셈이다.

    가격이 고점 아래일 때만 본다. 거래량이 줄면서 가격이 계속 오르는 구간은 매수세
    소진이 아니라 매도 물량 고갈일 수 있어 해석이 반대가 된다.
    """

    window: int = 20
    dry_ratio: float = 0.5
    name: str = "volume_dry_up"
    _volumes: list[float] = field(default_factory=list, init=False)
    _peak: float = field(default=0.0, init=False)

    def reset(self) -> None:
        self._volumes = []
        self._peak = 0.0

    def update(self, bar: Bar) -> bool:
        self._peak = max(self._peak, bar.high)
        prior = self._volumes[-self.window:]
        self._volumes.append(bar.volume)
        if bar.volume <= 0 or len(prior) < self.window:
            return False
        average = sum(prior) / len(prior)
        if average <= 0:
            return False
        return bar.volume < average * self.dry_ratio and bar.close < self._peak


def default_detectors(trailing_pct: float = 5.0) -> list[PeakDetector]:
    """백로그가 지정한 검토 대상 전부와 베이스라인을 함께 돌려준다.

    첫 원소가 베이스라인이며, 평가는 항상 이것과의 차이로 판정한다.
    """
    return [
        ObservedPeakTrailing(trailing_pct=trailing_pct),
        ChandelierExit(),
        MovingAverageBreak(window=20),
        MovingAverageBreak(window=50),
        SwingHighFailure(),
        DonchianBreak(),
        ZigZagReversal(),
        PivotSupportBreak(),
        ParabolicSAR(),
        VolumeDryUp(),
    ]


@dataclass(frozen=True)
class EpisodeResult:
    """한 급등 사례에 대한 판정기 하나의 성적."""

    detector: str
    exit_index: int | None
    exit_price: float
    peak_price: float

    @property
    def capture_rate(self) -> float:
        """고점 대비 얼마나 건졌는가. 1.0이면 절대 고점에서 판 것."""
        if self.peak_price <= 0:
            return 0.0
        return self.exit_price / self.peak_price


def run_episode(detector: PeakDetector, bars: list[Bar]) -> EpisodeResult:
    """판정기 하나를 한 사례에 돌린다.

    끝까지 청산 신호가 없으면 마지막 봉 종가로 청산한 것으로 본다. 표본 구간이 끝났는데
    아직 들고 있는 상태를 "청산하지 않음"으로 두면 그 사례가 비교에서 빠져, 늦게 파는
    판정기일수록 불리한 사례를 회피하는 셈이 된다.
    """
    detector.reset()
    peak = 0.0
    for index, bar in enumerate(bars):
        peak = max(peak, bar.high)
        if detector.update(bar):
            return EpisodeResult(detector.name, index, bar.close, peak)
    last_close = bars[-1].close if bars else 0.0
    return EpisodeResult(detector.name, None, last_close, peak)


def compare(
    detectors: list[PeakDetector], bars: list[Bar]
) -> dict[str, dict[str, float | int | None]]:
    """베이스라인 대비 개선분으로 비교한다.

    원시 청산가가 아니라 개선분으로 보는 이유는 docs/strategy_alpha_verdict.md의 교훈
    그대로다. 급등주 표본에서는 어떤 판정기든 큰 양의 수익을 내므로 절대 숫자만 보면
    전부 훌륭해 보인다. 판단은 언제나 동일 조건 대비 차이로 한다.
    """
    if not detectors or not bars:
        return {}
    names = [detector.name for detector in detectors]
    duplicates = {name for name in names if names.count(name) > 1}
    if duplicates:
        # 같은 이름이면 뒤 것이 앞 것을 덮어써 판정기가 통째로 사라진다. 비교표는 조용히
        # 한 줄 짧아질 뿐이라 눈치채기 어렵다 - 그래서 침묵 대신 실패를 택한다.
        raise ValueError(f"판정기 이름이 중복됐다: {sorted(duplicates)}")
    results = [run_episode(detector, bars) for detector in detectors]
    baseline = results[0]
    table: dict[str, dict[str, float | int | None]] = {}
    for result in results:
        improvement = 0.0
        if baseline.exit_price > 0 and math.isfinite(baseline.exit_price):
            improvement = (result.exit_price - baseline.exit_price) / baseline.exit_price * 100.0
        table[result.detector] = {
            "exit_index": result.exit_index,
            "exit_price": result.exit_price,
            "capture_rate": result.capture_rate,
            "improvement_pct_vs_baseline": improvement,
        }
    return table
