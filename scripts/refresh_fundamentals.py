"""Normalize SEC Company Facts into local fundamentals artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from company_lens.financial_results import filed_figures_status, load_financial_results
from company_lens.refresh import refresh_fundamentals
from company_lens.universe import supported_companies


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=["AAPL"],
        help="tickers to refresh (default: AAPL)",
    )
    parser.add_argument("--data-dir", default="data/build")
    parser.add_argument(
        "--all", action="store_true", help="refresh every company in the local universe"
    )
    parser.add_argument("--universe", default=None)
    parser.add_argument("--requested-years", type=int, default=10)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="read cached Company Facts only; do not call SEC",
    )
    parser.add_argument(
        "--cache-dir",
        default="data/cache/edgar",
        help="Edgar cache used by --offline",
    )
    parser.add_argument(
        "--require",
        nargs="+",
        default=[],
        help="tickers that must have structured, displayable filed figures",
    )
    parser.add_argument(
        "--fundamentals-dir",
        default=None,
        help="optional override; defaults to <data-dir>/fundamentals",
    )
    args = parser.parse_args()
    data_dir = args.data_dir
    if args.fundamentals_dir:
        data_dir = str(Path(args.fundamentals_dir).parent)
    result = refresh_fundamentals(
        data_dir=data_dir,
        universe_path=args.universe,
        tickers=(
            [
                company.ticker
                for company in supported_companies(args.universe or Path(data_dir) / "universe.csv")
            ]
            if args.all
            else args.tickers
        ),
        requested_years=args.requested_years,
        offline=args.offline,
        cache_dir=args.cache_dir,
    )
    print(
        f"Fundamentals refresh {result.status}: checked {result.companies_checked} "
        f"companies, wrote {len(result.artifact_paths)} artifact(s)."
    )
    if result.refreshed_tickers:
        print(f"refreshed tickers: {', '.join(result.refreshed_tickers)}")
    if result.failed_tickers:
        print(f"failed tickers: {', '.join(result.failed_tickers)}")
    for path in result.artifact_paths:
        print(f"artifact: {path}")
    print(f"checked at {result.checked_at}")
    blocked = []
    for ticker in [item.upper() for item in args.require]:
        report = load_financial_results(data_dir, ticker)
        kind = filed_figures_status(report)
        if kind != "numbers":
            blocked.append(f"{ticker}={kind}")
    if blocked:
        print(
            "required issuers lack structured displayable figures: " + ", ".join(blocked),
            file=sys.stderr,
        )
        return 1
    if args.offline:
        return 0
    return 0 if result.status == "current" else 2


if __name__ == "__main__":
    raise SystemExit(main())
