"""Assemble one cacheable company snapshot from local source artifacts."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from company_lens.contracts import (
    CompanySnapshot,
    EvidenceScopeSummary,
    HeadlineBrief,
)
from company_lens.filings import build_filing_briefs, build_filing_timeline
from company_lens.financial_results import load_financial_results
from company_lens.fundamentals import try_load_fundamentals
from company_lens.llm import ImportedDocument, deterministic_explanation, import_headline_index
from company_lens.performance import historical_picture
from company_lens.profiles import company_profile
from company_lens.reactions import build_filing_reactions
from company_lens.universe import (
    SupportedCompany,
    resolve_supported_company,
    supported_companies,
)
from filing_triage.ingest.prices import load_prices

DEFAULT_PERIODS = (1, 3, 5, 10)
COMPARISON_BENCHMARKS = ("QQQ",)
# A period is "partial" when matched history starts this much after the
# requested boundary (IPO, benchmark inception or a short cache).
PARTIAL_COVERAGE_DAYS = 7


def build_snapshot(
    ticker: str,
    *,
    data_dir: str | Path = "data/build",
    benchmark: str = "SPY",
    comparison_benchmarks: tuple[str, ...] = COMPARISON_BENCHMARKS,
    years: int = 5,
    initial_investment: float = 10_000.0,
    headline_index: str | Path | None = None,
) -> CompanySnapshot:
    """Build a complete, no-network company page read model."""
    return build_snapshots(
        [ticker],
        data_dir=data_dir,
        benchmark=benchmark,
        comparison_benchmarks=comparison_benchmarks,
        years=years,
        initial_investment=initial_investment,
        headline_index=headline_index,
    )[0]


def build_snapshots(
    tickers: list[str] | tuple[str, ...] | None = None,
    *,
    data_dir: str | Path = "data/build",
    benchmark: str = "SPY",
    comparison_benchmarks: tuple[str, ...] = COMPARISON_BENCHMARKS,
    years: int = 5,
    initial_investment: float = 10_000.0,
    headline_index: str | Path | None = None,
) -> list[CompanySnapshot]:
    """Build many snapshots while loading the shared local artifacts only once."""
    root = Path(data_dir)
    universe_path = root / "universe.csv"
    companies = (
        supported_companies(universe_path)
        if tickers is None
        else [resolve_supported_company(ticker, universe_path) for ticker in tickers]
    )
    prices = load_prices(root / "prices.parquet")
    events = pd.read_parquet(root / "events.parquet")
    headline_documents = (
        import_headline_index(headline_index) if headline_index is not None else None
    )
    price_tickers = prices["ticker"].astype(str).str.upper()
    event_tickers = events["ticker"].astype(str).str.upper()
    benchmark_rows = prices[price_tickers == benchmark.upper()]
    comparison_rows = {
        symbol: prices[price_tickers == symbol]
        for symbol in dict.fromkeys(item.upper() for item in comparison_benchmarks)
        if symbol != benchmark.upper()
    }
    price_groups = _group_frames(
        prices[price_tickers != benchmark.upper()],
        prices.loc[price_tickers != benchmark.upper(), "ticker"].astype(str).str.upper(),
    )
    event_groups = _group_frames(events, event_tickers)
    return [
        _assemble_snapshot(
            company,
            root,
            pd.concat([price_groups.get(company.ticker, pd.DataFrame()), benchmark_rows]),
            event_groups.get(company.ticker, events.iloc[0:0]),
            benchmark=benchmark,
            comparison_rows=comparison_rows,
            years=years,
            initial_investment=initial_investment,
            headline_documents=headline_documents,
        )
        for company in companies
    ]


def _group_frames(frame: pd.DataFrame, keys: pd.Series) -> dict[str, pd.DataFrame]:
    """Materialize ticker groups without relying on GroupBy's mapping protocol."""
    return {str(ticker): group for ticker, group in frame.groupby(keys, sort=False)}


