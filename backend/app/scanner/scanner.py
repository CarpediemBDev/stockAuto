import pandas as pd
import asyncio
import numpy as np

from app.translations.translator import Translator
from app.scanner.indicators import (
    calculate_vwap,
    calculate_rvol,
    calculate_ema,
    calculate_atr
)
from app.scanner.filters import (
    detect_obv_divergence,
    detect_rsi_bb_extreme,
    detect_orb_high,
    detect_smart_exit_signal,
    detect_fakeout_risk,
    check_fundamental_health,
    CATALYST_KEYWORDS
)
from app.scanner.discovery import get_seed_tickers
from app.scanner.data_provider import (
    fetch_ohlcv,
    fetch_index_data,
    fetch_bulk_ohlcv,
    fetch_ticker_news
)

# 지수 비교용 (Relative Strength)
MARKET_INDEX = "QQQ" 

async def check_market_sentiment() -> str:
    """
    나스닥(QQQ) 지수의 추세를 분석하여 전체 시장의 분위기를 파악합니다.
    """
    print("[Sentiment] Analyzing Market Condition (QQQ)...")
    try:
        # 데이터 프로바이더 사용
        df = await fetch_index_data(MARKET_INDEX)
        if df.empty: return "NEUTRAL"

        current_price = df['Close'].iloc[-1]
        ma20 = df['Close'].rolling(window=20).mean().iloc[-1]
        ma50 = df['Close'].rolling(window=50).mean().iloc[-1]
        
        is_bullish = current_price > ma20  # 단기 추세 생존
        is_long_term_safe = ma20 > ma50   # 정배열 확인
        
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

async def scan_market_expert() -> list:
    """
    전수 조사 기반 고수 필터 스캐너 (Stage 1 & 2) - ⭐ v2.0 레짐 스위칭 & 비동기 고성능 데이터 프로바이더 연동
    """
    # 0. 시장 감정 분석 및 시드 종목 확보
    sentiment = await check_market_sentiment()
    tickers = await get_seed_tickers()
    if not tickers: return []
    
    # 1. 지수 데이터 확보 (Relative Strength 계산용)
    df_qqq = await fetch_index_data(MARKET_INDEX)
    qqq_perf = (df_qqq['Close'].iloc[-1] / df_qqq['Close'].iloc[0] - 1) if not df_qqq.empty else 0
    
    print(f"[Stage 1] Scanning {len(tickers)} tickers with 15m data...")
    
    # 2. Stage 1: 15분봉 벌크 다운로드 및 필터링 (데이터 프로바이더 연동)
    chunk_size = 100
    all_results = []
    
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i+chunk_size]
        try:
            # yf.download 직접 호출을 fetch_bulk_ohlcv 로 전격 대체!
            data_15m = await fetch_bulk_ohlcv(chunk, period="5d", interval="15m")
            if data_15m.empty: continue

            for ticker in chunk:
                try:
                    if isinstance(data_15m.columns, pd.MultiIndex):
                        if ticker not in data_15m.columns.get_level_values(0): continue
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
                    
                    # 필수 유동성 필터: 당일 거래대금 최소 $1,000,000 이상만 선별
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

                    high_52w = float(df['High'].max())
                    is_near_52w_high = last_close >= high_52w * 0.98

                    momentum_candles = False
                    if len(df) >= 4:
                        c = df['Close']
                        v = df['Volume']
                        momentum_candles = bool(
                            c.iloc[-1] > c.iloc[-2] > c.iloc[-3] and
                            v.iloc[-1] > v.iloc[-2] > v.iloc[-3]
                        )

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

    # 3. Stage 2: 후보군 정밀 분석
    candidates = sorted(all_results, key=lambda x: (x['rvol'], x['s1_score']), reverse=True)[:25]
    if not candidates: return []
    
    print(f"[Stage 2] Precision scanning {len(candidates)} candidates via dynamic {sentiment} scorecard...")
    
    final_results = []
    candidate_tickers = [c['ticker'] for c in candidates]
    
    try:
        # 💡 [데이터 프로바이더 대량 수집 이식]
        async def fetch_1m_data():
            return await fetch_bulk_ohlcv(candidate_tickers, period="2d", interval="1m")
            
        async def fetch_daily_data():
            return await fetch_bulk_ohlcv(candidate_tickers, period="200d", interval="1d")

        async def fetch_news_parallel(ticker: str) -> bool:
            try:
                # yfinance Ticker 날것 호출을 데이터 프로바이더로 전면 격리
                news = await fetch_ticker_news(ticker)
                for n in (news[:5] if news else []):
                    title = n.get("title", "").lower()
                    if any(kw in title for kw in CATALYST_KEYWORDS):
                        return True
            except: pass
            return False

        news_tasks = [fetch_news_parallel(t) for t in candidate_tickers]
        fundamental_tasks = [check_fundamental_health(t) for t in candidate_tickers]
        
        data_1m, data_daily, news_results, fundamental_results = await asyncio.gather(
            fetch_1m_data(),
            fetch_daily_data(),
            asyncio.gather(*news_tasks),
            asyncio.gather(*fundamental_tasks)
        )
        
        news_map = {t: res for t, res in zip(candidate_tickers, news_results)}
        fundamental_map = {t: res for t, res in zip(candidate_tickers, fundamental_results)}
        
        for cand in candidates:
            ticker = cand['ticker']
            try:
                # 1. 1분봉 데이터 추출
                if isinstance(data_1m.columns, pd.MultiIndex):
                    if ticker not in data_1m.columns.get_level_values(0): continue
                    df_1m = data_1m[ticker].dropna()
                else:
                    df_1m = data_1m.dropna()
                if df_1m.empty or len(df_1m) < 10: continue
                
                # 2. 일봉 데이터 추출 (OBV 연산용)
                if isinstance(data_daily.columns, pd.MultiIndex):
                    if ticker not in data_daily.columns.get_level_values(0): continue
                    df_daily = data_daily[ticker].dropna()
                else:
                    df_daily = data_daily.dropna()
                
                last_close = float(df_1m['Close'].iloc[-1])
                has_news = news_map.get(ticker, False)
                is_fundamental_healthy = fundamental_map.get(ticker, True)
                
                if not is_fundamental_healthy:
                    print(f"[Scanner Filter] {ticker} discarded - Negative earnings (not healthy).")
                    continue
                
                _, _, is_orb_breakout = detect_orb_high(df_1m)
                is_rsi_bb_extreme = detect_rsi_bb_extreme(df_1m)
                is_obv_accumulation = detect_obv_divergence(df_daily) if not df_daily.empty else False
                
                vwap = calculate_vwap(df_1m)
                risk_level, wick_ratio = detect_fakeout_risk(df_1m)
                
                final_score = 0
                
                if sentiment == "BULLISH":
                    final_score = cand['s1_score']
                    
                    if not vwap.empty and last_close > vwap.iloc[-1]: final_score += 10
                    else: final_score -= 15
                    
                    if has_news: final_score += 10
                    
                    if risk_level == "LOW": final_score += 10
                    elif risk_level == "HIGH": final_score -= 20
                    
                    if is_orb_breakout: final_score += 20
                    final_score += 5
                    
                else:
                    if is_obv_accumulation:
                        final_score += 30
                    else:
                        final_score -= 20
                    
                    if not df_daily.empty and len(df_daily) >= 120:
                        daily_close = df_daily['Close']
                        ema120_daily = calculate_ema(daily_close, 120)
                        if daily_close.iloc[-1] > ema120_daily.iloc[-1]:
                            final_score += 30
                            
                    if is_rsi_bb_extreme:
                        final_score += 30
                        
                    if sentiment == "BEARISH":
                        final_score -= 30
                        
                    if not vwap.empty and last_close > vwap.iloc[-1]: final_score += 10
                    else: final_score -= 15
                    
                    if risk_level == "LOW": final_score += 10
                    elif risk_level == "HIGH": final_score -= 20

                final_score = max(0, min(final_score, 100))
                
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

