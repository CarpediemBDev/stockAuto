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

@router.post("/trigger-manual-report")
def trigger_manual_report(current_user: User = Depends(get_current_user)):
    """
    관리자가 대시보드 화면에서 원할 때 수동으로 모든 유저의 텔레그램 일일 리포트를 강제 기동합니다.
    """
    from app.core.telegram import send_daily_report_to_all_users_sync
    try:
        send_daily_report_to_all_users_sync()
        return success_response(message="전체 유저 대상 텔레그램 리포트 발송 요청이 정상적으로 처리되었습니다.")
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"수동 결산 리포트 일괄 발송 중 장애 발생: {str(e)}")

@router.post("/trigger-personal-report")
def trigger_personal_report(current_user: User = Depends(get_current_user)):
    """
    사용자가 개인 투자 설정 화면에서 원할 때 수동으로 본인의 텔레그램 일일 리포트를 강제 기동합니다.
    """
    from app.core.telegram import send_daily_report_to_user_sync
    try:
        send_daily_report_to_user_sync(current_user.id)
        return success_response(message="본인 성적표 텔레그램 리포트 발송 요청이 처리되었습니다.")
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"수동 결산 개인 리포트 발송 중 장애 발생: {str(e)}")
