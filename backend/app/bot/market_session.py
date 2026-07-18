from datetime import datetime, time
from enum import StrEnum
from zoneinfo import ZoneInfo

from app.bot.us_market_calendar import nyse_regular_close

# 미국 동부 표준시(ET)는 DST를 자동으로 반영합니다.
ET = ZoneInfo("America/New_York")


class MarketSession(StrEnum):
    PRE_MARKET = "PRE_MARKET"
    REGULAR = "REGULAR_MARKET"
    AFTER_HOURS = "AFTER_HOURS"
    CLOSED = "CLOSED"


PRE_MARKET_OPEN = time(4, 0)
REGULAR_MARKET_OPEN = time(9, 30)
REGULAR_MARKET_CLOSE = time(16, 0)
EARLY_CLOSE_AFTER_HOURS_END = time(17, 0)
AFTER_HOURS_CLOSE = time(20, 0)

ACTIVE_MARKET_SESSIONS = frozenset(
    {
        MarketSession.PRE_MARKET,
        MarketSession.REGULAR,
        MarketSession.AFTER_HOURS,
    }
)

EXTENDED_MARKET_SESSIONS = frozenset(
    {
        MarketSession.PRE_MARKET,
        MarketSession.AFTER_HOURS,
    }
)


def get_market_session(now_et: datetime | None = None) -> MarketSession:
    """
    현재 시각 기준 미국 주식시장 세션을 반환합니다.
    - PRE_MARKET: 04:00 ~ 09:30 ET
    - REGULAR_MARKET: 09:30 ~ 16:00 ET
    - AFTER_HOURS: 16:00 ~ 20:00 ET
    - CLOSED: 나머지 시간 및 주말
    """
    now_et = now_et or datetime.now(tz=ET)
    if now_et.tzinfo is None:
        now_et = now_et.replace(tzinfo=ET)
    else:
        now_et = now_et.astimezone(ET)

    regular_close = nyse_regular_close(now_et.date())
    if regular_close is None:
        return MarketSession.CLOSED

    current_time = now_et.time()
    after_hours_close = (
        EARLY_CLOSE_AFTER_HOURS_END
        if regular_close.hour == 13
        else AFTER_HOURS_CLOSE
    )

    if PRE_MARKET_OPEN <= current_time < REGULAR_MARKET_OPEN:
        return MarketSession.PRE_MARKET
    if REGULAR_MARKET_OPEN <= current_time < regular_close:
        return MarketSession.REGULAR
    if regular_close <= current_time < after_hours_close:
        return MarketSession.AFTER_HOURS
    return MarketSession.CLOSED