async def scan_overseas_market() -> list:
    return await scan_market_expert()

async def analyze_single_ticker(ticker: str) -> dict:
    """
    보유 종목에 대한 실시간 정밀 기술적 지표 및 스코어를 산출합니다. (폭락/약세 판정용)
    """
    try:
        df_qqq = await fetch_index_data(MARKET_INDEX)
        qqq_perf = (df_qqq['Close'].iloc[-1] / df_qqq['Close'].iloc[0] - 1) if not df_qqq.empty else 0
        sentiment = await check_market_sentiment()

        # 데이터 수집 (데이터 프로바이더 연동으로 강결합 제거)
        df_15m, df_1m, df_daily = await asyncio.gather(
            fetch_ohlcv(ticker, interval="15m", period="5d"),
            fetch_ohlcv(ticker, interval="1m", period="2d"),
            fetch_ohlcv(ticker, interval="1d", period="200d")
        )
        
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

        _, _, is_orb_breakout = detect_orb_high(df_1m)
        is_rsi_bb_extreme = detect_rsi_bb_extreme(df_1m)
        is_obv_accumulation = detect_obv_divergence(df_daily) if not df_daily.empty else False
        is_fundamental_healthy = await check_fundamental_health(ticker)

        fundamental_penalty = 0
        if not is_fundamental_healthy:
            fundamental_penalty = 40

        vwap = calculate_vwap(df_1m)
        risk_level, wick_ratio = detect_fakeout_risk(df_1m)

        final_score = 0
        
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

        final_score -= fundamental_penalty
        final_score = max(0, min(final_score, 100))

        if sentiment == "BULLISH":
            sig_type = "STRONG_BUY" if final_score >= 80 else "BUY" if final_score >= 60 else "WATCH"
        else:
            sig_type = "STRONG_BUY" if final_score >= 90 else "BUY" if final_score >= 70 else "WATCH"

        atr_series = calculate_atr(df_1m, period=14)
        latest_atr = float(atr_series.iloc[-1]) if not atr_series.empty else 0.0
        
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
