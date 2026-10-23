"""Incrementally refresh mutable SEC submission heads without re-downloading history."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from company_lens.fundamentals import (
    build_fundamentals_section,
    fundamentals_path,
    save_fundamentals,
)
from company_lens.universe import SupportedCompany, supported_companies
from filing_triage.ingest.edgar import EdgarClient, parse_submissions
from filing_triage.ingest.prices import fetch_daily

# SPY is the default benchmark; QQQ feeds the optional history comparison.
REFERENCE_SYMBOLS = ("SPY", "QQQ")


@dataclass(frozen=True)
class FilingRefreshResult:
    status: str
    checked_at: str
    companies_checked: int
    new_filings: int
    changed_tickers: list[str]
    failed_tickers: list[str]
    latest_acceptance_time: str | None


@dataclass(frozen=True)
class MarketRefreshResult:
    status: str
    checked_at: str
    tickers_checked: int
    refreshed_tickers: list[str]
    failed_tickers: list[str]
    latest_price_date: str | None


@dataclass(frozen=True)
class FundamentalsRefreshResult:
    status: str
    checked_at: str
    companies_checked: int
    refreshed_tickers: list[str]
    failed_tickers: list[str]
    artifact_paths: list[str]
    failures: tuple[dict[str, str], ...] = ()


def refresh_filings(
    *,
    data_dir: str | Path = "data/build",
    universe_path: str | Path | None = None,
    tickers: list[str] | tuple[str, ...] | None = None,
    since: str | date | None = None,
    client: Any | None = None,
) -> FilingRefreshResult:
    """Refresh issuer submission heads and append only unseen 8-K accessions.

    Existing accession documents are immutable and remain cached. The consolidated
    event panel is replaced atomically only after every successful issuer has been
    merged, so a partial network failure cannot erase previously collected filings.
    """
    root = Path(data_dir)
    event_path = root / "events.parquet"
    universe = Path(universe_path) if universe_path else root / "universe.csv"
    if not event_path.exists():
        raise FileNotFoundError(f"missing local event panel: {event_path}")

    events = pd.read_parquet(event_path)
    companies = supported_companies(universe)
    requested = {ticker.strip().upper() for ticker in tickers or ()}
    if requested:
        known = {company.ticker for company in companies}
        missing = sorted(requested - known)
        if missing:
            raise ValueError(f"unknown local ticker(s): {', '.join(missing)}")
        companies = [company for company in companies if company.ticker in requested]

    sec = client or EdgarClient()
    cutoff = _cutoff_date(events, since)
    seen = set(events["accession"].astype(str))
    additions: list[pd.DataFrame] = []
    changed: list[str] = []
    failures: list[str] = []

    for company in companies:
        if company.cik is None:
            failures.append(company.ticker)
            continue
        try:
            current = parse_submissions(
                sec.submissions(company.cik, refresh=True), company.cik
            )
            current = current[current["filing_date"] >= cutoff].copy()
            current = current[~current["accession"].astype(str).isin(seen)]
            if current.empty:
                continue
            current["ticker"] = company.ticker
            current["text"] = [
                sec.document_text(company.cik, accession, document)
                for accession, document in zip(
                    current["accession"], current["primary_document"], strict=True
                )
            ]
            current["event_id"] = current["accession"]
            additions.append(current)
            changed.append(company.ticker)
            seen.update(current["accession"].astype(str))
        except Exception:  # noqa: BLE001 - one issuer must not invalidate the refresh
            failures.append(company.ticker)

    if additions:
        merged = pd.concat([events, *additions], ignore_index=True)
        merged = (
            merged.drop_duplicates("accession", keep="last")
            .sort_values(["acceptance_time", "ticker", "accession"])
            .reset_index(drop=True)
        )
        _atomic_parquet(merged, event_path)
    else:
        merged = events

    checked_at = datetime.now(UTC).isoformat()
    latest = pd.to_datetime(merged["acceptance_time"]).max() if len(merged) else pd.NaT
    result = FilingRefreshResult(
        status="partial" if failures else "current",
        checked_at=checked_at,
        companies_checked=len(companies) - len(failures),
        new_filings=sum(len(frame) for frame in additions),
        changed_tickers=sorted(changed),
        failed_tickers=sorted(failures),
        latest_acceptance_time=None if pd.isna(latest) else pd.Timestamp(latest).isoformat(),
    )
    _write_refresh_provenance(root / "provenance.json", result, len(merged))
    return result


def refresh_market_data(
    *,
    data_dir: str | Path = "data/build",
    universe_path: str | Path | None = None,
    cache_dir: str | Path = "data/cache/prices",
    tickers: list[str] | tuple[str, ...] | None = None,
) -> MarketRefreshResult:
    """Refresh daily bars while retaining the last good rows for failed symbols."""
    root = Path(data_dir)
    price_path = root / "prices.parquet"
    universe = Path(universe_path) if universe_path else root / "universe.csv"
    if not price_path.exists():
        raise FileNotFoundError(f"missing local price panel: {price_path}")

    current = pd.read_parquet(price_path)
    companies = supported_companies(universe)
    requested = {ticker.strip().upper() for ticker in tickers or ()}
    if requested:
        known = {company.ticker for company in companies}
        missing = sorted(requested - known)
        if missing:
            raise ValueError(f"unknown local ticker(s): {', '.join(missing)}")
        symbols = sorted(requested | set(REFERENCE_SYMBOLS))
    else:
        symbols = sorted({company.ticker for company in companies} | set(REFERENCE_SYMBOLS))

    updated: dict[str, pd.DataFrame] = {}
    failures: list[str] = []
    for symbol in symbols:
        try:
            updated[symbol] = fetch_daily(
                symbol, cache_dir=Path(cache_dir), refresh=True
            )
        except Exception:  # noqa: BLE001 - preserve the last good symbol history
            failures.append(symbol)

    refreshed = sorted(updated)
    untouched = current[~current["ticker"].astype(str).str.upper().isin(refreshed)]
    frames = [untouched, *updated.values()]
    merged = (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(["ticker", "date"], keep="last")
        .sort_values(["ticker", "date"])
        .reset_index(drop=True)
    )
    _atomic_parquet(merged, price_path)

    checked_at = datetime.now(UTC).isoformat()
    latest = pd.to_datetime(merged["date"]).max() if len(merged) else pd.NaT
    result = MarketRefreshResult(
        status="partial" if failures else "current",
        checked_at=checked_at,
        tickers_checked=len(symbols) - len(failures),
        refreshed_tickers=refreshed,
        failed_tickers=sorted(failures),
        latest_price_date=None if pd.isna(latest) else pd.Timestamp(latest).date().isoformat(),
    )
    _write_market_provenance(root / "provenance.json", result)
    return result


def refresh_fundamentals(
    *,
    data_dir: str | Path = "data/build",
    universe_path: str | Path | None = None,
    tickers: list[str] | tuple[str, ...] | None = None,
    requested_years: int = 10,
    client: Any | None = None,
    refresh: bool = True,
) -> FundamentalsRefreshResult:
    """Fetch Company Facts, normalize annual series, and write local artifacts.

    Defaults to AAPL only. Tests inject a fake client so the suite never hits SEC.
    """
    root = Path(data_dir)
    universe = Path(universe_path) if universe_path else root / "universe.csv"
    companies = supported_companies(universe)
    requested = {ticker.strip().upper() for ticker in (tickers or ("AAPL",))}
    if companies:
        known = {company.ticker for company in companies}
        missing = sorted(requested - known)
        if missing:
            raise ValueError(f"unknown local ticker(s): {', '.join(missing)}")
        targets = [company for company in companies if company.ticker in requested]
    else:
        targets = [
            SupportedCompany(
                ticker=ticker,
                display_name=ticker,
                official_name=ticker,
                cik=320193 if ticker == "AAPL" else None,
            )
            for ticker in sorted(requested)
        ]

    sec = client or EdgarClient()
    refreshed: list[str] = []
    failures: list[dict[str, str]] = []
    artifacts: list[str] = []

    for company in targets:
        if company.cik is None:
            failure = {
                "ticker": company.ticker,
                "exception_type": "MissingCIK",
                "message": "Company has no local CIK mapping.",
            }
            failures.append(failure)
            print(
                f"fundamentals refresh failed ticker={failure['ticker']} "
                f"type={failure['exception_type']} message={failure['message']}"
            )
            continue
        try:
            facts = sec.company_facts(company.cik, refresh=refresh)
            submissions = sec.submissions(company.cik, refresh=False)
            section = build_fundamentals_section(
                facts,
                ticker=company.ticker,
                submissions=submissions,
                requested_years=requested_years,
            )
            path = fundamentals_path(root, company.ticker)
            save_fundamentals(section, path)
            refreshed.append(company.ticker)
            artifacts.append(str(path))
        except Exception as exc:  # noqa: BLE001 - isolate per-issuer failures
            failure = _safe_refresh_failure(company.ticker, exc)
            failures.append(failure)
            print(
                f"fundamentals refresh failed ticker={failure['ticker']} "
                f"type={failure['exception_type']} message={failure['message']}"
            )

    checked_at = datetime.now(UTC).isoformat()
    failed_tickers = sorted({row["ticker"] for row in failures})
    result = FundamentalsRefreshResult(
        status="partial" if failures else "current",
        checked_at=checked_at,
        companies_checked=len(targets) - len(failed_tickers),
        refreshed_tickers=sorted(refreshed),
        failed_tickers=failed_tickers,
        artifact_paths=artifacts,
        failures=tuple(failures),
    )
    _write_fundamentals_provenance(root / "provenance.json", result)
    return result


def _safe_refresh_failure(ticker: str, exc: BaseException) -> dict[str, str]:
    """Return a loggable failure record without credentials or request headers."""
    return {
        "ticker": ticker,
        "exception_type": type(exc).__name__,
        "message": _safe_exception_message(exc),
    }


def _safe_exception_message(exc: BaseException) -> str:
    text = str(exc).replace("\n", " ").strip() or type(exc).__name__
    # Drop credential-bearing phrases entirely, then scrub leftover token-like blobs.
    text = re.sub(
        r"(?i)\b(?:authorization|api[_-]?key|bearer|password|secret|token|cookie)\b"
        r"(?:\s*[:=]\s*|\s+)[^\s,;]+(?:\s+[A-Za-z0-9._\-]{8,})?",
        "[redacted]",
        text,
    )
    text = re.sub(r"(?i)\b[A-Za-z0-9_\-]{16,}\b", "[redacted]", text)
    return text[:240]


def _cutoff_date(events: pd.DataFrame, since: str | date | None) -> date:
    if since is not None:
        return pd.Timestamp(since).date()
    if events.empty:
        return date(2022, 1, 1)
    return pd.Timestamp(events["filing_date"].min()).date()


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_name(f".{path.name}.part")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def _write_refresh_provenance(
    path: Path, result: FilingRefreshResult, filing_count: int
) -> None:
    provenance = json.loads(path.read_text()) if path.exists() else {"source": "edgar"}
    provenance["filings"] = filing_count
    provenance["filing_refresh"] = asdict(result)
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    temporary.replace(path)


def _write_market_provenance(path: Path, result: MarketRefreshResult) -> None:
    provenance = json.loads(path.read_text()) if path.exists() else {"source": "edgar"}
    provenance["market_refresh"] = asdict(result)
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    temporary.replace(path)


def _write_fundamentals_provenance(
    path: Path, result: FundamentalsRefreshResult
) -> None:
    provenance = json.loads(path.read_text()) if path.exists() else {"source": "edgar"}
    provenance["fundamentals_refresh"] = asdict(result)
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    temporary.replace(path)
