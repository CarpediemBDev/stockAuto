"""라이브 진입 채점 입력과 전략 조건의 계약 회귀 테스트.

배경 - 전략 클래스는 백테스트 엔진이 만드는 지표 이름으로 작성돼 있는데, 라이브
스캐너가 같은 이름으로 값을 싣지 않으면 BaseStrategy._safe_get이 예외 없이 0.0을
돌려준다. 그 0.0이 어떻게 터지는지는 비교 연산자에 달려 있고, 세 가지 실패 모드가
모두 실제로 관측됐다(2026-08-23 실측).

  1. 미진입    - `flag == 1.0` 게이트가 영원히 거짓. 거래 0건, 수익률 정확히 0.00%.
  2. 오진입    - `close > 기준선(0.0)`이 항상 참. 무차별 매수 + 시그널 청산 무력화.
                 darvas_box -43.25% / opening_range_breakout -24.31% / donchian_breakout -20.93%.
  3. 부분 퇴화 - 게이트 하나만 조용히 죽고 나머지 조건으로 매매. macro_momentum이 이 상태.

에러도 로그도 남지 않아 "오늘은 살 종목이 없네"와 구분되지 않는 것이 이 결함의 성질이다.
따라서 이 파일은 정적 선언이 아니라 실제 발화 여부로 계약을 검증한다.
"""
import importlib.util
import json
from functools import lru_cache
from pathlib import Path

import pytest

from app.scanner.signal_contract import (
    FALLBACK_SUBSTITUTIONS,
    LIVE_SIGNAL_KEYS,
    PENDING_FIELD_SET,
    UNSUPPORTED_FIELD_SET,
)
from app.strategies.base_strategy import record_missing_fields
from app.strategies.strategy_factory import get_strategy

REGIMES = ("BULLISH", "NEUTRAL", "BEARISH")

# 청산 전용 경로(analyze_single_ticker)에만 실리는 키. 진입 채점 입력에는 없다.
EXIT_ONLY_KEYS = frozenset({"is_fundamental_healthy", "is_smart_exit"})

# 라이브 진입 채점이 실제로 받는 키. 목록을 여기에 복사해두면 스캐너가 바뀔 때
# 조용히 어긋나므로 계약 SSOT(app/scanner/signal_contract.py)에서 직접 읽는다.
LIVE_DETAIL_KEYS = tuple(sorted(LIVE_SIGNAL_KEYS - EXIT_ONLY_KEYS))

# 결손 시 `close > 기준선(0.0)`이 항상 참이 되어 무차별 진입했던 전략과 그 기준선.
BREAKOUT_REFERENCE_FIELDS = {
    "darvas_box": ("darvas_high",),
    "donchian_breakout": ("donchian_high_20", "BB_upper"),
    "opening_range_breakout": ("orb_high_30m", "BB_upper", "volume_ma20"),
    "chaikin_atr": ("donchian_high_20", "BB_upper", "volume_ma20"),
}

# 외부 데이터가 없어 라이브에서 원리상 진입할 수 없는 전략(마이그레이션 b7c3d9e14a20).
UNSELECTABLE_UNSUPPORTED = frozenset({
    "cross_asset", "dark_pool", "earn_drift", "float_rot", "gamma_flip", "gex_pinning",
    "insider_buying", "kalman_pairs", "max_pain", "obi_ofa", "offering_reb", "order_flow",
    "pairs_trading", "pca_knn", "pdufa_calendar", "sentiment_fomo", "social_buzz",
    "sympathy", "vix_hedging", "volatility_regime", "warrant_arb",
})

# 라이브 신호에 아직 실리지 않는 지표 때문에 진입하지 못하는 전략. 장중 프레임(ORB)이
# 있어야 채울 수 있어 일봉 스냅샷으로는 복구되지 않는다. 이 목록이 비면 살릴 수 있는
# 전략을 전부 살린 것이다.
PENDING_RESTORATION = frozenset({"opening_range_breakout"})

# 설계상 진입 채점을 하지 않는 전략(calculate_score가 is_entry에서 항상 0.0).
# 보유 종목의 위험 극점 청산만 담당하므로 단독 선택 시 매수가 발생하지 않는다.
EXIT_ONLY_STRATEGIES = frozenset({"parabolic_blow"})

