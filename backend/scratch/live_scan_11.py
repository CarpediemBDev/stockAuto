import asyncio
import pandas as pd
import sys
import os

# 부모 디렉토리를 path에 추가하여 engine 모듈을 불러올 수 있게 합니다.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.scanner import scan_market_expert, get_ticker_name
# pyrefly: ignore [missing-import]
import yfinance as yf

async def live_scan_11():
    # 캡처본에서 추출한 11개 종목
    tickers = ["WOK", "MRNO", "EZGO", "HUBC", "HCWB", "TDIC", "QNRX", "PIII", "ALPH", "EDBL", "NBIZ"]
    
    print(f"--- Running Expert Signal Logic on 11 Tickers (Live Data) ---")
    print(f"Target Universe: {', '.join(tickers)}\n")

    # 기존 scan_market_expert를 활용하되, 시드 종목만 우리가 지정한 11개로 제한하여 분석합니다.
    # 이를 위해 내부 로직의 Stage 1 & 2를 직접 수행합니다.
    
    # 1. 지수 데이터 확보
    df_qqq = await asyncio.to_thread(yf.download, "QQQ", period="2d", interval="15m", progress=False)
    if isinstance(df_qqq.columns, pd.MultiIndex): df_qqq.columns = df_qqq.columns.get_level_values(0)
    qqq_perf = (df_qqq['Close'].iloc[-1] / df_qqq['Close'].iloc[0] - 1) if not df_qqq.empty else 0

    # 2. 분석 시작
    results = []
    
    # 11개 종목 데이터 벌크 다운로드
    data_15m = await asyncio.to_thread(yf.download, tickers, period="5d", interval="15m", group_by="ticker", progress=False)
    data_1m = await asyncio.to_thread(yf.download, tickers, period="2d", interval="1m", group_by="ticker", progress=False)

    from engine.scanner import calculate_vwap, detect_fakeout_risk, calculate_rvol, calculate_ema

    for ticker in tickers:
        try:
            # 15분봉 데이터 (Stage 1)
            df_15 = data_15m[ticker].dropna() if len(tickers) > 1 else data_15m.dropna()
            if df_15.empty: continue
            
            # 지표 계산
            last_close = float(df_15['Close'].iloc[-1])
            prev_close = float(df_15['Close'].iloc[-2])
            gap_pct = (df_15['Open'].iloc[-1] / prev_close - 1) * 100
            rvol = calculate_rvol(df_15)
            
            stock_perf = (last_close / df_15['Close'].iloc[0] - 1)
            rs = (stock_perf - qqq_perf) * 100
            
            ema9 = calculate_ema(df_15['Close'], 9)
            ema20 = calculate_ema(df_15['Close'], 20)
            ema_aligned = ema9.iloc[-1] > ema20.iloc[-1]

            # 1분봉 데이터 (Stage 2)
            df_1 = data_1m[ticker].dropna() if len(tickers) > 1 else data_1m.dropna()
            if df_1.empty: continue
            
            vwap = calculate_vwap(df_1)
            risk_level, wick_ratio = detect_fakeout_risk(df_1)
            
            # 최종 점수 산출 (SIGNAL.md 기준)
            score = 0
            if gap_pct >= 2.0: score += 20
            if rvol >= 1.5: score += 20
            if rs > 0: score += 15
            if ema_aligned: score += 15
            if last_close > vwap.iloc[-1]: score += 20
            if risk_level == "LOW": score += 10
            elif risk_level == "HIGH": score -= 20
            
            results.append({
                "ticker": ticker,
                "name": get_ticker_name(ticker),
                "score": min(score, 100),
                "signal": "STRONG_BUY" if score >= 80 else "BUY" if score >= 60 else "WATCH",
                "price": round(last_close, 2),
                "gap": round(gap_pct, 1),
                "rvol": rvol,
                "rs": round(rs, 1),
                "risk": risk_level,
                "wick": round(wick_ratio, 2)
            })
        except: continue

    # 결과 출력
    results = sorted(results, key=lambda x: -x['score'])
    print(f"{'TICKER':8s} | {'SCORE':5s} | {'SIGNAL':10s} | {'PRICE':7s} | {'GAP%':5s} | {'RVOL':4s} | {'RS':5s} | {'RISK':6s} | {'WICK'}")
    print("-" * 85)
    for r in results:
        print(f"{r['ticker']:8s} | {r['score']:5d} | {r['signal']:10s} | {r['price']:7.2f} | {r['gap']:5.1f} | {r['rvol']:4.1f} | {r['rs']:5.1f} | {r['risk']:6s} | {r['wick']:4.1f}")

if __name__ == "__main__":
    asyncio.run(live_scan_11())
