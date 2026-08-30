"""라이브 신호 필드 계약 (SSOT).

전략 클래스(`app/strategies/*`)는 **백테스트 엔진**(`app/backtests/backtest_engine.py`)이
생산하는 지표 이름으로 작성돼 있다. 라이브 스캐너가 같은 값을 다른 이름으로 실으면
`BaseStrategy._safe_get`이 예외 없이 기본값 0을 돌려주고, 전략은 에러 한 줄 없이
"진입 조건 미충족"으로 퇴화한다.

2026-08-23 실측(라이브 30키 신호로 전략 95종에 무작위 4,000회 진입 채점):
진입 도달 가능 21종 / **영구 미진입 74종**. 대표 사례가 챔피언십 대형주 3년 부문
우승 전략인 `cross_sectional_momentum`으로, `change_pct`·`relative_strength`·
`is_triple_ema_up`·`dist_to_high`가 라이브 신호에 실리지 않아 단 한 번도 진입하지
못했다. 네 값 모두 스캐너가 이미 보유하거나 즉시 계산 가능한 값이었다.

따라서 라이브 신호 딕셔너리는 **백테스트와 동일한 이름**을 써야 한다. 이 모듈이
그 이름과 계산식을 단독으로 소유하며, 스캐너의 두 신호 생산 지점(전체 스캔 /
단일 종목 전용 분석)이 공통으로 사용한다.
"""

import numpy as np
import pandas as pd

from app.core.logging import logger
from app.scanner.indicator_metrics import build_indicator_metrics
from app.scanner.indicators import calculate_ema

# 백테스트 엔진과 이름·의미를 맞춘 표준 필드 목록.
# 스캐너 신호에 이 이름들이 빠지면 전략이 조용히 미진입으로 퇴화한다.
CANONICAL_FIELDS = (
    "Open",
    "gap_pct",
    "Wick",
    "change_pct",
    "relative_strength",
    "dist_to_high",
    "is_penny",
    "is_triple_ema_up",
    # 아래는 일봉 지표 스냅샷(build_indicator_metrics)에서 그대로 실어오는 값이다.
    # 백테스트와 같은 함수가 계산하므로 이름·의미·관측 구간이 정의상 일치한다.
    "BB_lower", "BB_upper", "EMA10", "EMA200", "EMA3", "EMA5", "HA_Close", "HA_Low", "HA_Open",
    "High", "Low", "RSI", "RSI2", "cci", "cci_prev", "chaikin_volatility", "close",
    "connors_rsi", "coppock", "coppock_up", "darvas_high", "darvas_low", "donchian_high_20",
    "donchian_low_10", "elder_ray_bear", "elder_ray_bear_up", "fisher", "fisher_signal",
    "hma_up", "hurst_exponent", "is_bollinger_trend_up", "is_death_rebound",
    "is_double_bottom_break", "is_first_red_day", "is_gap_fade", "is_keltner_trend_up",
    "is_macd_divergence_buy", "is_overnight_setup", "is_panic_drop", "is_parabolic_climax",
    "is_pivot_rebound_buy", "is_pre_gapper_setup", "is_pump_run_pullback",
    "is_range_contraction_break", "is_relative_strong", "is_squeeze_breakout",
    "is_squeeze_setup", "is_stoch_extreme_buy", "is_supernova_setup", "is_tom", "is_uptrend",
    "is_vcp_breakout", "is_vol_10x_spike", "is_wyckoff_spring", "keltner_reentry",
    "keltner_upper", "kijun_sen", "pivot_r1", "pivot_r2", "pivot_s1", "pivot_s2",
    "poc_distance_pct", "premarket_high", "premarket_max_volume", "sar_direction",
    "senkou_span_a", "senkou_span_b", "sma20", "sma50", "sortino_rank", "sortino_ratio_60d",
    "supertrend_direction", "td_buy_setup_count", "td_sell_setup_count", "trendline_support",
    "vol_sma20", "volume", "volume_ma20", "volume_poc", "williams_r", "zscore",
)

