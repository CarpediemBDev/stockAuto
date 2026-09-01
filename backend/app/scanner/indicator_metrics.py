"""전략 채점 입력 지표의 단일 계산 지점(SSOT).

전략 클래스는 여기서 만든 이름으로만 지표를 읽는다. 백테스트 엔진과 라이브 스캐너가
각자 계산하면 같은 이름이 서로 다른 값을 뜻하거나(관측 구간 불일치), 한쪽에만 존재해
BaseStrategy._safe_get이 기본값 0을 돌려주고 전략이 조용히 퇴화한다. 2026-08-23 실측에서
카탈로그 100종 중 72종이 라이브 미진입, 3종이 무조건 매수로 퇴화한 원인이 이 이중 계산이었다.

이 모듈이 계산식을 단독 소유하고, 백테스트(app/backtests/backtest_engine.py)와
라이브 신호(app/scanner/signal_contract.py)가 모두 이 함수를 호출한다.
"""

import numpy as np
import pandas as pd

from app.bot.trade_calculations import (
    DEFAULT_ROLLING_BOX_MINUTES,
    bar_minutes_for_interval,
    resolve_rolling_box_bars,
)
from app.scanner.macro_data import macro_columns_for_index
from app.scanner.indicators import (
    calculate_atr,
    detect_cup_and_handle,
    detect_vcp_pattern,
    calculate_connors_rsi,
    calculate_double_bb_reversion_signals,
    calculate_ema,
    calculate_macd,
    calculate_obv_divergence,
    calculate_rsi,
    calculate_rsi_bb,
    calculate_vwap,
    calculate_wick_ratio,
)


def _rolling_pattern_flag(df, detector, min_bars, window_bars):
    """봉마다 패턴 감지기를 돌려 0.0/1.0 시리즈를 만든다.

    감지기는 프레임을 받아 '마지막 봉 기준' 성립 여부를 돌려주는 스칼라 함수다.
    라이브 스캐너가 쓰는 바로 그 함수를 백테스트에서도 그대로 호출해야 두 경로의
    패턴 판정이 같아진다. 재구현하면 이름만 같고 뜻이 다른 지표가 또 생긴다
    (2026-08-23: strategy_c가 라이브에서만 is_cup/is_vcp를 받아 서로 다른 전략이 됐다).
    """
    import pandas as pd

    values = [0.0] * len(df)
    for position in range(min_bars, len(df)):
        window = df.iloc[max(0, position - window_bars + 1):position + 1]
        try:
            values[position] = 1.0 if detector(window) else 0.0
        except Exception:
            values[position] = 0.0
    return pd.Series(values, index=df.index)


def build_qqq_regime_metrics(qqq_daily):
    """QQQ 일봉에서 레짐 판정 프레임을 만든다(SSOT).

    `cross_asset_ok`가 이 프레임의 `regime` 컬럼을 읽는다. 원래 이 계산은
    backtest_engine.py 안에만 있어서 라이브가 같은 판정을 재현할 수 없었고, 그 결과
    `cross_asset_ok`는 라이브에서 산출 불가로 분류돼 `cross_asset` 전략이 영구
    미진입 상태였다. 두 경로가 같은 함수를 쓰도록 여기로 옮긴다.

    판정 규칙은 옮기기 전과 동일하다.
      - 종가 > MA20 이고 MA20 > MA50 -> BULLISH
      - 종가 < MA20                  -> BEARISH
      - 그 외                        -> NEUTRAL

    이동평균은 단순평균이 아니라 EMA다(`calculate_ema`). 이름이 MA인 것은 기존
    컬럼명을 유지한 것이며, 정의를 바꾸면 백테스트 성적이 소급 변경된다.
    """
    if qqq_daily is None or qqq_daily.empty or "Close" not in qqq_daily:
        return None

    metrics = pd.DataFrame(index=qqq_daily.index)
    metrics["Close"] = qqq_daily["Close"]
    metrics["MA20"] = calculate_ema(qqq_daily["Close"], 20)
    metrics["MA50"] = calculate_ema(qqq_daily["Close"], 50)

    close = metrics["Close"]
    ma20 = metrics["MA20"]
    ma50 = metrics["MA50"]
    regime = np.where(
        ma20.isna() | ma50.isna(),
        "NEUTRAL",
        np.where(
            (close > ma20) & (ma20 > ma50),
            "BULLISH",
            np.where(close < ma20, "BEARISH", "NEUTRAL"),
        ),
    )
    metrics["regime"] = regime
    return metrics


