"""One cadence table for the scheduler, the health check, and the company page.

Intervals are targets. GitHub's scheduler can delay or skip a run, so a missed
window is a health fact rather than a promise that a check occurred.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from company_lens.events.calendar import NY, as_utc, in_new_york, market_phase, next_price_due

DATASETS = (
    "news",
    "sec_index",
    "filing_parse",
    "company_facts",
    "future_events",
    "prices",
    "full_recompute",
    "health",
)

# Service coverage, not a reader's browser watchlist. Twenty names is the cap.
HIGH_FREQUENCY_TICKERS = (
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
    "AVGO",
    "JPM",
    "V",
    "UNH",
    "XOM",
    "LLY",
    "JNJ",
    "MA",
    "COST",
    "HD",
    "PG",
    "BAC",
    "WMT",
)
HIGH_FREQUENCY_LIMIT = 20

# Ordinary news and SEC index: twice each New York day.
ORDINARY_CLOCKS = (time(8, 0), time(18, 0))
FACTS_CLOCK = time(6, 30)
RECOMPUTE_CLOCK = time(7, 0)
FUTURE_CLOCK = time(6, 0)

NEWS_COLD_DAYS = 7
SEC_COLD_DAYS = 90
NEWS_OVERLAP = timedelta(hours=24)
SEC_OVERLAP = timedelta(hours=24)

# More than two missed due windows is degraded; more than four is critical.
DEGRADED_AFTER = 2
CRITICAL_AFTER = 4


@dataclass(frozen=True)
class FrequencyBoost:
    """A temporary faster cadence. `until` is exclusive and is not renewed here."""

    dataset: str
    until: datetime
    interval: timedelta

    def covers(self, dataset: str, moment: datetime) -> bool:
        return self.dataset == dataset and as_utc(moment) < as_utc(self.until)


def boost_for_confirmed_event(
    dataset: str,
    event_at: datetime,
    *,
    confirmed: bool,
    now: datetime,
) -> FrequencyBoost | None:
    """Confirmed events can run faster for a bounded window. Estimates never do."""
    if not confirmed:
        return None
    event_at = as_utc(event_at)
    now = as_utc(now)
    if dataset == "news":
        until = event_at + timedelta(hours=2)
        if now >= until or now < event_at - timedelta(hours=2):
            return None
        return FrequencyBoost("news", until, timedelta(minutes=15))
    if dataset == "sec_index":
        until = event_at + timedelta(hours=6)
        if now >= until or now < event_at:
            return None
        return FrequencyBoost("sec_index", until, timedelta(minutes=30))
    return None


def coverage_tier(ticker: str, supported: set[str] | frozenset[str]) -> str:
    """High frequency only for the fixed list, and only when the universe supports it."""
    symbol = ticker.strip().upper()
    if symbol not in supported:
        return "unsupported"
    if symbol in HIGH_FREQUENCY_TICKERS:
        return "high_frequency"
    return "ordinary"


def select_targets(
    supported: set[str] | frozenset[str],
    tier: str,
    watchlist: list[str] | tuple[str, ...] = (),
) -> tuple[list[str], list[str]]:
    """Return fetch targets and the watchlist names that were not added.

    A browser watchlist must not enlarge the paid fetch set.
    """
    if tier == "high_frequency":
        wanted = HIGH_FREQUENCY_TICKERS
    elif tier == "ordinary":
        wanted = tuple(sorted(symbol for symbol in supported if symbol not in HIGH_FREQUENCY_TICKERS))
    elif tier == "supported":
        wanted = tuple(sorted(supported))
    else:
        raise ValueError(f"unknown coverage tier {tier}")
    targets = [symbol for symbol in wanted if coverage_tier(symbol, supported) != "unsupported"]
    if tier == "ordinary":
        targets = [symbol for symbol in targets if coverage_tier(symbol, supported) == "ordinary"]
    ignored = [
        symbol.strip().upper()
        for symbol in watchlist
        if symbol.strip() and symbol.strip().upper() not in targets
    ]
    return targets, ignored


def tier_copy(tier: str) -> dict[str, str]:
    if tier == "high_frequency":
        return {"en": "High-frequency coverage", "zh": "高频覆盖"}
    if tier == "ordinary":
        return {"en": "Standard coverage", "zh": "普通覆盖"}
    return {"en": "Outside the fetch set", "zh": "不在抓取范围"}


def interval_at(
    dataset: str,
    tier: str,
    moment: datetime,
    *,
    boost: FrequencyBoost | None = None,
    quota_degraded: bool = False,
) -> timedelta | None:
    """Return a relative interval, or None when the dataset uses a clock time."""
    if dataset == "health":
        return timedelta(minutes=15)
    if dataset == "prices":
        return None
    if boost is not None and boost.covers(dataset, moment):
        return boost.interval
    phase = market_phase(moment)
    if dataset == "news":
        if quota_degraded or tier != "high_frequency":
            return None
        if phase == "active":
            return timedelta(minutes=30)
        if phase == "weekend":
            return timedelta(hours=4)
        return timedelta(hours=2)
    if dataset == "sec_index":
        if tier != "high_frequency":
            return None
        if phase == "active":
            return timedelta(hours=2)
        return timedelta(hours=6)
    if dataset == "future_events" and boost is not None and boost.covers(dataset, moment):
        return boost.interval
    return None


def _next_clock(after: datetime, clocks: tuple[time, ...]) -> datetime:
    local = in_new_york(after)
    for clock in clocks:
        candidate = datetime.combine(local.date(), clock, tzinfo=NY)
        if as_utc(candidate) > as_utc(after):
            return as_utc(candidate)
    tomorrow = local.date() + timedelta(days=1)
    return as_utc(datetime.combine(tomorrow, clocks[0], tzinfo=NY))


def next_check(
    dataset: str,
    tier: str,
    after: datetime,
    *,
    boost: FrequencyBoost | None = None,
    quota_degraded: bool = False,
) -> datetime:
    """The next time this dataset should run, strictly after `after`."""
    after = as_utc(after)
    if dataset == "prices":
        return next_price_due(after)
    if dataset == "company_facts":
        return _next_clock(after, (FACTS_CLOCK,))
    if dataset == "full_recompute":
        return _next_clock(after, (RECOMPUTE_CLOCK,))
    if dataset == "future_events":
        within = boost is not None and boost.covers("future_events", after)
        if within:
            return after + timedelta(hours=6)
        return _next_clock(after, (FUTURE_CLOCK,))
    if dataset == "filing_parse":
        # Queued when a new accession is discovered; the due policy is "next pass".
        return after + timedelta(minutes=30)
    step = interval_at(
        dataset, tier, after, boost=boost, quota_degraded=quota_degraded
    )
    if step is None:
        return _next_clock(after, ORDINARY_CLOCKS)
    return after + step


def missed_windows(
    dataset: str,
    tier: str,
    last_success: datetime | None,
    now: datetime,
    *,
    boost: FrequencyBoost | None = None,
    quota_degraded: bool = False,
) -> int | None:
    """How many due times passed with no success. None means the job has never succeeded."""
    if last_success is None:
        return None
    cursor = as_utc(last_success)
    now = as_utc(now)
    missed = 0
    while missed < 1000:
        due = next_check(
            dataset, tier, cursor, boost=boost, quota_degraded=quota_degraded
        )
        if due > now:
            break
        missed += 1
        cursor = due
    return missed


def freshness_level(missed: int | None, *, failed: bool, disabled: bool) -> str:
    if disabled:
        return "disabled"
    if missed is None:
        return "unavailable"
    if missed > CRITICAL_AFTER:
        return "critical"
    if missed > DEGRADED_AFTER or failed:
        return "degraded" if missed > DEGRADED_AFTER else "stale"
    return "current"


def count_checks(
    dataset: str,
    tier: str,
    start: datetime,
    end: datetime,
    *,
    quota_degraded: bool = False,
) -> int:
    """Count due instants in (start, end]. Used for the cost estimate, not a bill."""
    cursor = as_utc(start)
    end = as_utc(end)
    count = 0
    while count < 100_000:
        due = next_check(dataset, tier, cursor, quota_degraded=quota_degraded)
        if due > end:
            break
        count += 1
        cursor = due
    return count


def monthly_request_estimate(
    *,
    ordinary_companies: int,
    year: int = 2026,
    month: int = 10,
) -> dict[str, int | str]:
    """Request counts if every due check makes one provider call. Not an invoice."""
    start = datetime(year, month, 1, tzinfo=UTC)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=UTC) - timedelta(seconds=1)
    else:
        end = datetime(year, month + 1, 1, tzinfo=UTC) - timedelta(seconds=1)
    high_news = count_checks("news", "high_frequency", start, end)
    high_sec = count_checks("sec_index", "high_frequency", start, end)
    ordinary_news = count_checks("news", "ordinary", start, end)
    ordinary_sec = count_checks("sec_index", "ordinary", start, end)
    return {
        "high_frequency_companies": len(HIGH_FREQUENCY_TICKERS),
        "ordinary_companies": ordinary_companies,
        "news_requests": high_news * len(HIGH_FREQUENCY_TICKERS) + ordinary_news * ordinary_companies,
        "sec_index_requests": high_sec * len(HIGH_FREQUENCY_TICKERS) + ordinary_sec * ordinary_companies,
        "health_checks": count_checks("health", "high_frequency", start, end),
        "assumption": "one provider request per due check; no retries",
    }


def policy_table() -> list[dict[str, str]]:
    """Human-readable copy of the cadence. The functions above are the authority."""
    return [
        {
            "dataset": "news",
            "high_frequency_active": "30 minutes, America/New_York weekdays 04:00-20:00",
            "other": "2 hours inactive or holiday; 4 hours weekend; 15 minutes for 2 hours around a confirmed event",
            "ordinary": "08:00 and 18:00 America/New_York",
            "quota": "falls back to the ordinary clocks and says so",
        },
        {
            "dataset": "sec_index",
            "high_frequency_active": "2 hours in the active window",
            "other": "6 hours otherwise; 30 minutes for at most 6 hours after a confirmed release",
            "ordinary": "08:00 and 18:00 America/New_York",
            "quota": "unknown or estimated dates do not accelerate",
        },
        {
            "dataset": "prices",
            "high_frequency_active": "2 hours after that session's close, including 13:00 early closes",
            "other": "no missing-bar alarm on a closed day when the last due session is present",
            "ordinary": "same session rule",
            "quota": "not a news quota",
        },
        {
            "dataset": "company_facts",
            "high_frequency_active": "daily 06:30 America/New_York, plus a new 10-Q/10-K",
            "other": "XBRL lag is a delayed recheck, not a relabel of old facts",
            "ordinary": "same",
            "quota": "unchanged",
        },
        {
            "dataset": "future_events",
            "high_frequency_active": "daily 06:00 America/New_York",
            "other": "every 6 hours when a confirmed event is inside 48 hours",
            "ordinary": "same",
            "quota": "an estimate is not promoted to confirmed",
        },
        {
            "dataset": "health",
            "high_frequency_active": "15 minutes",
            "other": "15 minutes",
            "ordinary": "15 minutes",
            "quota": "reads task time and coverage, not HTTP 200",
        },
    ]
