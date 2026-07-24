import asyncio

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
    result = await add_watchlist_item(
        db,
        current_user,
        item.ticker,
        item.ticker_name,
        ticker_validator=fetch_ohlcv,
    )
    from app.core import sse
    # 이 핸들러만 async라 발행이 uvicorn 메인 루프에서 돈다. publish_sync는 동기 소켓을
    # 쓰므로(설계상 의도 — core/sse.py 주석 참조) Redis 지연 시 루프가 소켓 타임아웃
    # (REDIS_SOCKET_TIMEOUT_SECONDS, 기본 2초)만큼 멈출 수 있어 스레드로 격리한다.
    # 동기 핸들러(삭제·봇 토글 등)는 이미 스레드풀에서 돌아 격리가 불필요하다.
    await asyncio.to_thread(sse.notify_watchlist, current_user.id)
    return result

@router.delete("/{item_id_or_ticker}")
def delete_from_watchlist(
    item_id_or_ticker: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    delete_watchlist_item(db, current_user, item_id_or_ticker)
    from app.core import sse
    sse.notify_watchlist(current_user.id)
    return {"message": f"Watchlist item '{item_id_or_ticker}' deleted successfully"}
