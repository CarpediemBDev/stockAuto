import asyncio
import pandas as pd
# pyrefly: ignore [missing-import]
import yfinance as yf
import sys
import os

# 부모 디렉토리를 path에 추가하여 engine 모듈을 불러올 수 있게 합니다.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.scanner import calculate_vwap, calculate_wick_ratio, detect_fakeout_risk, calculate_rvol

async def backtest_tdic():
    ticker = "TDIC" # Dreamland (Example ticker from SIGNAL.md)
    print(f"--- Backtesting {ticker} (Dreamland Case) ---")
    
    # 1. 데이터 다운로드 (5월 12일 ~ 14일, 1분봉)
    # yfinance에서 1분봉은 최근 7일 내에서만 조회가 가능하므로, 
    # 만약 현재 날짜가 5월 중순이 아니라면 시뮬레이션용 데이터를 생성하거나 
    # 최근 급등주 사례로 대체해야 할 수도 있습니다.
    
    start_date = "2026-05-12"
    end_date = "2026-05-15"
    
    print(f"Fetching 1m data for {ticker} from {start_date} to {end_date}...")
    df = yf.download(ticker, start=start_date, end=end_date, interval="1m")
    
    if df.empty:
        print(f"[Error] No data found for {ticker}. It might be too old for 1m interval or ticker is wrong.")
        # 데이터가 없을 경우 가상의 시나리오 데이터를 만들어 테스트합니다.
        print("Creating mock data for testing logic...")
        df = create_mock_tdic_data()
    else:
        # MultiIndex 처리 (yf.download 결과가 MultiIndex일 수 있음)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

    # 2. 지표 계산
    df['VWAP'] = calculate_vwap(df)
    df['WickRatio'] = calculate_wick_ratio(df)
    
    # 3. 시그널 검증 루프
    print(f"{'Time':19s} | {'Price':7s} | {'VWAP':7s} | {'Wick%':5s} | {'Risk':6s} | {'Action'}")
    print("-" * 75)
    
    for i in range(20, len(df)):
        sub_df = df.iloc[:i+1]
        
        # scalars로 변환하여 비교 오류 방지
        price = float(sub_df['Close'].iloc[-1])
        vwap = float(sub_df['VWAP'].iloc[-1])
        wick = float(sub_df['WickRatio'].iloc[-1])
        prev_price = float(sub_df['Close'].iloc[-2]) if len(sub_df) > 1 else price
        prev_vwap = float(sub_df['VWAP'].iloc[-2]) if len(sub_df) > 1 else vwap
        
        risk, _ = detect_fakeout_risk(sub_df)
        
        action = ""
        # 매수 시그널 예시 (Price > VWAP AND low wick)
        if price > vwap and wick < 0.2 and prev_price <= prev_vwap:
            action = "BUY SIGNAL (Breakout)"
        elif price > vwap and wick < 0.2:
            action = "TRENDING"
        # 매도/탈출 시그널 예시 (Wick > 0.5 OR Price < VWAP)
        elif wick > 0.5:
            action = "FAKEOUT DANGER (Sell)"
        elif price < vwap and prev_price >= prev_vwap:
            action = "VWAP BREAKDOWN (Exit)"
            
        if action:
            time_str = str(sub_df.index[-1])[:19]
            print(f"{time_str} | {price:7.2f} | {vwap:7.2f} | {wick*100:4.1f}% | {risk:6s} | {action}")

def create_mock_tdic_data():
    """테스트를 위한 가상 급등/급락 데이터를 생성합니다."""
    times = pd.date_range("2026-05-12 09:30", periods=100, freq="1min")
    data = {
        "Open": [10.0] * 100,
        "High": [10.5] * 100,
        "Low": [9.9] * 100,
        "Close": [10.2] * 100,
        "Volume": [1000] * 100
    }
    mock_df = pd.DataFrame(data, index=times)
    
    # 급등 구간 (RVOL 폭발, Price > VWAP)
    for i in range(30, 50):
        mock_df.iloc[i, 3] = 10.2 + (i-30) * 0.5 # Close 상승
        mock_df.iloc[i, 1] = mock_df.iloc[i, 3] + 0.1 # High
        mock_df.iloc[i, 4] = 10000 # Volume 폭발
        
    # 가짜 돌파 구간 (윗꼬리 폭발)
    mock_df.iloc[60, 1] = 25.0 # High가 매우 높음
    mock_df.iloc[60, 3] = 18.0 # Close는 낮음 -> 윗꼬리 발생
    
    # 하향 돌파 구간
    for i in range(70, 90):
        mock_df.iloc[i, 3] = mock_df.iloc[i-1, 3] - 1.0
        
    return mock_df

if __name__ == "__main__":
    asyncio.run(backtest_tdic())
