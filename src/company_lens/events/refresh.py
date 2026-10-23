"""Incremental event refresh. One issuer failing does not roll back the others.

This module fetches and publishes data. It does not rebuild HTML or deploy.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from company_lens.events.calendar import as_utc
from company_lens.events.contracts import SCHEMA_VERSION, version_id
from company_lens.events.evidence import build_event_evidence
from company_lens.events.normalize import merge_events, normalize_item
from company_lens.events.policy import (
    NEWS_COLD_DAYS,
    NEWS_OVERLAP,
    SEC_COLD_DAYS,
    SEC_OVERLAP,
    interval_at,
)
from company_lens.events.store import FileEventStore, LeaseHeld, StaleWriter

COLD_DAYS = {"news": NEWS_COLD_DAYS, "sec_index": SEC_COLD_DAYS}
OVERLAP = {"news": NEWS_OVERLAP, "sec_index": SEC_OVERLAP}


class RefreshInterrupted(RuntimeError):
    """The candidate was written and then the process stopped before publish."""


class FetchResult:
    def __init__(
        self,
        *,
        ok: bool,
        items: list[dict[str, Any]] | None = None,
        error_class: str | None = None,
        retryable: bool = False,
        retry_after: float | None = None,
    ) -> None:
        self.ok = ok
        self.items = items or []
        self.error_class = error_class
        self.retryable = retryable
        self.retry_after = retry_after


class EventSource(Protocol):
    name: str
    max_window_days: int

    def fetch(self, ticker: str, start: datetime, end: datetime) -> FetchResult: ...

    def lookback_floor(self, now: datetime) -> datetime | None: ...


@dataclass
class TickerOutcome:
    ticker: str
    status: str
    error_class: str | None = None
    attempts: int = 0
    requests: int = 0
    version_id: str | None = None
    published: bool = False
    pending: bool = False
    coverage_gaps: list[dict[str, str]] = field(default_factory=list)
    event_count: int = 0
    retry_not_before: str | None = None


@dataclass
class RefreshReport:
    dataset: str
    redeployed: bool
    outcomes: list[TickerOutcome]
    watchlist_ignored: list[str]
    requests: int
    elapsed_ms: int

    @property
    def status(self) -> str:
        if any(item.status == "disabled" for item in self.outcomes):
            return "disabled"
        if any(item.error_class for item in self.outcomes):
            return "partial"
        return "current"


def _windows(start: datetime, end: datetime, max_days: int) -> list[tuple[datetime, datetime]]:
    if max_days < 1:
        raise ValueError("max window must be at least one day")
    cursor = as_utc(start)
    end = as_utc(end)
    spans: list[tuple[datetime, datetime]] = []
    while cursor <= end:
        stop = min(end, cursor + timedelta(days=max_days) - timedelta(seconds=1))
        spans.append((cursor, stop))
        cursor = stop + timedelta(seconds=1)
    return spans


def plan_windows(
    *,
    dataset: str,
    now: datetime,
    coverage_through: str | None,
    floor: datetime | None,
    max_window_days: int,
) -> tuple[list[tuple[datetime, datetime]], list[dict[str, str]], bool]:
    """Cold start is a bounded window. Recovery starts at the watermark minus overlap."""
    now = as_utc(now)
    initialization = coverage_through is None
    if initialization:
        start = now - timedelta(days=COLD_DAYS[dataset])
    else:
        through = datetime.fromisoformat(coverage_through)
        start = as_utc(through) - OVERLAP[dataset]
    gaps: list[dict[str, str]] = []
    if floor is not None and start < as_utc(floor):
        gaps.append(
            {
                "end": as_utc(floor).isoformat(),
                "reason": "provider_lookback",
                "start": start.isoformat(),
            }
        )
        start = as_utc(floor)
    if start > now:
        start = now
    return _windows(start, now, max_window_days), gaps, initialization


def _backoff(attempt: int, retry_after: float | None, rng: Any) -> float:
    base = min(60.0, 1.5 * (2 ** (attempt - 1)))
    jittered = base * (0.5 + rng.random() * 0.5)
    if retry_after is not None:
        return max(jittered, float(retry_after))
    return jittered


def _pending(
    ticker: str,
    error_class: str,
    attempts: int,
    requests: int,
    retry_not_before: str | None = None,
) -> TickerOutcome:
    return TickerOutcome(
        ticker,
        "pending",
        error_class=error_class,
        attempts=attempts,
        requests=requests,
        pending=True,
        retry_not_before=retry_not_before,
    )


def _fetch_windows(
    source: EventSource,
    ticker: str,
    windows: list[tuple[datetime, datetime]],
    *,
    max_attempts: int,
    sleep: Any,
    rng: Any,
    deadline: datetime,
    clock: Any,
    requests_left: list[int],
    store: FileEventStore,
    dataset: str,
    day: str,
) -> tuple[list[dict[str, Any]], TickerOutcome | None, int, int]:
    items: list[dict[str, Any]] = []
    attempts = 0
    requests = 0
    for start, end in windows:
        attempt = 0
        while True:
            if clock() >= deadline:
                return items, _pending(ticker, "time_budget", attempts, requests), attempts, requests
            if requests_left[0] <= 0:
                return items, _pending(ticker, "budget", attempts, requests), attempts, requests
            attempt += 1
            attempts += 1
            requests += 1
            requests_left[0] -= 1
            store.charge_budget(dataset, day, 1)
            try:
                result = source.fetch(ticker, start, end)
            except Exception as exc:  # noqa: BLE001 - one window must not abort other issuers
                result = FetchResult(ok=False, error_class=type(exc).__name__, retryable=True)
            if result.ok:
                items.extend(result.items)
                break
            if not result.retryable or result.error_class in {"config", "forbidden"} or attempt >= max_attempts:
                outcome = TickerOutcome(
                    ticker,
                    "failed",
                    error_class=result.error_class or "upstream",
                    attempts=attempts,
                    requests=requests,
                )
                return items, outcome, attempts, requests
            delay = _backoff(attempt, result.retry_after, rng)
            remaining = (deadline - clock()).total_seconds()
            if delay > remaining:
                # The full Retry-After is persisted. This run does not sleep a shorter stand-in.
                not_before = (as_utc(clock()) + timedelta(seconds=delay)).isoformat()
                return (
                    items,
                    _pending(
                        ticker,
                        "retry_wait",
                        attempts,
                        requests,
                        retry_not_before=not_before,
                    ),
                    attempts,
                    requests,
                )
            sleep(delay)
            if clock() >= deadline:
                return items, _pending(ticker, "time_budget", attempts, requests), attempts, requests
    return items, None, attempts, requests


def _state_shell(dataset: str, ticker: str, previous: dict | None) -> dict:
    base = {
        "attempt": 0,
        "coverage_gaps": [],
        "coverage_through": None,
        "dataset": dataset,
        "initialization": False,
        "key": ticker,
        "last_attempt_at": None,
        "last_error_class": None,
        "last_successful_check_at": None,
        "pending": False,
        "quota_degraded": False,
        "request_day": None,
        "requests_today": 0,
        "status": "unavailable",
        "version_id": None,
    }
    if previous:
        base.update(previous)
    return base


def refresh_feed(
    *,
    store: FileEventStore,
    source: EventSource,
    dataset: str,
    tickers: list[str],
    now: datetime,
    watchlist: list[str] | None = None,
    allowed: set[str] | None = None,
    max_attempts: int = 3,
    daily_request_budget: int = 500,
    time_budget_seconds: float = 600,
    max_items: int | None = None,
    sleep: Any = lambda _seconds: None,
    clock: Any | None = None,
    rng: Any | None = None,
    owner: str = "events-refresh",
    tiers: dict[str, str] | None = None,
    lease_ttl_seconds: float = 300,
    crash_after: str | None = None,
    quota_degraded: bool = False,
) -> RefreshReport:
    """Pull each ticker from its own watermark. Publishing one ticker is independent."""
    if dataset not in COLD_DAYS:
        raise ValueError(f"unsupported dataset {dataset}")
    generator = rng
    if generator is None:
        import random

        generator = random.Random(0)
    clock = clock or (lambda: datetime.now(UTC))
    opened = clock()
    now = as_utc(now)
    seen_at = now.isoformat()
    day = now.date().isoformat()
    already_used = store.budget_used(dataset, day)
    requests_left = [max(0, daily_request_budget - already_used)]
    deadline = clock() + timedelta(seconds=time_budget_seconds)
    targets = [ticker.strip().upper() for ticker in tickers if ticker.strip()]
    if allowed is not None:
        targets = [ticker for ticker in targets if ticker in allowed]
    ignored = [
        ticker.strip().upper()
        for ticker in (watchlist or [])
        if ticker.strip() and ticker.strip().upper() not in targets
    ]
    outcomes: list[TickerOutcome] = []

    for ticker in targets:
        if clock() >= deadline:
            outcomes.append(TickerOutcome(ticker, "pending", error_class="time_budget", pending=True))
            continue
        try:
            lease = store.acquire_lease(dataset, ticker, owner, now, lease_ttl_seconds)
        except LeaseHeld:
            outcomes.append(TickerOutcome(ticker, "skipped", error_class="lease_held"))
            continue
        try:
            outcomes.append(
                _refresh_one(
                    store=store,
                    source=source,
                    dataset=dataset,
                    ticker=ticker,
                    now=now,
                    seen_at=seen_at,
                    lease=lease,
                    max_attempts=max_attempts,
                    requests_left=requests_left,
                    max_items=max_items,
                    sleep=sleep,
                    clock=clock,
                    rng=generator,
                    deadline=deadline,
                    day=day,
                    tiers=tiers or {},
                    crash_after=crash_after,
                    quota_degraded=quota_degraded,
                )
            )
        except StaleWriter:
            outcomes.append(TickerOutcome(ticker, "failed", error_class="stale_writer"))
        finally:
            store.release_lease(dataset, ticker, lease["token"])

    elapsed = int(max(0.0, (clock() - opened).total_seconds()) * 1000)
    return RefreshReport(
        dataset=dataset,
        redeployed=False,
        outcomes=outcomes,
        watchlist_ignored=ignored,
        requests=sum(item.requests for item in outcomes),
        elapsed_ms=elapsed,
    )


def _refresh_one(
    *,
    store: FileEventStore,
    source: EventSource,
    dataset: str,
    ticker: str,
    now: datetime,
    seen_at: str,
    lease: dict,
    max_attempts: int,
    requests_left: list[int],
    max_items: int | None,
    sleep: Any,
    clock: Any,
    rng: Any,
    deadline: datetime,
    day: str,
    tiers: dict[str, str],
    crash_after: str | None,
    quota_degraded: bool,
) -> TickerOutcome:
    previous_state = store.read_state(dataset, ticker)
    expected_revision = 0 if previous_state is None else int(previous_state.get("revision") or 0)
    state = _state_shell(dataset, ticker, previous_state)
    previous_doc = store.current_version(dataset, ticker)
    previous_events = list(previous_doc.get("events") or []) if previous_doc else []
    windows, gaps, initialization = plan_windows(
        dataset=dataset,
        now=now,
        coverage_through=state.get("coverage_through"),
        floor=source.lookback_floor(now),
        max_window_days=source.max_window_days,
    )
    raw_items, failure, attempts, requests = _fetch_windows(
        source,
        ticker,
        windows,
        max_attempts=max_attempts,
        sleep=sleep,
        rng=rng,
        deadline=deadline,
        clock=clock,
        requests_left=requests_left,
        store=store,
        dataset=dataset,
        day=day,
    )
    state["attempt"] = int(state.get("attempt") or 0) + attempts
    state["last_attempt_at"] = seen_at
    state["quota_degraded"] = quota_degraded
    if failure is not None:
        state["last_error_class"] = failure.error_class
        state["status"] = "pending" if failure.pending else "stale"
        state["pending"] = failure.pending
        if failure.retry_not_before:
            state["retry_not_before"] = failure.retry_not_before
        else:
            state.pop("retry_not_before", None)
        # A failure must not move the success watermark.
        store.write_state(dataset, ticker, _public_state(state), expected_revision)
        store.write_failure(
            dataset,
            ticker,
            {
                "attempts": attempts,
                "at": seen_at,
                "error_class": failure.error_class,
                "retryable": failure.error_class not in {"config", "forbidden"},
            },
        )
        failure.requests = requests
        failure.attempts = attempts
        failure.version_id = state.get("version_id")
        failure.coverage_gaps = gaps
        return failure

    normalized = [
        event
        for payload in raw_items
        if (event := normalize_item(payload, ticker=ticker, seen_at=seen_at)) is not None
    ]
    merged = merge_events(previous_events, normalized, seen_at=seen_at)
    pending = False
    if max_items is not None and len(merged) > max_items:
        pending = True
        dropped = merged[max_items:]
        merged = merged[:max_items]
        if dropped:
            gaps.append(
                {
                    "end": str(dropped[-1].get("source_published_at") or ""),
                    "reason": "item_budget",
                    "start": str(dropped[0].get("source_published_at") or ""),
                }
            )
    new_ids = {event["id"] for event in normalized}
    old_ids = {event["id"] for event in previous_events}
    added = len(new_ids - old_ids)
    content_same = [event["content_hash"] for event in merged] == [
        event["content_hash"] for event in previous_events
    ]
    if gaps or pending:
        status = "partial"
    elif added == 0:
        status = "no_new_events"
    else:
        status = "current"
    state["coverage_gaps"] = gaps
    state["initialization"] = initialization and previous_doc is None
    state["last_error_class"] = None
    state["pending"] = pending
    state["status"] = status
    state.pop("retry_not_before", None)
    if pending:
        # Keep the previous watermark so the unfinished tail is fetched again.
        state["coverage_through"] = None if previous_state is None else previous_state.get(
            "coverage_through"
        )
    else:
        state["coverage_through"] = now.isoformat()
        state["last_successful_check_at"] = seen_at
    step = interval_at(dataset, tiers.get(ticker, "ordinary"), now)
    state["cadence_seconds"] = int(step.total_seconds()) if step is not None else 12 * 60 * 60
    document = {
        "content_hash": version_id(ticker, merged),
        "coverage_gaps": gaps,
        "dataset": dataset,
        "events": merged,
        "generated_at": seen_at,
        "initialization": state["initialization"],
        "schema_version": SCHEMA_VERSION,
        "ticker": ticker,
        "version_id": version_id(ticker, merged),
    }
    document["evidence"] = build_event_evidence(document)
    document["evidence_ready"] = True
    if content_same and previous_doc is not None and not pending and not gaps:
        state["version_id"] = previous_doc.get("version_id")
        store.write_state(dataset, ticker, _public_state(state), expected_revision)
        return TickerOutcome(
            ticker,
            status,
            attempts=attempts,
            requests=requests,
            version_id=state["version_id"],
            published=False,
            event_count=len(merged),
            coverage_gaps=gaps,
        )
    store.put_version(dataset, document)
    if crash_after == "version":
        raise RefreshInterrupted(ticker)
    manifest = store.read_manifest(dataset)
    store.publish(
        dataset,
        ticker=ticker,
        version_id=document["version_id"],
        expected_fence=int(manifest.get("fence") or 0),
        lease_token=lease["token"],
        now=now,
    )
    state["version_id"] = document["version_id"]
    # The version is already current. A lost state write is retried next pass.
    with contextlib.suppress(StaleWriter):
        store.write_state(dataset, ticker, _public_state(state), expected_revision)
    return TickerOutcome(
        ticker,
        status,
        attempts=attempts,
        requests=requests,
        version_id=document["version_id"],
        published=True,
        pending=pending,
        event_count=len(merged),
        coverage_gaps=gaps,
    )


def _public_state(state: dict) -> dict:
    hidden = {"revision"}
    return {key: value for key, value in state.items() if key not in hidden}
