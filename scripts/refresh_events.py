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
from company_lens.universe import SupportedCompany, supported_companies

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
    parser.add_argument(
        "--require-blob",
        action="store_true",
        help="Fail when the blob token is missing. Drill runs use this.",
    )
    parser.add_argument("--now", default=None, help="ISO timestamp for a drill; default is current UTC")
    args = parser.parse_args(argv)

    flags = presence()
    if args.check_config:
        print(format_presence(flags))
        print("durable_store=" + ("blob" if flags["BLOB_READ_WRITE_TOKEN"] else "not_configured"))
        wake = "named" if flags["EVENTS_RERUN_TOKEN"] and flags["EVENTS_RERUN_URL"] else "not_configured"
        print(f"independent_wake={wake}")
        if args.require_blob and not flags["BLOB_READ_WRITE_TOKEN"]:
            print("config_error=blob_missing")
            return 2
        return 0

    now = datetime.fromisoformat(args.now) if args.now else datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    companies, config_error = _load_companies(args.universe)
    if config_error:
        print(config_error)
        return 2
    chosen, ignored, config_error = _select_companies(
        companies,
        args.tickers,
        args.tier,
        args.watchlist,
    )
    if config_error:
        print(config_error)
        return 2
    datasets = ("news", "sec_index") if args.dataset == "all" else (args.dataset,)
    if "sec_index" in datasets:
        missing_cik = [company.ticker for company in chosen if company.cik is None]
        if missing_cik:
            print("config_error=missing_cik tickers=" + ",".join(missing_cik))
            return 2
    if ignored:
        print("watchlist ignored for paid fetch: " + ",".join(ignored))
    targets = [company.ticker for company in chosen]
    print("fetch_targets=" + ",".join(targets))
    if args.require_blob and not flags["BLOB_READ_WRITE_TOKEN"]:
        print("config_error=blob_missing")
        return 2
    supported = set(targets)
    ciks = {company.ticker: int(company.cik) for company in chosen if company.cik is not None}
    sources = _sources(flags, datasets, ciks)
    durable, publish_transport = open_durable(flags)
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


def open_durable(flags: dict[str, bool]):
    """Return the checkpoint store and the publish transport. Tests replace this."""
    if flags["BLOB_READ_WRITE_TOKEN"]:
        transport = HttpBlobTransport(os.environ["BLOB_READ_WRITE_TOKEN"])
        return BlobDurable(transport), transport
    return UnconfiguredDurable(), None


def _sources(
    flags: dict[str, bool],
    datasets: tuple[str, ...],
    ciks: dict[str, int],
) -> dict:
    sources = {}
    if "news" in datasets and flags["FINNHUB_API_KEY"]:
        sources["news"] = FinnhubEventSource(os.environ["FINNHUB_API_KEY"])
    if "sec_index" in datasets and flags["EDGAR_USER_AGENT"]:
        sources["sec_index"] = EdgarRecentIndex(
            os.environ["EDGAR_USER_AGENT"],
            ciks=ciks,
        )
    return sources


def _load_companies(universe: Path) -> tuple[list[SupportedCompany], str | None]:
    path = universe if universe.is_absolute() else ROOT / universe
    if not path.exists():
        return [], f"config_error=universe_missing path={path}"
    companies = supported_companies(path)
    if not companies:
        return [], f"config_error=universe_empty path={path}"
    return companies, None


def _select_companies(
    companies: list[SupportedCompany],
    tickers: list[str] | None,
    tier: str,
    watchlist: list[str],
) -> tuple[list[SupportedCompany], list[str], str | None]:
    """News and SEC share this list. Explicit tickers do not bypass the universe."""
    by_ticker = {company.ticker: company for company in companies}
    if tickers is not None:
        wanted = [ticker.strip().upper() for ticker in tickers if ticker.strip()]
        if not wanted:
            return [], [], "config_error=tickers_empty"
        unknown = [ticker for ticker in wanted if ticker not in by_ticker]
        if unknown:
            return [], [], "config_error=unknown_ticker tickers=" + ",".join(unknown)
        return [by_ticker[ticker] for ticker in wanted], [], None
    names, ignored = select_targets(set(by_ticker), tier, watchlist)
    if not names:
        return [], ignored, "config_error=universe_empty"
    return [by_ticker[name] for name in names if name in by_ticker], ignored, None


if __name__ == "__main__":
    sys.exit(main())