# 라이브 진입/청산 신호(details)가 실제로 싣는 전체 키.
# scanner.py의 두 details 딕셔너리와 일치해야 하며, 어긋나면 상시 가드가 반려한다
# (scripts/check_signal_field_contract.py).
LIVE_SIGNAL_KEYS = frozenset({
    # 스캐너 고유 표기(레거시) — 프론트/매니저가 읽으므로 유지한다.
    "gap", "rvol", "wick", "rs", "risk", "has_news", "ema_aligned", "atr",
    "dollar_volume", "recent_lows_15m", "regime_mode",
    # 백테스트와 이름이 같은 공통 지표
    "Close", "Volume", "VWAP", "RVOL", "EMA9", "EMA20", "EMA120", "OBV_divergence",
    "is_near_52w_high", "is_near_recent_high", "momentum_candles", "premarket_gap_pct",
    "is_orb_breakout", "is_rsi_bb_extreme", "is_obv_accumulation", "is_vcp", "is_cup",
    "is_double_bb_buy", "is_double_bb_sell",
    # 단일 종목 전용 분석 경로에만 실리는 키
    "is_fundamental_healthy", "is_smart_exit",
    # 아래 CANONICAL_FIELDS
    "Open", "gap_pct", "Wick", "change_pct", "relative_strength", "dist_to_high",
    "is_penny", "is_triple_ema_up",
    # 일봉 지표 스냅샷으로 실어오는 값
    "BB_lower", "BB_upper", "EMA10", "EMA200", "EMA3", "EMA5", "HA_Close", "HA_Low", "HA_Open",
    "High", "Low", "RSI", "RSI2", "cci", "cci_prev", "chaikin_volatility", "close",
    "connors_rsi", "coppock", "coppock_up", "darvas_high", "darvas_low", "donchian_high_20",
    "donchian_low_10", "elder_ray_bear", "elder_ray_bear_up", "fisher", "fisher_signal",
    "hma_up", "hurst_exponent", "is_bollinger_trend_up", "is_death_rebound",
    "is_double_bottom_break", "is_first_red_day", "is_gap_fade", "is_keltner_trend_up",
    "is_macd_divergence_buy", "is_overnight_setup", "is_panic_drop", "is_parabolic_climax",
    "is_pivot_rebound_buy", "is_pre_gapper_setup", "is_pump_run_pullback",
    "is_range_contraction_break", "is_relative_strong", "is_squeeze_breakout",
    "is_squeeze_setup", "is_stoch_extreme_buy", "is_supernova_setup", "is_tom", "is_uptrend",
    "is_vcp_breakout", "is_vol_10x_spike", "is_wyckoff_spring", "keltner_reentry",
    "keltner_upper", "kijun_sen", "pivot_r1", "pivot_r2", "pivot_s1", "pivot_s2",
    "poc_distance_pct", "premarket_high", "premarket_max_volume", "sar_direction",
    "senkou_span_a", "senkou_span_b", "sma20", "sma50", "sortino_rank", "sortino_ratio_60d",
    "supertrend_direction", "td_buy_setup_count", "td_sell_setup_count", "trendline_support",
    "vol_sma20", "volume", "volume_ma20", "volume_poc", "williams_r", "zscore",
})

# 라이브 신호에는 실리지만 백테스트 지표(app/scanner/indicator_metrics.py)가 만들지
# 못하는 필드. 장중 프레임이 있어야 산출되므로 일봉 기반 백테스트에서는 채울 수 없다.
#
# 이 방향의 결손은 앞의 것들과 반대로 터진다. 라이브에서는 조건이 살아 있고 백테스트에서만
# 죽으므로, 같은 전략이 두 경로에서 서로 다르게 동작한다. 2026-08-23에 strategy_c가 이 상태로
# 실거래 587건을 집행했다(is_cup/is_vcp/premarket_gap_pct는 이후 백테스트에도 배선했고,
# is_orb_breakout만 남았다). 목록에 남는 동안은 해당 전략의 백테스트 성적을 라이브 성적의
# 예측치로 쓸 수 없다.
LIVE_ONLY_FIELDS = frozenset({
    "is_orb_breakout",   # 장초반 30분 레인지 돌파. 5분봉이 있어야 산출된다
})

