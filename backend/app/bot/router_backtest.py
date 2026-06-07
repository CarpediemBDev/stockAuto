from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from datetime import datetime
from app.core.dependencies import get_current_user
from app.core.models import User
from app.bot.backtest_engine import BacktestSimulator

router = APIRouter()

class BacktestRequest(BaseModel):
    tickers: List[str] = Field(..., description="백테스트 대상 티커 리스트", example=["TSLA", "NVDA", "AAPL"])
    start_date: str = Field(..., description="시작일 (YYYY-MM-DD)", example="2026-04-01")
    end_date: str = Field(..., description="종료일 (YYYY-MM-DD)", example="2026-05-30")
    interval: Literal["15m", "1h", "1d"] = Field("1h", description="차트 분봉 인터벌 (15m, 1h, 1d)", example="1h")
    initial_cash: Optional[float] = Field(10000.0, description="가상 투자 예수금 (USD)", example=10000.0)

@router.post("/run")
async def run_backtest(
    req: BacktestRequest,
    current_user: User = Depends(get_current_user)
):
    """
    역사적 백테스팅 엔진을 구동하여 퀀트 투자 성적표를 반환합니다.
    """
    tickers_list = [t.strip().upper() for t in req.tickers if t.strip()]
    if not tickers_list:
        raise HTTPException(status_code=400, detail="유효한 티커가 입력되지 않았습니다.")
        
    try:
        # 시뮬레이터 객체 생성 및 구동
        sim = BacktestSimulator(
            tickers=tickers_list,
            start_date=req.start_date,
            end_date=req.end_date,
            interval=req.interval,
            initial_cash=req.initial_cash
        )
        
        await sim.prepare_data()
        
        if not sim.tickers_data:
            raise HTTPException(
                status_code=400, 
                detail="지정된 기간 내에 데이터가 존재하는 종목이 없습니다."
            )
            
        report = sim.run()
        
        if "error" in report:
            raise HTTPException(status_code=500, detail=report["error"])
            
        # JSON 직렬화를 위해 datetime 객체들을 문자열 포맷팅
        formatted_trade_logs = []
        for log in report["trade_logs"]:
            formatted_log = dict(log)
            if isinstance(log["timestamp"], datetime):
                formatted_log["timestamp"] = log["timestamp"].isoformat()
            formatted_trade_logs.append(formatted_log)
            
        formatted_equity_curve = []
        for eq in report["equity_curve"]:
            formatted_eq = dict(eq)
            if isinstance(eq["timestamp"], datetime):
                formatted_eq["timestamp"] = eq["timestamp"].isoformat()
            formatted_equity_curve.append(formatted_eq)
            
        return {
            "initial_cash": report["initial_cash"],
            "final_value": report["final_value"],
            "total_pnl": report["total_pnl"],
            "total_return_rate": report["total_return_rate"],
            "mdd": report["mdd"],
            "total_trades": report["total_trades"],
            "win_rate": report["win_rate"],
            "profit_factor": report["profit_factor"],
            "qqq_bench_return_rate": report["qqq_bench_return_rate"],
            "trade_logs": formatted_trade_logs,
            "equity_curve": formatted_equity_curve
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        raise HTTPException(
            status_code=500, 
            detail=f"백테스팅 중 오류가 발생했습니다: {str(e)}\n{traceback.format_exc()}"
        )
