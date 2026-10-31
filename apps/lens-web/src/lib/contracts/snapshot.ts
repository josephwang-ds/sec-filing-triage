/**
 * The company snapshot contract, mirrored from `src/company_lens/contracts.py`.
 *
 * This file is a *reader*. Every number it describes was computed by the Python
 * research engine and is displayed as given; nothing here recalculates a
 * return, a drawdown, a beta or a percentile. Where a value is missing the
 * contract says so with `null` and the UI shows an absence rather than a zero.
 *
 * Objects are loose on purpose. The engine adds fields faster than a front end
 * needs them, and a snapshot carrying something new must still render instead
 * of failing the build. What is listed below is what the UI actually reads, and
 * that part is validated.
 */
import { z } from "zod";

export const citation = z.looseObject({
  anchor: z.string(),
  accession: z.string(),
  source_url: z.string(),
  text: z.string(),
});

export const filingReaction = z.looseObject({
  session: z.string(),
  asset_open_to_close: z.number(),
  benchmark_open_to_close: z.number(),
  benchmark_adjusted_move: z.number(),
  magnitude_percentile: z.number().nullable().default(null),
  prior_sample_size: z.number(),
});

export const filingItem = z.looseObject({
  code: z.string(),
  label: z.string(),
  label_zh: z.string().nullish(),
});

export const filingChange = z.looseObject({
  kind: z.string(),
  current: citation.nullable(),
  prior: citation.nullable(),
  similarity: z.number().nullish(),
});

export const filingComparison = z.looseObject({
  comparable_key: z.string(),
  prior_accession: z.string(),
  prior_accepted_at: z.string(),
  prior_source_url: z.string(),
  changes: z.array(filingChange).default([]),
  counts: z.record(z.string(), z.number()).default({}),
});

export const filingEntity = z.looseObject({
  text: z.string(),
  kind: z.string(),
  normalized_value: z.string(),
  unit: z.string(),
  citation: z.string(),
});

export const keyNumber = z.looseObject({
  label: z.string().nullish(),
  value: z.string().nullish(),
  anchor: z.string().nullish(),
});

export const filingBrief = z.looseObject({
  accession: z.string(),
  form: z.string(),
  accepted_at: z.string(),
  items: z.array(filingItem).default([]),
  source_url: z.string(),
  novelty: z.number().nullish(),
  key_numbers: z.array(keyNumber).default([]),
  entities: z.array(filingEntity).default([]),
  passages: z.array(citation).default([]),
  comparison: filingComparison.nullish(),
  reaction: filingReaction.nullish(),
});

export const filingTimelinePoint = z.looseObject({
  accession: z.string(),
  accepted_at: z.string(),
  item_code: z.string(),
  item_label: z.string(),
  item_label_zh: z.string().nullish(),
  source_url: z.string(),
  reaction: filingReaction.nullish(),
});

/** One side of a period comparison: the issuer, or its benchmark. */
export const periodStats = z.looseObject({
  total_return: z.number(),
  cagr: z.number(),
  annualized_volatility: z.number(),
  max_drawdown: z.number(),
  current_drawdown: z.number().nullish(),
  max_drawdown_date: z.string().nullish(),
  recovery_sessions: z.number().nullish(),
  worst_day: z.number().nullish(),
});

export const performance = z.looseObject({
  initial_investment: z.number(),
  ending_value: z.number(),
  asset: periodStats,
  benchmark: periodStats,
  relative_total_return: z.number(),
  beta: z.number().nullish(),
  correlation: z.number().nullish(),
  observations: z.number(),
  dividends: z.string().nullish(),
});

export const growthPoint = z.looseObject({
  date: z.string(),
  asset_value: z.number(),
  benchmark_value: z.number(),
});

export const coverage = z.looseObject({
  status: z.string(),
  requested_start: z.string().nullish(),
  start: z.string().nullish(),
  end: z.string().nullish(),
  observations: z.number().nullish(),
  reason: z.string().nullish(),
});

export const periodOption = z.looseObject({
  period: z.looseObject({ start: z.string(), end: z.string() }),
  performance,
  growth: z.array(growthPoint).default([]),
  coverage: coverage.nullish(),
});

/**
 * An alternative history benchmark (QQQ today).
 *
 * Either a period record carrying real numbers or a recorded reason the pair is
 * unavailable — never a silent gap, because a missing comparison rendered as an
 * enabled button is how a reader ends up reading SPY numbers under a QQQ label.
 */
export const benchmarkComparisonPeriod = z.looseObject({
  status: z.string(),
  reason: z.string().nullish(),
  period: z.looseObject({ start: z.string(), end: z.string() }).nullish(),
  performance: performance.nullish(),
  growth: z.array(growthPoint).default([]),
  coverage: coverage.nullish(),
});

export const benchmarkComparison = z.looseObject({
  symbol: z.string(),
  status: z.string(),
  reason: z.string().nullish(),
  /** Present when the benchmark's own history ends before the company's. */
  price_end: z.string().nullish(),
  company_end: z.string().nullish(),
  periods: z.record(z.string(), benchmarkComparisonPeriod).default({}),
});