# 신규 진입을 막는 전략 (SSOT). 청산 경로가 결손이라 시그널로 못 빠져나오는 전략이다.
#
# 진입만 되고 청산이 죽은 조합이 가장 위험하다. 청산 조건이 결손 필드를 읽으면
# `_safe_get`이 0.0을 돌려주고 `close >= 기준선(0.0)`이 항상 참이 되어 **홀딩 판정이
# 영구히 유지**된다. 포지션은 잡히는데 시그널로는 절대 못 나오고 손절·트레일링으로만
# 정리된다.
#
# `is_selectable=0`(카탈로그 차단)만으로는 부족하다. 그 플래그는 카탈로그 조회
# (app/strategy_catalog/router.py)와 전략 변경 검증(app/admin/router.py)에서만 쓰이고
# 스케줄러는 보지 않는다. 이미 그 전략으로 설정된 계정은 계속 매수한다. 그래서 진입
# 채점 경로(app/bot/scheduler.py)에서도 함께 막는다.
#
# 청산 경로는 건드리지 않는다 - 기존 보유분은 그대로 두고 신규 진입만 막는 것이 의도다.
ENTRY_BLOCKED_STRATEGIES = {
    "청산 경로 필드 결손 - 시그널 청산 불가(2026-08-30)": (
        "asqs",              # is_float_rotation (유통주식수 데이터 없음)
        "macro_momentum",    # yield_curve_spread, inflation_expectation (매크로 미연동)
        "strategy_c",        # news_sentiment, news_sentiment_score (뉴스 감성 중첩 누락)
        # 아래 2종은 이미 is_selectable=0이지만 그 플래그는 스케줄러를 거치지 않는다.
        # 실측 결과 각각 계정 1개가 붙어 보유분(3건/2건)을 들고 계속 매수 중이었다.
        "strategy_b",        # news_sentiment, news_sentiment_score
        "exploded_c",        # news_sentiment, news_sentiment_score
    ),
}

ENTRY_BLOCKED_STRATEGY_SET = frozenset(
    strategy
    for strategies in ENTRY_BLOCKED_STRATEGIES.values()
    for strategy in strategies
)

# 폴백 치환 선언 (SSOT). 원본 필드가 비었을 때 다른 필드로 갈아타는 경로다.
#
# 이 목록이 따로 있어야 하는 이유: 위의 결손 검사들은 "필드에 값이 있는가"를 본다.
# 폴백은 값을 실제로 채우므로 그 검사를 전부 통과한다. 전략은 정상 채점되지만
# **측정 대상이 바뀐다**. opening_range_breakout이 orb_high_30m 대신 BB_upper를 읽던
# 시절, 이름은 ORB인데 실제로는 볼린저 돌파를 재고 있었고 어떤 가드도 그것을 잡지
# 못했다(2026-08-23 판정 문서 §8 후속 과제).
#
# 형식은 "전략파일:원본필드->대체필드"이며 scripts/check_signal_field_contract.py가
# AST로 검출한 결과와 **정확히 일치**해야 한다. 새 치환을 추가하거나 제거하면 가드가
# 반려하므로, 무엇을 실제로 재고 있는지가 항상 diff에 남는다.
#
# 원본이 UNSUPPORTED/PENDING으로 선언된 치환은 가드가 "대체 측정 중"으로 경고한다.
# 그 전략의 백테스트 성적은 이름이 말하는 것의 성적이 아니다.
FALLBACK_SUBSTITUTIONS = {
    "VWAP 미산출 시 단기 EMA로 대체(둘 다 당일 평균가 근사, 의미 보존)": (
        "lava_volume:VWAP->EMA9",
        "opening_range_breakout:VWAP->EMA9",
    ),
    "EMA10 미산출 시 EMA9로 대체(1봉 차이, 추세 판정 의미 보존)": (
        "chaikin_atr:EMA10->EMA9",
        "gex_pinning:EMA10->EMA9",
    ),
    "OHLC 개별값 결손 시 종가로 대체(봉 자체가 없으면 앞단에서 이미 0점)": (
        "institutional_follow:Open->Close",
        "institutional_follow:High->Close",
        "institutional_follow:Low->Close",
    ),
    "거래량 이동평균 결손 시 당봉 거래량으로 대체(비율이 1.0이 되어 조건이 닫힌다)": (
        "institutional_follow:vol_sma20->Volume",
    ),
    "직전 CCI 결손 시 현재 CCI로 대체(차분이 0이 되어 진입 조건이 닫힌다)": (
        "woodies_cci:cci_prev->cci",
    ),
}

