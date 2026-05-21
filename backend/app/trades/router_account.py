from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.bot.broker_factory import get_broker_client
from app.core.response import success_response
from app.core.dependencies import get_current_user
from app.core.models import User

router = APIRouter(tags=["Account"])

@router.get("/balance")
def get_balance(current_user: User = Depends(get_current_user)):
    """
    현재 로그인한 사용자의 UserSettings에 맞춰 알맞은 증권사 API(또는 로컬 시뮬레이터)를 호출하여
    현재 계좌의 예수금, 주식 평가금, 총자산 및 전체 실시간 수익률 정보를 가져옵니다.
    """
    broker = get_broker_client(current_user.settings)
    balance = broker.get_account_balance()
    return success_response(data=balance)

@router.get("/holdings")
def get_holdings(current_user: User = Depends(get_current_user)):
    """
    현재 로그인한 사용자의 UserSettings에 맞춰 알맞은 증권사 API(또는 로컬 시뮬레이터)를 호출하여
    현재 보유 중인 종목 리스트와 개별 수익률을 가져옵니다.
    """
    broker = get_broker_client(current_user.settings)
    holdings = broker.get_holdings()
    return success_response(data=holdings)
