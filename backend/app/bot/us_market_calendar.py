import os
from datetime import date, time, timedelta


REGULAR_CLOSE = time(16, 0)
EARLY_CLOSE = time(13, 0)


def _observed_date(holiday: date) -> date:
    if holiday.weekday() == 5:
        return holiday - timedelta(days=1)
    if holiday.weekday() == 6:
        return holiday + timedelta(days=1)
    return holiday


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    current = date(year, month, 1)
    offset = (weekday - current.weekday()) % 7
    return current + timedelta(days=offset + 7 * (occurrence - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        current = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        current = date(year, month + 1, 1) - timedelta(days=1)
    return current - timedelta(days=(current.weekday() - weekday) % 7)


def _easter_sunday(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _parse_override_dates(env_name: str) -> set[date]:
    values = os.getenv(env_name, "")
    parsed = set()
    for value in values.split(","):
        value = value.strip()
        if value:
            parsed.add(date.fromisoformat(value))
    return parsed


def nyse_holidays(year: int) -> set[date]:
    holidays = {
        _observed_date(date(year, 1, 1)),
        _nth_weekday(year, 1, 0, 3),
        _nth_weekday(year, 2, 0, 3),
        _easter_sunday(year) - timedelta(days=2),
        _last_weekday(year, 5, 0),
        _observed_date(date(year, 6, 19)),
        _observed_date(date(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),
        _nth_weekday(year, 11, 3, 4),
        _observed_date(date(year, 12, 25)),
    }

    next_new_year_observed = _observed_date(date(year + 1, 1, 1))
    if next_new_year_observed.year == year:
        holidays.add(next_new_year_observed)

    return holidays | _parse_override_dates("US_MARKET_CLOSED_DATES")


def nyse_early_closes(year: int) -> set[date]:
    thanksgiving = _nth_weekday(year, 11, 3, 4)
    candidates = {
        thanksgiving + timedelta(days=1),
        date(year, 12, 24),
    }

    independence_day = date(year, 7, 4)
    if independence_day.weekday() in {1, 2, 3, 4}:
        candidates.add(independence_day - timedelta(days=1))

    holidays = nyse_holidays(year)
    standard_early_closes = {
        candidate
        for candidate in candidates
        if candidate.weekday() < 5 and candidate not in holidays
    }
    return standard_early_closes | _parse_override_dates("US_MARKET_EARLY_CLOSE_DATES")


def nyse_regular_close(market_date: date) -> time | None:
    if market_date.weekday() >= 5 or market_date in nyse_holidays(market_date.year):
        return None
    if market_date in nyse_early_closes(market_date.year):
        return EARLY_CLOSE
    return REGULAR_CLOSE