def build_indicator_metrics(
    df: pd.DataFrame,
    qqq_data: pd.DataFrame = None,
    qqq_metrics: pd.DataFrame = None,
    macro_data: pd.DataFrame = None,
    interval: str = "1d",
    rolling_box_minutes: float = DEFAULT_ROLLING_BOX_MINUTES,
    include_pattern_flags: bool = True,
) -> pd.DataFrame:
    """OHLCV 프레임에서 전략이 읽는 모든 지표를 계산한다.

    Args:
        df: Open/High/Low/Close/Volume 컬럼을 가진 프레임.
        qqq_data: 기준 지수 프레임. 상대강도·크로스에셋·VIX 프록시 계산에 쓰인다.
            없으면 해당 지표는 중립값으로 떨어진다.
        qqq_metrics: 지수 레짐 컬럼('regime')을 가진 프레임.
        interval: df의 봉 간격. 롤링 박스 길이를 봉 수로 환산하는 데 쓴다.
        rolling_box_minutes: 전략이 선언한 롤링 박스 길이(분).
        include_pattern_flags: VCP·컵앤핸들 패턴 플래그를 계산할지 여부. 감지기를 봉마다
            호출해야 해서 비용이 크다. 라이브 스캐너는 이 두 값을 자체적으로 계산해
            신호에 이미 싣고 있으므로, 라이브 스냅샷 경로는 False로 건너뛴다.

    Returns:
        df.index를 그대로 쓰는 지표 프레임.
    """
    metrics = pd.DataFrame(index=df.index)
    metrics['Open'] = df['Open']
    metrics['High'] = df['High']
    metrics['Low'] = df['Low']
    metrics['Close'] = df['Close']
    metrics['Volume'] = df['Volume']

    # 지표 추가
    metrics['EMA9'] = calculate_ema(df['Close'], 9)
    metrics['EMA20'] = calculate_ema(df['Close'], 20)
    metrics['EMA120'] = calculate_ema(df['Close'], 120)
    metrics['RSI'] = calculate_rsi(df['Close'], 14)

    macd_line, sig_line, _ = calculate_macd(df['Close'])
    metrics['MACD_line'] = macd_line
    metrics['MACD_signal'] = sig_line
    metrics['ATR'] = calculate_atr(df, 14)

    # 롤링 박스 스탑용 최근 N봉 저점 (현재 봉 제외 — 박스는 직전 봉들로만 형성)
    # 박스 길이는 전략이 '분' 단위로 선언하고, 백테스트 인터벌의 봉 길이로 환산한다.
    # 라이브(15분봉)와 동일한 환산 함수를 써야 두 경로의 박스가 같은 실시간 길이를 갖는다.
    rolling_box_bars = resolve_rolling_box_bars(
        rolling_box_minutes,
        bar_minutes_for_interval(interval),
    )
    metrics['rolling_box_low'] = df['Low'].shift(1).rolling(rolling_box_bars).min()

    # VWAP 및 Wick 계산
    metrics['VWAP'] = calculate_vwap(df)
    metrics['Wick'] = calculate_wick_ratio(df)

    # RVOL (최근 20봉 평균 대비 현재 거래량)
    vol_ma = df['Volume'].rolling(window=20).mean()
    metrics['RVOL'] = df['Volume'] / vol_ma.shift(1)
    metrics['RVOL'] = metrics['RVOL'].fillna(1.0)

    # OBV 매집 판정
    metrics['OBV_divergence'] = calculate_obv_divergence(df)

    # RSI 볼린저밴드 하단 극점 판독 (RSI BB)
    rsi_vals, _, rsi_lower = calculate_rsi_bb(df)
    metrics['RSI_lower_bb'] = rsi_lower
    metrics['is_rsi_bb_extreme'] = rsi_vals < rsi_lower

    # 스마트 익절 감지용 시그널 (RSI 과매수 + MACD 데드크로스)
    macd_prev = metrics['MACD_line'].shift(1)
    sig_prev = metrics['MACD_signal'].shift(1)
    is_dead_cross = (metrics['MACD_line'] < metrics['MACD_signal']) & (macd_prev >= sig_prev)
    metrics['is_smart_exit'] = (metrics['RSI'] >= 70.0) & is_dead_cross

    # 52주 신고가 근접 비율
    high_52w = df['High'].cummax()
    metrics['dist_to_high'] = (df['Close'] / high_52w.shift(1) - 1) * 100
    metrics['is_near_52w_high'] = df['Close'] >= high_52w.shift(1) * 0.98

    # 3연속 거래량 실린 강세 양봉
    c_up = df['Close'] > df['Close'].shift(1)
    v_up = df['Volume'] > df['Volume'].shift(1)
    metrics['momentum_candles'] = (c_up & c_up.shift(1) & c_up.shift(2) & 
                                   v_up & v_up.shift(1) & v_up.shift(2))

    # 💡 [세계적인 유명 전략용 신규 지표 탑재]
    # 1. 래리 코너스(Larry Connors) RSI 2 및 EMA 5
    metrics['RSI2'] = calculate_rsi(df['Close'], 2)
    metrics['EMA5'] = calculate_ema(df['Close'], 5)
    metrics['connors_rsi'] = calculate_connors_rsi(df['Close'], 3, 2, 100)
    metrics['EMA3'] = calculate_ema(df['Close'], 3)


    # 2. 존 카터(John Carter) 볼린저 밴드 스퀴즈 (BB Squeeze)
    ma20 = df['Close'].rolling(window=20).mean()
    std20 = df['Close'].rolling(window=20).std()
    metrics['upper_bb'] = ma20 + 2 * std20
    metrics['lower_bb'] = ma20 - 2 * std20

    atr20 = calculate_atr(df, 20)
    metrics['upper_kc'] = ma20 + 1.5 * atr20
    metrics['lower_kc'] = ma20 - 1.5 * atr20

    is_squeeze = (metrics['upper_bb'] < metrics['upper_kc']) & (metrics['lower_bb'] > metrics['lower_kc'])
    metrics['was_squeeze'] = is_squeeze.rolling(window=5).max() > 0
    metrics['bb_breakout'] = df['Close'] > metrics['upper_bb']
    metrics['is_squeeze_breakout'] = metrics['was_squeeze'] & metrics['bb_breakout']

    # 💡 [전략 패턴] 지수 대비 강세 (Relative Strength) 사전 연산 및 저장
    if qqq_data is not None and not qqq_data.empty:
        qqq_close_aligned = qqq_data['Close'].reindex(df.index).ffill()
        first_valid = qqq_close_aligned.first_valid_index()
        if first_valid is None:
            qqq_returns = pd.Series(0.0, index=df.index)
        else:
            qqq_returns = qqq_close_aligned / qqq_close_aligned.loc[first_valid] - 1
        stock_returns = df['Close'] / df['Close'].iloc[0] - 1
        metrics['relative_strength'] = stock_returns - qqq_returns
        metrics['relative_strength'] = metrics['relative_strength'].fillna(0.0)
    else:
        metrics['relative_strength'] = 0.0

    # -------------------------------------------------------------
    # 🚀 17개 차세대 신규 전략용 지표 사전 연산 탑재 (Pure Pandas/NumPy)
    # -------------------------------------------------------------

    # [1] Episodic Pivot (갭상승 비율)
    prev_close = df['Close'].shift(1)
    metrics['gap_pct'] = ((df['Open'] / prev_close - 1) * 100).fillna(0.0)

    # [2] Volatility Contraction Pattern (VCP)
    high_low_ratio_20 = (df['High'].rolling(20).max() - df['Low'].rolling(20).min()) / df['Close']
    high_low_ratio_10 = (df['High'].rolling(10).max() - df['Low'].rolling(10).min()) / df['Close']
    high_low_ratio_5 = (df['High'].rolling(5).max() - df['Low'].rolling(5).min()) / df['Close']
    is_contracting = (high_low_ratio_20 > high_low_ratio_10) & (high_low_ratio_10 > high_low_ratio_5)
    is_tight = high_low_ratio_5 < 0.08
    is_vcp_breakout = is_contracting & is_tight & (df['Close'] > df['High'].shift(1).rolling(5).max())
    metrics['is_vcp_breakout'] = is_vcp_breakout.fillna(False)

    # [3] Pairs Trading (QQQ 대비 상대가치 Z-Score)
    if qqq_data is not None and not qqq_data.empty:
        qqq_close_aligned = qqq_data['Close'].reindex(df.index).ffill()
        spread = df['Close'] / qqq_close_aligned
        spread_mean = spread.rolling(20).mean()
        spread_std = spread.rolling(20).std()
        metrics['spread_zscore'] = ((spread - spread_mean) / spread_std).fillna(0.0)
    else:
        metrics['spread_zscore'] = 0.0

    # [4] Darvas Box (20일 다바스 박스 고가/저가선)
    metrics['darvas_high'] = df['High'].rolling(20).max().shift(1).fillna(df['High'])
    metrics['darvas_low'] = df['Low'].rolling(20).min().shift(1).fillna(df['Low'])

    # [5] Z-Score Mean Reversion (일반 주가 Z-Score)
    ma20_p = df['Close'].rolling(20).mean()
    std20_p = df['Close'].rolling(20).std()
    metrics['zscore'] = ((df['Close'] - ma20_p) / std20_p).fillna(0.0)

    # [6] Heikin-Ashi (하이킨아시 캔들 계산)
    ha_close = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
    ha_open = np.zeros(len(df))
    ha_open[0] = df['Open'].iloc[0]
    ha_close_vals = ha_close.values
    for i in range(1, len(df)):
        ha_open[i] = (ha_open[i-1] + ha_close_vals[i-1]) / 2
    metrics['HA_Close'] = ha_close
    metrics['HA_Open'] = ha_open
    metrics['HA_Low'] = np.minimum(df['Low'].values, np.minimum(ha_open, ha_close))

    # [7] Ichimoku (일목균형표 전환선, 기준선, 선행스팬 A/B)
    high_9 = df['High'].rolling(9).max()
    low_9 = df['Low'].rolling(9).min()
    metrics['tenkan_sen'] = (high_9 + low_9) / 2

    high_26 = df['High'].rolling(26).max()
    low_26 = df['Low'].rolling(26).min()
    metrics['kijun_sen'] = (high_26 + low_26) / 2

    metrics['senkou_span_a'] = ((metrics['tenkan_sen'] + metrics['kijun_sen']) / 2).shift(26)
    high_52 = df['High'].rolling(52).max()
    low_52 = df['Low'].rolling(52).min()
    metrics['senkou_span_b'] = ((high_52 + low_52) / 2).shift(26)

    # [8] Parabolic SAR (가속변수 기반 SAR 계산)
    high_vals = df['High'].values
    low_vals = df['Low'].values
    close_vals = df['Close'].values
    sar = np.zeros(len(df))
    sar_direction = np.ones(len(df))
    sar[0] = low_vals[0]
    ep = high_vals[0]
    af = 0.02
    for i in range(1, len(df)):
        if sar_direction[i-1] == 1:
            sar[i] = sar[i-1] + af * (ep - sar[i-1])
            sar[i] = min(sar[i], low_vals[i-1], low_vals[max(0, i-2)])
            if low_vals[i] < sar[i]:
                sar_direction[i] = -1
                sar[i] = ep
                ep = low_vals[i]
                af = 0.02
            else:
                sar_direction[i] = 1
                if high_vals[i] > ep:
                    ep = high_vals[i]
                    af = min(0.2, af + 0.02)
        else:
            sar[i] = sar[i-1] + af * (ep - sar[i-1])
            sar[i] = max(sar[i], high_vals[i-1], high_vals[max(0, i-2)])
            if high_vals[i] > sar[i]:
                sar_direction[i] = 1
                sar[i] = ep
                ep = high_vals[i]
                af = 0.02
            else:
                sar_direction[i] = -1
                if low_vals[i] < ep:
                    ep = low_vals[i]
                    af = min(0.2, af + 0.02)
    metrics['sar'] = sar
    metrics['sar_direction'] = sar_direction

    # [9] SuperTrend (ATR 기반 3배 변동성 밴드)
    hl2 = (df['High'] + df['Low']) / 2
    basic_ub = hl2 + 3 * metrics['ATR']
    basic_lb = hl2 - 3 * metrics['ATR']
    final_ub = basic_ub.copy()
    final_lb = basic_lb.copy()
    for i in range(1, len(df)):
        if basic_ub.iloc[i] < final_ub.iloc[i-1] or close_vals[i-1] > final_ub.iloc[i-1]:
            final_ub.iloc[i] = basic_ub.iloc[i]
        else:
            final_ub.iloc[i] = final_ub.iloc[i-1]
        if basic_lb.iloc[i] > final_lb.iloc[i-1] or close_vals[i-1] < final_lb.iloc[i-1]:
            final_lb.iloc[i] = basic_lb.iloc[i]
        else:
            final_lb.iloc[i] = final_lb.iloc[i-1]
    supertrend = pd.Series(0.0, index=df.index)
    st_direction = np.ones(len(df))
    for i in range(1, len(df)):
        if st_direction[i-1] == 1:
            if close_vals[i] < final_lb.iloc[i]:
                st_direction[i] = -1
                supertrend.iloc[i] = final_ub.iloc[i]
            else:
                st_direction[i] = 1
                supertrend.iloc[i] = final_lb.iloc[i]
        else:
            if close_vals[i] > final_ub.iloc[i]:
                st_direction[i] = 1
                supertrend.iloc[i] = final_lb.iloc[i]
            else:
                st_direction[i] = -1
                supertrend.iloc[i] = final_ub.iloc[i]
    metrics['supertrend'] = supertrend
    metrics['supertrend_direction'] = st_direction

    # [10] HMA (Hull Moving Average)
    def _wma(series, period):
        w = np.arange(1, period + 1)
        return series.rolling(period).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)
    wma_half = _wma(df['Close'], 10)
    wma_full = _wma(df['Close'], 20)
    hma_raw = 2 * wma_half - wma_full
    metrics['hma'] = _wma(hma_raw, 4).fillna(df['Close'])

    # [11] Coppock Curve
    roc_14 = (df['Close'] / df['Close'].shift(14) - 1) * 100
    roc_11 = (df['Close'] / df['Close'].shift(11) - 1) * 100
    metrics['coppock'] = _wma(roc_14 + roc_11, 10).fillna(0.0)

    # [12] Elder Ray Index
    metrics['elder_ray_bull'] = df['High'] - metrics['EMA20']
    metrics['elder_ray_bear'] = df['Low'] - metrics['EMA20']

    # [13] Woodies CCI
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    tp_ma = tp.rolling(14).mean()
    tp_md = tp.rolling(14).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    metrics['cci'] = ((tp - tp_ma) / (0.015 * tp_md)).fillna(0.0)

    # [14] Pivot Point (Floor Trader)
    prev_high_val = df['High'].shift(1)
    prev_low_val = df['Low'].shift(1)
    prev_close_val = df['Close'].shift(1)
    p_val = (prev_high_val + prev_low_val + prev_close_val) / 3
    metrics['pivot_p'] = p_val
    metrics['pivot_s1'] = 2 * p_val - prev_high_val
    metrics['pivot_r1'] = 2 * p_val - prev_low_val
    metrics['pivot_s2'] = p_val - (prev_high_val - prev_low_val)
    metrics['pivot_r2'] = p_val + (prev_high_val - prev_low_val)

    # [15] Fisher Transform
    high_10 = df['High'].rolling(10).max()
    low_10 = df['Low'].rolling(10).min()
    f_val = np.zeros(len(df))
    fisher = np.zeros(len(df))
    for i in range(1, len(df)):
        h_10 = high_10.iloc[i]
        l_10 = low_10.iloc[i]
        c = close_vals[i]
        if h_10 - l_10 > 0:
            v = 0.66 * ((c - l_10) / (h_10 - l_10) - 0.5) + 0.67 * f_val[i-1]
        else:
            v = 0.0
        f_val[i] = max(-0.99, min(0.99, v))
        fisher[i] = 0.5 * np.log((1 + f_val[i]) / (1 - f_val[i])) + 0.5 * fisher[i-1]
    metrics['fisher'] = fisher
    metrics['fisher_signal'] = pd.Series(fisher, index=df.index).shift(1).fillna(0.0)

    # [16] Keltner Channel Reversion
    metrics['keltner_upper'] = metrics['EMA20'] + 2 * metrics['ATR']
    metrics['keltner_lower'] = metrics['EMA20'] - 2 * metrics['ATR']

    # [17] 추가 방향성 헬퍼 지표 계산
    metrics['hma_up'] = (metrics['hma'] > metrics['hma'].shift(1)).astype(float)
    metrics['coppock_up'] = (metrics['coppock'] > metrics['coppock'].shift(1)).astype(float)
    metrics['elder_ray_bear_up'] = (metrics['elder_ray_bear'] > metrics['elder_ray_bear'].shift(1)).astype(float)

    keltner_lower_prev = metrics['keltner_lower'].shift(1)
    metrics['keltner_reentry'] = ((df['Close'] > metrics['keltner_lower']) & (prev_close <= keltner_lower_prev)).astype(float)

    # [18] Larry Williams %R 및 NR7 보완 계산
    high_14_max = df['High'].rolling(14).max()
    low_14_min = df['Low'].rolling(14).min()
    metrics['williams_r'] = (((high_14_max - df['Close']) / (high_14_max - low_14_min)) * -100).fillna(-50.0)

    candle_range = df['High'] - df['Low']
    metrics['nr7'] = (candle_range == candle_range.rolling(7).min()).astype(float)

    # -------------------------------------------------------------
    # 🚀 2차 신규 제미나이 추천 13개 차세대 전략용 지표 사전 연산 탑재
    # -------------------------------------------------------------

    # [2-1] PDUFA 임상 스윙 (임상 예정일 기대감 일수 시뮬레이션)
    metrics['days_to_pdufa'] = (df.index.dayofyear % 90).astype(float)

    # [2-2] 내부자 매수 추적 (60일 최저점권에서 대량 RVOL 1.5배 이상 동반 지지선 형성)
    metrics['insider_signal'] = ((df['Low'] == df['Low'].rolling(60).min()) & (metrics['RVOL'] >= 1.5)).astype(float)

    # [2-3] 공매도 숏 스퀴즈 가속 (RVOL 2.0배 이상 & 10일 고가 돌파)
    metrics['is_squeeze_setup'] = ((metrics['RVOL'] >= 2.0) & (df['Close'] > df['High'].shift(1).rolling(10).max())).astype(float)

    # [2-4] 다바스/다크풀 블록딜 가격 추적 (최근 60일 내 최대 거래량 터진 캔들의 종가선 유지)
    block_print = df['Close'].where(df['Volume'] == df['Volume'].rolling(60).max()).ffill()
    metrics['dark_pool_price'] = block_print.fillna(df['Close'])

    # [2-5] 감마 플립 (EMA20 상방 안착 여부)
    metrics['gamma_flip'] = np.where(df['Close'] > metrics['EMA20'], 1.0, -1.0)

    # [2-6] 맥스 페인 반전 (옵션 만기일 주간 판정 및 목표 POC)
    is_exp_wk = (df.index.day >= 15) & (df.index.day <= 21) & (df.index.dayofweek == 4)
    metrics['is_expiry_week'] = is_exp_wk.astype(float)
    metrics['max_pain_price'] = metrics['VWAP']

    # [2-7] 와이코프 스프링 트랩 (전저점 20일 최저가를 이탈했다가 당일 즉시 말아올리며 회복)
    prev_low_20 = df['Low'].shift(1).rolling(20).min()
    metrics['is_wyckoff_spring'] = ((df['Low'] < prev_low_20) & (df['Close'] > prev_low_20) & (metrics['RVOL'] >= 1.2)).astype(float)

    # [2-8] 시초가 갭 페이드 (갭하락 -3% 이하에서 양봉 회복 돌파)
    metrics['is_gap_fade'] = ((metrics['gap_pct'] <= -3.0) & (df['Close'] > df['Open'])).astype(float)

    # [2-9] 소셜 버즈 폭증 (RVOL 3.0배 이상 & 3일 연속 누적 상승 5% 이상)
    buzz_condition = (metrics['RVOL'] >= 3.0) & (((df['Close'] / df['Close'].shift(3) - 1) * 100) >= 5.0)
    metrics['social_buzz_surge'] = buzz_condition.astype(float)

    # [2-10] 자산간 DXY/TNX 금리 필터 (QQQ 장세 레짐이 BEARISH가 아닐 때 1.0)
    if qqq_metrics is not None and 'regime' in qqq_metrics.columns:
        aligned_regime = qqq_metrics['regime'].reindex(df.index).ffill()
        metrics['cross_asset_ok'] = np.where(aligned_regime != "BEARISH", 1.0, 0.0)
    else:
        metrics['cross_asset_ok'] = 1.0

    # [2-10b] 매크로 시계열 (FRED). 없으면 열 자체를 만들지 않는다 -
    # 기본값으로 채우면 `is_recession_alert`가 상수로 굳어 매크로 판단이 사문화된다.
    # 이름을 리터럴로 대입한다. 루프로 동적 대입하면 정적 가드
    # (scripts/check_signal_field_contract.py)가 생산자를 보지 못해
    # "백테스트가 만들지 않는 필드"로 반려한다.
    macro_columns = macro_columns_for_index(macro_data, df.index)
    if "yield_curve_spread" in macro_columns:
        metrics['yield_curve_spread'] = macro_columns["yield_curve_spread"]
    if "inflation_expectation" in macro_columns:
        metrics['inflation_expectation'] = macro_columns["inflation_expectation"]

    # [2-11] 볼륨 델타 체결 불균형 (양봉 volume 매수 우위 vs 음봉 volume 매도 우위 프록시)
    body_ratio = (df['Close'] - df['Low']) / (df['High'] - df['Low']).replace(0, 1)
    delta = df['Volume'] * (body_ratio - 0.5) * 2
    metrics['order_flow_delta'] = delta.rolling(5).sum().fillna(0.0)

    # [2-12] 매물대 프로파일 POC
    metrics['volume_poc'] = metrics['dark_pool_price']

    # [2-13] 월말 효과 계절성 매매 (월말 28일부터 다음 달 3일까지의 계절성 리밸런싱 기간)
    metrics['is_tom'] = ((df.index.day >= 28) | (df.index.day <= 3)).astype(float)

    # -------------------------------------------------------------
    # 🚀 3차 신규 동전주 & 폭등주 및 계량 특화 24개 전략 지표 탑재 (Pure Pandas/NumPy)
    # -------------------------------------------------------------

    # 동전주 판정 프록시 (가격 10달러 이하)
    metrics['is_penny'] = (df['Close'] <= 10.0).astype(float)

    # [3-1] 슈퍼노바 (RVOL 5배 이상 폭증 & 시가 대비 15% 이상 장대양봉)
    metrics['is_supernova_setup'] = ((metrics['RVOL'] >= 5.0) & ((df['Close'] / df['Open'] - 1) >= 0.15)).astype(float)

    # [3-2] 모닝 패닉 딥 바잉 (갭하락 포함 장초반 -10% 이상 수직 급락 & RSI 25 이하 과매도 극점)
    metrics['is_panic_drop'] = (((df['Open'] / df['Close'].shift(1) - 1) <= -0.10) & (metrics['RSI'] <= 25.0)).astype(float)

    # [3-3] 퍼스트 레드 데이 숏 (5일 누적 +30% 이상 폭등 후 고점 첫 음봉 마감)
    cum_ret_5 = df['Close'] / df['Close'].shift(5) - 1
    metrics['is_first_red_day'] = ((cum_ret_5 >= 0.30) & (df['Close'] < df['Open']) & (df['Close'] < df['Close'].shift(1))).astype(float)

    # [3-4] 펌프 앤 런 눌림목 (최근 20일 내 고가 40% 이상 폭등 후 거래량 급감하며 EMA20 지지선 근처)
    pump_20 = (df['High'].rolling(20).max() / df['Low'].rolling(20).min() - 1) >= 0.40
    pullback_ema20 = (df['Close'] >= metrics['EMA20'] * 0.97) & (df['Close'] <= metrics['EMA20'] * 1.03)
    metrics['is_pump_run_pullback'] = (pump_20 & pullback_ema20 & (metrics['RVOL'] < 0.80)).astype(float)

    # [3-5] 프리마켓 갭 돌파 (장전 갭상승 7% 이상 & RVOL 2배 이상 거래량 동반)
    metrics['is_pre_gapper_setup'] = ((metrics['gap_pct'] >= 7.0) & (metrics['RVOL'] >= 2.0)).astype(float)

    # [3-6] 유통주 회전율 돌파 (회전율 100% 돌파 프록시 - RVOL 8배 폭증)
    metrics['is_float_rotation'] = (metrics['RVOL'] >= 8.0).astype(float)

    # [3-7] 테마 2등주 짝짓기 (RVOL 2배 이상 거래량 급증 & RSI 65 이상 강세)
    metrics['is_sympathy_setup'] = ((metrics['RVOL'] >= 2.0) & (metrics['RSI'] >= 65.0)).astype(float)

    # [3-8] 워런트 괴리 매수 (60일 최저점 부근 지지 형성 및 최근 변동폭 극소화 안정)
    low_60 = df['Low'].rolling(60).min()
    metrics['is_warrant_support'] = ((df['Close'] <= low_60 * 1.05) & (df['Close'].rolling(3).std() / df['Close'] < 0.015)).astype(float)

    # [3-9] 실적 서프라이즈 갭 앤 드리프트 (갭상승 8% 이상 출발 후 양봉 지지 유지)
    metrics['is_earnings_gap_drift'] = ((metrics['gap_pct'] >= 8.0) & (df['Close'] >= df['Open'])).astype(float)

    # [3-10] 유증 악재 소멸 반등 (최근 5일간 -30% 이상 폭락 후 거래대금 실린 종가 양봉)
    drop_5 = (df['Close'] / df['Close'].shift(5) - 1) <= -0.30
    metrics['is_offering_rebound'] = (drop_5 & (metrics['RVOL'] >= 3.0) & (df['Close'] > df['Open'])).astype(float)

    # [3-11] 파라볼릭 폭발 청산 (5일 누적 +50% 폭등 각도 & RVOL 3배 이상 위꼬리 긴 음봉 클라이맥스)
    slope_5 = (df['Close'] / df['Close'].shift(5) - 1) >= 0.50
    upper_tail = df['High'] - np.maximum(df['Close'], df['Open'])
    body = np.abs(df['Close'] - df['Open'])
    metrics['is_parabolic_climax'] = (slope_5 & (metrics['RVOL'] >= 3.0) & (upper_tail > body)).astype(float)

    # [3-12] 이중바닥 W 돌파 (60일 최저 지지구간 다중 확인 후 20일 고가선 상방 탈출)
    is_w = (df['Low'] <= low_60 * 1.05).rolling(20).sum() >= 2
    metrics['is_double_bottom_break'] = (is_w & (df['Close'] > df['High'].shift(1).rolling(20).max())).astype(float)

    # [3-13] 오버나이트 갭 사냥 (거래량 3배 이상 & HOD 당일 최고가 99% 부근 마감 양봉)
    metrics['is_overnight_setup'] = ((metrics['RVOL'] >= 3.0) & (df['Close'] >= df['High'] * 0.99) & (df['Close'] > df['Open'])).astype(float)

    # [3-14] 역배열 극점 평균회귀 (EMA120선 대비 -40% 하방 이탈 후 EMA20선 위로 상향 복귀)
    metrics['is_death_rebound'] = ((df['Close'] <= metrics['EMA120'] * 0.60) & (df['Close'] > metrics['EMA20'])).astype(float)

    # [3-15] 지수 대비 상대강도 주도주 (최근 20일 수익률이 QQQ 인덱스 대비 5일 연속 아웃퍼폼)
    if qqq_data is not None and not qqq_data.empty:
        qqq_aligned = qqq_data['Close'].reindex(df.index).ffill()
        stock_ret_20 = df['Close'] / df['Close'].shift(20) - 1
        qqq_ret_20 = qqq_aligned / qqq_aligned.shift(20) - 1
        rs_20 = stock_ret_20 - qqq_ret_20
        metrics['is_relative_strong'] = (rs_20.rolling(5).min() > 0.0).astype(float)
    else:
        metrics['is_relative_strong'] = 0.0

    # 다수 지표 열 추가로 조각난 내부 블록을 정리해 후반 계산 비용을 낮춥니다.
    metrics = metrics.copy()

    # [3-16] 볼밴 상단 돌파 추세 (볼린저 밴드 상단 돌파 및 대세 밴드 폭 확장)
    bb_width = std20_p / ma20_p
    bb_width_expanding = bb_width > bb_width.shift(1)
    metrics['is_bollinger_trend_up'] = ((df['Close'] > metrics['upper_bb']) & bb_width_expanding).astype(float)

    # [3-17] MACD 다이버전스 (주가는 신저점을 경신하나 MACD 히스토그램 저점은 높아지는 바닥 신호)
    price_new_low = df['Close'] <= df['Close'].shift(1).rolling(20).min()
    macd_not_new_low = metrics['MACD_line'] > metrics['MACD_line'].shift(1).rolling(20).min()
    metrics['is_macd_divergence_buy'] = (price_new_low & macd_not_new_low).astype(float)

    # [3-18] 스토캐스틱 극점 반전 (14일 Stochastic Slow %K가 %D를 20 이하 과매도 극점에서 골든크로스)
    low_14 = df['Low'].rolling(14).min()
    high_14 = df['High'].rolling(14).max()
    fast_k = ((df['Close'] - low_14) / (high_14 - low_14) * 100).fillna(50.0)
    slow_k = fast_k.rolling(3).mean()
    slow_d = slow_k.rolling(3).mean()
    metrics['slow_k'] = slow_k
    metrics['slow_d'] = slow_d
    metrics['is_stoch_extreme_buy'] = ((slow_k <= 20.0) & (slow_k > slow_d) & (slow_k.shift(1) <= slow_d.shift(1))).astype(float)

    # [3-19] 켈트너 채널 추세추종 (켈트너 채널 상단 돌파 안착)
    metrics['is_keltner_trend_up'] = (df['Close'] > metrics['keltner_upper']).astype(float)

    # [3-20] 삼중 EMA 정배열 교차 (EMA 9 > 20 > 120 정배열 확산 개시)
    metrics['is_triple_ema_up'] = ((metrics['EMA9'] > metrics['EMA20']) & (metrics['EMA20'] > metrics['EMA120'])).astype(float)

    # [3-21] 변동성 캔들 수축 돌파 (3일 연속 캔들 고저 편차 진폭 수축 후 저항 돌파)
    range_pct = (df['High'] - df['Low']) / df['Close']
    range_contracting = (range_pct < range_pct.shift(1)) & (range_pct.shift(1) < range_pct.shift(2))
    metrics['is_range_contraction_break'] = (range_contracting & (df['Close'] > df['High'].shift(1))).astype(float)

    # [3-22] 10배 거래량 장대양봉 돌파 (RVOL 10.0배 초과 스파이크 발생)
    metrics['is_vol_10x_spike'] = ((metrics['RVOL'] >= 10.0) & (df['Close'] > df['Open'])).astype(float)

    # [3-23] 피봇 저항/지지 반등 (피봇 S2 지지 반등 또는 R2 상방 돌파)
    metrics['is_pivot_rebound_buy'] = ((df['Low'] <= metrics['pivot_s2'] * 1.01) & (df['Close'] > metrics['pivot_s2']) | (df['Close'] > metrics['pivot_r2'])).astype(float)

    # [3-24] VIX 변동성 연계 헷지 (QQQ 지수 변동성 표준편차 상승 억제)
    if qqq_data is not None and not qqq_data.empty:
        qqq_close_aligned = qqq_data['Close'].reindex(df.index).ffill()
        qqq_vol = qqq_close_aligned.rolling(20).std() / qqq_close_aligned.rolling(20).mean()
        metrics['is_vix_ok'] = (qqq_vol < qqq_vol.rolling(60).mean() * 1.2).astype(float)
    else:
        metrics['is_vix_ok'] = 1.0

    # [3-25] 프리마켓 고점 돌파 매매 프록시 지표
    metrics['premarket_high'] = df['High'].shift(1).rolling(10).max().fillna(df['High'])
    metrics['premarket_max_volume'] = df['Volume'].rolling(20).mean().fillna(df['Volume']) * 1.5

    # [3-26] 추세 안정화 눌림목 프록시 지표
    metrics['change_pct'] = ((df['Close'] / df['Close'].shift(20) - 1) * 100).fillna(0.0)
    metrics['trendline_support'] = metrics['EMA20']
    metrics['is_uptrend'] = (metrics['EMA9'] > metrics['EMA20'])

    # 💡 마켓트랩 더블 볼린저 밴드 역추세 전략 신호 사전 연산
    metrics = calculate_double_bb_reversion_signals(metrics)
    # ------------------------------------------------------------------
    # [4] 전략이 읽지만 위 블록이 만들지 않던 지표.
    # 이름 드리프트(전략은 BB_upper, 엔진은 upper_bb)와 미계산 지표를 함께 해소한다.
    # 이 값들이 없으면 _safe_get이 0.0을 돌려주고, `close > 0.0` 형태의 돌파 조건이
    # 항상 참으로 퇴화한다(2026-08-23: darvas_box/donchian_breakout/ORB 무차별 진입).
    # ------------------------------------------------------------------

    # 볼린저 밴드 별칭 — 전략은 BB_upper/BB_lower로 읽는다.
    metrics['BB_upper'] = metrics['upper_bb']
    metrics['BB_lower'] = metrics['lower_bb']

    # 이동평균 보강
    metrics['EMA10'] = calculate_ema(df['Close'], 10)
    metrics['EMA200'] = calculate_ema(df['Close'], 200)
    metrics['sma20'] = df['Close'].rolling(20).mean()
    metrics['sma50'] = df['Close'].rolling(50).mean()

    # 거래량 기준선 — 당일 거래량과 비교하는 용도이므로 직전 봉까지로 shift한다.
    volume_baseline = df['Volume'].rolling(20).mean().shift(1)
    metrics['volume_ma20'] = volume_baseline.fillna(df['Volume'])
    metrics['vol_sma20'] = metrics['volume_ma20']

    # 돈키언 채널 — 당일 봉을 제외한 직전 N봉 기준(룩어헤드 방지).
    metrics['donchian_high_20'] = df['High'].rolling(20).max().shift(1).fillna(df['High'])
    metrics['donchian_low_10'] = df['Low'].rolling(10).min().shift(1).fillna(df['Low'])

    # CCI 직전값 — woodies_cci가 교차 판정에 쓴다.
    metrics['cci_prev'] = metrics['cci'].shift(1).fillna(0.0)

    # 채이킨 변동성 — 고저 스프레드 EMA10의 10봉 변화율(%).
    hl_spread_ema = calculate_ema(df['High'] - df['Low'], 10)
    metrics['chaikin_volatility'] = (
        (hl_spread_ema / hl_spread_ema.shift(10) - 1) * 100
    ).replace([np.inf, -np.inf], 0.0).fillna(0.0)

    # 허스트 지수 근사 — 60봉 분산비. 0.5보다 크면 추세, 작으면 평균회귀 성향.
    log_returns = np.log(df['Close'] / df['Close'].shift(1))
    var_1 = log_returns.rolling(60).var()
    # 5봉 누적수익의 분산. rolling.apply(lambda)는 봉마다 파이썬 호출이 일어나 프레임
    # 하나에 수백 ms가 든다. 같은 값을 벡터 연산으로 구한다.
    var_5 = log_returns.rolling(5).sum().rolling(60).var()
    with np.errstate(divide='ignore', invalid='ignore'):
        hurst = 0.5 + 0.5 * np.log((var_5 / (5 * var_1)).replace([np.inf, -np.inf], np.nan)) / np.log(5)
    metrics['hurst_exponent'] = hurst.fillna(0.5).clip(0.0, 1.0)

    # 소르티노 — 하방 변동성 대비 수익. 랭크는 1년 구간 백분위.
    downside = log_returns.where(log_returns < 0, 0.0)
    downside_std = downside.rolling(60).std()
    sortino = (log_returns.rolling(60).mean() / downside_std).replace(
        [np.inf, -np.inf], 0.0
    ).fillna(0.0)
    metrics['sortino_ratio_60d'] = sortino
    metrics['sortino_rank'] = sortino.rolling(252).rank(pct=True).fillna(0.5)

    # TD 시퀀셜 셋업 카운트 — 종가가 4봉 전보다 낮으면(높으면) 연속 카운트.
    buy_setup = (df['Close'] < df['Close'].shift(4)).astype(int)
    sell_setup = (df['Close'] > df['Close'].shift(4)).astype(int)
    metrics['td_buy_setup_count'] = (
        buy_setup * (buy_setup.groupby((buy_setup != buy_setup.shift()).cumsum()).cumcount() + 1)
    ).astype(float)
    metrics['td_sell_setup_count'] = (
        sell_setup * (sell_setup.groupby((sell_setup != sell_setup.shift()).cumsum()).cumcount() + 1)
    ).astype(float)

    # 거래량 POC 이격률(%) — lava_volume이 읽는다.
    metrics['poc_distance_pct'] = (
        (df['Close'] / metrics['volume_poc'] - 1) * 100
    ).replace([np.inf, -np.inf], 0.0).fillna(0.0)

    # 소문자 별칭 — 일부 전략이 close/volume으로 읽는다.
    metrics['close'] = df['Close']
    metrics['volume'] = df['Volume']

    # ------------------------------------------------------------------
    # [5] 라이브 스캐너만 싣던 패턴 플래그. 백테스트가 만들지 않아 strategy_c가
    # 라이브와 백테스트에서 서로 다른 조건으로 돌던 것을 해소한다(역방향 결손).
    # ------------------------------------------------------------------
    if include_pattern_flags:
        metrics['is_vcp'] = _rolling_pattern_flag(df, detect_vcp_pattern, 60, 60)
        metrics['is_cup'] = _rolling_pattern_flag(df, detect_cup_and_handle, 80, 80)

    # 프리마켓 갭 — 일봉에는 장전 거래가 없으므로 시가 갭이 같은 개념이다.
    # 라이브는 장전 세션 갭을, 백테스트는 전일 종가 대비 시가 갭을 쓴다.
    metrics['premarket_gap_pct'] = metrics['gap_pct']

    return metrics
