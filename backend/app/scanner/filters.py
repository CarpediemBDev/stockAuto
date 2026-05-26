import pandas as pd
import numpy as np
import time
import asyncio

from app.scanner.indicators import (
    calculate_obv, 
    calculate_rsi_bb, 
    calculate_rsi, 
    calculate_macd
)
from app.scanner.data_provider import fetch_ticker_info

# 뉴스 촉매제 키워드
CATALYST_KEYWORDS = ["earnings", "fda", "partnership", "acquisition", "breakthrough", "launch", "contract"]
FUNDAMENTAL_CACHE = {} # {ticker: (is_healthy, timestamp)}

async def check_fundamental_health(ticker: str) -> bool:
    """
    데이터 프로바이더를 활용하여 최근 분기 실적이 흑자인지 판독 (후지모토 시게루 우량주 필터)
    """
    now = time.time()
    
    # 캐시 만료: 24시간
    if ticker in FUNDAMENTAL_CACHE:
        is_healthy, ts = FUNDAMENTAL_CACHE[ticker]
        if now - ts < 86400:
            return is_healthy
            
    try:
        # yfinance Ticker 날것 결합을 완전히 해제하고 데이터 프로바이더 호출
        info = await fetch_ticker_info(ticker)
        
        ebitda = info.get("ebitda")
        operating_margins = info.get("operatingMargins")
        net_income = info.get("netIncomeToCommon")
        
        is_healthy = True
        
        # 셋 중 0보다 작은 값이 뚜렷하게 확인되는 경우 적자 기업 판정
        if ebitda is not None and ebitda < 0: is_healthy = False
        elif operating_margins is not None and operating_margins < 0: is_healthy = False
        elif net_income is not None and net_income < 0: is_healthy = False
        
        FUNDAMENTAL_CACHE[ticker] = (is_healthy, now)
        return is_healthy
    except Exception as e:
        print(f"[Fundamental] Check failed for {ticker}: {e}. Fallback to True.")
        # yfinance API 에러 대비 기본값은 패스(True) 처리하여 봇의 멈춤 방지
        FUNDAMENTAL_CACHE[ticker] = (True, now)
        return True

def detect_obv_divergence(df_daily: pd.DataFrame, window: int = 20) -> bool:
    """
    일봉 기준 20일간 주가 vs OBV 기울기 비교 (상승 다이버전스 감지 - 세력 매집 확인)
    """
    if df_daily.empty or len(df_daily) < window: return False
    
    temp_df = df_daily.copy()
    if isinstance(temp_df.columns, pd.MultiIndex):
        temp_df.columns = temp_df.columns.get_level_values(0)
        
    sub_df = temp_df.iloc[-window:]
    prices = sub_df['Close'].values.astype(float)
    
    # OBV 계산
    obv_series = calculate_obv(sub_df)
    if obv_series.empty: return False
    obvs = obv_series.values.astype(float)
    
    # 정규화 (기울기 비교를 위해 0~1 값으로 스케일링)
    p_min, p_max = prices.min(), prices.max()
    o_min, o_max = obvs.min(), obvs.max()
    
    if p_max == p_min or o_max == o_min: return False
    
    norm_prices = (prices - p_min) / (p_max - p_min)
    norm_obvs = (obvs - o_min) / (o_max - o_min)
    
    # 기울기 계산 (np.polyfit 활용)
    x = np.arange(len(prices))
    price_slope = np.polyfit(x, norm_prices, 1)[0]
    obv_slope = np.polyfit(x, norm_obvs, 1)[0]
    
    # 주가는 횡보 또는 하락하는데, OBV는 우상향하는 세력 매집 다이버전스 판독
    # (주가 기울기는 미비(<= 0.05) 또는 하락(< 0), OBV 기울기는 강한 우상향(>= 0.15))
    if price_slope <= 0.05 and obv_slope >= 0.15:
        return True
    return False

def detect_rsi_bb_extreme(df_1m: pd.DataFrame) -> bool:
    """
    RSI가 볼밴 하단을 뚫고 이탈했다가 직전 또는 현재 봉에서 다시 안으로 들어왔는지 여부 (과매도 극점 반등)
    """
    if df_1m.empty or len(df_1m) < 40: return False
    
    rsi, upper, lower = calculate_rsi_bb(df_1m)
    if rsi.empty or len(rsi) < 3: return False
    
    # 최근 3개 봉 데이터 기준 판정
    was_below = (rsi.iloc[-3] < lower.iloc[-3]) or (rsi.iloc[-2] < lower.iloc[-2])
    is_inside = rsi.iloc[-1] > lower.iloc[-1]
    
    return bool(was_below and is_inside)

