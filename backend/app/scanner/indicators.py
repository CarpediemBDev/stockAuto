import pandas as pd
import numpy as np

def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """
    장중 VWAP (Volume Weighted Average Price) 계산.
    장 시작 시점부터 현재까지의 거래량 가중 평균가입니다.
    """
    if df.empty: return pd.Series()
    
    temp_df = df.copy()
    if isinstance(temp_df.columns, pd.MultiIndex):
        temp_df.columns = temp_df.columns.get_level_values(0)
    
    # 당일 데이터만 추출 (일자별로 초기화되는 방식)
    temp_df['Date'] = pd.to_datetime(temp_df.index).date
    
    # 각 날짜별로 누적 계산
    typical_price = (temp_df['High'] + temp_df['Low'] + temp_df['Close']) / 3
    temp_df['TP_V'] = typical_price * temp_df['Volume']
    
    # 날짜별 누적합 계산
    grouped = temp_df.groupby('Date')
    cum_tp_v = grouped['TP_V'].cumsum()
    cum_vol = grouped['Volume'].cumsum()
    
    # 결과 반환 시 인덱스 정합성 유지
    vwap = cum_tp_v / cum_vol
    return vwap

def calculate_wick_ratio(df: pd.DataFrame) -> pd.Series:
    """
    캔들 몸통 대비 윗꼬리의 비율을 계산합니다.
    (High - max(Open, Close)) / (High - Low)
    """
    if df.empty: return pd.Series()
    
    temp_df = df.copy()
    if isinstance(temp_df.columns, pd.MultiIndex):
        temp_df.columns = temp_df.columns.get_level_values(0)
    
    high = temp_df['High']
    low = temp_df['Low']
    close = temp_df['Close']
    open_ = temp_df['Open']
    
    top_of_body = np.maximum(open_.values, close.values)
    wick_length = high.values - top_of_body
    total_length = high.values - low.values
    
    # 0으로 나누기 방지
    with np.errstate(divide='ignore', invalid='ignore'):
        ratio = np.where(total_length > 0, wick_length / total_length, 0)
        
    return pd.Series(ratio, index=df.index).fillna(0)

def calculate_rvol(df: pd.DataFrame, window: int = 20) -> float:
    """
    상대 거래량 (Relative Volume) 계산.
    최근 N개 캔들의 평균 거래량 대비 '마지막 마감된 봉'의 거래량 비율입니다.
    """
    if df.empty or len(df) < window + 2: return 1.0
    
    temp_df = df.copy()
    if isinstance(temp_df.columns, pd.MultiIndex):
        temp_df.columns = temp_df.columns.get_level_values(0)
    
    avg_volume = temp_df['Volume'].iloc[-window-2:-2].mean()
    completed_volume = temp_df['Volume'].iloc[-2]
    
    if avg_volume == 0: return 1.0
    return round(completed_volume / avg_volume, 2)

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI (Relative Strength Index) 계산"""
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=period - 1, adjust=False).mean()
    ema_down = down.ewm(com=period - 1, adjust=False).mean()
    
    # 0으로 나누기 방지
    with np.errstate(divide='ignore', invalid='ignore'):
        rs = ema_up / ema_down
        rsi = 100 - (100 / (1 + rs))
        return rsi.fillna(50)

def calculate_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD 계산"""
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """EMA 계산"""
    return series.ewm(span=period, adjust=False).mean()

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    ATR (Average True Range) 계산.
    TR = max(High - Low, abs(High - Close_prev), abs(Low - Close_prev))
    """
    if df.empty or len(df) < period + 1: return pd.Series()
    
    temp_df = df.copy()
    if isinstance(temp_df.columns, pd.MultiIndex):
        temp_df.columns = temp_df.columns.get_level_values(0)
        
    high = temp_df['High']
    low = temp_df['Low']
    close_prev = temp_df['Close'].shift(1)
    
    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    return atr

def calculate_obv(df: pd.DataFrame) -> pd.Series:
    """OBV (On-Balance Volume) 계산 (차트픽 기법)"""
    if df.empty: return pd.Series()
    temp_df = df.copy()
    if isinstance(temp_df.columns, pd.MultiIndex):
        temp_df.columns = temp_df.columns.get_level_values(0)
    
    close = temp_df['Close']
    volume = temp_df['Volume']
    
    obv = [0]
    for i in range(1, len(close)):
        c_curr = float(close.iloc[i])
        c_prev = float(close.iloc[i-1])
        v_curr = float(volume.iloc[i])
        
        if c_curr > c_prev:
            obv.append(obv[-1] + v_curr)
        elif c_curr < c_prev:
            obv.append(obv[-1] - v_curr)
        else:
            obv.append(obv[-1])
    return pd.Series(obv, index=df.index, dtype=float)

def calculate_rsi_bb(df: pd.DataFrame, rsi_period: int = 14, bb_window: int = 20, bb_std: float = 2.0):
    """
    RSI 지표 데이터 자체 위에 볼린저 밴드(20, 2)를 플로팅합니다. (비트고수 RSI 볼밴 기법)
    """
    if df.empty or len(df) < rsi_period + bb_window:
        return pd.Series(), pd.Series(), pd.Series()
        
    temp_df = df.copy()
    if isinstance(temp_df.columns, pd.MultiIndex):
        temp_df.columns = temp_df.columns.get_level_values(0)
        
    rsi = calculate_rsi(temp_df['Close'], period=rsi_period)
    
    # RSI에 대한 볼린저 밴드 계산
    rsi_ma = rsi.rolling(window=bb_window).mean()
    rsi_std = rsi.rolling(window=bb_window).std()
    
    upper_band = rsi_ma + (rsi_std * bb_std)
    lower_band = rsi_ma - (rsi_std * bb_std)
    
    return rsi, upper_band, lower_band
