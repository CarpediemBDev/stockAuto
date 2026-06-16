import pandas as pd
import asyncio
import numpy as np
import inspect
from app.core.config import settings
from app.core.logging import logger


from app.translations.translator import Translator
from app.scanner.indicators import (
    calculate_vwap,
    calculate_rvol,
    calculate_ema,
    calculate_atr,
    detect_vcp_pattern,
    detect_cup_and_handle,
    calculate_double_bb_reversion_signals
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
from app.scanner.news_analyzer import analyze_news_sentiment

# 지수 비교용 (Relative Strength)
MARKET_INDEX = "QQQ" 

# 최소 거래대금 기준 (한국 돈 1억 원)
MIN_KRW_VOLUME = 100_000_000.0

# 💡 Sentiment 캐시 (5분 TTL - API 호출 최소화 & 로그 과다 출력 방지)
_sentiment_cache = {"value": None, "timestamp": 0}
SENTIMENT_TTL = 300  # 5분 (API 호출 빈도 대폭 감소)

# 💡 동시 호출 방지용 비동기 락 (이벤트 루프 종속성 이슈 해결을 위해 per-loop 로 관리)
_sentiment_locks = {}

def get_sentiment_lock() -> asyncio.Lock:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # 이벤트 루프가 없는 상황 (일부 테스트 환경 등)
        return asyncio.Lock()
    
    loop_id = id(loop)
    if loop_id not in _sentiment_locks:
        _sentiment_locks[loop_id] = asyncio.Lock()
    return _sentiment_locks[loop_id]

def calculate_strategy_score(strategy_instance, row, regime: str, is_entry: bool = True, score_card: list | None = None) -> float:
    """세부 채점표를 지원하는 전략에만 score_card를 전달합니다."""
    params = inspect.signature(strategy_instance.calculate_score).parameters
    if score_card is not None and "score_card" in params:
        return strategy_instance.calculate_score(row, regime, is_entry=is_entry, score_card=score_card)
    return strategy_instance.calculate_score(row, regime, is_entry=is_entry)

async def check_market_sentiment() -> str:
    """
    나스닥(QQQ) 지수의 추세를 분석하여 전체 시장의 분위기를 파악합니다.
    캐싱 + 비동기 락을 통해 동시 호출을 원천 차단하고 API 호출을 최소화합니다.
    """
    import time
    now = time.time()

    # 1. 락 없이 빠르게 캐시 확인 (대부분의 경우 여기서 반환)
    if _sentiment_cache["value"] is not None and (now - _sentiment_cache["timestamp"]) < SENTIMENT_TTL:
        return _sentiment_cache["value"]

    # 2. 캐시 미스 시 락 획득 후 계산 (동시성 제어)
    lock = get_sentiment_lock()
    async with lock:
        # 락 획득 후 다시 한 번 캐시 확인 (다른 태스크가 먼저 계산했을 수 있음)
        now = time.time()
        if _sentiment_cache["value"] is not None and (now - _sentiment_cache["timestamp"]) < SENTIMENT_TTL:
            return _sentiment_cache["value"]

        # 진짜 계산 수행 (오직 하나의 태스크만 실행)
        result = await _calculate_market_sentiment()
        _sentiment_cache["value"] = result
        _sentiment_cache["timestamp"] = now
        return result

async def _calculate_market_sentiment() -> str:
    """
    실제 시장 감정 분석 로직 (캐시 미스 시에만 호출).
    """
    logger.info("[Sentiment] Analyzing Market Condition (QQQ)...")
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
            logger.info("[Sentiment] Market is BULLISH. Aggressive mode ON.")
            return "BULLISH"
        elif not is_bullish:
            logger.info("[Sentiment] Market is BEARISH. Defensive mode ON.")
            return "BEARISH"
        else:
            return "NEUTRAL"
    except Exception as e:
        logger.error(f"[Sentiment] Error checking QQQ: {e}", exc_info=True)
        return "NEUTRAL"

def get_ticker_name(ticker: str) -> str:
    """Translator 메모리 캐시를 이용해 종목명을 초고속 번역 및 Fallback 반환합니다."""
    return Translator.translate(ticker)

async def scan_market_expert(bypass_tickers: set = None) -> list:
    """
    전수 조사 기반 고수 필터 스캐너 (Stage 1 & 2) - ⭐ v2.0 레짐 스위칭 & 비동기 고성능 데이터 프로바이더 연동
    """
    # 0. 시장 감정 분석 및 시드 종목 확보
    sentiment = await check_market_sentiment()
    tickers, source_map = await get_seed_tickers()
    if not tickers: return []
    
    # 1. 지수 데이터 확보 (Relative Strength 계산용)
    df_qqq = await fetch_index_data(MARKET_INDEX)
    qqq_perf = (df_qqq['Close'].iloc[-1] / df_qqq['Close'].iloc[0] - 1) if not df_qqq.empty else 0
    
    # 1.5. 최소 거래대금 기준 설정 (설정된 한국 돈 기준 환산)
    from app.bot.fx_cache import FXRateCache
    min_dollar_volume = MIN_KRW_VOLUME / FXRateCache.get_rate()
    
    logger.info(f"[Stage 1] Scanning {len(tickers)} tickers with 15m data (Min Vol: ${min_dollar_volume:,.2f})...")
    
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
                    
                    # 당일 누적 거래대금(Dollar Volume) 계산
                    temp_df = df.copy()
                    temp_df['Date'] = pd.to_datetime(temp_df.index).date
                    today = temp_df['Date'].max()
                    today_df = temp_df[temp_df['Date'] == today]
                    today_dollar_volume = float((today_df['Close'] * today_df['Volume']).sum())
                    
                    # 필수 유동성 필터: 당일 거래대금 최소 1억 원 이상만 선별
                    if today_dollar_volume < min_dollar_volume:
                        continue
                    
                    session_gap_pct = 0.0
                    try:
                        if not today_df.empty and len(df) >= 20:
                            first_open_today = float(today_df['Open'].iloc[0])
                            prev_day_data = df[df.index < today_df.index[0]]
                            if not prev_day_data.empty:
                                prev_day_close = float(prev_day_data['Close'].iloc[-1])
                                session_gap_pct = (first_open_today / prev_day_close - 1) * 100
                    except Exception:
                        session_gap_pct = 0.0

                    gap_pct = session_gap_pct
                    rvol = calculate_rvol(df)
                    recent_high = df['High'].iloc[:-1].max()
                    dist_to_high = (last_close / recent_high - 1) * 100

                    stock_perf = (last_close / df['Close'].iloc[0] - 1)
                    relative_strength = stock_perf - qqq_perf
                    
                    ema9 = calculate_ema(df['Close'], 9)
                    ema20 = calculate_ema(df['Close'], 20)
                    latest_ema9 = float(ema9.iloc[-1]) if not ema9.empty else 0.0
                    latest_ema20 = float(ema20.iloc[-1]) if not ema20.empty else 0.0
                    is_aligned = bool(latest_ema9 > latest_ema20)

                    recent_5d_high = float(df['High'].max())
                    is_near_recent_high = last_close >= recent_5d_high * 0.98

                    momentum_candles = False
                    if len(df) >= 4:
                        c = df['Close']
                        v = df['Volume']
                        momentum_candles = bool(
                            c.iloc[-1] > c.iloc[-2] > c.iloc[-3] and
                            v.iloc[-1] > v.iloc[-2] > v.iloc[-3]
                        )

                    premarket_gap_pct = session_gap_pct
                    
                    s1_score = 0
                    if gap_pct >= 3.0: s1_score += 30
                    elif gap_pct >= 1.5: s1_score += 15
                    
                    if rvol >= 2.0: s1_score += 30
                    elif rvol >= 1.2: s1_score += 15
                    
                    if dist_to_high > -1.5: s1_score += 20
                    if relative_strength > 0: s1_score += 10
                    if is_aligned: s1_score += 10
 
                    if is_near_recent_high: s1_score += 25
                    if momentum_candles: s1_score += 15
                    if premarket_gap_pct >= 5.0: s1_score += 20
 
                    if is_near_recent_high and momentum_candles and premarket_gap_pct >= 5.0:
                        s1_score += 10
                        
                    # 관심종목(WATCHLIST)은 Stage 1 필터 면제: 점수 무관하게 무조건 Stage 2 진입
                    is_watchlist = "WATCHLIST" in source_map.get(ticker, [])
                    if s1_score >= 30 or rvol >= 2.5 or is_watchlist:
                        all_results.append({
                            "ticker": ticker,
                            "source": source_map.get(ticker, ["MARKET"]),
                            "s1_score": s1_score,
                            "df_15m": df,
                            "gap_pct": round(gap_pct, 2),
                            "rvol": rvol,
                            "RVOL": rvol,
                            "dist_to_high": round(dist_to_high, 2),
                            "relative_strength": relative_strength,
                            "rs": round(relative_strength * 100, 2),
                            "EMA9": latest_ema9,
                            "EMA20": latest_ema20,
                            "ema_aligned": is_aligned,
                            "dollar_volume": round(today_dollar_volume, 2),
                            "is_near_recent_high": is_near_recent_high,
                            "is_near_52w_high": False,
                            "momentum_candles": momentum_candles,
                            "premarket_gap_pct": round(premarket_gap_pct, 2),
                        })
                except Exception:
                    continue
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"[Stage 1] Error in chunk: {e}", exc_info=True)

    # 3. Stage 2: 후보군 정밀 분석
    candidates = sorted(all_results, key=lambda x: (x['rvol'], x['s1_score']), reverse=True)[:25]
    if not candidates: return []
    
    logger.info(f"[Stage 2] Precision scanning {len(candidates)} candidates via dynamic {sentiment} scorecard...")
    
    final_results = []
    candidate_tickers = [c['ticker'] for c in candidates]
    
    try:
        # 💡 [데이터 프로바이더 대량 수집 이식]
        async def fetch_5m_data():
            return await fetch_bulk_ohlcv(candidate_tickers, period="5d", interval="5m")
            
        async def fetch_daily_data():
            return await fetch_bulk_ohlcv(candidate_tickers, period="1y", interval="1d")
            
        async def fetch_news_data(ticker: str) -> list:
            try:
                # yfinance Ticker 날것 호출을 데이터 프로바이더로 전면 격리
                return await fetch_ticker_news(ticker)
            except Exception:
                return []

        news_tasks = [fetch_news_data(t) for t in candidate_tickers]
        fundamental_tasks = [check_fundamental_health(t) for t in candidate_tickers]
        
        data_5m, data_daily, news_results, fundamental_results = await asyncio.gather(
            fetch_5m_data(),
            fetch_daily_data(),
            asyncio.gather(*news_tasks),
            asyncio.gather(*fundamental_tasks)
        )
        
        news_map = {t: res for t, res in zip(candidate_tickers, news_results)}
        fundamental_map = {t: res for t, res in zip(candidate_tickers, fundamental_results)}
        
        for cand in candidates:
            ticker = cand['ticker']
            try:
                # 1. 5분봉 데이터 추출
                if isinstance(data_5m.columns, pd.MultiIndex):
                    if ticker not in data_5m.columns.get_level_values(0): continue
                    df_5m = data_5m[ticker].dropna()
                else:
                    df_5m = data_5m.dropna()
                if df_5m.empty or len(df_5m) < 10: continue
                
                # 2. 일봉 데이터 추출 (OBV, VCP, Cup & Handle 연산용)
                if isinstance(data_daily.columns, pd.MultiIndex):
                    if ticker not in data_daily.columns.get_level_values(0): continue
                    df_daily = data_daily[ticker].dropna()
                else:
                    df_daily = data_daily.dropna()

                last_close = float(df_5m['Close'].iloc[-1])

                is_near_52w_high = False
                if not df_daily.empty:
                    high_52w = float(df_daily['High'].max())
                    if high_52w > 0:
                        is_near_52w_high = last_close >= high_52w * 0.98
                cand['is_near_52w_high'] = is_near_52w_high

                news_list = news_map.get(ticker, [])
                is_fundamental_healthy = fundamental_map.get(ticker, True)
                
                # 💡 [필터 우회] 사용자가 관심종목(WATCHLIST)으로 등록했거나, 외부 주입된 우회 대상 종목(bypass_tickers)인 경우
                # 적자 기업이더라도 매매가 가능하도록 재무 필터링(퇴출)을 적용하지 않고 통과시킵니다.
                is_target_ticker = ticker in bypass_tickers if bypass_tickers else False
                is_watchlist = "WATCHLIST" in cand.get("source", [])
                
                if not is_fundamental_healthy and not is_watchlist and not is_target_ticker:
                    logger.info(f"[Scanner Filter] {ticker} discarded - Negative earnings (not healthy).")
                    continue
                
                # AI 기반 뉴스 감성 판독 호출 (Gemini API + 로컬 룰 백업 하이브리드 엔진)
                news_analysis = await analyze_news_sentiment(ticker, news_list)
                news_sentiment = news_analysis["sentiment"]
                news_sentiment_score = news_analysis["sentiment_score"]
                news_summary = news_analysis["summary"]
                news_url = news_analysis["url"]
                
                # 기술적 지표 및 퀀트 차트 패턴 감지
                _, _, is_orb_breakout = detect_orb_high(df_5m)
                is_rsi_bb_extreme = detect_rsi_bb_extreme(df_5m)
                is_obv_accumulation = detect_obv_divergence(df_daily) if not df_daily.empty else False
                
                # VCP / Cup & Handle 패턴 인식 적용
                is_vcp = detect_vcp_pattern(df_daily) if not df_daily.empty else False
                is_cup = detect_cup_and_handle(df_daily) if not df_daily.empty else False
                
                vwap = calculate_vwap(df_5m)
                risk_level, wick_ratio = detect_fakeout_risk(df_5m)
                
                # 💡 마켓트랩 더블 볼린저 밴드 역추세 전략 신호 실시간 계산
                df_bb_signals = calculate_double_bb_reversion_signals(df_5m)
                is_double_bb_buy = float(df_bb_signals['is_double_bb_buy'].iloc[-1]) if not df_bb_signals.empty else 0.0
                is_double_bb_sell = float(df_bb_signals['is_double_bb_sell'].iloc[-1]) if not df_bb_signals.empty else 0.0
                
                # ----------------- 다이내믹 세부 채점표 (score_card) 구축 -----------------
                score_card = []
                final_score = 0
                patterns_list = []
                
                # 💡 [전략 패턴] 전략 팩토리를 통해 실시간 전략 로드 및 채점
                from app.strategies.strategy_factory import get_strategy
                strategy_instance = get_strategy(settings.STRATEGY_TYPE)
                
                # 채점에 필요한 실시간 필드들을 cand(dict)에 바인딩
                cand['Close'] = last_close
                cand['Volume'] = float(df_5m['Volume'].iloc[-1]) if not df_5m.empty else 0.0
                cand['VWAP'] = float(vwap.iloc[-1]) if not vwap.empty and pd.notna(vwap.iloc[-1]) else None
                cand['Wick'] = wick_ratio
                cand['RVOL'] = cand.get('RVOL', cand.get('rvol', 1.0))
                cand['EMA9'] = cand.get('EMA9', 0.0)
                cand['EMA20'] = cand.get('EMA20', 0.0)
                cand['is_rsi_bb_extreme'] = is_rsi_bb_extreme
                cand['OBV_divergence'] = 1.0 if is_obv_accumulation else -1.0
                cand['relative_strength'] = cand.get('relative_strength', cand.get('rs', 0.0) / 100.0)
                cand['premarket_gap_pct'] = cand.get('premarket_gap_pct', 0.0)
                cand['news_sentiment'] = news_sentiment
                cand['news_sentiment_score'] = news_sentiment_score
                cand['is_vcp'] = is_vcp
                cand['is_cup'] = is_cup
                cand['is_orb_breakout'] = is_orb_breakout
                cand['risk_level'] = risk_level
                cand['is_double_bb_buy'] = is_double_bb_buy
                cand['is_double_bb_sell'] = is_double_bb_sell
                
                if not df_daily.empty and len(df_daily) >= 120:
                    daily_ema120 = calculate_ema(df_daily['Close'], 120)
                    cand['EMA120'] = float(daily_ema120.iloc[-1]) if not daily_ema120.empty and pd.notna(daily_ema120.iloc[-1]) else None
                else:
                    cand['EMA120'] = None
                
                # 전략 클래스를 통한 채점 가동
                final_score = calculate_strategy_score(strategy_instance, cand, sentiment, is_entry=True, score_card=score_card)
                
                # 패턴 감지 여부 누적
                if is_vcp: patterns_list.append("VCP")
                if is_cup: patterns_list.append("CUP_AND_HANDLE")

                # 최종 범위 보장 및 등급 판독
                final_score = max(0, min(final_score, 100))
                
                if sentiment == "BULLISH":
                    sig_type = "STRONG_BUY" if final_score >= 85 else "BUY" if final_score >= 65 else "WATCH"
                else:
                    sig_type = "STRONG_BUY" if final_score >= 95 else "BUY" if final_score >= 75 else "WATCH"
                
                atr_series = calculate_atr(df_5m, period=14)
                latest_atr = float(atr_series.iloc[-1]) if not atr_series.empty else 0.0
                
                final_results.append({
                    "ticker": ticker,
                    "source": cand.get("source", ["MARKET"]),
                    "name": get_ticker_name(ticker),
                    "price": last_close,
                    "signal_score": final_score,
                    "signal_type": sig_type,
                    "news_sentiment": news_sentiment,
                    "news_sentiment_score": news_sentiment_score,
                    "news_summary": news_summary,
                    "news_url": news_url,
                    "patterns": patterns_list,
                    "score_card": score_card,
                    "details": {
                        "gap": cand['gap_pct'],
                        "rvol": cand['rvol'],
                        "wick": round(wick_ratio, 2),
                        "has_news": len(news_list) > 0,
                        "risk": risk_level,
                        "rs": cand['rs'],
                        "ema_aligned": cand.get('ema_aligned', True),
                        "atr": round(latest_atr, 4),
                        "dollar_volume": cand.get('dollar_volume', 0.0),
                        "is_near_52w_high": cand.get('is_near_52w_high', False),
                        "is_near_recent_high": cand.get('is_near_recent_high', False),
                        "momentum_candles": cand.get('momentum_candles', False),
                        "premarket_gap_pct": cand.get('premarket_gap_pct', 0.0),
                        "is_orb_breakout": is_orb_breakout,
                        "is_rsi_bb_extreme": is_rsi_bb_extreme,
                        "is_obv_accumulation": is_obv_accumulation,
                        "is_vcp": is_vcp,
                        "is_cup": is_cup,
                        "regime_mode": sentiment,
                        "Close": last_close,
                        "Volume": cand.get('Volume', 0.0),
                        "VWAP": cand.get('VWAP', None),
                        "RVOL": cand.get('RVOL', 1.0),
                        "EMA9": cand.get('EMA9', 0.0),
                        "EMA20": cand.get('EMA20', 0.0),
                        "EMA120": cand.get('EMA120', None),
                        "OBV_divergence": cand.get('OBV_divergence', -1.0),
                        "is_double_bb_buy": is_double_bb_buy,
                        "is_double_bb_sell": is_double_bb_sell
                    }
                })
            except Exception as item_err:
                logger.error(f"[Stage 2] Error processing candidate {ticker}: {item_err}", exc_info=True)
                continue
    except Exception as e:
        logger.error(f"[Stage 2] Error: {e}", exc_info=True)
        
    return sorted(final_results, key=lambda x: -x['signal_score'])

