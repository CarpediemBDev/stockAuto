from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core import models
from pydantic import BaseModel, ConfigDict
from app.scanner.data_provider import fetch_ohlcv
from app.core.dependencies import get_current_user
from app.watchlist.services import (
    add_watchlist_item,
    delete_watchlist_item,
    get_watchlist_items,
)

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
    return get_watchlist_items(db, current_user)

@router.post("")
async def add_to_watchlist(
    item: WatchListCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return await add_watchlist_item(
        db,
        current_user,
        item.ticker,
        item.ticker_name,
        ticker_validator=fetch_ohlcv,
    )

@router.delete("/{item_id_or_ticker}")
def delete_from_watchlist(
    item_id_or_ticker: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    delete_watchlist_item(db, current_user, item_id_or_ticker)
    return {"message": f"Watchlist item '{item_id_or_ticker}' deleted successfully"}
