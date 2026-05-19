from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.core import models
from pydantic import BaseModel
from typing import List
import yfinance as yf

router = APIRouter()

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class WatchListCreate(BaseModel):
    ticker: str
    ticker_name: str = None

class WatchListResponse(BaseModel):
    id: int
    ticker: str
    ticker_name: str = None
    
    class Config:
        from_attributes = True

from app.translations.translator import Translator

from app.core.response import success_response
from app.core.exceptions import StockAutoException

@router.get("/")
def get_watchlist(db: Session = Depends(get_db)):
    items = db.query(models.WatchList).all()
    return success_response(data=items)

@router.post("/")
def add_to_watchlist(item: WatchListCreate, db: Session = Depends(get_db)):
    ticker_upper = item.ticker.upper().strip()
    
    # 1. 영문 알파벳, 점, 하이픈만 포함하는지 정규식 검증
    import re
    if not re.match(r"^[A-Z.\-]+$", ticker_upper):
        raise StockAutoException(code="INVALID_TICKER", message="올바른 영문 나스닥 티커를 입력해 주세요. (예: AAPL, TSLA)")
        
    # 중복 체크
    db_item = db.query(models.WatchList).filter(models.WatchList.ticker == ticker_upper).first()
    if db_item:
        raise StockAutoException(code="WATCHLIST_DUPLICATE", message="이미 관심종목에 등록되어 있습니다.")
        
    # 2. 한글명 결정 및 자동 번역 캐시 학습 연동
    ticker_name = item.ticker_name
    
    # 만약 사용자가 수동 입력을 하지 않았거나 티커와 동일하게 보냈다면 자동 번역 미들웨어 가동
    if not ticker_name or ticker_name.strip() == "" or ticker_name.upper() == ticker_upper:
        # 번역기 작동 (이 과정에서 상장 여부 검증 및 실시간 AI 번역 + 자가학습 캐싱이 한 번에 가동됩니다!)
        resolved_name = Translator.translate(ticker_upper, default_name=None, db=db)
        if resolved_name == ticker_upper:
            # yfinance 등에서 상장 정보를 찾지 못한 경우 (가짜 영문 티커 예: CHITAH)
            raise StockAutoException(code="TICKER_NOT_FOUND", message=f"나스닥 시장에 존재하지 않거나 정보를 찾을 수 없는 티커입니다: {ticker_upper}")
        ticker_name = resolved_name
    else:
        # 사용자가 수동으로 커스텀 한글명을 주입한 경우 (예: AAPL 애플)
        # 실제 존재하는 주식인지 yfinance로 검증
        try:
            ticker_obj = yf.Ticker(ticker_upper)
            info = ticker_obj.info
            if not info or "symbol" not in info or not info.get("symbol"):
                raise StockAutoException(code="TICKER_NOT_FOUND", message=f"나스닥 시장에 존재하지 않는 티커입니다: {ticker_upper}")
        except StockAutoException:
            raise
        except Exception as e:
            raise StockAutoException(code="TICKER_VALIDATION_FAILED", message=f"티커 검증 중 오류가 발생했습니다: {str(e)}")
            
        # 해당 커스텀 한글명을 번역 사전에 자동 동기화하여 자가학습시킵니다!
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
        ticker=ticker_upper,
        ticker_name=ticker_name
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return success_response(data=new_item)

@router.delete("/{item_id_or_ticker}")
def delete_from_watchlist(item_id_or_ticker: str, db: Session = Depends(get_db)):
    # 1. 숫자인 경우 데이터베이스 ID로 조회 (프론트엔드 호환성 100% 확보)
    if item_id_or_ticker.isdigit():
        db_item = db.query(models.WatchList).filter(models.WatchList.id == int(item_id_or_ticker)).first()
    else:
        # 2. 문자열인 경우 영문 티커명으로 조회
        db_item = db.query(models.WatchList).filter(models.WatchList.ticker == item_id_or_ticker.upper()).first()
        
    if not db_item:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다.")
    
    db.delete(db_item)
    db.commit()
    return {"message": f"Watchlist item '{item_id_or_ticker}' deleted successfully"}
