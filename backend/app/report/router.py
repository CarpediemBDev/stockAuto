from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.models import User, TradeLog
from app.core.dependencies import get_current_user, get_current_admin_user
from sqlalchemy import asc

from app.core.response import SuccessResponseRoute
router = APIRouter(route_class=SuccessResponseRoute, tags=["Report"])

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
        return {
            "kpi": {
                "total_trades": 0,
                "total_realized_pnl": 0.0,
                "win_rate": 0.0,
                "profit_factor": 0.0
            },
            "chart_data": []
        }

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

    return {
        "kpi": {
            "total_trades": total_trades,
            "total_realized_pnl": round(total_realized_pnl, 2),
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2)
        },
        "chart_data": chart_data
    }

@router.post("/trigger-manual-report")
def trigger_manual_report(current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """
    관리자가 대시보드 화면에서 원할 때 수동으로 관리자 본인의 텔레그램 일일 리포트를 강제 기동합니다. (테스트 목적 격리)
    """
    from fastapi import HTTPException
    from app.core.models import UserSettings
    
    u_settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if not u_settings or not u_settings.telegram_enabled or not u_settings.telegram_chat_id:
        raise HTTPException(status_code=400, detail="텔레그램 연동이 되어있지 않거나 알림이 비활성화 상태입니다. 먼저 개인 설정에서 연동을 완료해주세요.")

    from app.core.telegram import send_daily_report_to_user_sync
    try:
        send_daily_report_to_user_sync(current_user.id)
        return {"message": "관리자 본인 계정의 텔레그램 리포트 발송 요청이 정상적으로 처리되었습니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"수동 결산 리포트 테스트 발송 중 장애 발생: {str(e)}")

@router.post("/trigger-global-report")
def trigger_global_report(current_user: User = Depends(get_current_admin_user)):
    """
    관리자가 대시보드 화면에서 원할 때 수동으로 전체 사용자에게 텔레그램 일일 리포트를 강제 기동합니다.
    """
    from app.core.telegram import send_daily_report_to_all_users_sync
    
    try:
        result = send_daily_report_to_all_users_sync()
        total = result.get("total_enabled_users", 0)
        sent = result.get("sent_count", 0)
        
        return {"message": f"텔레그램 알림 활성 사용자 총 {total}명 중 {sent}명에게 리포트 발송이 완료되었습니다."}
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"수동 전체 리포트 발송 중 장애 발생: {str(e)}")

@router.post("/trigger-personal-report")
def trigger_personal_report(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    사용자가 개인 투자 설정 화면에서 원할 때 수동으로 본인의 텔레그램 일일 리포트를 강제 기동합니다.
    """
    from fastapi import HTTPException
    from app.core.models import UserSettings
    
    u_settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if not u_settings or not u_settings.telegram_enabled or not u_settings.telegram_chat_id:
        raise HTTPException(status_code=400, detail="텔레그램 연동이 되어있지 않거나 알림이 비활성화 상태입니다. 먼저 텔레그램 연동을 완료해주세요.")

    from app.core.telegram import send_daily_report_to_user_sync
    try:
        send_daily_report_to_user_sync(current_user.id)
        return {"message": "본인 성적표 텔레그램 리포트 발송 요청이 처리되었습니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"수동 결산 개인 리포트 발송 중 장애 발생: {str(e)}")