# 라이브에서 원리상 산출 불가능한 필드. 외부 데이터 없이는 채울 수 없으므로 해당
# 전략은 라이브에서 진입하지 못한다. 카탈로그에서 선택 불가로 막는 것이 정답이며,
# 데이터를 조달하기 전까지 이 목록에 남는다.
UNSUPPORTED_LIVE_FIELDS = {
    "매크로 시계열 미연동": ("yield_curve_spread", "inflation_expectation"),
    "수급·내부자 공시 데이터 없음": (
        "insider_signal", "institutional_net_buy_days", "foreigner_net_buy",
        "organ_net_buy", "smart_money_score",
    ),
    "옵션 체인 데이터 없음": (
        "gamma_flip", "net_gex_proxy", "max_pain_price", "strike_distance",
        "is_expiry_week",
    ),
    "호가·체결 틱 데이터 없음": (
        "order_book_imbalance", "order_flow_delta", "OFI_acceleration",
        "dark_pool_price",
    ),
    "실적·공시 데이터 없음": (
        "is_earnings_gap_drift", "is_offering_rebound", "is_warrant_support",
        "days_to_pdufa",
    ),
    "SNS 버즈 데이터 없음": ("mention_zscore", "social_buzz_surge", "sentiment_positive"),
    "타 자산·변동성 지수 미연동": (
        "cross_asset_ok", "is_vix_ok", "vix_term_structure", "vix_vxv_ratio",
    ),
    "타 종목 동시 시계열(페어) 미지원": ("spread_zscore", "kalman_zscore"),
    "사전 학습 모델 미탑재": ("knn_up_probability",),
    "유통주식수 데이터 없음": ("is_float_rotation", "is_sympathy_setup"),
}

# 스캐너가 이미 받는 OHLCV로 계산 가능하지만 아직 신호에 싣지 않은 필드(2차 백로그).
# 이 목록이 비면 라이브에서 살릴 수 있는 전략을 전부 살린 것이다.
# 2026-08-23: 일봉 지표 스냅샷 배선으로 81개가 LIVE로 이동했다. 남은 것은 장중
# 프레임이나 뉴스가 있어야 하는 값이라 일봉 스냅샷으로는 채울 수 없다.
PENDING_LIVE_FIELDS = {
    "피벗·레인지": ("orb_high_30m", "orb_low_30m",),
    "뉴스 감성(중첩 누락)": ("news_sentiment", "news_sentiment_score",),
}


def _flatten(groups: dict) -> frozenset:
    """그룹별 필드 딕셔너리를 평탄한 집합으로 만든다."""
    return frozenset(field for fields in groups.values() for field in fields)


UNSUPPORTED_FIELD_SET = _flatten(UNSUPPORTED_LIVE_FIELDS)
PENDING_FIELD_SET = _flatten(PENDING_LIVE_FIELDS)

