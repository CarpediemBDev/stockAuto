import yfinance as yf # pyrefly: ignore [missing-import]
import pandas as pd
import asyncio
import numpy as np
import requests

from app.bot.kis_api import KISClient
from app.translations.translator import Translator
from app.core.database import SessionLocal
from app.core.models import WatchList

# KIS API 클라이언트 초기화
kis_client = KISClient()

# --- Configuration & Consts ---

# 지수 비교용 (Relative Strength)
MARKET_INDEX = "QQQ" 

# 뉴스 키워드 (Catalyst)
CATALYST_KEYWORDS = ["earnings", "fda", "partnership", "acquisition", "breakthrough", "launch", "contract"]

async def check_market_sentiment():
    """
    나스닥(QQQ) 지수의 추세를 분석하여 전체 시장의 분위기를 파악합니다.
    """
    print("[Sentiment] Analyzing Market Condition (QQQ)...")
    try:
        # yf.Ticker 대신 직접 download를 사용하여 병목 방지
        df = await asyncio.to_thread(yf.download, "QQQ", period="60d", interval="1d", progress=False)
        if df.empty: return "NEUTRAL"

        # MultiIndex 처리
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        current_price = df['Close'].iloc[-1]
        ma20 = df['Close'].rolling(window=20).mean().iloc[-1]
        ma50 = df['Close'].rolling(window=50).mean().iloc[-1]
        
        # 1. 이동평균선 기반 추세 확인
        is_bullish = current_price > ma20  # 단기 추세 생존
        is_long_term_safe = ma20 > ma50   # 정배열 확인 (데드크로스 아님)
        
        if is_bullish and is_long_term_safe:
            print("[Sentiment] Market is BULLISH. Aggressive mode ON.")
            return "BULLISH"
        elif not is_bullish:
            print("[Sentiment] Market is BEARISH. Defensive mode ON.")
            return "BEARISH"
        else:
            return "NEUTRAL"
    except Exception as e:
        print(f"[Sentiment] Error checking QQQ: {e}")
        return "NEUTRAL"

def get_ticker_name(ticker: str) -> str:
    """Translator 메모리 캐시를 이용해 종목명을 초고속 번역 및 Fallback 반환합니다."""
    return Translator.translate(ticker)


# --- Data Fetchers ---

async def fetch_ohlcv(ticker: str, interval: str = "1h", period: str = "5d"):
    """
    yfinance를 통해 특정 종목의 OHLCV 데이터를 가져옵니다.
    """
    try:
        # 1분봉의 경우 최대 7일까지만 제공되므로 예외 처리 필요
        data = await asyncio.to_thread(yf.download, ticker, period=period, interval=interval, progress=False)
        if data.empty:
            return pd.DataFrame()
            
        # MultiIndex 컬럼인 경우 단순화 (예: ('Close', 'AAPL') -> 'Close')
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
            
        return data
    except Exception as e:
        print(f"Error fetching {ticker} ({interval}): {e}")
        return pd.DataFrame()

async def get_multi_timeframe_data(ticker: str):
    """
    15분봉(추세용)과 1분봉(실행용) 데이터를 동시에 가져옵니다.
    """
    # 15분봉은 1주일치, 1분봉은 최근 2일치면 충분함
    task_15m = fetch_ohlcv(ticker, interval="15m", period="7d")
    task_1m = fetch_ohlcv(ticker, interval="1m", period="2d")
    
    return await asyncio.gather(task_15m, task_1m)

# --- Calculators (Pure Functions) ---

