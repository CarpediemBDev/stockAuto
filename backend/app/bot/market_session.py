from datetime import time
from enum import StrEnum


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