# 저가주 판정 기준가($). backtest_engine.py의 `metrics['is_penny']`와 동일 기준.
PENNY_PRICE_THRESHOLD = 10.0

# 절대 모멘텀 산출 구간(봉). backtest_engine.py의 `change_pct`가 20봉 수익률이므로
# 라이브도 20봉으로 맞춘다. 단 라이브는 일봉 프레임에서 계산한다(아래 주석 참고).
MOMENTUM_LOOKBACK_BARS = 20


def _last_float(series, default: float = 0.0) -> float:
    """시리즈 마지막 값을 float로 안전 추출한다."""
    if series is None or len(series) == 0:
        return default
    value = series.iloc[-1]
    if pd.isna(value):
        return default
    return float(value)


def _session_open(df_5m) -> float:
    """당일 장 시작가를 구한다.

    주의: 스캐너의 5분봉은 `period="5d"`로 5거래일치를 담고 있다. 단순히 `iloc[0]`을
    쓰면 5일 전 시가가 잡혀 `gap_pct`·`Open` 기반 전략이 엉뚱한 값으로 채점된다.
    반드시 마지막 거래일의 첫 봉을 골라야 한다.
    """
    if df_5m is None or df_5m.empty or "Open" not in df_5m:
        return 0.0
    index = df_5m.index
    try:
        session_dates = index.date
        today_bars = df_5m[session_dates == session_dates[-1]]
        if not today_bars.empty:
            return float(today_bars["Open"].iloc[0])
    except AttributeError:
        # DatetimeIndex가 아닌 경우(테스트용 정수 인덱스 등)는 마지막 봉으로 대체한다.
        pass
    return float(df_5m["Open"].iloc[-1])


def _daily_triple_ema_up(df_daily) -> float:
    """일봉 기준 EMA 9>20>120 완전 정배열 여부.

    주의: 라이브 `cand`의 EMA9/EMA20은 15분봉, EMA120은 일봉에서 산출된다. 세 값을
    그대로 비교하면 시간축이 뒤섞여, 상승 추세에서 일봉 EMA120이 늘 아래에 깔리는
    탓에 조건이 사실상 항상 참이 된다(백테스트는 세 EMA가 모두 같은 인터벌이다).
    정배열 판정만은 일봉으로 통일해 백테스트와 의미를 맞춘다.
    """
    if df_daily is None or "Close" not in df_daily or len(df_daily) < 120:
        return 0.0
    close = df_daily["Close"]
    ema9 = _last_float(calculate_ema(close, 9))
    ema20 = _last_float(calculate_ema(close, 20))
    ema120 = _last_float(calculate_ema(close, 120))
    return 1.0 if ema9 > ema20 > ema120 > 0.0 else 0.0


def canonical_dist_to_high(last_close: float, df_daily) -> float:
    """52주 고가 대비 이격(%). 백테스트 `metrics['dist_to_high']`과 시간축을 맞춘다.

    주의: 스캐너 1단계는 이 값을 15분봉 5거래일 고점(`df['High'].iloc[:-1].max()`)으로
    계산하는데, 백테스트는 누적 최고가(`High.cummax().shift(1)`) 기준이다. 5일 고점은
    52주 고가보다 훨씬 낮으므로 라이브에서만 "고점 근접" 조건이 쉽게 참이 되어
    (strategy_a/strategy_c는 -1.5% 기준 +20점, cross_sectional_momentum은 -5% 기준
    +10점) 백테스트보다 헐겁게 진입한다. 일봉 전 구간 최고가로 통일한다.

    같은 스캐너의 `is_near_52w_high`는 이미 일봉 최고가로 계산하고 있어, 통일 전에는
    한 신호 안에서 '고점'의 정의가 둘로 갈려 있었다.
    """
    if df_daily is None or "High" not in df_daily or len(df_daily) < 2:
        # 일봉이 없으면 헐거운 15분봉 값으로 되돌아가지 않고 보수적으로 막는다.
        return -100.0
    # 백테스트의 shift(1)에 맞춰 당일 봉은 제외한 과거 최고가를 쓴다.
    high = df_daily["High"].iloc[:-1].max()
    if pd.isna(high) or float(high) <= 0.0:
        return -100.0
    return (float(last_close) / float(high) - 1) * 100


