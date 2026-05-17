from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.bot.kis_api import KISClient
from app.core.database import SessionLocal
from app.core.models import Holding
from app.core.response import success_response

router = APIRouter(tags=["Account"])
kis_client = KISClient()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/balance")
def get_balance():
    """
    한국투자증권 API를 호출하여 현재 계좌의 잔고 및 수익률 정보를 가져옵니다.
    """
    balance = kis_client.get_account_balance()
    return success_response(data=balance)

@router.get("/holdings")
def get_holdings(db: Session = Depends(get_db)):
    """현재 보유 중인 종목 리스트를 반환합니다."""
    holdings = db.query(Holding).all()
    return success_response(data=holdings)
