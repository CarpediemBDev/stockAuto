"""크로스에셋 카나리아 배분 (Canary Allocation) — 목표비중형 자율 슬롯 전략.

QQQ 자신의 가격이 아니라 '다른 자산'의 흐름 7개를 조기경보(카나리아)로 보고,
양호한 비율만큼 QQQ를 보유한다. 나머지는 IEF(중기 국채) 또는 BIL(초단기 국채)에 둔다.
월말 완결 일봉으로 한 번 판단하고 다음 정규장에서 집행한다.

이 모듈은 네트워크·DB를 만지지 않는 순수 계산만 담는다. 라이브 집행부
(app/bot/target_weight_executor.py)와 백테스트 엔진(_run_target_weight)이 같은
함수를 호출해 두 경로의 판단이 항상 일치한다(SSOT).

설계·근거: docs/plans/canary_allocation_live_port.md
"""
from __future__ import annotations

import pandas as pd

from app.strategies.base_strategy import BaseStrategy

# 13612U = 1·3·6·12개월(21·63·126·252 거래일) 수익률 평균
MOMENTUM_LOOKBACKS = (21, 63, 126, 252)
MIN_BARS = max(MOMENTUM_LOOKBACKS) + 1

# (신호 키, 종류, 분자 티커, 분모 티커). 종류: mom=절대 모멘텀, ratio=비율 모멘텀.
# 신호 구성이 바뀌면 백테스트 성적이 소급 변경되므로 연구 검증 없이 교체 금지.
PRICE_SIGNALS = (
    ("vwo", "mom", "VWO", None),
    ("agg", "mom", "AGG", None),
    ("smh_spy", "ratio", "SMH", "SPY"),
    ("xhb", "mom", "XHB", None),
    ("xlf_spy", "ratio", "XLF", "SPY"),
    ("sox", "mom", "^SOX", None),
)
NFCI_SIGNAL = "nfci"
SIGNAL_KEYS = tuple(k for k, *_ in PRICE_SIGNALS) + (NFCI_SIGNAL,)

NFCI_SERIES_ID = "NFCI"
NFCI_LAG_DAYS = 5        # 주간 발표 지연(관측 금요일 → 다음 주 수요일 발표) 보수적 반영, 거래일 기준
NFCI_WINDOW = 252        # 판단일 값 ≤ 직전 252거래일 평균이면 양호

EQUITY = "QQQ"
DEFENSIVE = ("IEF", "BIL")
CALENDAR_TICKER = "SPY"  # 거래일 달력 기준
DATA_TICKERS = ("VWO", "AGG", "SMH", "SPY", "XHB", "XLF", "^SOX", "IEF", "BIL")
HOLD_TICKERS = (EQUITY,) + DEFENSIVE
BAND = 0.10


def momentum_13612u(prices: pd.Series) -> float | None:
    """마지막 값 기준 13612U. 데이터가 MIN_BARS 미만이면 None."""
    p = prices.dropna()
    if len(p) < MIN_BARS:
        return None
    last = float(p.iloc[-1])
    vals = []
    for k in MOMENTUM_LOOKBACKS:
        base = float(p.iloc[-1 - k])
        if base <= 0:
            return None
        vals.append(last / base - 1.0)
    return sum(vals) / len(vals)


