import re
from collections.abc import Callable, Awaitable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.exceptions import StockAutoException
from app.core.models import StockTranslation, User, WatchList
from app.scanner.data_provider import fetch_ohlcv
from app.translations.translator import Translator


TickerValidator = Callable[..., Awaitable[object]]


def get_watchlist_items(db: Session, user: User) -> list[WatchList]:
    return db.query(WatchList).filter(WatchList.user_id == user.id).all()


async def add_watchlist_item(
    db: Session,
    user: User,
    ticker: str,
    ticker_name: str | None = None,
    ticker_validator: TickerValidator = fetch_ohlcv,
) -> WatchList:
    ticker_upper = ticker.upper().strip()

    if not re.match(r"^[A-Z.\-]+$", ticker_upper):
        raise StockAutoException(
            code="INVALID_TICKER",
            message="올바른 영문 나스닥 티커를 입력해 주세요. (예: AAPL, TSLA)",
        )

    existing_item = (
        db.query(WatchList)
        .filter(WatchList.user_id == user.id, WatchList.ticker == ticker_upper)
        .first()
    )
    if existing_item:
        raise StockAutoException(
            code="WATCHLIST_DUPLICATE",
            message="이미 관심종목에 등록되어 있습니다.",
        )

    resolved_ticker_name = ticker_name
    if (
        not resolved_ticker_name
        or resolved_ticker_name.strip() == ""
        or resolved_ticker_name.upper() == ticker_upper
    ):
        translated_name = Translator.translate(ticker_upper, default_name=None, db=db)
        if translated_name == ticker_upper:
            raise StockAutoException(
                code="TICKER_NOT_FOUND",
                message=f"나스닥 시장에 존재하지 않거나 정보를 찾을 수 없는 티커입니다: {ticker_upper}",
            )
        resolved_ticker_name = translated_name
    else:
        try:
            df = await ticker_validator(ticker_upper, interval="1d", period="1d")
            if df.empty:
                raise StockAutoException(
                    code="TICKER_NOT_FOUND",
                    message=f"나스닥 시장에 존재하지 않는 티커입니다: {ticker_upper}",
                )
        except StockAutoException:
            raise
        except Exception as exc:
            raise StockAutoException(
                code="TICKER_VALIDATION_FAILED",
                message=f"티커 검증 중 오류가 발생했습니다: {str(exc)}",
            ) from exc

        try:
            existing_translation = (
                db.query(StockTranslation)
                .filter(StockTranslation.ticker == ticker_upper)
                .first()
            )
            if existing_translation:
                existing_translation.name_ko = resolved_ticker_name
            else:
                db.add(
                    StockTranslation(
                        ticker=ticker_upper,
                        name_ko=resolved_ticker_name,
                    )
                )
            db.commit()
            Translator.update_cache_item(ticker_upper, resolved_ticker_name)
        except Exception as exc:
            db.rollback()
            print(f"[i18n] Failed to save custom translation to DB: {exc}")

    new_item = WatchList(
        user_id=user.id,
        ticker=ticker_upper,
        ticker_name=resolved_ticker_name,
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item


def delete_watchlist_item(db: Session, user: User, item_id_or_ticker: str) -> None:
    lookup_value = item_id_or_ticker.strip()
    if lookup_value.isdigit():
        db_item = (
            db.query(WatchList)
            .filter(WatchList.user_id == user.id, WatchList.id == int(lookup_value))
            .first()
        )
    else:
        db_item = (
            db.query(WatchList)
            .filter(WatchList.user_id == user.id, WatchList.ticker == lookup_value.upper())
            .first()
        )

    if not db_item:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다.")

    db.delete(db_item)
    db.commit()

def load_watchlist_tickers_by_user(db: Session, user_ids: list[int]) -> dict[int, set[str]]:
    """사용자 ID 리스트를 받아 각 사용자별 관심종목 티커 셋을 반환합니다."""
    watchlists = {user_id: set() for user_id in user_ids}
    if not user_ids:
        return watchlists

    rows = db.query(WatchList.user_id, WatchList.ticker).filter(
        WatchList.user_id.in_(user_ids)
    ).all()
    for user_id, raw_ticker in rows:
        ticker = (raw_ticker or "").strip().upper()
        if ticker and user_id in watchlists:
            watchlists[user_id].add(ticker)
    return watchlists


def load_all_watchlist_tickers_by_user(db: Session) -> dict[int, set[str]]:
    """시스템 내 모든 사용자의 관심종목 티커 셋을 반환합니다."""
    watchlists: dict[int, set[str]] = {}
    rows = db.query(WatchList.user_id, WatchList.ticker).all()
    for user_id, raw_ticker in rows:
        ticker = (raw_ticker or "").strip().upper()
        if ticker:
            watchlists.setdefault(user_id, set()).add(ticker)
    return watchlists