def canonical_relative_strength(last_close: float, df_daily, qqq_daily) -> float:
    """지수 대비 초과수익(비율). 백테스트 `metrics['relative_strength']`와 시간축을 맞춘다.

    주의: 기존 라이브 계산은 종목 15분봉 5거래일 수익률에서 지수 15분봉 10거래일
    수익률을 뺐다(scanner.py의 stock_perf vs qqq_perf). 두 항의 구간이 달라 그 자체로
    틀린 뺄셈이며, 상승장에서 지수 10일 수익률이 5일보다 크므로 초과강도가 체계적으로
    과소평가된다. 종목과 지수 모두 같은 일봉 구간의 누적 수익률로 계산한다.
    """
    if df_daily is None or "Close" not in df_daily or len(df_daily) < 2:
        return 0.0
    if qqq_daily is None or "Close" not in qqq_daily or len(qqq_daily) < 2:
        return 0.0
    stock_base = df_daily["Close"].iloc[0]
    index_base = qqq_daily["Close"].iloc[0]
    index_last = qqq_daily["Close"].iloc[-1]
    if pd.isna(stock_base) or float(stock_base) <= 0.0:
        return 0.0
    if pd.isna(index_base) or float(index_base) <= 0.0 or pd.isna(index_last):
        return 0.0
    stock_return = float(last_close) / float(stock_base) - 1
    index_return = float(index_last) / float(index_base) - 1
    return stock_return - index_return


# 일봉 스냅샷으로 실어오는 지표. CANONICAL_FIELDS의 뒷부분과 같은 목록이며,
# build_indicator_metrics가 만든 마지막 완결 행에서 그대로 읽는다.
_DAILY_SNAPSHOT_FIELDS = tuple(CANONICAL_FIELDS[8:])

# 지표 대부분이 20~60봉 롤링을 쓰므로 그보다 짧은 일봉으로는 의미 있는 값이 안 나온다.
MIN_DAILY_BARS_FOR_SNAPSHOT = 60


def daily_indicator_snapshot(df_daily) -> dict:
    """일봉에서 전략 지표를 계산해 마지막 봉의 값만 뽑아 돌려준다.

    백테스트와 동일한 build_indicator_metrics를 호출하므로 두 경로의 지표가 정의상
    같은 값이 된다. 이 배선이 없으면 전략은 같은 이름을 읽고도 라이브에서만 0.0을
    받아 조용히 미진입하거나, `close > 0.0` 형태로 무조건 진입한다.

    일봉이 없거나 너무 짧으면 **빈 딕셔너리**를 돌려준다. 0.0으로 채우면 '값이 없음'과
    '값이 0'을 구분할 수 없게 되어 같은 퇴화가 재발하기 때문이다.
    """
    if df_daily is None or len(df_daily) < MIN_DAILY_BARS_FOR_SNAPSHOT:
        return {}
    required = {"Open", "High", "Low", "Close", "Volume"}
    if not required.issubset(set(df_daily.columns)):
        return {}

    try:
        # 패턴 플래그(is_vcp/is_cup)는 스캐너가 같은 감지기로 이미 계산해 신호에 싣는다.
        # 여기서 봉마다 다시 돌리면 스캔 한 사이클이 종목당 수 초씩 느려진다.
        metrics = build_indicator_metrics(df_daily, interval="1d", include_pattern_flags=False)
    except Exception:
        # 지표 계산 실패가 스캔 전체를 멈추게 해서는 안 된다. 값을 싣지 않으면
        # 전략은 진입하지 않을 뿐이고, 이는 잘못된 값으로 매매하는 것보다 안전하다.
        logger.exception("[SignalContract] 일봉 지표 스냅샷 계산 실패")
        return {}

    last = metrics.iloc[-1]
    snapshot = {}
    for field in _DAILY_SNAPSHOT_FIELDS:
        if field not in metrics.columns:
            continue
        value = last[field]
        if pd.isna(value):
            continue
        snapshot[field] = float(value) if isinstance(value, (bool, np.bool_)) else value
    return snapshot