def detect_orb_high(df_1m: pd.DataFrame) -> tuple:
    """
    당일 장 개시 최초 5분봉(Opening Range)의 고점 및 거래량 판독 (토비 크라벨 ORB 돌파 기법)
    반환값: (orb_high, orb_volume, is_breakout)
    """
    if df_1m.empty or len(df_1m) < 10: return 0.0, 0.0, False
    
    temp_df = df_1m.copy()
    if isinstance(temp_df.columns, pd.MultiIndex):
        temp_df.columns = temp_df.columns.get_level_values(0)
        
    # 오늘 자 날짜의 데이터만 추출
    today_date = temp_df.index[-1].date()
    today_df = temp_df[temp_df.index.date == today_date]
    if len(today_df) < 5: return 0.0, 0.0, False
    
    # 장초반 최초 5분봉 데이터 슬라이싱 (1분봉 5개)
    first_5m = today_df.iloc[:5]
    
    high_series = first_5m['High'].squeeze()
    vol_series_5m = first_5m['Volume'].squeeze()
    close_series_today = today_df['Close'].squeeze()
    vol_series_today = today_df['Volume'].squeeze()
    
    if isinstance(high_series, pd.DataFrame): high_series = high_series.iloc[:, 0]
    if isinstance(vol_series_5m, pd.DataFrame): vol_series_5m = vol_series_5m.iloc[:, 0]
    if isinstance(close_series_today, pd.DataFrame): close_series_today = close_series_today.iloc[:, 0]
    if isinstance(vol_series_today, pd.DataFrame): vol_series_today = vol_series_today.iloc[:, 0]
    
    orb_high = float(high_series.max())
    orb_volume = float(vol_series_5m.mean()) # 장초반 평균 거래량
    
    last_close = float(close_series_today.iloc[-2]) if len(today_df) >= 2 else float(close_series_today.iloc[-1])
    last_volume = float(vol_series_today.iloc[-2]) if len(today_df) >= 2 else float(vol_series_today.iloc[-1])
    
    is_breakout = bool((last_close > orb_high) and (last_volume >= orb_volume * 1.2))
    return orb_high, orb_volume, is_breakout

def detect_smart_exit_signal(df_1m: pd.DataFrame) -> bool:
    """
    RSI 하락 다이버전스(추세 둔화) + MACD 데드크로스 조기 익절 시그널 감지 (비트고수 RSI 비밀매매)
    """
    if df_1m.empty or len(df_1m) < 30: return False
    
    temp_df = df_1m.copy()
    if isinstance(temp_df.columns, pd.MultiIndex):
        temp_df.columns = temp_df.columns.get_level_values(0)
        
    close = temp_df['Close'].squeeze()
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
        
    rsi = calculate_rsi(close, period=14).squeeze()
    macd_line, signal_line, _ = calculate_macd(close)
    macd_line = macd_line.squeeze()
    signal_line = signal_line.squeeze()
    
    if isinstance(rsi, pd.DataFrame): rsi = rsi.iloc[:, 0]
    if isinstance(macd_line, pd.DataFrame): macd_line = macd_line.iloc[:, 0]
    if isinstance(signal_line, pd.DataFrame): signal_line = signal_line.iloc[:, 0]
    
    if rsi.empty or macd_line.empty or signal_line.empty or len(rsi) < 5:
        return False
        
    # 최근 5개 봉 기준 분석
    try:
        price_rising = float(close.iloc[-1]) > float(close.iloc[-5])
        rsi_falling = float(rsi.iloc[-1]) < float(rsi.iloc[-5])
        overbought = float(rsi.iloc[-1]) >= 55.0
        
        macd_death_cross = False
        for i in [-1, -2]:
            was_above = float(macd_line.iloc[i-1]) > float(signal_line.iloc[i-1])
            is_below = float(macd_line.iloc[i]) < float(signal_line.iloc[i])
            if was_above and is_below:
                macd_death_cross = True
                break
                
        if price_rising and rsi_falling and overbought and macd_death_cross:
            return True
    except:
        pass
        
    return False

def detect_fakeout_risk(df_1m: pd.DataFrame) -> tuple:
    """
    가짜 돌파(Fakeout) 위험도 감지.
    마지막 마감된 봉(iloc[-2])을 기준으로 분석합니다.
    """
    if df_1m.empty or len(df_1m) < 2: return "LOW", 0.0
    
    from app.scanner.indicators import calculate_wick_ratio
    wick_ratios = calculate_wick_ratio(df_1m).squeeze()
    
    if isinstance(wick_ratios, pd.DataFrame):
        wick_ratios = wick_ratios.iloc[:, 0]
        
    try:
        target_wick = float(wick_ratios.iloc[-2])
    except:
        target_wick = 0.0
    
    if target_wick >= 0.5: # 윗꼬리 50% 이상
        risk = "HIGH"
    elif target_wick >= 0.3: # 윗꼬리 30% 이상
        risk = "MEDIUM"
    else:
        risk = "LOW"
        
    return risk, target_wick
