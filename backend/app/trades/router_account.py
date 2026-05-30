from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.scanner.data_provider import fetch_ohlcv

from app.core.database import get_db
from app.bot.broker_factory import get_broker_client
from app.core.response import success_response
from app.core.dependencies import get_current_user
from app.core.models import User, Holding, TradeLog, ActionLog
from app.core.config import settings as app_settings

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

@router.post("/reset-balance")
def reset_balance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    [개인투자자 위험 영역] 모의투자(SIMULATED) 모드 잔고 및 매매기록 초기화.
    보유 자산 삭제, 거래 로그 및 활동 로그를 삭제하여 초기 가상 예수금(1,000만 원) 상태로 복원합니다.
    """
    settings = current_user.settings
    if not settings or settings.trade_mode != "SIMULATED":
        raise HTTPException(
            status_code=400, 
            detail="모의투자(SIMULATED) 모드에서만 가상 계좌 자산 초기화가 가능합니다."
        )
    
    try:
        # 해당 사용자의 보유종목, 거래 로그, 행동 로그 일체 삭제
        db.query(Holding).filter(Holding.user_id == current_user.id).delete()
        db.query(TradeLog).filter(TradeLog.user_id == current_user.id).delete()
        db.query(ActionLog).filter(ActionLog.user_id == current_user.id).delete()
        db.commit()
        return success_response(message="가상 모의투자 계좌 자산 및 로그가 성공적으로 초기화되었습니다.")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"계좌 초기화 중 오류가 발생했습니다: {str(e)}")

@router.post("/force-liquidate")
async def force_liquidate(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    [개인투자자 위험 영역] 보유 중인 모든 종목 즉시 시장가 전량 강제 매도 청산.
    현재 보유 중인 모든 종목을 실시간 시장 가격으로 일괄 일시 처분합니다.
    """
    holdings = db.query(Holding).filter(Holding.user_id == current_user.id).all()
    if not holdings:
        return success_response(message="현재 보유 주식이 없어 청산할 주식이 없습니다.")
    
    broker = get_broker_client(current_user.settings)
    liquidated_tickers = []
    
    try:
        for h in holdings:
            # 실시간 청산 가격 조회 (데이터 프로바이더 연동으로 결합도 해제)
            try:
                df = await fetch_ohlcv(h.ticker, interval="1m", period="1d")
                if not df.empty:
                    price = float(df["Close"].iloc[-1])
                else:
                    price = h.highest_price or h.avg_price
            except Exception:
                price = h.highest_price or h.avg_price
            
            # 통합 브로커 규격을 사용해 매도 주문 전송
            res = broker.sell_order(ticker=h.ticker, quantity=h.quantity, price=price)
            
            if res.get("success"):
                filled_price = res.get("filled_price", price)
                filled_qty = res.get("filled_qty", h.quantity)
                order_no = res.get("order_no", "LIQUIDATE_MANUAL")
                
                # 💡 [수수료 정밀 반영] 스케줄러의 자동 매도와 동일한 수수료 공식 적용
                buy_gross = h.avg_price * filled_qty
                buy_fee = buy_gross * app_settings.KIS_FEE_RATE
                sell_gross = filled_price * filled_qty
                sell_fee = sell_gross * app_settings.KIS_FEE_RATE
                sec_fee = sell_gross * app_settings.SEC_FEE_RATE
                
                realized_pnl = sell_gross - buy_gross - buy_fee - sell_fee - sec_fee
                calc_return_rate = (realized_pnl / buy_gross) * 100 if buy_gross > 0 else 0.0
                
                db.add(TradeLog(
                    user_id=current_user.id,
                    ticker=h.ticker,
                    ticker_name=h.ticker_name,
                    trade_type="SELL",
                    price=filled_price,
                    quantity=filled_qty,
                    order_no=order_no,
                    regime_mode="LIQUIDATE",
                    signal_score=0,
                    realized_pnl=round(realized_pnl, 2),
                    return_rate=round(calc_return_rate, 2)
                ))
                db.delete(h)
                liquidated_tickers.append(h.ticker)
                
        db.commit()
            
        return success_response(
            message=f"보유 중인 {len(liquidated_tickers)}개 종목({', '.join(liquidated_tickers)})이 모두 시장가 일괄 청산되었습니다."
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"일괄 청산 과정 중 오류가 발생했습니다: {str(e)}")