def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """
    장중 VWAP (Volume Weighted Average Price) 계산.
    장 시작 시점부터 현재까지의 거래량 가중 평균가입니다.
    """
    if df.empty: return pd.Series()
    
    # yfinance 벌크 다운로드 시 MultiIndex 처리
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
    
    # MultiIndex 처리
    temp_df = df.copy()
    if isinstance(temp_df.columns, pd.MultiIndex):
        temp_df.columns = temp_df.columns.get_level_values(0)
    
    high = temp_df['High']
    low = temp_df['Low']
    close = temp_df['Close']
    open_ = temp_df['Open']
    
    # pd.concat 대신 numpy를 사용하여 몸통 상단값 계산 (더 안전함)
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
    # window + 2개의 데이터가 필요함 (평균용 window개 + 마감된 봉 1개 + 현재 봉 1개)
    """
    if df.empty or len(df) < window + 2: return 1.0
    
    # MultiIndex 처리
    temp_df = df.copy()
    if isinstance(temp_df.columns, pd.MultiIndex):
        temp_df.columns = temp_df.columns.get_level_values(0)
    
    # 마지막 봉(iloc[-1])은 진행 중일 수 있으므로 마감된 봉(iloc[-2]) 사용
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
        return rsi.fillna(50) # 데이터가 없는 경우 중립값(50) 반환

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
    # EMA 방식으로 ATR 스무딩
    atr = tr.ewm(span=period, adjust=False).mean()
    return atr

# ⭐ v2.0 신규 보조지표 연산기 및 판독 필터들

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
        # float 명시적 변환
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

def detect_rsi_bb_extreme(df_1m: pd.DataFrame) -> bool:
    """
    RSI가 볼밴 하단을 뚫고 이탈했다가 직전 또는 현재 봉에서 다시 안으로 들어왔는지 여부 (과매도 극점 반등)
    """
    if df_1m.empty or len(df_1m) < 40: return False
    
    rsi, upper, lower = calculate_rsi_bb(df_1m)
    if rsi.empty or len(rsi) < 3: return False
    
    # 최근 3개 봉 데이터 기준 판정
    # was_below: 최근 3개 봉 이내에 rsi가 lower 밴드 아래로 떨어진 적이 있는지
    # is_inside: 현재 rsi가 밴드 하단 위로 복귀했는지
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
        
    # 날짜별로 그룹화하여 오늘 자 날짜의 데이터만 추출
    today_date = temp_df.index[-1].date()
    today_df = temp_df[temp_df.index.date == today_date]
    if len(today_df) < 5: return 0.0, 0.0, False
    
    # 장초반 최초 5분봉 데이터 슬라이싱 (1분봉 5개)
    first_5m = today_df.iloc[:5]
    orb_high = float(first_5m['High'].max())
    orb_volume = float(first_5m['Volume'].mean()) # 장초반 평균 거래량
    
    # 현재 마감된 봉(iloc[-2])의 종가가 ORB High를 대량 거래량(현재 거래량이 장초반 평균 거래량의 1.2배 이상)으로 돌파했는지 판별
    last_close = float(today_df['Close'].iloc[-2]) if len(today_df) >= 2 else float(today_df['Close'].iloc[-1])
    last_volume = float(today_df['Volume'].iloc[-2]) if len(today_df) >= 2 else float(today_df['Volume'].iloc[-1])
    
    is_breakout = (last_close > orb_high) and (last_volume >= orb_volume * 1.2)
    return orb_high, orb_volume, is_breakout

def detect_smart_exit_signal(df_1m: pd.DataFrame) -> bool:
    """
    RSI 하락 다이버전스(추세 둔화) + MACD 데드크로스 조기 익절 시그널 감지 (비트고수 RSI 비밀매매)
    """
    if df_1m.empty or len(df_1m) < 30: return False
    
    temp_df = df_1m.copy()
    if isinstance(temp_df.columns, pd.MultiIndex):
        temp_df.columns = temp_df.columns.get_level_values(0)
        
    close = temp_df['Close']
    rsi = calculate_rsi(close, period=14)
    macd_line, signal_line, _ = calculate_macd(close)
    
    if rsi.empty or macd_line.empty or signal_line.empty or len(rsi) < 5:
        return False
        
    # 최근 5개 봉 기준 분석
    # 1) 주가는 고점을 높임 (iloc[-1] 종가 > iloc[-5] 종가)
    price_rising = float(close.iloc[-1]) > float(close.iloc[-5])
    
    # 2) RSI는 고점을 낮춤 (iloc[-1] RSI < iloc[-5] RSI)
    rsi_falling = float(rsi.iloc[-1]) < float(rsi.iloc[-5])
    
    # 3) 현재 과매수 구간 근처 (RSI >= 55)
    overbought = float(rsi.iloc[-1]) >= 55.0
    
    # 4) MACD 데드크로스 (직전 봉 또는 현재 봉에서 macd_line이 signal_line을 하향 돌파)
    macd_death_cross = False
    for i in [-1, -2]:
        was_above = macd_line.iloc[i-1] > signal_line.iloc[i-1]
        is_below = macd_line.iloc[i] < signal_line.iloc[i]
        if was_above and is_below:
            macd_death_cross = True
            break
            
    # RSI 하락 다이버전스(추세 둔화) + MACD 데드크로스 동시 확정
    if price_rising and rsi_falling and overbought and macd_death_cross:
        return True
    return False

FUNDAMENTAL_CACHE = {} # {ticker: (is_healthy, timestamp)}

def check_fundamental_health(ticker: str) -> bool:
    """
    yfinance를 활용하여 최근 분기 실적이 흑자인지 판독 (후지모토 시게루 우량주 필터)
    """
    import time
    now = time.time()
    
    # 캐시 만료: 24시간
    if ticker in FUNDAMENTAL_CACHE:
        is_healthy, ts = FUNDAMENTAL_CACHE[ticker]
        if now - ts < 86400:
            return is_healthy
            
    try:
        t = yf.Ticker(ticker)
        # fast_info 또는 info에서 재무 상태 약식 파악
        info = t.info
        
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
        # yfinance API 에러 대비 기본값은 패스(True) 처리하여 봇의 멈춤 방지
        FUNDAMENTAL_CACHE[ticker] = (True, now)
        return True

# --- Seed Ticker Discovery (Modular) ---

def fetch_db_watchlist() -> list:
    """DB에서 사용자의 관심종목 리스트를 가져옵니다."""
    db = SessionLocal()
    try:
        watchlist = db.query(WatchList).all()
        tickers = [item.ticker for item in watchlist if item.ticker]
        if tickers: print(f"[Discovery] Found {len(tickers)} tickers from DB Watchlist.")
        return tickers
    except Exception as e:
        print(f"[Discovery] DB fetch failed: {e}")
        return []
    finally:
        db.close()

async def fetch_kis_rankings() -> list:
    """KIS API를 통해 실시간 순위 종목을 가져옵니다."""
    tickers = []
    try:
        exchanges = ["NAS", "NYS"]
        rank_types = ["2", "3"] # 2: 거래대금, 3: 등락률
        for ex in exchanges:
            for rt in rank_types:
                res = kis_client.get_overseas_ranking(ex, rt)
                if res:
                    tickers.extend([item.get("symb") for item in res if item.get("symb")])
        if tickers: print(f"[Discovery] Found {len(tickers)} tickers via KIS API.")
        return list(set(tickers))
    except Exception as e:
        print(f"[Discovery] KIS API failed: {e}")
        return []

async def fetch_yahoo_most_active() -> list:
    """Yahoo Finance API를 통해 실시간 활성 종목을 가져옵니다."""
    try:
        url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=false&scrIds=most_actives&count=100"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            quotes = data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
            tickers = [q.get("symbol") for q in quotes if q.get("symbol")]
            if tickers: print(f"[Discovery] Found {len(tickers)} tickers via Yahoo Finance.")
            return tickers
    except Exception as e:
        print(f"[Discovery] Yahoo Screener failed: {e}")
    return []

async def get_seed_tickers():
    """
    여러 소스에서 분석 대상 종목(Seed Tickers)을 병렬로 수집하고 병합합니다.
    Stage 1에서 벌크 다운로드를 수행하므로 100~200개 종목도 성능 저하 없이 분석 가능합니다.
    """
    print("\n[Discovery] Starting parallel ticker discovery process...")
    
    # 1. 병렬 수집 예약 (KIS + Yahoo)
    kis_task = fetch_kis_rankings()
    yahoo_task = fetch_yahoo_most_active()
    
    # 2. DB 관심종목 수집 (동기)
    db_list = fetch_db_watchlist()
    
    # 3. 모든 소스 결과 대기 및 병합
    kis_list, yahoo_list = await asyncio.gather(kis_task, yahoo_task)
    final_universe = list(set(kis_list + db_list + yahoo_list))
    
    if not final_universe:
        print("[Discovery] All sources failed. Using safety tech list.")
        return ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META", "AMD", "NFLX", "TSM"]
    
    print(f"[Discovery] Process complete. Final universe size: {len(final_universe)}")
    print(f" - KIS: {len(kis_list)} | Yahoo: {len(yahoo_list)} | Watchlist: {len(db_list)}")
    
    return final_universe

# --- Expert Filters (Stage 1) ---

async def fetch_index_data():
    """나스닥 지수(QQQ) 데이터를 가져옵니다."""
    df = await fetch_ohlcv(MARKET_INDEX, interval="15m", period="2d")
    return df

def detect_fakeout_risk(df_1m: pd.DataFrame):
    """
    가짜 돌파(Fakeout) 위험도 감지
    마지막 마감된 봉(iloc[-2])을 기준으로 분석합니다.
    """
    if df_1m.empty or len(df_1m) < 2: return "LOW", 0.0
    
    wick_ratios = calculate_wick_ratio(df_1m)
    target_wick = float(wick_ratios.iloc[-2])
    
    # 위험 단계 설정
    if target_wick >= 0.5: # 윗꼬리 50% 이상
        risk = "HIGH"
    elif target_wick >= 0.3: # 윗꼬리 30% 이상
        risk = "MEDIUM"
    else:
        risk = "LOW"
        
    return risk, target_wick

async def scan_market_expert():
    """
    전수 조사 기반 고수 필터 스캐너 (Stage 1 & 2) - ⭐ v2.0 레짐 스위칭 연동
    """
    # 0. 시장 감정 분석 및 시드 종목 확보
    sentiment = await check_market_sentiment()
    tickers = await get_seed_tickers()
    if not tickers: return []
    
    # 1. 지수 데이터 확보 (Relative Strength 계산용)
    df_qqq = await fetch_index_data()
    qqq_perf = (df_qqq['Close'].iloc[-1] / df_qqq['Close'].iloc[0] - 1) if not df_qqq.empty else 0
    
    print(f"[Stage 1] Scanning {len(tickers)} tickers with 15m data...")
    
    # 2. Stage 1: 15분봉 벌크 다운로드 및 필터링
    # KIS API 속도 제한 방지를 위해 100개씩 청크 분할
    chunk_size = 100
    all_results = []
    
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i+chunk_size]
        try:
            data_15m = await asyncio.to_thread(yf.download, chunk, period="5d", interval="15m", group_by="ticker", progress=False)
            if data_15m.empty: continue

            for ticker in chunk:
                try:
                    if isinstance(data_15m.columns, pd.MultiIndex):
                        if ticker not in data_15m.columns.levels[0]: continue
                        df = data_15m[ticker].dropna()
                    else:
                        df = data_15m.dropna()
                        
                    if df.empty or len(df) < 5: continue
                    
                    last_close = float(df['Close'].iloc[-1])
                    prev_close = float(df['Close'].iloc[-2])
                    open_price = float(df['Open'].iloc[-1])
                    
                    # 당일 누적 거래대금(Dollar Volume) 계산
                    temp_df = df.copy()
                    temp_df['Date'] = pd.to_datetime(temp_df.index).date
                    today = temp_df['Date'].max()
                    today_df = temp_df[temp_df['Date'] == today]
                    today_dollar_volume = float((today_df['Close'] * today_df['Volume']).sum())
                    
                    # 필수 유동성 필터: 당일 거래대금 최소 $1,000,000(100만 달러) 이상인 주도주만 선별
                    if today_dollar_volume < 1000000.0:
                        continue
                    
                    gap_pct = (open_price / prev_close - 1) * 100
                    rvol = calculate_rvol(df)
                    recent_high = df['High'].iloc[:-1].max()
                    dist_to_high = (last_close / recent_high - 1) * 100

                    stock_perf = (last_close / df['Close'].iloc[0] - 1)
                    relative_strength = stock_perf - qqq_perf
                    
                    ema9 = calculate_ema(df['Close'], 9)
                    ema20 = calculate_ema(df['Close'], 20)
                    is_aligned = bool(ema9.iloc[-1] > ema20.iloc[-1])

                    # 52주 신고가 근접
                    high_52w = float(df['High'].max())
                    is_near_52w_high = last_close >= high_52w * 0.98

                    # 3봉 연속 상승 모멘텀
                    momentum_candles = False
                    if len(df) >= 4:
                        c = df['Close']
                        v = df['Volume']
                        momentum_candles = bool(
                            c.iloc[-1] > c.iloc[-2] > c.iloc[-3] and
                            v.iloc[-1] > v.iloc[-2] > v.iloc[-3]
                        )

                    # Pre-market 갭 감지
                    premarket_gap_pct = 0.0
                    try:
                        today_data = today_df
                        if not today_data.empty and len(df) >= 20:
                            first_open_today = float(today_data['Open'].iloc[0])
                            prev_day_data = df[df.index < today_data.index[0]]
                            if not prev_day_data.empty:
                                prev_day_close = float(prev_day_data['Close'].iloc[-1])
                                premarket_gap_pct = (first_open_today / prev_day_close - 1) * 100
                    except:
                        premarket_gap_pct = 0.0
                    
                    # --- Stage 1 기본 점수 빌드 ---
                    s1_score = 0
                    if gap_pct >= 3.0: s1_score += 30
                    elif gap_pct >= 1.5: s1_score += 15
                    
                    if rvol >= 2.0: s1_score += 30
                    elif rvol >= 1.2: s1_score += 15
                    
                    if dist_to_high > -1.5: s1_score += 20
                    if relative_strength > 0: s1_score += 10
                    if is_aligned: s1_score += 10
 
                    if is_near_52w_high: s1_score += 25
                    if momentum_candles: s1_score += 15
                    if premarket_gap_pct >= 5.0: s1_score += 20
 
                    if is_near_52w_high and momentum_candles and premarket_gap_pct >= 5.0:
                        s1_score += 10
                        
                    # Stage 2 진입 후보군 (모멘텀 or 거래량 폭증)
                    if s1_score >= 30 or rvol >= 2.5:
                        all_results.append({
                            "ticker": ticker,
                            "s1_score": s1_score,
                            "df_15m": df,
                            "gap_pct": round(gap_pct, 2),
                            "rvol": rvol,
                            "dist_to_high": round(dist_to_high, 2),
                            "rs": round(relative_strength * 100, 2),
                            "ema_aligned": is_aligned,
                            "dollar_volume": round(today_dollar_volume, 2),
                            "is_near_52w_high": is_near_52w_high,
                            "momentum_candles": momentum_candles,
                            "premarket_gap_pct": round(premarket_gap_pct, 2),
                        })
                except: continue
            await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[Stage 1] Error in chunk: {e}")

    # 3. Stage 2: 후보군 정밀 분석 (1분봉 & 일봉 병렬 수집)
    candidates = sorted(all_results, key=lambda x: (x['rvol'], x['s1_score']), reverse=True)[:25]
    if not candidates: return []
    
    print(f"[Stage 2] Precision scanning {len(candidates)} candidates via dynamic {sentiment} scorecard...")
    
    final_results = []
    candidate_tickers = [c['ticker'] for c in candidates]
    
    try:
        # 💡 지연 방지를 위해 1분봉 데이터, 일봉 데이터, 뉴스 조회를 병렬(asyncio.gather)로 동시 다운로드
        async def fetch_1m_data():
            return await asyncio.to_thread(yf.download, candidate_tickers, period="2d", interval="1m", group_by="ticker", progress=False)
            
        async def fetch_daily_data():
            return await asyncio.to_thread(yf.download, candidate_tickers, period="60d", interval="1d", group_by="ticker", progress=False)

        async def fetch_news_parallel(ticker: str) -> bool:
            try:
                ticker_obj = yf.Ticker(ticker)
                news = await asyncio.to_thread(lambda: ticker_obj.news)
                for n in (news[:5] if news else []):
                    title = n.get("title", "").lower()
                    if any(kw in title for kw in CATALYST_KEYWORDS):
                        return True
            except: pass
            return False

        news_tasks = [fetch_news_parallel(t) for t in candidate_tickers]
        
        # 병렬 수집 기동
        data_1m, data_daily, news_results = await asyncio.gather(
            fetch_1m_data(),
            fetch_daily_data(),
            asyncio.gather(*news_tasks)
        )
        
        news_map = {t: res for t, res in zip(candidate_tickers, news_results)}
        
        for cand in candidates:
            ticker = cand['ticker']
            try:
                # 1. 1분봉 데이터 추출
                if isinstance(data_1m.columns, pd.MultiIndex):
                    if ticker not in data_1m.columns.levels[0]: continue
                    df_1m = data_1m[ticker].dropna()
                else:
                    df_1m = data_1m.dropna()
                if df_1m.empty or len(df_1m) < 10: continue
                
                # 2. 일봉 데이터 추출 (OBV 연산용)
                if isinstance(data_daily.columns, pd.MultiIndex):
                    if ticker not in data_daily.columns.levels[0]: continue
                    df_daily = data_daily[ticker].dropna()
                else:
                    df_daily = data_daily.dropna()
                
                last_close = float(df_1m['Close'].iloc[-1])
                has_news = news_map.get(ticker, False)
                
                # 3. 신규 지표 연산 (ORB, RSI 볼밴, OBV 다이버전스, 흑자 우량주)
                _, _, is_orb_breakout = detect_orb_high(df_1m)
                is_rsi_bb_extreme = detect_rsi_bb_extreme(df_1m)
                is_obv_accumulation = detect_obv_divergence(df_daily) if not df_daily.empty else False
                is_fundamental_healthy = check_fundamental_health(ticker)
                
                # 후지모토 시게루 우량주 필수 필터: 적자 잡주는 상승장/하락장 불문 원천 탈락
                if not is_fundamental_healthy:
                    print(f"[Scanner Filter] {ticker} discarded - Negative earnings (not healthy).")
                    continue
                
                vwap = calculate_vwap(df_1m)
                risk_level, wick_ratio = detect_fakeout_risk(df_1m)
                
                # 💡 4. 장세 레짐 스위칭별 다이내믹 채점판 적용 (TRADING_SCORECARD.md 스펙 구현)
                final_score = 0
                
                if sentiment == "BULLISH":
                    # 🦁 상승장: 모멘텀 돌파 채점표 가동
                    final_score = cand['s1_score'] # 기존 모멘텀 기본점수 계승
                    
                    if not vwap.empty and last_close > vwap.iloc[-1]: final_score += 10
                    else: final_score -= 15 # VWAP 붕괴 감점
                    
                    if has_news: final_score += 10
                    
                    if risk_level == "LOW": final_score += 10
                    elif risk_level == "HIGH": final_score -= 20 # 윗꼬리 감점
                    
                    if is_orb_breakout: final_score += 20 # ORB 돌파 가점
                    final_score += 5 # 상승장 보너스
                    
                else:
                    # 🦊 하락/횡보장: 차트픽 OBV 매집 & RSI 볼밴 극점 반등 채점표 가동 (돌파 지표 제거)
                    # OBV 세력 매집 성공 여부 (차트픽 관문 필터)
                    if is_obv_accumulation:
                        final_score += 30
                    else:
                        final_score -= 20 # 세력 매집 미감지 시 강제 감점 탈락
                    
                    # 120일 이평선 돌파 및 추세선 지지 확인 (추세선 기법)
                    # 일봉 기준 EMA 120선 돌파 지지 확인
                    if not df_daily.empty and len(df_daily) >= 120:
                        daily_close = df_daily['Close']
                        ema120_daily = calculate_ema(daily_close, 120)
                        if daily_close.iloc[-1] > ema120_daily.iloc[-1]:
                            final_score += 30
                            
                    # RSI 볼밴 극점 반등 성공 여부 (RSI 볼밴 기법)
                    if is_rsi_bb_extreme:
                        final_score += 30
                        
                    # 하락장 페널티 적용
                    if sentiment == "BEARISH":
                        final_score -= 30
                        
                    # 기본 안전 필터 연동
                    if not vwap.empty and last_close > vwap.iloc[-1]: final_score += 10
                    else: final_score -= 15
                    
                    if risk_level == "LOW": final_score += 10
                    elif risk_level == "HIGH": final_score -= 20

                # 5. 최종 보정 점수 및 신호 타입 판정
                final_score = max(0, min(final_score, 100))
                
                # 장세별 컷오프 분기
                if sentiment == "BULLISH":
                    sig_type = "STRONG_BUY" if final_score >= 80 else "BUY" if final_score >= 60 else "WATCH"
                else:
                    sig_type = "STRONG_BUY" if final_score >= 90 else "BUY" if final_score >= 70 else "WATCH"
                
                atr_series = calculate_atr(df_1m, period=14)
                latest_atr = float(atr_series.iloc[-1]) if not atr_series.empty else 0.0

                final_results.append({
                    "ticker": ticker,
                    "name": get_ticker_name(ticker),
                    "price": last_close,
                    "signal_score": final_score,
                    "signal_type": sig_type,
                    "details": {
                        "gap": cand['gap_pct'],
                        "rvol": cand['rvol'],
                        "wick": round(wick_ratio, 2),
                        "has_news": has_news,
                        "risk": risk_level,
                        "rs": cand['rs'],
                        "ema_aligned": cand.get('ema_aligned', True),
                        "atr": round(latest_atr, 4),
                        "dollar_volume": cand.get('dollar_volume', 0.0),
                        "is_near_52w_high": cand.get('is_near_52w_high', False),
                        "momentum_candles": cand.get('momentum_candles', False),
                        "premarket_gap_pct": cand.get('premarket_gap_pct', 0.0),
                        "is_orb_breakout": is_orb_breakout,
                        "is_rsi_bb_extreme": is_rsi_bb_extreme,
                        "is_obv_accumulation": is_obv_accumulation,
                        "regime_mode": sentiment
                    }
                })
            except: continue
    except Exception as e:
        print(f"[Stage 2] Error: {e}")
        
    return sorted(final_results, key=lambda x: -x['signal_score'])

async def scan_overseas_market():
    return await scan_market_expert()


async def analyze_single_ticker(ticker: str) -> dict:
    """
    보유 종목에 대한 실시간 정밀 기술적 지표 및 스코어를 산출합니다. (폭락/약세 판정용) - ⭐ v2.0 레짐 스위칭 연동
    """
    try:
        df_qqq = await fetch_index_data()
        qqq_perf = (df_qqq['Close'].iloc[-1] / df_qqq['Close'].iloc[0] - 1) if not df_qqq.empty else 0
        sentiment = await check_market_sentiment()

        # 데이터 수집 (병렬 처리)
        async def fetch_15m():
            return await asyncio.to_thread(yf.download, ticker, period="5d", interval="15m", progress=False)
            
        async def fetch_1m():
            return await asyncio.to_thread(yf.download, ticker, period="2d", interval="1m", progress=False)
            
        async def fetch_daily():
            return await asyncio.to_thread(yf.download, ticker, period="60d", interval="1d", progress=False)

        df_15m, df_1m, df_daily = await asyncio.gather(fetch_15m(), fetch_1m(), fetch_daily())
        
        if df_15m.empty or df_1m.empty or len(df_15m) < 5:
            return None

        last_close = float(df_1m['Close'].iloc[-1])
        rvol = calculate_rvol(df_15m)
        
        ema9 = calculate_ema(df_15m, 9)
        ema20 = calculate_ema(df_15m, 20)
        ema_aligned = False
        if not ema9.empty and not ema20.empty:
            ema_aligned = bool(ema9.iloc[-1] > ema20.iloc[-1])

        stock_perf = (df_15m['Close'].iloc[-1] / df_15m['Close'].iloc[0] - 1)
        rs = stock_perf - qqq_perf

        # 1. 신규 지표 연산 (ORB, RSI 볼밴, OBV 다이버전스, 흑자 우량주)
        _, _, is_orb_breakout = detect_orb_high(df_1m)
        is_rsi_bb_extreme = detect_rsi_bb_extreme(df_1m)
        is_obv_accumulation = detect_obv_divergence(df_daily) if not df_daily.empty else False
        is_fundamental_healthy = check_fundamental_health(ticker)

        # 재무 건전성 붕괴 시 즉시 강등 및 감점 (-40점)
        fundamental_penalty = 0
        if not is_fundamental_healthy:
            fundamental_penalty = 40

        vwap = calculate_vwap(df_1m)
        risk_level, wick_ratio = detect_fakeout_risk(df_1m)

        final_score = 0
        
        # 💡 2. 장세 모드별 동일한 다이내믹 채점판 대조 계산 (TRADING_SCORECARD.md 스펙 반영)
        if sentiment == "BULLISH":
            s1_score = 30
            if ema_aligned: s1_score += 15
            if rs > 0: s1_score += 10
            if rvol >= 2.0: s1_score += 30
            elif rvol >= 1.2: s1_score += 15
            
            final_score = s1_score
            if not vwap.empty and last_close > vwap.iloc[-1]: final_score += 10
            else: final_score -= 15
            
            if risk_level == "LOW": final_score += 10
            elif risk_level == "HIGH": final_score -= 20
            
            if is_orb_breakout: final_score += 20
            final_score += 5
        else:
            if is_obv_accumulation: final_score += 30
            else: final_score -= 20
            
            if not df_daily.empty and len(df_daily) >= 120:
                daily_close = df_daily['Close']
                ema120_daily = calculate_ema(daily_close, 120)
                if daily_close.iloc[-1] > ema120_daily.iloc[-1]:
                    final_score += 30
                    
            if is_rsi_bb_extreme: final_score += 30
            if sentiment == "BEARISH": final_score -= 30
            
            if not vwap.empty and last_close > vwap.iloc[-1]: final_score += 10
            else: final_score -= 15
            
            if risk_level == "LOW": final_score += 10
            elif risk_level == "HIGH": final_score -= 20

        # 재무 패널티 반영 및 보정
        final_score -= fundamental_penalty
        final_score = max(0, min(final_score, 100))

        if sentiment == "BULLISH":
            sig_type = "STRONG_BUY" if final_score >= 80 else "BUY" if final_score >= 60 else "WATCH"
        else:
            sig_type = "STRONG_BUY" if final_score >= 90 else "BUY" if final_score >= 70 else "WATCH"

        atr_series = calculate_atr(df_1m, period=14)
        latest_atr = float(atr_series.iloc[-1]) if not atr_series.empty else 0.0
        
        # ⭐ v2.0 RSI 하락 다이버전스 + MACD 데드크로스 조기 익절 판독
        is_smart_exit = detect_smart_exit_signal(df_1m)

        return {
            "ticker": ticker,
            "name": get_ticker_name(ticker),
            "price": last_close,
            "signal_score": final_score,
            "signal_type": sig_type,
            "details": {
                "gap": 0.0,
                "rvol": rvol,
                "wick": round(wick_ratio, 2),
                "has_news": False,
                "risk": risk_level,
                "rs": rs,
                "ema_aligned": ema_aligned,
                "atr": round(latest_atr, 4),
                "is_orb_breakout": is_orb_breakout,
                "is_rsi_bb_extreme": is_rsi_bb_extreme,
                "is_obv_accumulation": is_obv_accumulation,
                "is_fundamental_healthy": is_fundamental_healthy,
                "is_smart_exit": is_smart_exit,
                "regime_mode": sentiment
            }
        }
    except Exception as e:
        print(f"[Scanner] Dedicated analysis failed for {ticker}: {e}")
        return None
