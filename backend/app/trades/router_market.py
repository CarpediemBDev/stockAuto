from fastapi import APIRouter
import asyncio
import pandas as pd
from app.scanner.data_provider import fetch_ohlcv
from app.scanner.scanner import check_market_sentiment
from app.core.response import success_response

router = APIRouter(tags=["Market"])

async def get_ticker_summary(ticker_symbol: str):
    """특정 티커의 현재가와 전일 대비 등락 정보를 가져옵니다."""
    try:
        # 데이터 프로바이더 연동 (yf.download 결합 해제 및 MultiIndex 파싱 가드 통합)
        df = await fetch_ohlcv(ticker_symbol, interval="1d", period="10d")
        if df.empty: return None

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
    nasdaq_task = get_ticker_summary("^IXIC") # 나스닥 종합 지수 기준
    fx_task = get_ticker_summary("USDKRW=X") # 달러/원 환율
    
    sentiment, nasdaq, fx = await asyncio.gather(sentiment_task, nasdaq_task, fx_task)
    
    return success_response(data={
        "sentiment": sentiment,
        "nasdaq": nasdaq,
        "exchange_rate": fx,
        "timestamp": pd.Timestamp.now().isoformat()
    })
