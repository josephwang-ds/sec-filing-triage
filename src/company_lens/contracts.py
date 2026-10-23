"""Stable read-model contracts shared by the CLI and a future web UI."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class Citation:
    anchor: str
    accession: str
    source_url: str
    text: str


@dataclass(frozen=True)
class FilingChange:
    kind: str
    current: Citation | None
    prior: Citation | None
    similarity: float | None = None


@dataclass(frozen=True)
class FilingComparison:
    comparable_key: str
    prior_accession: str
    prior_accepted_at: str
    prior_source_url: str
    changes: list[FilingChange]
    counts: dict[str, int]


@dataclass(frozen=True)
class FilingEntity:
    text: str
    kind: str
    normalized_value: str
    unit: str
    citation: str
    source_start: int
    source_end: int


@dataclass(frozen=True)
class FilingReaction:
    session: str
    asset_open_to_close: float
    benchmark_open_to_close: float
    benchmark_adjusted_move: float
    magnitude_percentile: float | None
    prior_sample_size: int


@dataclass(frozen=True)
class FilingBrief:
    accession: str
    form: str
    accepted_at: str
    items: list[dict[str, str]]
    source_url: str
    novelty: float | None
    key_numbers: list[dict[str, str]] = field(default_factory=list)
    entities: list[FilingEntity] = field(default_factory=list)
    passages: list[Citation] = field(default_factory=list)
    comparison: FilingComparison | None = None
    reaction: FilingReaction | None = None


@dataclass(frozen=True)
class FilingTimelinePoint:
    accession: str
    accepted_at: str
    item_code: str
    item_label: str
    source_url: str
    reaction: FilingReaction | None = None
    item_label_zh: str | None = None


@dataclass(frozen=True)
class EvidenceScopeSummary:
    status: Literal["available", "empty", "stale", "not_configured"]
    source_types: list[str]
    query: str | None
    max_chunks: int
    selected_chunks: int
    published_after: str | None
    generated_at: str | None


@dataclass(frozen=True)
class HeadlineBrief:
    headline: str
    publisher: str
    published_at: str
    fetched_at: str | None
    url: str
    source_type: Literal["company_news", "market_news"]
    ticker: str | None
    topic: str | None
    citation: str


@dataclass(frozen=True)
class FundamentalCitation:
    citation_id: str
    taxonomy: str
    concept: str
    accession: str
    form: str
    source_url: str
    period_start: str | None
    period_end: str
    filed_date: str
    accepted_at: str | None
    fiscal_year: int
    fiscal_period: str
    unit: str
    document_fy: int | None = None
    document_fp: str | None = None


@dataclass(frozen=True)
class FundamentalObservation:
    metric_id: str
    value: float
    unit: str
    period_start: str | None
    period_end: str
    fiscal_year: int
    knowledge_at: str
    citation: FundamentalCitation
    quality_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class FundamentalSeries:
    metric_id: str
    label: str
    definition: str
    expected_unit: str
    observations: tuple[FundamentalObservation, ...]
    concept_priority: tuple[str, ...]
    coverage_status: str


@dataclass(frozen=True)
class DerivedMetricObservation:
    metric_id: str
    value: float | None
    unit: str
    period_end: str
    fiscal_year: int
    status: Literal["available", "missing_input", "not_meaningful"]
    formula_version: str
    components: dict[str, str | None]
    quality_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class DerivedMetricSeries:
    metric_id: str
    label: str
    definition: str
    unit: str
    observations: tuple[DerivedMetricObservation, ...]


@dataclass(frozen=True)
class FundamentalsSection:
    schema_version: str
    status: Literal[
        "available", "not_ingested", "insufficient_history", "unsupported_template"
    ]
    template: str
    requested_years: int
    knowledge_at: str | None
    annual_periods: tuple[dict[str, Any], ...]
    reported_series: tuple[FundamentalSeries, ...]
    derived_series: tuple[DerivedMetricSeries, ...]
    coverage: dict[str, Any]
    warnings: tuple[str, ...]
    provenance: dict[str, Any]
    as_reported_series: tuple[FundamentalSeries, ...] = ()
    series_basis: str = "latest_restated"


@dataclass(frozen=True)
class CompanySnapshot:
    schema_version: str
    ticker: str
    company_name: str
    as_of: str
    benchmark: str
    period: dict[str, str]
    profile: dict[str, Any]
    market: dict[str, Any]
    performance: dict[str, Any]
    growth: list[dict[str, Any]]
    period_options: dict[str, dict[str, Any]]
    latest_filings: list[FilingBrief]
    explanation: dict[str, Any]
    provenance: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    filing_timeline: list[FilingTimelinePoint] = field(default_factory=list)
    evidence_scope: EvidenceScopeSummary | None = None
    headlines: list[HeadlineBrief] = field(default_factory=list)
    """Headlines about this issuer specifically."""
    market_headlines: list[HeadlineBrief] = field(default_factory=list)
    """Broad market and sector headlines, shared across issuers.

    Kept apart from `headlines` rather than merged, because the two answer
    different questions and a reader must be able to tell which one a claim came
    from. Repeating the same general-market rows on every company page as if
    they were company evidence is exactly the confusion the split prevents."""
    fundamentals: FundamentalsSection | None = None
    disclosure_signal: dict[str, Any] | None = None
    """The latest filing measured against this issuer's own filing history.

    Optional, and the page degrades rather than fails without it: it is produced
    by a separate scoring run, and a company page must stay readable when that
    run has not happened. Everything inside is issuer-relative -- a percentile
    against this company's past, never a rank against other companies -- and it
    describes reaction *magnitude*, which carries no direction."""
    volatility_forecast: dict[str, Any] | None = None
    """How wide a range the next twenty sessions are expected to cover.

    Also optional, and present only when a forecaster passed its coverage gate
    out of sample -- the export writes the file for a calibrated forecaster and
    deletes it otherwise, so this field is absent rather than misleading when
    nothing earned it. A band and a horizon, never a direction: it says how much
    movement to expect, not which way."""
    benchmark_comparisons: dict[str, dict[str, Any]] = field(default_factory=dict)
    """Optional alternative history benchmarks, keyed by symbol (e.g. QQQ).

    Each entry mirrors `period_options` for one company/benchmark pair on
    exactly matched dates, or records why the pair is unavailable. `benchmark`,
    `performance`, filing reactions and AI evidence stay on the default
    benchmark; these entries only feed the history comparison selector."""
    financial_results: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.financial_results is None:
            payload.pop("financial_results")
        if not self.benchmark_comparisons:
            payload.pop("benchmark_comparisons")
        if self.evidence_scope is None:
            payload.pop("evidence_scope")
            payload.pop("headlines")
            payload.pop("market_headlines")
        if self.fundamentals is None:
            payload.pop("fundamentals")
        if self.disclosure_signal is None:
            payload.pop("disclosure_signal")
        if self.volatility_forecast is None:
            payload.pop("volatility_forecast")
        return payload