def build_canonical_metrics(cand: dict, last_close: float, wick_ratio: float,
                            df_5m=None, df_daily=None) -> dict:
    """백테스트 표준 이름으로 라이브 지표를 구성해 돌려준다.

    이미 `cand`에 있는 값은 그대로 통과시키고(스캐너가 계산해 두고 신호에 싣지 않던
    값들), 없는 값만 여기서 계산한다. 반환 딕셔너리를 details에 병합하면 된다.

    Args:
        cand: 스캐너 후보 딕셔너리. `gap_pct`·`relative_strength`·`dist_to_high`·
            `EMA9`/`EMA20`/`EMA120`를 이미 담고 있다.
        last_close: 현재가.
        wick_ratio: 윗꼬리 비율(`detect_fakeout_risk` 산출값).
        df_5m: 5분봉(5거래일치). 당일 시가(`Open`) 산출에 사용.
        df_daily: 일봉. 20일 절대 모멘텀(`change_pct`)과 EMA 정배열
            (`is_triple_ema_up`) 산출에 사용. 둘 다 백테스트와 시간축을 맞추기 위해
            15분봉이 아닌 일봉으로 계산한다.
    """
    # 당일 시가 — 백테스트의 metrics['Open']에 대응.
    open_price = _session_open(df_5m)

    # 20봉 절대 모멘텀 — 백테스트는 전략 인터벌 20봉이지만, 라이브 스캐너의 주 프레임
    # (15분봉)에서 20봉을 쓰면 약 5시간짜리 초단기 신호가 되어 '모멘텀'의 의미가 뒤집힌다
    # (cross_sectional_momentum 클래스 주석의 1h vs 1d 실측 경고와 같은 함정).
    # 따라서 라이브에서는 일봉 20일 수익률로 계산한다.
    change_pct = 0.0
    if df_daily is not None and len(df_daily) > MOMENTUM_LOOKBACK_BARS and "Close" in df_daily:
        past_close = df_daily["Close"].iloc[-(MOMENTUM_LOOKBACK_BARS + 1)]
        if pd.notna(past_close) and float(past_close) != 0.0:
            change_pct = (last_close / float(past_close) - 1) * 100

    # 일봉 지표 스냅샷을 먼저 깔고, 아래 값들로 덮어쓴다. 겹치는 이름(Open, gap_pct,
    # relative_strength, dist_to_high 등)은 라이브 관측 구간에 맞춰 따로 계산한 쪽이
    # 정확하므로 그쪽이 이긴다.
    snapshot = daily_indicator_snapshot(df_daily)

    return {
        **snapshot,
        "Open": open_price,
        # 스캐너 후보는 이미 백테스트와 같은 이름으로 들고 있었다. details로 옮기기만 하면 된다.
        "gap_pct": cand.get("gap_pct", 0.0),
        "Wick": round(float(wick_ratio), 2),
        "change_pct": round(change_pct, 2),
        "relative_strength": cand.get("relative_strength", 0.0),
        "dist_to_high": cand.get("dist_to_high", -100.0),
        # 백테스트 기준과 동일하게 1.0/0.0 실수로 싣는다(전략이 `>= 1.0`/`== 1.0`로 비교).
        "is_penny": 1.0 if 0.0 < float(last_close) <= PENNY_PRICE_THRESHOLD else 0.0,
        "is_triple_ema_up": _daily_triple_ema_up(df_daily),
    }