export const evidenceScope = z.looseObject({
  status: z.enum(["available", "empty", "stale", "not_configured"]),
  source_types: z.array(z.string()).default([]),
  query: z.string().nullish(),
  max_chunks: z.number().nullish(),
  selected_chunks: z.number().nullish(),
  published_after: z.string().nullish(),
  generated_at: z.string().nullish(),
});

export const headline = z.looseObject({
  headline: z.string(),
  publisher: z.string(),
  published_at: z.string(),
  fetched_at: z.string().nullish(),
  url: z.string(),
  source_type: z.enum(["company_news", "market_news"]),
  ticker: z.string().nullish(),
  topic: z.string().nullish(),
  citation: z.string(),
});

export const claim = z.looseObject({
  text: z.string(),
  text_zh: z.string().nullish(),
  citations: z.array(z.string()).default([]),
});

export const explanation = z.looseObject({
  mode: z.string().nullish(),
  what_changed: z.array(claim).default([]),
  why_it_matters: z.array(claim).default([]),
  uncertainties: z.array(claim).default([]),
});

export const fundamentalCitation = z.looseObject({
  citation_id: z.string(),
  taxonomy: z.string().nullish(),
  concept: z.string().nullish(),
  accession: z.string().nullish(),
  form: z.string().nullish(),
  source_url: z.string().nullish(),
  period_end: z.string().nullish(),
  fiscal_year: z.number().nullish(),
  fiscal_period: z.string().nullish(),
  unit: z.string().nullish(),
});

export const fundamentalObservation = z.looseObject({
  metric_id: z.string(),
  value: z.number().nullish(),
  unit: z.string().nullish(),
  period_start: z.string().nullish(),
  period_end: z.string().nullish(),
  fiscal_year: z.number().nullish(),
  knowledge_at: z.string().nullish(),
  citation: fundamentalCitation.nullish(),
  quality_flags: z.array(z.string()).default([]),
});

export const fundamentalSeries = z.looseObject({
  metric_id: z.string(),
  label: z.string(),
  definition: z.string().nullish(),
  expected_unit: z.string().nullish(),
  observations: z.array(fundamentalObservation).default([]),
  coverage_status: z.string().nullish(),
});

export const derivedObservation = z.looseObject({
  metric_id: z.string(),
  value: z.number().nullish(),
  unit: z.string().nullish(),
  period_end: z.string().nullish(),
  fiscal_year: z.number().nullish(),
  status: z.string(),
  formula_version: z.string().nullish(),
  components: z.record(z.string(), z.string().nullable()).default({}),
  quality_flags: z.array(z.string()).default([]),
});

export const derivedSeries = z.looseObject({
  metric_id: z.string(),
  label: z.string(),
  definition: z.string().nullish(),
  unit: z.string().nullish(),
  observations: z.array(derivedObservation).default([]),
});

export const fundamentals = z.looseObject({
  schema_version: z.string().nullish(),
  status: z.string(),
  template: z.string().nullish(),
  requested_years: z.number().nullish(),
  knowledge_at: z.string().nullish(),
  annual_periods: z.array(z.looseObject({})).default([]),
  reported_series: z.array(fundamentalSeries).default([]),
  derived_series: z.array(derivedSeries).default([]),
  as_reported_series: z.array(fundamentalSeries).default([]),
  series_basis: z.string().nullish(),
  coverage: z.looseObject({}).nullish(),
  warnings: z.array(z.string()).default([]),
  provenance: z.looseObject({}).nullish(),
});

/**
 * One peer-growth reference for a filed metric.
 *
 * `status` is load-bearing: the engine withholds the comparison below five
 * eligible issuers and records why, and a card that showed the median anyway
 * would be reporting a sample of two as an industry rate.
 */
export const metricReference = z.looseObject({
  status: z.enum(["available", "unavailable"]),
  reason: z.string().nullish(),
  sic_group: z.string().nullish(),
  n: z.number(),
  minimum: z.number(),
  as_of: z.string().nullish(),
  median_yoy: z.number().nullish(),
  gap_pp: z.number().nullish(),
  members: z
    .array(
      z.looseObject({
        ticker: z.string(),
        yoy: z.number(),
        period_end: z.string(),
        filed: z.string().nullish(),
        source_url: z.string(),
      }),
    )
    .default([]),
});

export const filedMetric = z.looseObject({
  id: z.string(),
  concept: z.string(),
  unit: z.string(),
  value: z.number(),
  start: z.string(),
  end: z.string(),
  prior_value: z.number().nullish(),
  prior_start: z.string().nullish(),
  prior_end: z.string().nullish(),
  change: z.number().nullish(),
  /** Absent for a loss or zero base, where a growth rate means nothing. */
  yoy: z.number().nullish(),
  reference: metricReference.nullish(),
});

export const financialResults = z.looseObject({
  status: z.string(),
  reason: z.string().nullish(),
  metrics: z.array(filedMetric).default([]),
  form: z.string().nullish(),
  period_end: z.string().nullish(),
  filed: z.string().nullish(),
  accession: z.string().nullish(),
  source_url: z.string().nullish(),
  period_kind: z.string().nullish(),
  basis: z.string().nullish(),
  financial_issuer: z.boolean().nullish(),
  sic: z.string().nullish(),
  sic_description: z.string().nullish(),
  cik: z.string().nullish(),
});

