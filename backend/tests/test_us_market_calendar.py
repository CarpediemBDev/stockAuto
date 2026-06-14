from datetime import datetime
from zoneinfo import ZoneInfo

from app.bot.scheduler import get_market_session
from app.bot.market_session import MarketSession


ET = ZoneInfo("America/New_York")


def market_time(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=ET)


def test_nyse_holiday_is_closed():
    assert get_market_session(market_time(2026, 7, 3, 10)) is MarketSession.CLOSED


def test_nyse_early_close_switches_to_after_hours_at_one_pm():
    assert get_market_session(market_time(2026, 11, 27, 12, 59)) is MarketSession.REGULAR
    assert get_market_session(market_time(2026, 11, 27, 13, 0)) is MarketSession.AFTER_HOURS
    assert get_market_session(market_time(2026, 11, 27, 17, 0)) is MarketSession.CLOSED


def test_regular_trading_day_keeps_normal_hours():
    assert get_market_session(market_time(2026, 6, 8, 9, 29)) is MarketSession.PRE_MARKET
    assert get_market_session(market_time(2026, 6, 8, 9, 30)) is MarketSession.REGULAR
    assert get_market_session(market_time(2026, 6, 8, 16, 0)) is MarketSession.AFTER_HOURS
