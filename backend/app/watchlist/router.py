from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core import models
from pydantic import BaseModel, ConfigDict
from app.scanner.data_provider import fetch_ohlcv
import re

from app.translations.translator import Translator
from app.core.response import success_response
from app.core.exceptions import StockAutoException
from app.core.dependencies import get_current_user

from app.core.response import SuccessResponseRoute
router = APIRouter(route_class=SuccessResponseRoute)

class WatchListCreate(BaseModel):
    ticker: str
    ticker_name: str = None

class WatchListResponse(BaseModel):
    id: int
    ticker: str
    ticker_name: str = None

    model_config = ConfigDict(from_attributes=True)

@router.get("")
def get_watchlist(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    items = db.query(models.WatchList).filter(models.WatchList.user_id == current_user.id).all()
    return success_response(data=items)

@router.post("")
async def add_to_watchlist(
    item: WatchListCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    ticker_upper = item.ticker.upper().strip()
    
    # 1. 영문 나스닥 티커 검증
    if not re.match(r"^[A-Z.\-]+$", ticker_upper):
        raise StockAutoException(code="INVALID_TICKER", message="올바른 영문 나스닥 티커를 입력해 주세요. (예: AAPL, TSLA)")
        
    # 중복 체크 (사용자별 격리)
    db_item = db.query(models.WatchList).filter(
        models.WatchList.user_id == current_user.id,
        models.WatchList.ticker == ticker_upper
    ).first()
    if db_item:
        raise StockAutoException(code="WATCHLIST_DUPLICATE", message="이미 관심종목에 등록되어 있습니다.")
        
    ticker_name = item.ticker_name
    
    if not ticker_name or ticker_name.strip() == "" or ticker_name.upper() == ticker_upper:
        resolved_name = Translator.translate(ticker_upper, default_name=None, db=db)
        if resolved_name == ticker_upper:
            raise StockAutoException(code="TICKER_NOT_FOUND", message=f"나스닥 시장에 존재하지 않거나 정보를 찾을 수 없는 티커입니다: {ticker_upper}")
        ticker_name = resolved_name
    else:
        try:
            # 데이터 프로바이더 연동으로 강결합 해제 및 비동기 검증 완료
            df = await fetch_ohlcv(ticker_upper, interval="1d", period="1d")
            if df.empty:
                raise StockAutoException(code="TICKER_NOT_FOUND", message=f"나스닥 시장에 존재하지 않는 티커입니다: {ticker_upper}")
        except StockAutoException:
            raise
        except Exception as e:
            raise StockAutoException(code="TICKER_VALIDATION_FAILED", message=f"티커 검증 중 오류가 발생했습니다: {str(e)}")
            
        try:
            existing_trans = db.query(models.StockTranslation).filter(models.StockTranslation.ticker == ticker_upper).first()
            if existing_trans:
                existing_trans.name_ko = ticker_name
            else:
                new_trans = models.StockTranslation(ticker=ticker_upper, name_ko=ticker_name)
                db.add(new_trans)
            db.commit()
            Translator.update_cache_item(ticker_upper, ticker_name)
        except Exception as e:
            print(f"[i18n] Failed to save custom translation to DB: {e}")
    
    new_item = models.WatchList(
        user_id=current_user.id,
        ticker=ticker_upper,
        ticker_name=ticker_name
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return success_response(data=new_item)

@router.delete("/{item_id_or_ticker}")
def delete_from_watchlist(
    item_id_or_ticker: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if item_id_or_ticker.isdigit():
        db_item = db.query(models.WatchList).filter(
            models.WatchList.user_id == current_user.id,
            models.WatchList.id == int(item_id_or_ticker)
        ).first()
    else:
        db_item = db.query(models.WatchList).filter(
            models.WatchList.user_id == current_user.id,
            models.WatchList.ticker == item_id_or_ticker.upper()
        ).first()
        
    if not db_item:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다.")
    
    db.delete(db_item)
    db.commit()
    return {"message": f"Watchlist item '{item_id_or_ticker}' deleted successfully"}