BOOLEAN_SIGNAL_KEYS = (
    "is_near_52w_high", "is_near_recent_high", "momentum_candles", "is_orb_breakout",
    "is_rsi_bb_extreme", "is_obv_accumulation", "is_vcp", "is_cup", "has_news",
    "ema_aligned",
)


def _synthetic_daily_frame(drift_pct_per_bar, seed, volatility=0.004):
    """지표 계산용 합성 일봉. 지표 대부분이 60~252봉 롤링이라 300봉을 만든다."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(seed)
    steps = 1.0 + drift_pct_per_bar / 100.0 + rng.normal(0.0, volatility, 300)
    close = pd.Series(
        100.0 * np.cumprod(steps),
        index=pd.date_range("2024-01-01", periods=300, freq="D"),
    )
    return pd.DataFrame(
        {
            "Open": close.shift(1).fillna(close.iloc[0]),
            "High": close * 1.008,
            "Low": close * 0.992,
            "Close": close,
            "Volume": rng.uniform(2e6, 3e6, 300),
        },
        index=close.index,
    )


def _base_signal():
    """스캐너 고유 표기 키와 라이브 전용 계산값. 일봉 스냅샷이 채우지 않는 부분이다."""
    return {
        "gap": 0.0, "rvol": 1.0, "wick": 0.1, "has_news": False, "risk": "LOW",
        "rs": 0.0, "ema_aligned": False, "atr": 1.0, "recent_lows_15m": [98.0, 97.0],
        "dollar_volume": 5e7, "is_near_52w_high": False, "is_near_recent_high": False,
        "momentum_candles": False, "premarket_gap_pct": 0.0, "is_orb_breakout": False,
        "is_rsi_bb_extreme": False, "is_obv_accumulation": False, "is_vcp": False,
        "is_cup": False, "regime_mode": "NEUTRAL", "Close": 100.0, "Volume": 2_000_000.0,
        "VWAP": 100.5, "RVOL": 1.0, "EMA9": 101.0, "EMA20": 102.0, "EMA120": 105.0,
        "OBV_divergence": -1.0, "is_double_bb_buy": 0.0, "is_double_bb_sell": 0.0,
        # build_canonical_metrics가 라이브 관측 구간에 맞춰 따로 계산하는 값
        "Open": 101.0, "gap_pct": 0.0, "Wick": 0.1, "change_pct": -1.0,
        "relative_strength": -2.0, "dist_to_high": -30.0, "is_penny": 0.0,
        "is_triple_ema_up": 0.0,
    }


@lru_cache(maxsize=None)
def _cached_snapshot(drift_pct_per_bar, seed):
    """같은 (추세, 시드)의 지표 스냅샷을 재사용한다.

    스냅샷 한 번이 300봉 기준 1초 가까이 걸려서, 캐시 없이는 이 파일 하나로 테스트
    실행이 수 분 늘어난다. 반환값은 호출부가 수정하므로 항상 사본을 준다.
    """
    from app.scanner.signal_contract import daily_indicator_snapshot

    return daily_indicator_snapshot(_synthetic_daily_frame(drift_pct_per_bar, seed))


def live_signal(drift_pct_per_bar=-0.05, seed=101):
    """라이브가 실제로 만드는 것과 같은 경로로 진입 채점 입력을 만든다.

    지표 값을 손으로 적어두면 스캐너가 새 지표를 싣기 시작할 때 테스트 입력만 낡아
    조용히 무의미해지므로, 라이브와 같은 daily_indicator_snapshot을 통과시킨다.
    """
    signal = _base_signal()
    signal.update(_cached_snapshot(drift_pct_per_bar, seed))
    return signal


def strong_live_signal():
    """강세 신호를 최대로 켠 입력. 정상 전략이라면 여기서 진입해야 한다."""
    signal = live_signal(0.25, seed=202)
    signal.update({
        "gap": 9.0, "gap_pct": 9.0, "rvol": 8.0, "RVOL": 8.0, "rs": 3.0,
        "relative_strength": 3.0, "change_pct": 6.0, "dist_to_high": -0.5,
        "premarket_gap_pct": 7.0, "Close": 110.0, "Open": 100.0, "Volume": 9_000_000.0,
        "VWAP": 104.0, "EMA9": 105.0, "EMA20": 100.0, "EMA120": 90.0,
        "OBV_divergence": 1.0, "is_double_bb_buy": 1.0, "is_triple_ema_up": 1.0,
    })
    for key in BOOLEAN_SIGNAL_KEYS:
        signal[key] = True
    return signal


def diverse_live_signals():
    """상승·하락·횡보를 고루 덮는 입력 집합."""
    return [
        strong_live_signal(),
        live_signal(0.20, seed=11),
        live_signal(0.05, seed=12),
        live_signal(0.0, seed=13),
        live_signal(-0.05, seed=14),
        live_signal(-0.20, seed=15),
        live_signal(0.0, seed=16),
        live_signal(-0.10, seed=17),
    ]


def randomized_live_signals(count=200, seed=20260823):
    """라이브가 실을 수 있는 값 범위를 무작위로 훑는다.

    합성 일봉은 매끄러운 추세라 `RVOL 5배 + 당일 15% 급등`(supernova)이나
    `-10% 갭 + RSI 25 이하`(panic_dip) 같은 극단 셋업을 만들지 못한다. 도달 가능성은
    "그 지표 값이 나올 수 있는가"의 문제이므로 필드 값을 직접 흔들어 확인한다.
    """
    import random

    rng = random.Random(seed)
    template = live_signal()
    numeric_keys = [
        key for key, value in template.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    signals = []
    for _ in range(count):
        signal = dict(template)
        close = rng.uniform(5.0, 400.0)
        signal["Close"] = close
        signal["Volume"] = rng.uniform(1e5, 5e7)
        for key in numeric_keys:
            if key in ("Close", "Volume"):
                continue
            # 필드마다 값 영역이 다르다(0/1 플래그, -100~100 오실레이터, 가격, 거래량).
            # 이름이나 기본값 크기로 영역을 추정하면 RSI에 주가 스케일 값을 넣는 식으로
            # 틀리므로, 네 영역을 섞어 뽑아 어느 조건이든 도달 가능하게 한다.
            draw = rng.random()
            if draw < 0.30:
                signal[key] = float(rng.random() < 0.5)
            elif draw < 0.60:
                signal[key] = rng.uniform(-100.0, 100.0)
            elif draw < 0.75:
                signal[key] = close * rng.uniform(0.6, 1.4)
            elif draw < 0.90:
                # 지지선·저항선 근접 조건(현재가 대비 ±2%)을 만들기 위한 좁은 영역
                signal[key] = close * rng.uniform(0.98, 1.02)
            else:
                signal[key] = rng.uniform(1e5, 5e7)
        for key in BOOLEAN_SIGNAL_KEYS:
            signal[key] = rng.random() < 0.5
        signals.append(signal)
    return signals


def narrow_setup_signals():
    """세 조건이 동시에 성립해야 하는 전략을 위한 손수 만든 셋업.

    무작위 추출로는 좁은 교집합(예: 전일비 +5~15% & 상승추세 & 추세선 ±1% 근접)이
    거의 안 나온다. 도달 가능성을 못 보여주는 것이 전략 결함으로 오인되지 않게 한다.
    """
    signal = live_signal(0.20, seed=303)
    close = 100.0
    signal.update({
        "Close": close, "close": close, "change_pct": 8.0,
        "is_uptrend": 1.0, "trendline_support": close,
        "Volume": 3_000_000.0,
    })
    return [signal]


def entry_score(strategy, signal, regime):
    payload = dict(signal)
    payload["regime_mode"] = regime
    try:
        return float(strategy.calculate_score(payload, regime, is_entry=True))
    except TypeError:
        return float(strategy.calculate_score(payload, regime, is_entry=True, score_card=None))


def fires(strategy, signal):
    return any(
        entry_score(strategy, signal, regime) >= strategy.get_cutoff_score(regime)
        for regime in REGIMES
    )


def selectable_strategy_types():
    from app.core import models
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        return [
            row[0]
            for row in db.query(models.Strategy.strategy_type)
            .filter(models.Strategy.is_selectable == True)  # noqa: E712
            .all()
        ]
    finally:
        db.close()


def test_live_signal_covers_exactly_the_contract_keys():
    """테스트 입력이 실제 라이브 신호 계약과 어긋나면 이 파일 전체가 무의미해진다."""
    assert set(live_signal()) == set(LIVE_DETAIL_KEYS)


@pytest.mark.parametrize(
    "strategy_type,reference_fields", sorted(BREAKOUT_REFERENCE_FIELDS.items())
)
def test_breakout_strategies_do_not_enter_without_their_reference_line(
    strategy_type, reference_fields
):
    """돌파 기준선이 없으면 진입 점수를 내지 않는다(0.0과 비교하지 않는다).

    상장 초기 종목처럼 일봉이 짧아 스냅샷이 실리지 않을 때 실제로 발생하는 상황이다.
    """
    strategy = get_strategy(strategy_type)
    signal = strong_live_signal()
    for field in reference_fields:
        signal.pop(field, None)
    for regime in REGIMES:
        assert entry_score(strategy, signal, regime) == 0.0


@pytest.mark.parametrize("strategy_type", sorted(BREAKOUT_REFERENCE_FIELDS))
def test_breakout_strategies_still_work_when_indicators_are_present(strategy_type):
    """지표가 실리면 정상 판정한다(과잉 차단 회귀 방지)."""
    strategy = get_strategy(strategy_type)
    breakout = strong_live_signal()
    breakout.update({
        "Close": 500.0,           # 어떤 기준선보다도 높은 종가
        "Volume": 5e8,            # 거래량 필터 통과
        "chaikin_volatility": 5.0,
        # 시초 레인지는 장중 5분봉에서만 나오므로 라이브·백테스트 어느 쪽도 싣지 않는다.
        # 볼린저 밴드로 대체하면 이름만 ORB인 다른 전략을 재는 셈이라 폴백을 없앴고,
        # 대신 값이 실제로 주어졌을 때 정상 판정하는지를 여기서 확인한다.
        "orb_high_30m": 400.0,
        "orb_low_30m": 380.0,
    })
    assert max(entry_score(strategy, breakout, regime) for regime in REGIMES) == 100.0


def test_no_strategy_enters_indiscriminately():
    """모든 시세에서 진입하는 전략이 있어서는 안 된다.

    조건이 소멸해 '무조건 매수'로 퇴화한 상태의 서명이다. 거래가 활발해 지표만 봐서는
    정상으로 보이지만, 실제로 집행되는 것은 전략이 아니라 무차별 매수다.
    """
    signals = diverse_live_signals()
    offenders = []
    for strategy_type in sorted(selectable_strategy_types()):
        strategy = get_strategy(strategy_type)
        if getattr(strategy, "is_autonomous", False) or getattr(strategy, "is_composite", False):
            continue
        if all(fires(strategy, signal) for signal in signals):
            offenders.append(strategy_type)
    assert not offenders, f"모든 시세에서 진입하는 전략(조건 소멸 의심): {offenders}"


def test_strategies_needing_external_data_are_not_selectable():
    """외부 데이터가 없어 진입이 불가능한 전략은 사용자가 고를 수 없어야 한다.

    고를 수 있게 두면 봇은 기동되지만 단 한 건도 매매하지 않고 수익률 0%에 머문다.
    """
    exposed = sorted(UNSELECTABLE_UNSUPPORTED & set(selectable_strategy_types()))
    assert not exposed, f"외부 데이터 의존 전략이 카탈로그에 노출돼 있다: {exposed}"


def test_every_selectable_strategy_can_enter_unless_it_is_a_known_backlog():
    """사용자가 고를 수 있는 전략은 라이브 신호만으로 진입에 도달할 수 있어야 한다.

    PENDING_RESTORATION에 등록되지 않은 도달 불가 전략이 생기면 실패한다. 목록이 비면
    "고를 수 있는 모든 전략은 실제로 매매할 수 있다"는 완전한 불변식이 된다.
    """
    signals = diverse_live_signals() + narrow_setup_signals() + randomized_live_signals()
    unreachable = []
    for strategy_type in sorted(selectable_strategy_types()):
        strategy = get_strategy(strategy_type)
        if getattr(strategy, "is_autonomous", False) or getattr(strategy, "is_composite", False):
            continue
        if strategy_type in PENDING_RESTORATION or strategy_type in EXIT_ONLY_STRATEGIES:
            continue
        if not any(fires(strategy, signal) for signal in signals):
            unreachable.append(strategy_type)
    assert not unreachable, (
        "라이브 신호로 진입할 수 없는 전략이 카탈로그에 노출돼 있다: " + repr(unreachable)
    )


def test_no_strategy_silently_reads_a_field_the_live_signal_lacks():
    """라이브 신호로 채점할 때 결손 필드 읽기가 남아 있으면 안 된다.

    _safe_get은 없는 키를 기본값 0.0으로 돌려주고 아무 흔적도 남기지 않는다. 정적
    검사는 소스에 리터럴로 적힌 읽기만 보므로, 실제 실행에서 무엇이 결손이었는지는
    관찰자로만 알 수 있다. 결손이 허용되는 것은 계약이 아직 못 싣는다고 선언한
    필드(PENDING)와 외부 데이터가 필요한 필드(UNSUPPORTED)뿐이다.
    """
    declared_absent = PENDING_FIELD_SET | UNSUPPORTED_FIELD_SET | EXIT_ONLY_KEYS
    signal = strong_live_signal()

    with record_missing_fields() as missing:
        for strategy_type in sorted(selectable_strategy_types()):
            strategy = get_strategy(strategy_type)
            for regime in REGIMES:
                for is_entry in (True, False):
                    payload = dict(signal)
                    payload["regime_mode"] = regime
                    try:
                        strategy.calculate_score(payload, regime, is_entry=is_entry)
                    except TypeError:
                        strategy.calculate_score(
                            payload, regime, is_entry=is_entry, score_card=None
                        )

    undeclared = sorted({key for _, key in missing if key not in declared_absent})
    assert not undeclared, (
        "라이브 신호에 없는데 계약에도 선언되지 않은 필드를 전략이 읽고 있다: "
        + repr(undeclared)
    )


# --- 폴백 치환 (대체 측정) 계약 -------------------------------------------------
#
# 필드 '존재' 검사는 폴백 경로를 통과한다. 값이 실제로 채워지기 때문이다. 그래서
# 전략은 정상 채점되지만 측정 대상이 바뀐다 - opening_range_breakout이 orb_high_30m
# 대신 BB_upper를 읽던 시절, 이름은 ORB인데 실제로는 볼린저 돌파를 재고 있었다.
# 아래 세 테스트가 그 경로를 상시로 감시한다.

_GUARD_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "check_signal_field_contract.py"
)
_REPO_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def _guard_module():
    spec = importlib.util.spec_from_file_location("_signal_contract_guard", _GUARD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fallback_substitutions_match_the_contract_declaration():
    """코드의 폴백 치환과 FALLBACK_SUBSTITUTIONS 선언이 정확히 일치해야 한다.

    일치를 강제해야 무엇을 실제로 재고 있는지가 diff에 남는다. 종수 임계값이
    아니라 목록 차분으로 검사하는 이유이기도 하다 - 치환 하나가 다른 하나로
    교체되면 개수는 같지만 측정 대상은 달라진다.
    """
    detected = _guard_module()._fallback_substitutions(_REPO_ROOT)
    declared = {item for group in FALLBACK_SUBSTITUTIONS.values() for item in group}

    assert detected == declared, (
        "폴백 치환 선언이 코드와 어긋났다. "
        f"코드에만 있음={sorted(detected - declared)}, "
        f"선언에만 있음={sorted(declared - detected)}"
    )


def test_no_strategy_is_silently_measuring_a_substitute():
    """원본이 결손으로 선언된 필드를 폴백으로 대체하는 전략이 없어야 한다.

    이 상태의 전략은 이름이 말하는 것과 다른 것을 잰다. 백테스트 성적을 그대로
    믿을 수 없으므로, 새로 생기면 반드시 사람이 판단해야 한다.
    """
    declared_absent = PENDING_FIELD_SET | UNSUPPORTED_FIELD_SET
    substituted = sorted(
        item
        for group in FALLBACK_SUBSTITUTIONS.values()
        for item in group
        if item.split("->")[0].split(":")[1] in declared_absent
    )
    assert not substituted, (
        "결손 필드를 다른 필드로 대체 측정 중인 전략이 있다(백테스트 성적 무효): "
        + repr(substituted)
    )


def test_fallback_guard_detects_a_reintroduced_substitution(tmp_path):
    """가드가 실제로 치환을 잡는지 확인하는 네거티브 컨트롤.

    2026-08-23에 실제로 있었던 결함(ORB가 시초 레인지 대신 볼린저 상단을 읽던 것)을
    합성 전략 파일로 재현한다. 이 테스트가 통과해야 위 두 테스트의 통과가 의미를 갖는다.
    """
    strategies = tmp_path / "backend" / "app" / "strategies"
    strategies.mkdir(parents=True)
    (strategies / "fake_orb.py").write_text(
        "class FakeOrb:\n"
        "    def calculate_score(self, row, regime, is_entry=True):\n"
        "        orb_high = self._safe_get(row, 'orb_high_30m')\n"
        "        if orb_high == 0.0:\n"
        "            orb_high = self._safe_get(row, 'BB_upper')\n"
        "        vwap = self._safe_get(row, 'VWAP', self._safe_get(row, 'EMA9'))\n"
        "        return 100.0 if orb_high > vwap else 0.0\n",
        encoding="utf-8",
    )

    detected = _guard_module()._fallback_substitutions(tmp_path)

    assert "fake_orb:orb_high_30m->BB_upper" in detected, (
        "결손 확인 후 재대입(`if X == 0.0: X = ...`) 형태를 놓쳤다"
    )
    assert "fake_orb:VWAP->EMA9" in detected, (
        "기본값 자리에 다른 필드를 넣는 형태를 놓쳤다"
    )


# --- 전략별 기대 상태 스냅샷 --------------------------------------------------
#
# "미진입 N종 이하면 통과" 식의 임계값 가드는 쓰지 않는다. 2026-08-23 실측에서
# 퇴화 3종을 차단하는 정당한 수정이 미진입 종수를 21->18 진입 / 73->76 미진입으로
# 늘렸다. 종수만 보면 회귀로 오판한다. 반대로 종수가 같아도 구성이 바뀔 수 있다
# (퇴화 3종이 부활 3종으로 교체된 사례). 그래서 종수가 아니라 목록 차분을 본다.
#
# 상태를 바꾸는 변경은 스냅샷 갱신을 강제하므로, 왜 바뀌었는지가 항상 diff에 남는다.

ENTRY_STATE_SNAPSHOT = Path(__file__).with_name("strategy_entry_states.json")

STATE_ENTERABLE = "진입가능"
STATE_MISSING_FIELD = "미진입-지표누락"
STATE_BLOCKED = "미진입-의도차단"
STATE_AUTONOMOUS = "자율"


@lru_cache(maxsize=1)
def _reachability_signals():
    """도달 가능성 판정용 입력 집합. 무거우므로 한 번만 만든다."""
    return tuple(diverse_live_signals() + randomized_live_signals() + narrow_setup_signals())


# 슬롯 합성 전략은 팩토리 분기문에 리터럴로 나타나지 않는다.
# scripts/check_strategy_consistency.py가 쓰는 목록과 같은 값을 유지한다.
_MULTI_SLOT_KEYS = ("multi_slot", "multi_slot_3", "three_slot", "core_satellite")


@lru_cache(maxsize=1)
def _catalog_strategy_types():
    """전략 목록을 코드에서 뽑는다. DB에서 읽으면 안 된다.

    strategies 테이블은 환경마다 시드가 다르다(로컬 개발 DB 100종, CI 시드는 별개).
    DB를 기준으로 스냅샷을 뜨면 같은 커밋이 머신에 따라 통과와 실패를 오간다.
    실제로 이 가드의 첫 판이 그 이유로 CI에서 반려됐다. 전략의 존재 여부를 결정하는
    SSOT는 팩토리이므로 거기서 뽑는다.
    """
    import re

    source = (
        Path(__file__).resolve().parents[1]
        / "app" / "strategies" / "strategy_factory.py"
    ).read_text(encoding="utf-8")

    keys = set(_MULTI_SLOT_KEYS)
    keys |= set(re.findall(r'strategy_type\s*==\s*"([^"]+)"', source))
    for block in re.findall(r"strategy_type\s*in\s*\[(.*?)\]", source, re.S):
        keys |= set(re.findall(r'"([^"]+)"', block))
    return sorted(keys)


def _classify_entry_state(strategy_type):
    """전략 하나의 라이브 진입 상태를 판정한다."""
    try:
        strategy = get_strategy(strategy_type)
    except Exception:
        return None
    if strategy is None:
        return None

    # 자율 전략은 스캐너 채점을 타지 않는다. 0점이 정상이므로 별도 상태로 둔다.
    if getattr(strategy, "is_autonomous", False):
        return STATE_AUTONOMOUS

    if any(fires(strategy, signal) for signal in _reachability_signals()):
        return STATE_ENTERABLE

    # 발화하지 않는 이유를 가른다. 결손 필드를 읽고 있으면 배선 문제이고,
    # 아니면 조건 자체가 이 입력 범위에서 닫혀 있는 것이다(의도된 차단 포함).
    declared_absent = PENDING_FIELD_SET | UNSUPPORTED_FIELD_SET
    with record_missing_fields() as missing:
        for regime in REGIMES:
            entry_score(strategy, _reachability_signals()[0], regime)
    if any(key in declared_absent for _, key in missing):
        return STATE_MISSING_FIELD
    return STATE_BLOCKED


def current_entry_states():
    """카탈로그 전 전략의 현재 상태 맵."""
    states = {}
    for strategy_type in _catalog_strategy_types():
        state = _classify_entry_state(strategy_type)
        if state is not None:
            states[strategy_type] = state
    return states


def test_strategy_entry_states_match_the_snapshot():
    """전략별 진입 상태가 스냅샷과 정확히 일치해야 한다.

    실패했다면 둘 중 하나다.
      1. 조용한 퇴화 - 배선이 끊겨 진입가능 전략이 미진입으로 내려갔다. 코드를 고친다.
      2. 의도된 변경 - 퇴화 차단이나 신규 배선이다. 스냅샷을 갱신하고 그 사유를
         현황판 `변경 영향 기록`에 남긴다.

    스냅샷 갱신 명령:
        python scripts/update_strategy_entry_states.py
    """
    assert ENTRY_STATE_SNAPSHOT.exists(), (
        f"기대 상태 스냅샷이 없다: {ENTRY_STATE_SNAPSHOT}. "
        "python scripts/update_strategy_entry_states.py 로 생성하세요."
    )
    expected = json.loads(ENTRY_STATE_SNAPSHOT.read_text(encoding="utf-8"))["states"]
    actual = current_entry_states()

    appeared = sorted(set(actual) - set(expected))
    disappeared = sorted(set(expected) - set(actual))
    changed = sorted(
        f"{name}: {expected[name]} -> {actual[name]}"
        for name in set(expected) & set(actual)
        if expected[name] != actual[name]
    )

    assert not (appeared or disappeared or changed), (
        "전략 진입 상태가 스냅샷과 다르다. 조용한 퇴화가 아니라면 "
        "python scripts/update_strategy_entry_states.py 로 갱신하고 사유를 현황판에 남길 것.\n"
        f"  신규 전략: {appeared}\n"
        f"  사라진 전략: {disappeared}\n"
        f"  상태 변경: {changed}"
    )


# --- 청산 반응성 -------------------------------------------------------------
#
# 2026-08-31: 이 절은 원래 "청산 경로에서 결손 필드를 읽는가"를 셌다. 그 지표로
# 13종을 "시그널 청산 불가"로 판정하고 진입까지 막았는데, 실측에서 전제가 거짓임이
# 드러나 철회했다. 청산 로그 20,532건 중 91%가 시그널 붕괴였고 대상 전략일수록
# 오히려 그 비중이 높았다(asqs 2,346건 중 2,276건, 손절 0건).
#
# 지표가 틀린 것을 재고 있었다. "필드를 읽는다"와 "그 필드가 없으면 청산이 깨진다"는
# 다른 명제다. 읽기는 분기 위에서도 일어나고(asqs의 is_float_rotation은 진입 분기에서만
# 쓰인다), 결손 필드가 게이트가 아니라 가점·감점이면 아무것도 깨지지 않는다.
#
# 그래서 읽기 대신 **결과**를 잰다. 청산 점수가 시장 상태에 반응하는가, 즉 나쁜
# 조건에서 cutoff 아래로 떨어져 붕괴 판정이 나는가만 본다. 이것이 "시그널로 빠져나올
# 수 있는가"의 직접적인 측정이며, 위 오판을 재현했다면 즉시 걸렸을 검사다.


def _exit_unresponsive():
    """청산 점수가 어떤 시장 조건에서도 cutoff 아래로 내려가지 않는 전략을 찾는다.

    그런 전략은 시그널로는 절대 빠져나오지 못하고 손절·트레일링에만 의존한다.
    반대로 하나라도 붕괴 조건이 있으면 시그널 청산 능력은 있는 것이다.
    """
    signals = _reachability_signals()
    stuck = []
    for strategy_type in _catalog_strategy_types():
        try:
            strategy = get_strategy(strategy_type)
        except Exception:
            continue
        if strategy is None or getattr(strategy, "is_autonomous", False):
            continue
        can_collapse = False
        for signal in signals:
            for regime in REGIMES:
                payload = dict(signal)
                payload["regime_mode"] = regime
                try:
                    score = strategy.calculate_score(payload, regime, is_entry=False)
                except TypeError:
                    score = strategy.calculate_score(
                        payload, regime, is_entry=False, score_card=None
                    )
                if float(score) < strategy.get_cutoff_score(regime):
                    can_collapse = True
                    break
            if can_collapse:
                break
        if not can_collapse:
            stuck.append(strategy_type)
    return sorted(stuck)


def test_no_enterable_strategy_is_stuck_without_a_signal_exit():
    """진입할 수 있는 전략은 반드시 시그널로 빠져나올 수도 있어야 한다.

    위험한 것은 "청산 불가" 자체가 아니라 **진입 가능 + 청산 불가**의 조합이다.
    진입하지 못하는 전략은 포지션이 생기지 않으므로 묶일 것도 없다. 실제로 현재
    청산 반응이 없는 5종(cross_asset, obi_ofa, pairs_trading, pca_knn,
    pdufa_calendar)은 전부 지표 결손으로 진입 자체가 막혀 있어 무해하다.

    이 검사는 2026-08-31 오판을 그대로 재현했다면 즉시 통과했을 것이고(차단한 13종은
    모두 청산 반응이 정상이었다), 따라서 그 차단이 불필요함을 알려줬을 검사다.
    조합이 아니라 한쪽만 보면 같은 실수를 반복한다.
    """
    states = json.loads(ENTRY_STATE_SNAPSHOT.read_text(encoding="utf-8"))["states"]
    stuck = set(_exit_unresponsive())
    risky = sorted(name for name in stuck if states.get(name) == STATE_ENTERABLE)
    assert not risky, (
        "진입은 되는데 시그널로는 빠져나올 수 없는 전략이 있다. 포지션이 손절·트레일링에만 "
        "의존하게 되므로 청산 조건을 배선하거나 진입을 막을 것: " + repr(risky)
    )


def test_exit_unresponsive_list_matches_the_snapshot():
    """시그널 청산이 불가능한 전략 목록이 스냅샷과 일치해야 한다.

    목록이 늘면 그 전략이 진입 가능해지는 순간 위 불변식이 깨진다. 줄면 청산 조건이
    배선된 것이므로 스냅샷에서 지운다. 어느 쪽이든 사람이 사유를 판단해야 한다.
    """
    expected = json.loads(
        ENTRY_STATE_SNAPSHOT.read_text(encoding="utf-8")
    ).get("exit_unresponsive", [])
    assert _exit_unresponsive() == sorted(expected), (
        "시그널 청산 불가 목록이 스냅샷과 다르다. "
        "python scripts/update_strategy_entry_states.py 로 갱신하고 사유를 현황판에 남길 것."
    )