export const disclosureSignalPoint = z.looseObject({
  novelty: z.number(),
  reaction: z.number(),
  date: z.string().nullish(),
  items: z.string().nullish(),
  current: z.boolean().nullish(),
});

export const disclosureSignal = z.looseObject({
  state: z.string(),
  reasons: z.array(z.string()).default([]),
  probability: z.number().nullish(),
  issuer_base_rate: z.number().nullish(),
  eligible_history: z.number().nullish(),
  confidence: z.string().nullish(),
  points: z.array(disclosureSignalPoint).default([]),
  model: z
    .looseObject({
      estimator: z.string().nullish(),
      calibration: z.string().nullish(),
      evaluated_through: z.string().nullish(),
    })
    .nullish(),
});

export const volatilityForecast = z.looseObject({
  as_of: z.string().nullish(),
  horizon_sessions: z.number().nullish(),
  median: z.number().nullish(),
  band_low: z.number().nullish(),
  band_high: z.number().nullish(),
  issuer_median: z.number().nullish(),
  vs_issuer: z.number().nullish(),
  state: z.string().nullish(),
  forecaster: z.string().nullish(),
  coverage_80: z.number().nullish(),
});

export const companySnapshot = z.looseObject({
  schema_version: z.string(),
  ticker: z.string(),
  company_name: z.string(),
  as_of: z.string(),
  benchmark: z.string(),
  period: z.looseObject({ start: z.string().nullish(), end: z.string().nullish() }),
  profile: z.looseObject({
    display_name: z.string().nullish(),
    official_name: z.string().nullish(),
    category: z.string().nullish(),
    category_zh: z.string().nullish(),
    summary: z.string().nullish(),
    summary_zh: z.string().nullish(),
    cik: z.string().nullish(),
    source_label: z.string().nullish(),
    source_url: z.string().nullish(),
    method: z.string().nullish(),
    coverage: z
      .looseObject({
        price_start: z.string().nullish(),
        price_end: z.string().nullish(),
        filings_in_snapshot: z.number().nullish(),
      })
      .nullish(),
  }),
  market: z.looseObject({
    latest_adjusted_close: z.number().nullish(),
    price_date: z.string().nullish(),
    price_field: z.string().nullish(),
  }),
  performance,
  growth: z.array(growthPoint).default([]),
  period_options: z.record(z.string(), periodOption).default({}),
  latest_filings: z.array(filingBrief).default([]),
  explanation: explanation.default({ what_changed: [], why_it_matters: [], uncertainties: [] }),
  provenance: z.record(z.string(), z.unknown()).default({}),
  warnings: z.array(z.string()).default([]),
  filing_timeline: z.array(filingTimelinePoint).default([]),
  evidence_scope: evidenceScope.nullish(),
  headlines: z.array(headline).default([]),
  market_headlines: z.array(headline).default([]),
  fundamentals: fundamentals.nullish(),
  financial_results: financialResults.nullish(),
  disclosure_signal: disclosureSignal.nullish(),
  volatility_forecast: volatilityForecast.nullish(),
  benchmark_comparisons: z.record(z.string(), benchmarkComparison).default({}),
});

export type Citation = z.infer<typeof citation>;
export type FilingReaction = z.infer<typeof filingReaction>;
export type FilingBrief = z.infer<typeof filingBrief>;
export type FilingTimelinePoint = z.infer<typeof filingTimelinePoint>;
export type PeriodStats = z.infer<typeof periodStats>;
export type Performance = z.infer<typeof performance>;
export type GrowthPoint = z.infer<typeof growthPoint>;
export type PeriodOption = z.infer<typeof periodOption>;
export type BenchmarkComparisonPeriod = z.infer<typeof benchmarkComparisonPeriod>;
export type BenchmarkComparison = z.infer<typeof benchmarkComparison>;
export type Headline = z.infer<typeof headline>;
export type Claim = z.infer<typeof claim>;
export type Explanation = z.infer<typeof explanation>;
export type Fundamentals = z.infer<typeof fundamentals>;
export type FinancialResults = z.infer<typeof financialResults>;
export type FiledMetric = z.infer<typeof filedMetric>;
export type MetricReference = z.infer<typeof metricReference>;
export type FundamentalSeries = z.infer<typeof fundamentalSeries>;
export type DerivedSeries = z.infer<typeof derivedSeries>;
export type DisclosureSignal = z.infer<typeof disclosureSignal>;
export type VolatilityForecast = z.infer<typeof volatilityForecast>;
export type EvidenceScope = z.infer<typeof evidenceScope>;
export type CompanySnapshot = z.infer<typeof companySnapshot>;

/** A comparison period that carries real numbers, as opposed to a recorded absence. */
export function hasComparisonNumbers(
  value: BenchmarkComparisonPeriod | undefined,
): value is BenchmarkComparisonPeriod & { performance: Performance } {
  return Boolean(value && value.status === "available" && value.performance);
}
