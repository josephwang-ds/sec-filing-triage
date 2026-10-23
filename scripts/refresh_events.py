"""Refresh news or the SEC index without rebuilding or deploying the site."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from company_lens.events.blob_store import HttpBlobTransport, publish_public_feeds
from company_lens.events.config_status import format_presence, presence
from company_lens.events.policy import coverage_tier, select_targets
from company_lens.events.providers import EdgarRecentIndex, FinnhubEventSource
from company_lens.events.public import public_feed
from company_lens.events.refresh import refresh_feed
from company_lens.events.store import FileEventStore
from company_lens.universe import supported_companies

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=("news", "sec_index", "all"), default="news")
    parser.add_argument("--tier", choices=("high_frequency", "ordinary", "supported"), default="high_frequency")
    parser.add_argument("--root", type=Path, default=Path("data/events-store"))
    parser.add_argument("--universe", type=Path, default=Path("data/build/universe.csv"))
    parser.add_argument("--tickers", nargs="*", default=None)
    parser.add_argument("--watchlist", nargs="*", default=())
    parser.add_argument("--check-config", action="store_true")
    parser.add_argument("--now", default=None, help="ISO timestamp for a drill; default is the current UTC time")
    args = parser.parse_args(argv)

    flags = presence()
    if args.check_config:
        print(format_presence(flags))
        print("durable_store=" + ("blob" if flags["BLOB_READ_WRITE_TOKEN"] else "not_configured"))
        print("independent_wake=not_configured" if not flags["EVENTS_RERUN_TOKEN"] else "independent_wake=named")
        return 0

    now = datetime.fromisoformat(args.now) if args.now else datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    supported = _supported(args.universe, args.tickers)
    if not supported:
        print("no supported universe and no explicit tickers; news and SEC fetches were not started")
        return 0
    targets, ignored = select_targets(supported, args.tier, args.watchlist)
    if ignored:
        print("watchlist ignored for paid fetch: " + ",".join(ignored))
    store = FileEventStore(args.root)
    datasets = ("news", "sec_index") if args.dataset == "all" else (args.dataset,)
    exit_code = 0
    feeds: dict[str, dict] = {}
    for dataset in datasets:
        code, dataset_feeds = _run_dataset(dataset, store, targets, supported, ignored, now, flags)
        feeds.update(dataset_feeds)
        exit_code = max(exit_code, code)
    if flags["BLOB_READ_WRITE_TOKEN"] and feeds:
        publish_public_feeds(
            HttpBlobTransport(os.environ["BLOB_READ_WRITE_TOKEN"]),
            feeds,
            expected_etag=os.environ.get("EVENTS_BLOB_MANIFEST_ETAG") or None,
        )
        print("published=blob")
    else:
        print("published=local_only")
        print("durable_store=not_configured")
    print("redeployed=false")
    return exit_code


def _ciks(universe: Path) -> dict[str, int]:
    path = universe if universe.is_absolute() else ROOT / universe
    return {
        company.ticker: company.cik
        for company in supported_companies(path)
        if company.cik is not None
    }


def _supported(universe: Path, tickers: list[str] | None) -> set[str]:
    if tickers:
        return {ticker.strip().upper() for ticker in tickers if ticker.strip()}
    path = universe if universe.is_absolute() else ROOT / universe
    return {company.ticker for company in supported_companies(path)}


def _run_dataset(dataset, store, targets, supported, ignored, now, flags) -> tuple[int, dict]:
    if dataset == "news" and not flags["FINNHUB_API_KEY"]:
        _disable(store, dataset, targets, now, "FINNHUB_API_KEY")
        print("news=disabled missing=FINNHUB_API_KEY")
        return 0, {}
    if dataset == "sec_index" and not flags["EDGAR_USER_AGENT"]:
        _disable(store, dataset, targets, now, "EDGAR_USER_AGENT")
        print("sec_index=disabled missing=EDGAR_USER_AGENT")
        return 0, {}
    if dataset == "news":
        source = FinnhubEventSource(os.environ["FINNHUB_API_KEY"])
    else:
        source = EdgarRecentIndex(
            os.environ["EDGAR_USER_AGENT"],
            ciks=_ciks(Path("data/build/universe.csv")),
        )
    report = refresh_feed(
        store=store,
        source=source,
        dataset=dataset,
        tickers=targets,
        now=now,
        watchlist=ignored,
        allowed=supported,
    )
    print(
        f"{dataset} status={report.status} requests={report.requests} "
        f"tickers={len(report.outcomes)} redeployed={report.redeployed}"
    )
    for outcome in report.outcomes:
        if outcome.error_class:
            print(f"{outcome.ticker} error_class={outcome.error_class} attempts={outcome.attempts}")
    feeds = {}
    if dataset == "news":
        for outcome in report.outcomes:
            document = store.current_version(dataset, outcome.ticker)
            state = store.read_state(dataset, outcome.ticker)
            feeds[outcome.ticker] = public_feed(
                ticker=outcome.ticker,
                tier=coverage_tier(outcome.ticker, supported),
                document=document,
                state=state,
                storage="blob" if flags["BLOB_READ_WRITE_TOKEN"] else "local",
            )
    if report.status == "partial":
        return 2, feeds
    return 0, feeds


def _disable(store, dataset, targets, now, missing: str) -> None:
    for ticker in targets:
        previous = store.read_state(dataset, ticker)
        expected = 0 if previous is None else int(previous.get("revision") or 0)
        store.write_state(
            dataset,
            ticker,
            {
                "dataset": dataset,
                "key": ticker,
                "last_attempt_at": now.isoformat(),
                "last_error_class": "config",
                "last_successful_check_at": None if previous is None else previous.get("last_successful_check_at"),
                "status": "disabled",
                "detail_code": missing,
            },
            expected,
        )


if __name__ == "__main__":
    sys.exit(main())
