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

def _resolve_ticker_name(ticker: str, db: Session) -> str:
    """Translator의 메모리 캐시를 확인하고, 없으면 yfinance를 조회한 뒤 DB와 캐시에 자동 동적 학습 적재합니다."""
    ticker_upper = ticker.upper().strip()
    
    # 1. Translator 캐시에서 조회 (0ms)
    korean_name = Translator.translate(ticker_upper, default_name=None)
    if korean_name != ticker_upper:
        return korean_name
        
    # 2. 캐시에 없으면 yfinance로 영문명을 조회하고, 이를 번역 사전에 자동 저장(자가학습)
    try:
        info = yf.Ticker(ticker).info
        fetched_name = info.get("shortName", "") or info.get("longName", "") or ticker_upper
        
        # 새로운 티커와 정식 명칭을 번역 테이블에 등록 및 캐시 동기화
        new_trans = models.StockTranslation(ticker=ticker_upper, name_ko=fetched_name)
        db.add(new_trans)
        db.commit()
        Translator.update_cache_item(ticker_upper, fetched_name)
        
        return fetched_name
    except Exception:
        return ticker_upper

from app.core.response import success_response
from app.core.exceptions import StockAutoException

@router.get("/")
def get_watchlist(db: Session = Depends(get_db)):
    items = db.query(models.WatchList).all()
    return success_response(data=items)

@router.post("/")
def add_to_watchlist(item: WatchListCreate, db: Session = Depends(get_db)):
    ticker_upper = item.ticker.upper().strip()
    
    # 중복 체크
    db_item = db.query(models.WatchList).filter(models.WatchList.ticker == ticker_upper).first()
    if db_item:
        raise StockAutoException(code="WATCHLIST_DUPLICATE", message="이미 관심종목에 등록되어 있습니다.")
    
    # 종목명이 비어있으면 자동 조회
    ticker_name = item.ticker_name
    if not ticker_name or ticker_name.strip() == "":
        ticker_name = _resolve_ticker_name(ticker_upper, db)
    else:
        # 사용자가 수동으로 커스텀 한글명을 지정해서 추가했다면(예: TSLA 테슬라),
        # 이 새로운 번역 매핑을 DB 테이블과 메모리 캐시에 동적으로 동기화하여 자가학습시킵니다!
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

@router.delete("/{ticker}")
def delete_from_watchlist(ticker: str, db: Session = Depends(get_db)):
    db_item = db.query(models.WatchList).filter(models.WatchList.ticker == ticker.upper()).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다.")
    
    db.delete(db_item)
    db.commit()
    return {"message": f"{ticker} deleted successfully"}
