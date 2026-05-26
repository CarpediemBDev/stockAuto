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
    
    # 각 데이터 시리즈에 대한 squeeze 가드 장착
    high = temp_df['High'].squeeze()
    low = temp_df['Low'].squeeze()
    close = temp_df['Close'].squeeze()
    volume = temp_df['Volume'].squeeze()
    
    if isinstance(high, pd.DataFrame): high = high.iloc[:, 0]
    if isinstance(low, pd.DataFrame): low = low.iloc[:, 0]
    if isinstance(close, pd.DataFrame): close = close.iloc[:, 0]
    if isinstance(volume, pd.DataFrame): volume = volume.iloc[:, 0]
    
    # 당일 데이터만 추출 (일자별로 초기화되는 방식)
    temp_df['Date'] = pd.to_datetime(temp_df.index).date
    
    # 각 날짜별로 누적 계산
    typical_price = (high + low + close) / 3
    tp_v = typical_price * volume
    
    # 날짜별 누적합 계산
    temp_df['TP_V'] = tp_v
    temp_df['Volume_Squeezed'] = volume
    
    grouped = temp_df.groupby('Date')
    cum_tp_v = grouped['TP_V'].cumsum()
    cum_vol = grouped['Volume_Squeezed'].cumsum()
    
    # 결과 반환 시 확실하게 단일 시리즈 가드
    vwap = (cum_tp_v / cum_vol).squeeze()
    if isinstance(vwap, pd.DataFrame):
        vwap = vwap.iloc[:, 0]
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
    
    high = temp_df['High'].squeeze()
    low = temp_df['Low'].squeeze()
    close = temp_df['Close'].squeeze()
    open_ = temp_df['Open'].squeeze()
    
    if isinstance(high, pd.DataFrame): high = high.iloc[:, 0]
    if isinstance(low, pd.DataFrame): low = low.iloc[:, 0]
    if isinstance(close, pd.DataFrame): close = close.iloc[:, 0]
    if isinstance(open_, pd.DataFrame): open_ = open_.iloc[:, 0]
    
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
    
    # squeeze()를 통해 1차원 데이터프레임을 확실하게 시리즈로 쥐어짜기 가드
    vol_series = temp_df['Volume'].squeeze()
    if isinstance(vol_series, pd.DataFrame):
        vol_series = vol_series.iloc[:, 0]
        
    avg_volume = float(vol_series.iloc[-window-2:-2].mean())
    completed_volume = float(vol_series.iloc[-2])
    
    if avg_volume == 0: return 1.0
    return round(completed_volume / avg_volume, 2)

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI (Relative Strength Index) 계산"""
    s_squeezed = series.squeeze()
    if isinstance(s_squeezed, pd.DataFrame):
        s_squeezed = s_squeezed.iloc[:, 0]
        
    delta = s_squeezed.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=period - 1, adjust=False).mean()
    ema_down = down.ewm(com=period - 1, adjust=False).mean()
    
    # 0으로 나누기 방지
    with np.errstate(divide='ignore', invalid='ignore'):
        rs = ema_up / ema_down
        rsi = 100 - (100 / (1 + rs))
        return rsi.fillna(50).squeeze()

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
        
    close = temp_df['Close'].squeeze()
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
        
    rsi = calculate_rsi(close, period=rsi_period)
    
    # RSI에 대한 볼린저 밴드 계산
    rsi_ma = rsi.rolling(window=bb_window).mean()
    rsi_std = rsi.rolling(window=bb_window).std()
    
    upper_band = rsi_ma + (rsi_std * bb_std)
    lower_band = rsi_ma - (rsi_std * bb_std)
    
    return rsi.squeeze(), upper_band.squeeze(), lower_band.squeeze()

def detect_vcp_pattern(df: pd.DataFrame) -> bool:
    """
    마크 미너비니의 VCP (변동성 축소 패턴) 감지 알고리즘.
    최근 가격 진폭이 점차 축소(예: 25% -> 12% -> 5%)되면서 수렴 구역을 돌파하려는 시점을 포착합니다.
    """
    if df.empty or len(df) < 60:
        return False
        
    temp_df = df.copy()
    if isinstance(temp_df.columns, pd.MultiIndex):
        temp_df.columns = temp_df.columns.get_level_values(0)
        
    close = temp_df['Close']
    high = temp_df['High']
    low = temp_df['Low']
    
    # 1. 기본 상승 추세 검증 (최소한 50일 이평선 위에 위치하거나 상승 흐름)
    ma50 = close.rolling(window=50).mean().iloc[-1]
    if close.iloc[-1] < ma50 * 0.95:
        return False
        
    # 2. 최근 3개 분할 구역의 변동성 진폭 계산 (45~30일 전, 30~15일 전, 15~0일 전)
    # VCP는 오른쪽으로 가면서 변동성이 줄어들어야 합니다. (진폭의 수축)
    try:
        range3 = high.iloc[-45:-30].max() - low.iloc[-45:-30].min()
        pct3 = (range3 / close.iloc[-45]) * 100
        
        range2 = high.iloc[-30:-15].max() - low.iloc[-30:-15].min()
        pct2 = (range2 / close.iloc[-30]) * 100
        
        range1 = high.iloc[-15:].max() - low.iloc[-15:].min()
        pct1 = (range1 / close.iloc[-15]) * 100
        
        # 진폭이 점차 유의미하게 쪼그라들었는지 검사 (e.g., 20% -> 10% -> 5% 수축 구조)
        is_contracting = pct3 > pct2 > pct1
        
        # 가장 최근 진폭(pct1)이 8% 미만으로 꽉 조여진 상태인지 검사 (미너비니의 좁은 수축 구역)
        is_tight = pct1 < 8.0
        
        # 3. 돌파 시그널 (현재 가격이 최근 10봉 최고가에 임박했거나 상방 돌파하며 거래량이 증가할 때)
        recent_max_high = high.iloc[-10:-1].max()
        is_breakout_attempt = close.iloc[-1] >= recent_max_high * 0.98
        
        if is_contracting and is_tight and is_breakout_attempt:
            return True
    except:
        pass
        
    return False

def detect_cup_and_handle(df: pd.DataFrame) -> bool:
    """
    윌리엄 오닐의 컵 앤 핸들 (Cup and Handle) 차트 패턴 감지 알고리즘.
    둥근 바닥형 컵을 형성한 후 얕은 눌림목(손잡이)을 거쳐 컵의 우측 립을 강하게 돌파하는 시점을 판별합니다.
    """
    if df.empty or len(df) < 80:
        return False
        
    temp_df = df.copy()
    if isinstance(temp_df.columns, pd.MultiIndex):
        temp_df.columns = temp_df.columns.get_level_values(0)
        
    close = temp_df['Close']
    high = temp_df['High']
    low = temp_df['Low']
    
    try:
        # 최근 80일 중 컵 왼쪽 림(Lip)의 최고가와 인덱스를 찾음
        cup_left_zone = high.iloc[-80:-30]
        left_lip_price = cup_left_zone.max()
        left_lip_idx = cup_left_zone.idxmax()
        
        # 컵의 깊이(Bottom) 검증: 왼쪽 림 형성 이후 최저점
        post_left_zone = low.loc[left_lip_idx:-15]
        if post_left_zone.empty:
            return False
        cup_bottom_price = post_left_zone.min()
        
        # 컵 바닥 깊이가 적당해야 함 (고점 대비 12%~35% 수준의 부드러운 조정)
        drawdown = (left_lip_price - cup_bottom_price) / left_lip_price
        if not (0.10 <= drawdown <= 0.40):
            return False
            
        # 컵의 오른쪽 림(Right Lip) 형성 검증: 전고점(좌측 림) 근처로 회복되었는지 확인
        recovery_zone = high.iloc[-25:-10]
        right_lip_price = recovery_zone.max()
        
        # 좌측 림 대비 우측 림이 10% 이상 차이나지 않아야 대칭형 컵 완성
        if abs(right_lip_price - left_lip_price) / left_lip_price > 0.12:
            return False
            
        # 손잡이(Handle) 형성 검증: 최근 10봉간 얕은 조정 영역
        handle_zone = close.iloc[-10:]
        handle_max = handle_zone.max()
        handle_min = handle_zone.min()
        
        # 손잡이 조정은 우측 림 대비 깊지 않아야 함 (최대 15% 조정 이내)
        handle_drawdown = (right_lip_price - handle_min) / right_lip_price
        if handle_drawdown > 0.15:
            return False
            
        # 현재 가격이 손잡이 영역의 좁은 고가 저항선을 뚫고 솟구치려 할 때 (컵앤핸들 돌파 포착)
        if close.iloc[-1] >= right_lip_price * 0.97:
            return True
            
    except:
        pass
        
    return False