async def scan_overseas_market(bypass_tickers: set = None) -> list:
    return await scan_market_expert(bypass_tickers=bypass_tickers)

async def analyze_single_ticker(ticker: str, bypass_fundamental: bool = False) -> dict:
    """
    보유 종목에 대한 실시간 정밀 기술적 지표 및 스코어를 산출합니다. (폭락/약세 판정용)
    """
    try:
        # 💡 QQQ 데이터는 check_market_sentiment() 캐시와 공유되므로 한 번만 조회
        sentiment = await check_market_sentiment()
        df_qqq = await fetch_index_data(MARKET_INDEX)
        qqq_perf = (df_qqq['Close'].iloc[-1] / df_qqq['Close'].iloc[0] - 1) if not df_qqq.empty else 0

        # 데이터 수집 (데이터 프로바이더 연동으로 강결합 제거)
        df_15m, df_5m, df_daily = await asyncio.gather(
            fetch_ohlcv(ticker, interval="15m", period="5d"),
            fetch_ohlcv(ticker, interval="5m", period="5d"),
            fetch_ohlcv(ticker, interval="1d", period="200d")
        )
        
        if df_15m.empty or df_5m.empty or len(df_15m) < 5:
            return None

        # [핵심 가드] yfinance MultiIndex 데이터 유출 방지 및 중복 컬럼 완전 제거 정화
        cleaned_dfs = []
        for dataframe in (df_15m, df_5m, df_daily):
            if dataframe.empty:
                cleaned_dfs.append(dataframe)
                continue
            temp = dataframe.copy()
            if isinstance(temp.columns, pd.MultiIndex):
                temp.columns = temp.columns.get_level_values(0)
            temp = temp.loc[:, ~temp.columns.duplicated()]
            cleaned_dfs.append(temp)
            
        df_15m, df_5m, df_daily = cleaned_dfs

        last_close = float(df_5m['Close'].iloc[-1])
        rvol = calculate_rvol(df_15m)
        
        ema9 = calculate_ema(df_15m['Close'], 9)
        ema20 = calculate_ema(df_15m['Close'], 20)
        ema_aligned = False
        if not ema9.empty and not ema20.empty:
            ema_aligned = bool(ema9.iloc[-1] > ema20.iloc[-1])

        stock_perf = float(df_15m['Close'].iloc[-1] / df_15m['Close'].iloc[0] - 1)
        rs = float(stock_perf - qqq_perf)

        _, _, is_orb_breakout = detect_orb_high(df_5m)
        is_rsi_bb_extreme = detect_rsi_bb_extreme(df_5m)
        is_obv_accumulation = detect_obv_divergence(df_daily) if not df_daily.empty else False
        is_fundamental_healthy = await check_fundamental_health(ticker)

        fundamental_penalty = 0
        if not is_fundamental_healthy and not bypass_fundamental:
            fundamental_penalty = 40

        vwap = calculate_vwap(df_5m)
        risk_level, wick_ratio = detect_fakeout_risk(df_5m)

        # 💡 마켓트랩 더블 볼린저 밴드 역추세 전략 신호 실시간 계산
        df_bb_signals = calculate_double_bb_reversion_signals(df_5m)
        is_double_bb_buy = float(df_bb_signals['is_double_bb_buy'].iloc[-1]) if not df_bb_signals.empty else 0.0
        is_double_bb_sell = float(df_bb_signals['is_double_bb_sell'].iloc[-1]) if not df_bb_signals.empty else 0.0

        # 💡 [전략 패턴] 전략 팩토리를 통해 실시간 전략 로드 및 채점
        from app.strategies.strategy_factory import get_strategy
        strategy_instance = get_strategy(settings.STRATEGY_TYPE)

        cand = {
            'Close': last_close,
            'Volume': float(df_5m['Volume'].iloc[-1]) if not df_5m.empty else 0.0,
            'VWAP': float(vwap.iloc[-1]) if not vwap.empty and pd.notna(vwap.iloc[-1]) else None,
            'Wick': wick_ratio,
            'is_rsi_bb_extreme': is_rsi_bb_extreme,
            'OBV_divergence': 1.0 if is_obv_accumulation else -1.0,
            'relative_strength': rs,
            'gap_pct': 0.0,
            'rvol': rvol,
            'RVOL': rvol,
            'rs': rs,
            'EMA9': float(ema9.iloc[-1]) if not ema9.empty else 0.0,
            'EMA20': float(ema20.iloc[-1]) if not ema20.empty else 0.0,
            'ema_aligned': ema_aligned,
            'dollar_volume': float(df_5m['Close'].iloc[-1] * df_5m['Volume'].iloc[-1]) if not df_5m.empty else 0.0,
            'is_near_52w_high': False,
            'momentum_candles': False,
            'premarket_gap_pct': 0.0,
            'news_sentiment': 'NEUTRAL',
            'news_sentiment_score': 0.0,
            'is_vcp': False,
            'is_cup': False,
            'is_orb_breakout': is_orb_breakout,
            'risk_level': risk_level,
            'is_double_bb_buy': is_double_bb_buy,
            'is_double_bb_sell': is_double_bb_sell
        }

        if not df_daily.empty and len(df_daily) >= 120:
            daily_ema120 = calculate_ema(df_daily['Close'], 120)
            cand['EMA120'] = float(daily_ema120.iloc[-1]) if not daily_ema120.empty and pd.notna(daily_ema120.iloc[-1]) else None
        else:
            cand['EMA120'] = None

        final_score = strategy_instance.calculate_score(cand, sentiment, is_entry=False)
        final_score -= fundamental_penalty
        final_score = max(0.0, min(float(final_score), 100.0))

        if sentiment == "BULLISH":
            sig_type = "STRONG_BUY" if final_score >= 85 else "BUY" if final_score >= 65 else "WATCH"
        else:
            sig_type = "STRONG_BUY" if final_score >= 95 else "BUY" if final_score >= 75 else "WATCH"

        atr_series = calculate_atr(df_5m, period=14)
        latest_atr = float(atr_series.iloc[-1]) if not atr_series.empty else 0.0
        
        is_smart_exit = detect_smart_exit_signal(df_5m)

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
                "regime_mode": sentiment,
                "Close": last_close,
                "Volume": cand.get('Volume', 0.0),
                "VWAP": cand.get('VWAP', None),
                "RVOL": cand.get('RVOL', 1.0),
                "EMA9": cand.get('EMA9', 0.0),
                "EMA20": cand.get('EMA20', 0.0),
                "EMA120": cand.get('EMA120', None),
                "OBV_divergence": cand.get('OBV_divergence', -1.0),
                "is_double_bb_buy": is_double_bb_buy,
                "is_double_bb_sell": is_double_bb_sell
            }
        }
    except Exception as e:
        logger.error(f"[Scanner] Dedicated analysis failed for {ticker}: {e}", exc_info=True)
        return None