def _assemble_snapshot(
    company: SupportedCompany,
    root: Path,
    prices: pd.DataFrame,
    events: pd.DataFrame,
    *,
    benchmark: str,
    comparison_rows: dict[str, pd.DataFrame] | None = None,
    years: int,
    initial_investment: float,
    headline_documents: list[ImportedDocument] | None,
) -> CompanySnapshot:
    ticker = company.ticker

    requested_periods = tuple(dict.fromkeys((*DEFAULT_PERIODS, years)))
    period_options = {}
    for option_years in requested_periods:
        option_metrics, option_growth = historical_picture(
            prices, ticker, benchmark, option_years, initial_investment
        )
        period_options[f"{option_years}Y"] = _period_view(
            option_metrics, option_growth, option_years
        )

    selected = period_options[f"{years}Y"]
    metrics = selected["performance"]
    growth = selected["growth"]
    reactions = build_filing_reactions(events, prices, ticker, benchmark)
    filings = build_filing_briefs(events, ticker, reactions=reactions)
    filing_timeline = build_filing_timeline(events, ticker, reactions=reactions)
    market_rows = prices[prices["ticker"].str.upper() == ticker]
    benchmark_comparisons = {
        symbol: _benchmark_comparison(
            market_rows, rows, ticker, symbol, requested_periods, initial_investment
        )
        for symbol, rows in (comparison_rows or {}).items()
    }
    company_name, cik = company.official_name, company.cik
    first_market = market_rows.sort_values("date").iloc[0]
    last_market = market_rows.sort_values("date").iloc[-1]
    period = {"start": growth[0]["date"], "end": growth[-1]["date"]}
    warnings = []
    if not filings:
        warnings.append("No 8-K filing was available in the local event dataset.")
    evidence_scope, headlines, market_headlines = _headline_context(
        headline_documents, ticker)
    fundamentals = try_load_fundamentals(root, ticker, requested_years=10)

    provenance = _provenance(root / "provenance.json")
    provenance.update(
        {
            "prices_artifact": "prices.parquet",
            "events_artifact": "events.parquet",
            "generated_at": datetime.now(UTC).isoformat(),
            "calculation": "company_lens.v2.0",
            "filing_reaction": (
                "issuer open-to-close return on the first eligible session after SEC "
                "acceptance, less benchmark open-to-close return; magnitude percentile "
                "uses only earlier measurable issuer filings"
            ),
            "chart_sampling": "deterministic stride; at most 520 points per period",
            "fundamentals_status": fundamentals.status,
        }
    )
    explanation = deterministic_explanation(ticker, metrics, filings)
    profile = company_profile(
        ticker,
        company_name,
        cik,
        price_start=pd.Timestamp(first_market["date"]).date().isoformat(),
        price_end=pd.Timestamp(last_market["date"]).date().isoformat(),
        filing_count=len(filings),
    )
    return CompanySnapshot(
        schema_version="2.0",
        ticker=ticker,
        company_name=company_name,
        as_of=period["end"],
        benchmark=benchmark.upper(),
        period=period,
        profile=profile,
        market={
            "latest_adjusted_close": float(last_market["close"]),
            "price_date": pd.Timestamp(last_market["date"]).date().isoformat(),
            "price_field": "vendor-adjusted close",
        },
        performance=metrics,
        growth=growth,
        period_options=period_options,
        latest_filings=filings,
        explanation=explanation,
        provenance=provenance,
        warnings=warnings,
        filing_timeline=filing_timeline,
        evidence_scope=evidence_scope,
        headlines=headlines,
        market_headlines=market_headlines,
        fundamentals=fundamentals,
        disclosure_signal=_disclosure_signal(root, ticker),
        volatility_forecast=_volatility_forecast(root, ticker),
        benchmark_comparisons=benchmark_comparisons,
        financial_results=load_financial_results(root, ticker),
    )


def _period_view(metrics: dict, growth: list[dict], years: int) -> dict:
    """One period's chart and metrics, with the matched overlap disclosed."""
    chart_growth = _downsample_growth(growth)
    start, end = growth[0]["date"], growth[-1]["date"]
    requested_start = (pd.Timestamp(end) - pd.DateOffset(years=years)).date().isoformat()
    shortfall = (pd.Timestamp(start) - pd.Timestamp(requested_start)).days
    return {
        "period": {"start": chart_growth[0]["date"], "end": chart_growth[-1]["date"]},
        "performance": metrics,
        "growth": chart_growth,
        "coverage": {
            "status": "partial" if shortfall > PARTIAL_COVERAGE_DAYS else "full",
            "requested_start": requested_start,
            "start": start,
            "end": end,
            "observations": metrics["observations"],
        },
    }


def _benchmark_comparison(
    company_rows: pd.DataFrame,
    benchmark_rows: pd.DataFrame,
    ticker: str,
    symbol: str,
    periods: tuple[int, ...],
    initial_investment: float,
) -> dict:
    """Company/benchmark history on exactly matched dates, or why it is unavailable.

    A benchmark whose cache ends before the company's prices is withheld rather
    than charted over a shorter window under the same period label.
    """
    if benchmark_rows.empty:
        return {"symbol": symbol, "status": "unavailable", "reason": "missing_prices",
                "periods": {}}
    company_end = pd.Timestamp(company_rows["date"].max()).date().isoformat()
    benchmark_end = pd.Timestamp(benchmark_rows["date"].max()).date().isoformat()
    if benchmark_end < company_end:
        return {"symbol": symbol, "status": "unavailable", "reason": "stale_prices",
                "price_end": benchmark_end, "company_end": company_end, "periods": {}}
    pair = pd.concat([company_rows, benchmark_rows])
    views: dict[str, dict] = {}
    for option_years in periods:
        label = f"{option_years}Y"
        try:
            metrics, growth = historical_picture(
                pair, ticker, symbol, option_years, initial_investment
            )
            # Sample volatility/covariance need at least two returns. A two-row
            # cache produces NaN, which would break JSON.parse for the whole page.
            if metrics["observations"] < 3:
                raise ValueError("not enough returns for comparison risk metrics")
            # Withhold a corrupt optional comparison without breaking the fixed
            # benchmark, chart, language controls or question initialization.
            json.dumps({"performance": metrics, "growth": growth}, allow_nan=False)
        except ValueError:
            views[label] = {"status": "unavailable", "reason": "insufficient_overlap"}
            continue
        views[label] = {"status": "available", **_period_view(metrics, growth, option_years)}
    available = any(view["status"] == "available" for view in views.values())
    return {
        "symbol": symbol,
        "status": "available" if available else "unavailable",
        "reason": None if available else "insufficient_overlap",
        "price_end": benchmark_end,
        "periods": views,
    }


