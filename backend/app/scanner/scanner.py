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
    전수 조사 기반 고수 필터 스캐너 (Stage 1 & 2)
    """
    # 0. 시드 종목 확보 및 시장 감정 분석
    sentiment = await check_market_sentiment()
    tickers = await get_seed_tickers()
    if not tickers: return []
    
    # 1. 지수 데이터 확보 (Relative Strength 계산용)
    df_qqq = await fetch_index_data()
    qqq_perf = (df_qqq['Close'].iloc[-1] / df_qqq['Close'].iloc[0] - 1) if not df_qqq.empty else 0
    
    print(f"[Stage 1] Scanning {len(tickers)} tickers with 15m data...")
    
    # 2. Stage 1: 15분봉 벌크 다운로드 및 필터링
    # 401 에러 방지를 위해 100개씩 청킹
    chunk_size = 100
    all_results = []
    
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i+chunk_size]
        try:
            # 15분봉 벌크 다운로드
            data_15m = await asyncio.to_thread(yf.download, chunk, period="5d", interval="15m", group_by="ticker", progress=False)
            if data_15m.empty: continue

            for ticker in chunk:
                try:
                    # 데이터 추출 (MultiIndex 대응)
                    if isinstance(data_15m.columns, pd.MultiIndex):
                        if ticker not in data_15m.columns.levels[0]: continue
                        df = data_15m[ticker].dropna()
                    else:
                        df = data_15m.dropna()
                        
                    if df.empty or len(df) < 5: continue
                    
                    # --- 고수 필터 조건 계산 ---
                    last_close = float(df['Close'].iloc[-1])
                    prev_close = float(df['Close'].iloc[-2])
                    open_price = float(df['Open'].iloc[-1])
                    
                    # 1) 최소 가격 필터 제거 (1안: 초고수익 동전주 전략 반영)
                    # if last_close < 5.0: continue
                    
                    # 1-1) 당일 누적 거래대금(Dollar Volume) 계산 (종가 * 거래량의 합)
                    temp_df = df.copy()
                    temp_df['Date'] = pd.to_datetime(temp_df.index).date
                    today = temp_df['Date'].max()
                    today_df = temp_df[temp_df['Date'] == today]
                    today_dollar_volume = float((today_df['Close'] * today_df['Volume']).sum())
                    
                    # 초고수 단타 핵심: 거래대금 최소 $1,000,000(100만 달러) 이상인 주도주만 선별 (유동성 쓰레기 잡주 필터링)
                    if today_dollar_volume < 1000000.0:
                        continue
                    
                    # 2) 갭 상승 (%)
                    gap_pct = (open_price / prev_close - 1) * 100
                    
                    # 3) 변동성 (RVOL)
                    rvol = calculate_rvol(df)
                    
                    # 4) 신고가 근처 (전일 고가 돌파 여부)
                    recent_high = df['High'].iloc[:-1].max()
                    dist_to_high = (last_close / recent_high - 1) * 100
                    
                    # 5) 지수 대비 강세 (Relative Strength)
                    stock_perf = (last_close / df['Close'].iloc[0] - 1)
                    relative_strength = stock_perf - qqq_perf
                    
                    # 6) EMA 정배열 (9, 20)
                    ema9 = calculate_ema(df['Close'], 9)
                    ema20 = calculate_ema(df['Close'], 20)
                    is_aligned = bool(ema9.iloc[-1] > ema20.iloc[-1])
                    
                    # --- Stage 1 점수화 (가중치 적용) ---
                    s1_score = 0
                    if gap_pct >= 3.0: s1_score += 30      # 갭 3% 이상 (강력)
                    elif gap_pct >= 1.5: s1_score += 15    # 갭 1.5% 이상
                    
                    if rvol >= 2.0: s1_score += 30         # 상대 거래량 2배 이상
                    elif rvol >= 1.2: s1_score += 15
                    
                    if dist_to_high > -1.5: s1_score += 20 # 신고가 근접
                    if relative_strength > 0: s1_score += 10 # 지수 대비 강세
                    if is_aligned: s1_score += 10          # 이평선 정배열
                    
                    # Stage 2 진입 기준: 점수 30점 이상 혹은 RVOL이 매우 높을 때
                    if s1_score >= 30 or rvol >= 3.0:
                        all_results.append({
                            "ticker": ticker,
                            "s1_score": s1_score,
                            "df_15m": df,
                            "gap_pct": round(gap_pct, 2),
                            "rvol": rvol,
                            "dist_to_high": round(dist_to_high, 2),
                            "rs": round(relative_strength * 100, 2),
                            "ema_aligned": is_aligned,
                            "dollar_volume": round(today_dollar_volume, 2)
                        })
                except: continue
            await asyncio.sleep(0.3) # API 속도 조절
        except Exception as e:
            print(f"[Stage 1] Error in chunk: {e}")

    # 3. Stage 2: 후보군 정밀 분석 (1분봉)
    # 정렬 기준: RVOL(거래량 폭발)을 최우선으로, 그 다음이 점수
    candidates = sorted(all_results, key=lambda x: (x['rvol'], x['s1_score']), reverse=True)[:25]
    if not candidates: return []
    
    print(f"[Stage 2] Precision scanning {len(candidates)} candidates with 1m data & news...")
    
    final_results = []
    candidate_tickers = [c['ticker'] for c in candidates]
    
    try:
        data_1m = await asyncio.to_thread(yf.download, candidate_tickers, period="2d", interval="1m", group_by="ticker", progress=False)
        if data_1m.empty: return []
        
        # 1. 후보 종목들의 뉴스를 병렬(Parallel)로 동시에 조회하여 병목 제거
        async def fetch_news_parallel(ticker: str) -> bool:
            try:
                ticker_obj = yf.Ticker(ticker)
                news = await asyncio.to_thread(lambda: ticker_obj.news)
                for n in (news[:5] if news else []):
                    title = n.get("title", "").lower()
                    if any(kw in title for kw in CATALYST_KEYWORDS):
                        return True
            except Exception as news_err:
                print(f"[Scanner News] Failed for {ticker}: {news_err}")
            return False

        news_tasks = [fetch_news_parallel(c['ticker']) for c in candidates]
        news_results = await asyncio.gather(*news_tasks)
        news_map = {c['ticker']: res for c, res in zip(candidates, news_results)}
        
        for cand in candidates:
            ticker = cand['ticker']
            try:
                if isinstance(data_1m.columns, pd.MultiIndex):
                    if ticker not in data_1m.columns.levels[0]: continue
                    df_1m = data_1m[ticker].dropna()
                else:
                    df_1m = data_1m.dropna()
                if df_1m.empty: continue
                
                # 병렬 조회 결과를 O(1) 해시 맵에서 가져오기
                has_news = news_map.get(ticker, False)
                
                vwap = calculate_vwap(df_1m)
                risk_level, wick_ratio = detect_fakeout_risk(df_1m)
                
                final_score = cand['s1_score']
                if df_1m['Close'].iloc[-1] > vwap.iloc[-1]: final_score += 10
                if has_news: final_score += 10
                if risk_level == "LOW": final_score += 10
                elif risk_level == "HIGH": final_score -= 20

                # 8) 시장 감정 필터 적용
                if sentiment == "BEARISH":
                    final_score -= 30  # 하락장에서는 매우 엄격하게
                elif sentiment == "BULLISH":
                    final_score += 5   # 상승장에서는 약간의 가점
                
                # ATR 계산 추가
                atr_series = calculate_atr(df_1m, period=14)
                latest_atr = float(atr_series.iloc[-1]) if not atr_series.empty else 0.0

                final_results.append({
                    "ticker": ticker,
                    "name": get_ticker_name(ticker),
                    "price": float(df_1m['Close'].iloc[-1]),
                    "signal_score": min(final_score, 100),
                    "signal_type": "STRONG_BUY" if final_score >= 80 else "BUY" if final_score >= 60 else "WATCH",
                    "details": {
                        "gap": cand['gap_pct'],
                        "rvol": cand['rvol'],
                        "wick": round(wick_ratio, 2),
                        "has_news": has_news,
                        "risk": risk_level,
                        "rs": cand['rs'],
                        "ema_aligned": cand.get('ema_aligned', True),
                        "atr": round(latest_atr, 4),
                        "dollar_volume": cand.get('dollar_volume', 0.0)
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
    보유 종목에 대한 실시간 정밀 기술적 지표 및 스코어를 산출합니다. (폭락/약세 판정용)
    """
    import yfinance as yf
    try:
        # 1. 지수 데이터 및 시장 감정 확보
        df_qqq = await fetch_index_data()
        qqq_perf = (df_qqq['Close'].iloc[-1] / df_qqq['Close'].iloc[0] - 1) if not df_qqq.empty else 0
        sentiment = await check_market_sentiment()

        # 2. 15분봉 & 1분봉 데이터 동시 확보
        df_15m = await asyncio.to_thread(yf.download, ticker, period="5d", interval="15m", progress=False)
        df_1m = await asyncio.to_thread(yf.download, ticker, period="1d", interval="1m", progress=False)
        
        if df_15m.empty or df_1m.empty or len(df_15m) < 5:
            return None

        # 3. 기술적 지표 계산 (Stage 1 필터와 정합성 유지)
        last_close = float(df_1m['Close'].iloc[-1])
        
        # 1) RVOL
        rvol = calculate_rvol(df_15m)
        
        # 2) EMA & Trend
        ema9 = calculate_ema(df_15m, 9)
        ema20 = calculate_ema(df_15m, 20)
        ema_aligned = False
        if not ema9.empty and not ema20.empty:
            ema_aligned = ema9.iloc[-1] > ema20.iloc[-1]

        # 3) Relative Strength (RS)
        stock_perf = (df_15m['Close'].iloc[-1] / df_15m['Close'].iloc[0] - 1)
        rs = stock_perf - qqq_perf

        # Stage 1 기본 점수 빌드
        s1_score = 30 # 기본 점수
        if ema_aligned: s1_score += 15
        if rs > 0: s1_score += 10
        if rvol >= 2.0: s1_score += 30
        elif rvol >= 1.2: s1_score += 15

        # 4. Stage 2 세부 지표 계산 (VWAP, Wick, Fakeout Risk)
        vwap = calculate_vwap(df_1m)
        risk_level, wick_ratio = detect_fakeout_risk(df_1m)
        
        final_score = s1_score
        if not vwap.empty and last_close > vwap.iloc[-1]: 
            final_score += 10
        else:
            final_score -= 15 # VWAP 붕괴 시 패널티

        if risk_level == "LOW": final_score += 10
        elif risk_level == "HIGH": final_score -= 20

        # 시장 감정 필터
        if sentiment == "BEARISH":
            final_score -= 30
        elif sentiment == "BULLISH":
            final_score += 5

        # ATR 계산
        atr_series = calculate_atr(df_1m, period=14)
        latest_atr = float(atr_series.iloc[-1]) if not atr_series.empty else 0.0

        return {
            "ticker": ticker,
            "name": get_ticker_name(ticker),
            "price": last_close,
            "signal_score": max(0, min(final_score, 100)),
            "signal_type": "STRONG_BUY" if final_score >= 80 else "BUY" if final_score >= 60 else "WATCH",
            "details": {
                "gap": 0.0, # 단독 종목은 갭 생략
                "rvol": rvol,
                "wick": round(wick_ratio, 2),
                "has_news": False,
                "risk": risk_level,
                "rs": rs,
                "ema_aligned": ema_aligned,
                "atr": round(latest_atr, 4)
            }
        }
    except Exception as e:
        print(f"[Scanner] Dedicated analysis failed for {ticker}: {e}")
        return None
