#!/usr/bin/env python3
"""Write the event-refresh company list from the committed service file.

This does not read the Saturday universe cache and does not call the SEC.
``build_demo_universe.py`` remains the demo-ingest helper; it downloads the
full SEC ticker map, so the event drill does not use it.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_COMPANIES = ROOT / "data" / "events" / "service_companies.csv"
DRILL_TICKERS = ("AAPL", "JPM", "NVDA")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="*", default=list(DRILL_TICKERS))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    rows, error = load_service_companies(args.tickers)
    if error:
        print(error, file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("ticker", "name", "cik"))
        writer.writeheader()
        writer.writerows(rows)
    print(f"event_universe={args.out} companies={','.join(row['ticker'] for row in rows)}")
    return 0


def load_service_companies(tickers: list[str]) -> tuple[list[dict[str, str]], str | None]:
    if not SERVICE_COMPANIES.exists():
        return [], f"config_error=service_companies_missing path={SERVICE_COMPANIES}"
    with SERVICE_COMPANIES.open(encoding="utf-8", newline="") as handle:
        found = list(csv.DictReader(handle))
    by_ticker = {}
    for row in found:
        ticker = str(row.get("ticker") or "").strip().upper()
        name = str(row.get("name") or "").strip()
        cik = str(row.get("cik") or "").strip()
        if not ticker or not name or not cik:
            return [], f"config_error=service_companies_incomplete ticker={ticker or 'blank'}"
        by_ticker[ticker] = {"ticker": ticker, "name": name, "cik": cik}
    if not by_ticker:
        return [], f"config_error=service_companies_empty path={SERVICE_COMPANIES}"
    wanted = [ticker.strip().upper() for ticker in tickers if ticker.strip()]
    if not wanted:
        return [], "config_error=tickers_empty"
    unknown = [ticker for ticker in wanted if ticker not in by_ticker]
    if unknown:
        return [], "config_error=unknown_ticker tickers=" + ",".join(unknown)
    return [by_ticker[ticker] for ticker in wanted], None


if __name__ == "__main__":
    sys.exit(main())
