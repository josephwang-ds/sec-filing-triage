"""NYSE session clock. Instants are timezone-aware; New York is not a fixed offset."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
SHANGHAI = ZoneInfo("Asia/Shanghai")

# News active window on a New York trading weekday. Early-close days stay inside
# this window; the price job uses the early close itself.
ACTIVE_OPEN = (4, 0)
ACTIVE_CLOSE = (20, 0)


def as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("events require timezone-aware instants")
    return moment.astimezone(UTC)


def in_new_york(moment: datetime) -> datetime:
    return as_utc(moment).astimezone(NY)


def in_shanghai(moment: datetime) -> datetime:
    return as_utc(moment).astimezone(SHANGHAI)


def easter_sunday(year: int) -> date:
    """Anonymous Gregorian computus. Good Friday is two days earlier."""
    century, year_mod = divmod(year, 100)
    epact_century, century_mod = divmod(century, 4)
    lunar_correction = (century + 8) // 25
    century_adjustment = (century - lunar_correction + 1) // 3
    epact = (19 * (year % 19) + century - epact_century - century_adjustment + 15) % 30
    weekday_century, weekday_year = divmod(year_mod, 4)
    weekday = (32 + 2 * century_mod + 2 * weekday_century - epact - weekday_year) % 7
    correction = (year % 19 + 11 * epact + 22 * weekday) // 451
    month, day_index = divmod(epact + weekday - 7 * correction + 114, 31)
    return date(year, month, day_index + 1)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        probe = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        probe = date(year, month + 1, 1) - timedelta(days=1)
    return probe - timedelta(days=(probe.weekday() - weekday) % 7)


def _observed(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def full_holidays(year: int) -> set[date]:
    """NYSE full closures. Saturday/Sunday holidays move to the observed weekday."""
    return {
        _observed(date(year, 1, 1)),
        _nth_weekday(year, 1, 0, 3),
        _nth_weekday(year, 2, 0, 3),
        easter_sunday(year) - timedelta(days=2),
        _last_weekday(year, 5, 0),
        _observed(date(year, 6, 19)),
        _observed(date(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),
        _nth_weekday(year, 11, 3, 4),
        _observed(date(year, 12, 25)),
    }


def early_close_days(year: int) -> set[date]:
    """1:00 p.m. New York closes: July 3, the day after Thanksgiving, Christmas Eve.

    July 3 is included only when the market is actually open. When Independence
    Day is observed on July 3, that day is a full close and is not also an early close.
    """
    holidays = full_holidays(year)
    days: set[date] = set()
    july3 = date(year, 7, 3)
    if july3.weekday() < 5 and july3 not in holidays:
        days.add(july3)
    thanksgiving = _nth_weekday(year, 11, 3, 4)
    black_friday = thanksgiving + timedelta(days=1)
    if black_friday not in holidays:
        days.add(black_friday)
    christmas_eve = date(year, 12, 24)
    if christmas_eve.weekday() < 5 and christmas_eve not in holidays:
        days.add(christmas_eve)
    return days


def is_full_holiday(day: date) -> bool:
    return day in full_holidays(day.year)


def is_trading_day(day: date) -> bool:
    return day.weekday() < 5 and not is_full_holiday(day)


def session_close(day: date) -> datetime | None:
    """Official cash close, or None when the market is shut."""
    if not is_trading_day(day):
        return None
    hour, minute = (13, 0) if day in early_close_days(day.year) else (16, 0)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=NY)


def price_due_at(day: date) -> datetime | None:
    """First price refresh is two hours after that session's close."""
    close = session_close(day)
    if close is None:
        return None
    return close + timedelta(hours=2)


def market_phase(moment: datetime) -> str:
    """active, inactive, holiday, or weekend. Holiday uses the inactive cadence."""
    local = in_new_york(moment)
    if local.weekday() >= 5:
        return "weekend"
    if is_full_holiday(local.date()):
        return "holiday"
    minutes = local.hour * 60 + local.minute
    open_minutes = ACTIVE_OPEN[0] * 60 + ACTIVE_OPEN[1]
    close_minutes = ACTIVE_CLOSE[0] * 60 + ACTIVE_CLOSE[1]
    if open_minutes <= minutes < close_minutes:
        return "active"
    return "inactive"


def latest_due_session(moment: datetime) -> date | None:
    """Latest trading session whose close-plus-two-hours is already in the past.

    A Saturday does not invent a new due session. An early close becomes due at
    15:00 New York, not at the regular 18:00.
    """
    local_day = in_new_york(moment).date()
    now = as_utc(moment)
    for offset in range(14):
        day = local_day - timedelta(days=offset)
        due = price_due_at(day)
        if due is not None and now >= as_utc(due):
            return day
    return None


def next_price_due(moment: datetime) -> datetime:
    """Next close-plus-two-hours strictly after `moment`."""
    now = as_utc(moment)
    start = in_new_york(moment).date()
    for offset in range(14):
        due = price_due_at(start + timedelta(days=offset))
        if due is not None and as_utc(due) > now:
            return as_utc(due)
    raise RuntimeError("no NYSE session within two weeks")


def price_status(last_bar: date | None, moment: datetime) -> str:
    """Current when the latest due session is present. Weekends do not alarm."""
    due = latest_due_session(moment)
    if due is None:
        return "current" if last_bar is not None else "unavailable"
    if last_bar is None:
        return "unavailable"
    if last_bar >= due:
        return "current"
    return "stale"


def format_dual(moment: datetime) -> dict[str, str]:
    """Display an exact instant in New York and Shanghai. Never used for date-only facts."""
    utc = as_utc(moment)
    ny = utc.astimezone(NY)
    sh = utc.astimezone(SHANGHAI)
    return {
        "utc": utc.isoformat(),
        "new_york": ny.strftime("%Y-%m-%d %H:%M %Z"),
        "shanghai": sh.strftime("%Y-%m-%d %H:%M %Z"),
    }
