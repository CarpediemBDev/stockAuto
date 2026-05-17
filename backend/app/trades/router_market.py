from fastapi import APIRouter
import yfinance as yf
import pandas as pd
import asyncio
from app.scanner.scanner import check_market_sentiment
from app.core.response import success_response

router = APIRouter(tags=["Market"])

async def get_ticker_summary(ticker_symbol: str):
    """특정 티커의 현재가와 전일 대비 등락 정보를 가져옵니다."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        # 최근 2일치 데이터를 가져와 등락 계산
        df = await asyncio.to_thread(yf.download, ticker_symbol, period="2d", interval="1d", progress=False)
        if df.empty: return None
        
        # MultiIndex 처리
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        current = float(df['Close'].iloc[-1])
        prev = float(df['Close'].iloc[-2])
        change = current - prev
        change_pct = (change / prev) * 100
        
        return {
            "symbol": ticker_symbol,
            "current": round(current, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2)
        }
    except Exception as e:
        print(f"Error fetching {ticker_symbol} summary: {e}")
        return None

@router.get("/overview")
async def get_market_overview():
    """나스닥, 환율, 시장 심리를 종합하여 반환합니다."""
    # 1. 병렬로 데이터 수집
    sentiment_task = check_market_sentiment()
    nasdaq_task = get_ticker_summary("QQQ") # 나스닥 100 ETF 기준
    fx_task = get_ticker_summary("USDKRW=X") # 달러/원 환율
    
    sentiment, nasdaq, fx = await asyncio.gather(sentiment_task, nasdaq_task, fx_task)
    
    return success_response(data={
        "sentiment": sentiment,
        "nasdaq": nasdaq,
        "exchange_rate": fx,
        "timestamp": pd.Timestamp.now().isoformat()
    })
