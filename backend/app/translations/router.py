from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.core import models
from pydantic import BaseModel
from app.translations.translator import Translator
from app.core.response import success_response

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class TranslationCreate(BaseModel):
    ticker: str
    name_ko: str

class TranslationUpdate(BaseModel):
    name_ko: str

@router.get("/")
def get_all_translations(db: Session = Depends(get_db)):
    """현재 DB에 저장된 모든 한글 번역 사전 목록을 조회합니다 (ID 오름차순)."""
    items = db.query(models.StockTranslation).order_by(models.StockTranslation.id.asc()).all()
    return success_response(data=items)

@router.post("/")
def create_or_update_translation(item: TranslationCreate, db: Session = Depends(get_db)):
    """번역쌍을 새로 생성하거나 덮어쓰고 실시간 캐시를 갱신합니다."""
    ticker_upper = item.ticker.upper().strip()
    if not ticker_upper or not item.name_ko.strip():
        raise HTTPException(status_code=400, detail="Ticker and name_ko cannot be empty")
        
    existing = db.query(models.StockTranslation).filter(models.StockTranslation.ticker == ticker_upper).first()
    if existing:
        existing.name_ko = item.name_ko.strip()
    else:
        new_trans = models.StockTranslation(ticker=ticker_upper, name_ko=item.name_ko.strip())
        db.add(new_trans)
    
    db.commit()
    
    # 실시간 메모리 캐시 즉각 동기화
    Translator.update_cache_item(ticker_upper, item.name_ko.strip())
    return success_response(message=f"Successfully saved {ticker_upper} translation.")

@router.put("/{trans_id}")
def update_translation(trans_id: int, item: TranslationUpdate, db: Session = Depends(get_db)):
    """기존 특정 ID의 번역 종목명을 수정하고 메모리 캐시를 동적 싱크합니다."""
    db_item = db.query(models.StockTranslation).filter(models.StockTranslation.id == trans_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Translation record not found")
    
    new_name = item.name_ko.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="name_ko cannot be empty")
        
    db_item.name_ko = new_name
    db.commit()
    
    # 실시간 메모리 캐시 동기화
    Translator.update_cache_item(db_item.ticker, new_name)
    return success_response(message=f"Successfully updated {db_item.ticker} to {new_name}.")

@router.delete("/{trans_id}")
def delete_translation(trans_id: int, db: Session = Depends(get_db)):
    """번역 데이터를 삭제하고 메모리 캐시에서 격리합니다."""
    db_item = db.query(models.StockTranslation).filter(models.StockTranslation.id == trans_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Translation record not found")
    
    ticker_upper = db_item.ticker.upper().strip()
    
    # 캐시 메모리에서 즉각 제거
    if ticker_upper in Translator._cache:
        del Translator._cache[ticker_upper]
        
    db.delete(db_item)
    db.commit()
    return success_response(message=f"Successfully deleted {ticker_upper} translation.")
