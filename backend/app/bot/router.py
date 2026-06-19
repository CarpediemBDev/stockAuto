from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.bot.order_reconciler import disable_auto_resume_for_user, has_unresolved_orders
from app.core.database import get_db
from app.core.models import User, UserSettings, utc_now_aware
from app.core.dependencies import get_current_user

from app.core.response import SuccessResponseRoute
router = APIRouter(route_class=SuccessResponseRoute)

@router.get("/status")
def get_bot_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    settings = current_user.settings
    if not settings:
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)
        db.commit()
        db.refresh(settings)

    return {
        "is_running": settings.is_running,
        "updated_at": settings.updated_at,
        "trade_mode": settings.trade_mode,
        "is_real": settings.trade_mode == "REAL",
        "has_unresolved_orders": has_unresolved_orders(db, current_user.id),
    }


@router.post("/start")
def start_bot(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if has_unresolved_orders(db, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="미해결 증권사 주문이 있어 자동매매를 시작할 수 없습니다. 주문 재조정이 완료될 때까지 기다리세요.",
        )
    settings = current_user.settings
    if not settings:
        settings = UserSettings(user_id=current_user.id, is_running=True)
        db.add(settings)
    else:
        settings.is_running = True
        settings.updated_at = utc_now_aware()
    db.commit()
    return {"message": "Bot started", "is_running": True}

@router.post("/stop")
def stop_bot(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    disable_auto_resume_for_user(db, current_user.id)
    settings = current_user.settings
    if not settings:
        settings = UserSettings(user_id=current_user.id, is_running=False)
        db.add(settings)
    else:
        settings.is_running = False
        settings.updated_at = utc_now_aware()
    db.commit()
    return {"message": "Bot stopped", "is_running": False}
