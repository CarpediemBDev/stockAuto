from sqlalchemy.orm import Session
from app.core.models import WatchList

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