def _upto(series: pd.Series, as_of: pd.Timestamp) -> pd.Series:
    s = series.dropna()
    idx = pd.to_datetime(s.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    s = pd.Series(s.values, index=idx).sort_index()
    return s[s.index <= as_of]


def _nfci_ok(nfci: pd.Series | None, calendar: pd.DatetimeIndex) -> bool | None:
    """거래일 달력에 맞춰 NFCI를 채우고 NFCI_LAG_DAYS만큼 늦춘 뒤, 마지막 값 ≤ 직전 NFCI_WINDOW 평균이면 양호."""
    if nfci is None or len(calendar) == 0:
        return None
    s = nfci.dropna()
    if s.empty:
        return None
    idx = pd.to_datetime(s.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    s = pd.Series(s.values, index=idx).sort_index()
    aligned = s.reindex(s.index.union(calendar)).ffill().reindex(calendar).shift(NFCI_LAG_DAYS)
    tail = aligned.dropna()
    if len(tail) < NFCI_WINDOW:
        return None
    window = tail.iloc[-NFCI_WINDOW:]
    if tail.index[-1] != calendar[-1]:
        return None
    return bool(window.iloc[-1] <= window.mean())


def compute_signals(closes: dict[str, pd.Series], nfci: pd.Series | None, as_of) -> dict[str, bool] | None:
    """as_of(포함)까지의 완결 데이터만으로 신호 7개를 계산한다. 하나라도 계산 불가면 None."""
    as_of = pd.Timestamp(as_of).tz_localize(None) if pd.Timestamp(as_of).tzinfo else pd.Timestamp(as_of)
    out: dict[str, bool] = {}
    for key, kind, a, b in PRICE_SIGNALS:
        if a not in closes or (b and b not in closes):
            return None
        pa = _upto(closes[a], as_of)
        if kind == "ratio":
            pb = _upto(closes[b], as_of)
            joined = pd.concat([pa, pb], axis=1, join="inner").dropna()
            if joined.empty:
                return None
            series = joined.iloc[:, 0] / joined.iloc[:, 1]
        else:
            series = pa
        if series.empty or series.index[-1] != as_of:
            return None  # 판단일 봉이 없으면 데이터가 덜 들어온 것
        m = momentum_13612u(series)
        if m is None:
            return None
        out[key] = m > 0
    if CALENDAR_TICKER not in closes:
        return None
    calendar = pd.DatetimeIndex(_upto(closes[CALENDAR_TICKER], as_of).index)
    ok = _nfci_ok(nfci, calendar)
    if ok is None:
        return None
    out[NFCI_SIGNAL] = ok
    return out


def compute_target(signals: dict[str, bool], closes: dict[str, pd.Series], as_of) -> dict[str, float] | None:
    """신호 → 목표비중. 방어자산은 IEF 13612U > BIL 13612U면 IEF, 아니면 BIL."""
    if signals is None or set(signals) != set(SIGNAL_KEYS):
        return None
    as_of = pd.Timestamp(as_of)
    exposure = sum(1 for v in signals.values() if v) / len(SIGNAL_KEYS)
    target = {EQUITY: round(exposure, 6)}
    rest = round(1.0 - exposure, 6)
    if rest > 0:
        m_ief = momentum_13612u(_upto(closes["IEF"], as_of)) if "IEF" in closes else None
        m_bil = momentum_13612u(_upto(closes["BIL"], as_of)) if "BIL" in closes else None
        if m_ief is None or m_bil is None:
            return None
        target["IEF" if m_ief > m_bil else "BIL"] = rest
    return target


def weight_distance(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a) | set(b)
    return sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in keys)


def apply_band(new: dict[str, float], last: dict[str, float] | None, band: float = BAND) -> tuple[dict[str, float], bool]:
    """직전 확정 목표와의 비중 차이 합이 band 미만이면 직전 목표 유지. (확정 목표, 변경 여부)."""
    if not last:
        return dict(new), True
    if weight_distance(new, last) < band:
        return dict(last), False
    return dict(new), True


def latest_decision_date(calendar: pd.DatetimeIndex, today) -> pd.Timestamp | None:
    """today가 속한 달 '이전' 달들 중 마지막 거래일. 이번 달은 아직 완결되지 않았으므로 제외한다."""
    if len(calendar) == 0:
        return None
    today_p = pd.Timestamp(today).to_period("M")
    cal = pd.DatetimeIndex(calendar)
    if getattr(cal, "tz", None) is not None:
        cal = cal.tz_localize(None)
    prior = cal[cal.to_period("M") < today_p]
    return prior.max() if len(prior) else None


def month_end_dates(calendar: pd.DatetimeIndex) -> pd.DatetimeIndex:
    cal = pd.DatetimeIndex(calendar).sort_values()
    return pd.DatetimeIndex(cal.to_series().groupby(cal.to_period("M")).max().values)


def compute_target_series(closes: dict[str, pd.Series], nfci: pd.Series | None, decision_dates) -> pd.DataFrame:
    """백테스트용 전방 패스. 각 판단일의 '확정 목표'(밴드·결측 보류 반영)를 행으로 돌려준다.

    결측으로 판단할 수 없는 달은 직전 확정 목표를 그대로 이어간다(첫 확정 전이면 행 없음).
    """
    rows = {}
    last = None
    for d in decision_dates:
        sig = compute_signals(closes, nfci, d)
        tgt = compute_target(sig, closes, d) if sig is not None else None
        if tgt is None:
            if last is not None:
                rows[pd.Timestamp(d)] = dict(last)
            continue
        last, _ = apply_band(tgt, last)
        rows[pd.Timestamp(d)] = dict(last)
    frame = pd.DataFrame.from_dict(rows, orient="index").fillna(0.0)
    for t in HOLD_TICKERS:
        if t not in frame.columns:
            frame[t] = 0.0
    return frame[list(HOLD_TICKERS)].sort_index()


class CanaryAllocation(BaseStrategy):
    """🐤 크로스에셋 카나리아 배분 — 다른 자산 7개의 조기경보 비율만큼 QQQ 보유(1x, 월 1회)."""

    is_autonomous = True       # 스캐너 진입·손절/트레일링 파이프라인 면제
    is_target_weight = True    # IN/OUT 경로가 아닌 목표비중 경로(target_weight_executor)로 집행

    data_tickers = DATA_TICKERS
    hold_tickers = HOLD_TICKERS
    band = BAND

    def __init__(self):
        super().__init__(name="🐤 크로스에셋 카나리아 배분 (QQQ × 경보 7종 양호비율)")
        self.base_allocation_pct = 1.0
        self.min_allocation_usd = 0.0

    def compute_signals(self, closes, nfci, as_of):
        return compute_signals(closes, nfci, as_of)

    def compute_target(self, signals, closes, as_of):
        return compute_target(signals, closes, as_of)

    def apply_band(self, new, last):
        return apply_band(new, last, self.band)

    def compute_target_series(self, closes, nfci, decision_dates):
        return compute_target_series(closes, nfci, decision_dates)

    def calculate_score(self, row, regime: str, is_entry: bool = True, score_card: list = None) -> float:
        """자율 슬롯은 스캐너 점수를 쓰지 않는다. 항상 0점(미발화)."""
        if score_card is not None:
            score_card.append({
                "factor": "자율 슬롯 (스캐너 점수 미사용 — 월말 카나리아 판단 전용)",
                "score": 0,
                "passed": False,
            })
        return 0.0
