"""Refresh news or the SEC index without rebuilding or deploying the site."""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from company_lens.events.blob_store import HttpBlobTransport
from company_lens.events.config_status import format_presence, presence
from company_lens.events.policy import select_targets
from company_lens.events.providers import EdgarRecentIndex, FinnhubEventSource
from company_lens.events.run import BlobDurable, UnconfiguredDurable, run_refresh_entry
from company_lens.universe import supported_companies

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=("news", "sec_index", "all"), default="news")
    parser.add_argument(
        "--tier",
        choices=("high_frequency", "ordinary", "supported"),
        default="high_frequency",
    )
    parser.add_argument("--root", type=Path, default=Path("data/events-store"))
    parser.add_argument("--universe", type=Path, default=Path("data/build/universe.csv"))
    parser.add_argument("--tickers", nargs="*", default=None)
    parser.add_argument("--watchlist", nargs="*", default=())
    parser.add_argument("--check-config", action="store_true")
    parser.add_argument("--now", default=None, help="ISO timestamp for a drill; default is current UTC")
    args = parser.parse_args(argv)

    flags = presence()
    if args.check_config:
        print(format_presence(flags))
        print("durable_store=" + ("blob" if flags["BLOB_READ_WRITE_TOKEN"] else "not_configured"))
        wake = "named" if flags["EVENTS_RERUN_TOKEN"] and flags["EVENTS_RERUN_URL"] else "not_configured"
        print(f"independent_wake={wake}")
        return 0

    now = datetime.fromisoformat(args.now) if args.now else datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    supported = _supported(args.universe, args.tickers)
    if not supported:
        print("no supported universe and no explicit tickers; fetches were not started")
        return 0
    targets, ignored = select_targets(supported, args.tier, args.watchlist)
    if ignored:
        print("watchlist ignored for paid fetch: " + ",".join(ignored))
    datasets = ("news", "sec_index") if args.dataset == "all" else (args.dataset,)
    sources = _sources(flags, args.universe, datasets)
    if flags["BLOB_READ_WRITE_TOKEN"]:
        transport = HttpBlobTransport(os.environ["BLOB_READ_WRITE_TOKEN"])
        durable = BlobDurable(transport)
        publish_transport = transport
    else:
        transport = None
        durable = UnconfiguredDurable()
        publish_transport = None
    result = run_refresh_entry(
        local_root=args.root,
        durable=durable,
        datasets=datasets,
        tickers=targets,
        now=now,
        sources=sources,
        supported=supported,
        watchlist=list(ignored),
        sleep=time.sleep,
        publish_transport=publish_transport,
    )
    print(f"durable_store={result.durable}")
    print("redeployed=false")
    for item in result.skipped:
        print(f"skipped dataset={item['dataset']} ticker={item['ticker']} reason={item['reason']}")
    for report in result.reports:
        print(
            f"{report.dataset} status={report.status} requests={report.requests} "
            f"tickers={len(report.outcomes)} redeployed={report.redeployed}"
        )
    if result.status == "read_error":
        print("checkpoint_read=failed")
        return 3
    if result.status == "stale_writer":
        print("checkpoint_write=stale")
        return 3
    if any(report.status == "partial" for report in result.reports):
        return 2
    return 0


def _sources(flags: dict[str, bool], universe: Path, datasets: tuple[str, ...]) -> dict:
    sources = {}
    if "news" in datasets and flags["FINNHUB_API_KEY"]:
        sources["news"] = FinnhubEventSource(os.environ["FINNHUB_API_KEY"])
    if "sec_index" in datasets and flags["EDGAR_USER_AGENT"]:
        sources["sec_index"] = EdgarRecentIndex(
            os.environ["EDGAR_USER_AGENT"],
            ciks=_ciks(universe),
        )
    return sources


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


if __name__ == "__main__":
    sys.exit(main())
