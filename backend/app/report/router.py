from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.models import User, TradeLog
from app.core.dependencies import get_current_user
from app.core.response import success_response
from sqlalchemy import asc

router = APIRouter(tags=["Report"])

@router.get("/stats")
def get_report_stats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    현재 사용자의 트레이딩 성적표 통계 데이터를 반환합니다.
    """
    sell_logs = db.query(TradeLog).filter(
        TradeLog.user_id == current_user.id,
        TradeLog.trade_type == "SELL",
        TradeLog.realized_pnl.isnot(None)
    ).order_by(asc(TradeLog.executed_at)).all()
    
    total_trades = len(sell_logs)
    if total_trades == 0:
        return success_response(data={
            "kpi": {
                "total_trades": 0,
                "total_realized_pnl": 0.0,
                "win_rate": 0.0,
                "profit_factor": 0.0
            },
            "chart_data": []
        })

    total_realized_pnl = 0.0
    win_trades = 0
    gross_profit = 0.0
    gross_loss = 0.0
    
    chart_data = []
    
    # 누적 수익금 계산 및 타임라인 데이터 구성
    for log in sell_logs:
        pnl = float(log.realized_pnl)
        total_realized_pnl += pnl
        
        if pnl > 0:
            win_trades += 1
            gross_profit += pnl
        elif pnl < 0:
            gross_loss += abs(pnl)
            
        chart_data.append({
            "id": log.id,
            "date": log.executed_at.strftime("%Y-%m-%d"),
            "time": log.executed_at.strftime("%H:%M:%S"),
            "ticker": log.ticker,
            "ticker_name": log.ticker_name,
            "realized_pnl": round(pnl, 2),
            "return_rate": round(float(log.return_rate or 0), 2),
            "cumulative_pnl": round(total_realized_pnl, 2)
        })
        
    win_rate = (win_trades / total_trades) * 100.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)
    
    return success_response(data={
        "kpi": {
            "total_trades": total_trades,
            "total_realized_pnl": round(total_realized_pnl, 2),
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2)
        },
        "chart_data": chart_data
    })