def _disclosure_signal(data_dir: Path, ticker: str) -> dict | None:
    """This issuer's latest-filing card, when a scoring run has produced one.

    Read from a file rather than computed here, and absent by default. The
    scoring pipeline is expensive and lives in `filing_triage`; importing it
    would make every company page depend on a model being loadable, and a page
    that cannot render without a model is a page that breaks whenever the model
    does. Missing file, missing section, everything else unchanged.
    """
    path = Path(data_dir) / "self_relative_cards.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    card = (payload.get("companies") or {}).get(str(ticker).upper())
    if not card:
        return None
    return {**card, "model": payload.get("model", {}),
            "boundary": payload.get("boundary", "")}


def _volatility_forecast(data_dir: Path, ticker: str) -> dict | None:
    """The 20-session volatility band, when a forecaster earned the right to one.

    The export writes this file only for a forecaster whose out-of-sample
    intervals passed their coverage gate, and deletes it when none does. So the
    card's precondition is enforced upstream, in the place that has the numbers,
    rather than by a threshold repeated here where it would drift.
    """
    path = Path(data_dir) / "volatility_cards.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    card = (payload.get("cards") or {}).get(str(ticker).upper())
    if not card:
        return None
    return {**card,
            "coverage_50": payload.get("coverage_50"),
            "coverage_80": payload.get("coverage_80")}


def _provenance(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {"source": "unknown"}


def _headline_context(
    documents: list[ImportedDocument] | None,
    ticker: str,
    *,
    now: datetime | None = None,
) -> tuple[EvidenceScopeSummary | None, list[HeadlineBrief], list[HeadlineBrief]]:
    if documents is None:
        return None, [], []
    ticker = ticker.upper()
    company_matches = [
        document
        for document in documents
        if document.source_type == "company_news"
        and (
            document.ticker == ticker
            or ticker in document.tickers
        )
    ]
    company_ranked = sorted(
        company_matches,
        key=lambda document: (
            -_timestamp(document.published_at).timestamp(),
            document.document_id,
        ),
    )
    market_matches = [
        document for document in documents if document.source_type == "market_news"
    ]
    market_ranked = sorted(
        market_matches,
        key=lambda document: (
            -_timestamp(document.published_at).timestamp(),
            document.document_id,
        ),
    )

    # Company and market rows stay in separate lists. They used to be merged and
    # then filtered down to company-only, on the reasoning that a company page
    # must not repeat the same generic market headlines for every ticker -- which
    # is right, and is a reason to *label* them rather than to drop them. The
    # market context selector is what consumes the second list, and a reader can
    # always see which of the two a cited headline came from.
    selected = company_ranked[:3]
    matching = company_matches
    headlines = [_brief(document) for document in selected]
    market_headlines = [_brief(document) for document in market_ranked[:3]]
    fetched_times = [
        _timestamp(document.fetched_at)
        for document in matching
        if document.fetched_at
    ]
    current = now or datetime.now(UTC)
    stale = bool(fetched_times) and max(fetched_times) < current - timedelta(days=2)
    status = "empty" if not matching else "stale" if stale else "available"
    return (
        EvidenceScopeSummary(
            status=status,
            source_types=sorted(
                {document.source_type for document in (*matching, *market_matches)}),
            query=None,
            max_chunks=0,
            selected_chunks=0,
            published_after=None,
            generated_at=current.isoformat(),
        ),
        headlines,
        market_headlines,
    )


def _brief(document: ImportedDocument) -> HeadlineBrief:
    return HeadlineBrief(
        headline=document.title,
        publisher=document.source_name,
        published_at=document.published_at or "",
        fetched_at=document.fetched_at,
        url=document.source_url,
        source_type=document.source_type,
        ticker=document.ticker,
        topic=document.topic,
        citation=f"news:{document.document_id}#headline",
    )


def _timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=UTC)
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _downsample_growth(
    growth: list[dict], max_points: int = 520
) -> list[dict]:
    """Bound chart payload size without changing daily-input metric calculations."""
    if len(growth) <= max_points:
        return growth
    stride = math.ceil((len(growth) - 1) / (max_points - 1))
    sampled = growth[::stride]
    if sampled[-1] != growth[-1]:
        sampled.append(growth[-1])
    return sampled
