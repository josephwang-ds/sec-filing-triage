"""The refresh and monitor entry. A local directory is only the working copy."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from company_lens.events.blob_store import (
    BlobRequestError,
    publish_releases,
    pull_checkpoint,
    push_checkpoint,
    read_pointer,
)
from company_lens.events.calendar import as_utc
from company_lens.events.policy import coverage_tier, next_check
from company_lens.events.public import public_feed
from company_lens.events.refresh import RefreshReport, refresh_feed
from company_lens.events.store import FileEventStore


class DurablePull:
    def __init__(self, status: str, payload: dict | None = None, etag: str | None = None) -> None:
        self.status = status
        self.payload = payload
        self.etag = etag


class DurableStore(Protocol):
    def pull(self) -> DurablePull: ...

    def push(self, payload: dict, expected_etag: str | None) -> dict: ...


class BlobDurable:
    """Checkpoint adapter. A read failure is not an empty store."""

    def __init__(self, transport: Any) -> None:
        self.transport = transport

    def pull(self) -> DurablePull:
        try:
            payload, etag = pull_checkpoint(self.transport)
        except (BlobRequestError, OSError, ValueError):
            return DurablePull("read_error")
        if payload is None:
            return DurablePull("missing")
        return DurablePull("ok", payload, etag)

    def push(self, payload: dict, expected_etag: str | None) -> dict:
        return push_checkpoint(self.transport, payload, expected_etag=expected_etag)


class UnconfiguredDurable:
    def pull(self) -> DurablePull:
        return DurablePull("not_configured")

    def push(self, payload: dict, expected_etag: str | None) -> dict:
        return {"stored": False}


@dataclass
class RunResult:
    status: str
    durable: str
    reports: list[RefreshReport] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    redeployed: bool = False


def is_due(dataset: str, tier: str, state: dict | None, now: datetime) -> bool:
    """Never-run and unfinished tickers are due. A fresh success waits for its own cadence."""
    if state is None or state.get("pending") or not state.get("last_successful_check_at"):
        return True
    last = datetime.fromisoformat(str(state["last_successful_check_at"]))
    return next_check(dataset, tier, last) <= as_utc(now)


def run_refresh_entry(
    *,
    local_root: Any,
    durable: DurableStore,
    datasets: tuple[str, ...],
    tickers: list[str],
    now: datetime,
    sources: dict[str, Any],
    supported: set[str],
    watchlist: list[str] | None = None,
    sleep: Any = time.sleep,
    clock: Any | None = None,
    daily_request_budget: int = 500,
    time_budget_seconds: float = 600,
    publish_transport: Any | None = None,
) -> RunResult:
    """Restore, refresh each dataset on its own cadence, then persist.

    ``publish_transport`` is the blob client for the public pointer. It is the
    same transport as a ``BlobDurable`` in production. Tests pass the memory blob.
    """
    pulled = durable.pull()
    if pulled.status == "read_error":
        return RunResult(status="read_error", durable="read_error")
    store = FileEventStore(local_root)
    if pulled.status == "ok" and pulled.payload is not None:
        store.restore_workspace(pulled.payload)
    reports: list[RefreshReport] = []
    skipped: list[dict[str, str]] = []
    clock = clock or (lambda: datetime.now(UTC))
    try:
        for dataset in datasets:
            due = []
            tier_map = {}
            for ticker in tickers:
                tier = coverage_tier(ticker, supported)
                tier_map[ticker] = tier if tier != "unsupported" else "ordinary"
                state = store.read_state(dataset, ticker)
                if is_due(dataset, tier_map[ticker], state, now):
                    due.append(ticker)
                else:
                    skipped.append({"dataset": dataset, "ticker": ticker, "reason": "not_due"})
            source = sources.get(dataset)
            if source is None:
                _mark_disabled(store, dataset, due, now)
                continue
            reports.append(
                refresh_feed(
                    store=store,
                    source=source,
                    dataset=dataset,
                    tickers=due,
                    now=now,
                    watchlist=watchlist,
                    allowed=supported,
                    sleep=sleep,
                    clock=clock,
                    daily_request_budget=daily_request_budget,
                    time_budget_seconds=time_budget_seconds,
                    tiers=tier_map,
                )
            )
    except Exception:
        if pulled.status in {"ok", "missing"}:
            _push_quiet(durable, store.export_workspace(datasets), pulled.etag)
        raise
    if pulled.status == "not_configured":
        return RunResult(
            status="not_configured",
            durable="not_configured",
            reports=reports,
            skipped=skipped,
        )
    try:
        if publish_transport is not None:
            _publish_pointer(publish_transport, store, supported)
        durable.push(store.export_workspace(datasets), pulled.etag)
    except BlobRequestError as exc:
        if exc.status == 412:
            return RunResult(status="stale_writer", durable="conflict", reports=reports, skipped=skipped)
        raise
    return RunResult(status="stored", durable="checkpoint", reports=reports, skipped=skipped)


def _push_quiet(durable: DurableStore, payload: dict, etag: str | None) -> None:
    try:
        durable.push(payload, etag)
    except BlobRequestError:
        return


def _mark_disabled(store: FileEventStore, dataset: str, tickers: list[str], now: datetime) -> None:
    for ticker in tickers:
        previous = store.read_state(dataset, ticker)
        expected = 0 if previous is None else int(previous.get("revision") or 0)
        store.write_state(
            dataset,
            ticker,
            {
                "cadence_seconds": 12 * 60 * 60,
                "dataset": dataset,
                "detail_code": "source_not_configured",
                "key": ticker,
                "last_attempt_at": now.isoformat(),
                "last_error_class": "config",
                "last_successful_check_at": None
                if previous is None
                else previous.get("last_successful_check_at"),
                "status": "disabled",
            },
            expected,
        )


def _publish_pointer(transport: Any, store: FileEventStore, supported: set[str]) -> None:
    """Publish the news feed. SEC state stays in the checkpoint, not this pointer."""
    releases = {}
    dataset = "news"
    manifest = store.read_manifest(dataset)
    for ticker, pointer in (manifest.get("tickers") or {}).items():
        if not isinstance(pointer, dict):
            continue
        document = store.read_version(dataset, str(pointer.get("version_id")))
        if not document or not document.get("evidence_ready") or not document.get("evidence"):
            continue
        state = store.read_state(dataset, ticker)
        feed = public_feed(
            ticker=ticker,
            tier=coverage_tier(ticker, supported),
            document=document,
            state=state,
            storage="blob",
        )
        releases[ticker] = {
            "evidence": document["evidence"],
            "feed": feed,
            "version_id": document["version_id"],
        }
    if not releases:
        return
    current, etag = read_pointer(transport)
    del current
    publish_releases(transport, releases, observed_etag=etag)


def production_sleep(seconds: float) -> None:
    time.sleep(seconds)
