#!/usr/bin/env node
/**
 * Build the committed development fixtures from engine output.
 *
 * Two snapshots, because the two states a company page has to survive are
 * "everything present" and "most of it absent", and a page tested only against
 * the first one is the page that renders an empty two-column block with an
 * internal field name in it.
 *
 *   SYN112  every optional section populated
 *   SYN071  prices and filings only: no filed financial report, no fundamentals,
 *           no issuer-relative score, no volatility band, no event coverage
 *
 * The base of both is a real engine snapshot, so the shapes are the engine's
 * own. The optional sections added to SYN112 are fixture values in the engine's
 * documented contract shape, and the issuers are `filing_triage.synth` output:
 * SYNxxx is not a company and none of these are market prices. The pages say so
 * when they are reading fixtures.
 *
 *   node scripts/make-fixtures.mjs
 */
import fs from "node:fs";
import path from "node:path";

const appRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const source = process.env.LENS_SNAPSHOT_DIR
  ? path.resolve(process.env.LENS_SNAPSHOT_DIR)
  : path.join(appRoot, "..", "..", "data", "build", "company_pages");
const target = path.join(appRoot, "fixtures", "snapshots");

/** Keep the shape of a curve while dropping most of its points. */
function thin(points, keep = 130) {
  if (points.length <= keep) return points;
  const stride = (points.length - 1) / (keep - 1);
  const out = [];
  for (let index = 0; index < keep; index += 1) {
    out.push(points[Math.round(index * stride)]);
  }
  return out;
}

function thinSnapshot(snapshot) {
  const copy = structuredClone(snapshot);
  copy.growth = thin(copy.growth);
  for (const option of Object.values(copy.period_options ?? {})) {
    option.growth = thin(option.growth);
  }
  for (const comparison of Object.values(copy.benchmark_comparisons ?? {})) {
    for (const option of Object.values(comparison.periods ?? {})) {
      if (option.growth) option.growth = thin(option.growth);
    }
  }
  return copy;
}

function read(ticker) {
  const file = path.join(source, `${ticker.toLowerCase()}.json`);
  if (!fs.existsSync(file)) {
    console.error(`missing engine snapshot: ${file}\nRun \`make company-pages\` first.`);
    process.exit(1);
  }
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

const quarter = { start: "2024-10-01", end: "2024-12-31" };
const priorQuarter = { start: "2023-10-01", end: "2023-12-31" };
const filed = "2025-01-28";
const sourceUrl =
  "https://www.sec.gov/Archives/edgar/data/1000112/000100011225000004/syn112-20241231.htm";

/** The filed-report section, in `company_lens.financial_results` shape. */
function financialResults() {
  const peer = (ticker, yoy) => ({
    ticker,
    yoy,
    period_end: quarter.end,
    filed: "2025-01-21",
    source_url: `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=${ticker}`,
  });
  const reference = (medianYoY, companyYoY, members) => ({
    status: "available",
    reason: null,
    sic_group: "357",
    n: members.length,
    minimum: 5,
    as_of: filed,
    median_yoy: medianYoY,
    gap_pp: (companyYoY - medianYoY) * 100,
    members,
  });
  const members = [
    peer("SYN000", 0.061),
    peer("SYN004", 0.088),
    peer("SYN033", 0.102),
    peer("SYN041", 0.044),
    peer("SYN050", 0.075),
    peer("SYN097", 0.118),
  ];
  return {
    form: "10-Q",
    period_end: quarter.end,
    filed,
    accession: "0001000112-25-000004",
    source_url: sourceUrl,
    status: "available",
    period_kind: "quarterly",
    basis: "as_reported_same_filing",
    reason: null,
    financial_issuer: false,
    sic: "3571",
    sic_description: "Electronic Computers",
    cik: "1000112",
    metrics: [
      {
        id: "revenue",
        concept: "RevenueFromContractWithCustomerExcludingAssessedTax",
        unit: "USD",
        value: 24_318_000_000,
        start: quarter.start,
        end: quarter.end,
        prior_value: 22_104_000_000,
        prior_start: priorQuarter.start,
        prior_end: priorQuarter.end,
        change: 2_214_000_000,
        yoy: 0.1001,
        reference: reference(0.075, 0.1001, members),
      },
      {
        id: "net_income",
        concept: "NetIncomeLoss",
        unit: "USD",
        value: 5_742_000_000,
        start: quarter.start,
        end: quarter.end,
        prior_value: 6_015_000_000,
        prior_start: priorQuarter.start,
        prior_end: priorQuarter.end,
        change: -273_000_000,
        yoy: null,
        reference: {
          status: "unavailable",
          reason: "no_company_growth",
          sic_group: "357",
          n: 0,
          minimum: 5,
          as_of: filed,
          median_yoy: null,
          gap_pp: null,
          members: [],
        },
      },
      {
        id: "eps",
        concept: "EarningsPerShareDiluted",
        unit: "USD/shares",
        value: 1.42,
        start: quarter.start,
        end: quarter.end,
        prior_value: 1.49,
        prior_start: priorQuarter.start,
        prior_end: priorQuarter.end,
        change: -0.07,
        yoy: null,
      },
      {
        id: "gross_profit",
        concept: "GrossProfit",
        unit: "USD",
        value: 11_206_000_000,
        start: quarter.start,
        end: quarter.end,
        prior_value: null,
        prior_start: null,
        prior_end: null,
        change: null,
        yoy: null,
      },
    ],
  };
}

/** `company_lens.contracts.FundamentalsSection`, status available. */
function fundamentals() {
  const years = [2020, 2021, 2022, 2023, 2024];
  const citation = (year, concept) => ({
    citation_id: `fact:${concept}:${year}`,
    taxonomy: "us-gaap",
    concept,
    accession: `0001000112-${String(year + 1).slice(2)}-000012`,
    form: "10-K",
    source_url: sourceUrl,
    period_start: `${year}-01-01`,
    period_end: `${year}-12-31`,
    filed_date: `${year + 1}-02-01`,
    accepted_at: `${year + 1}-02-01T16:31:00-05:00`,
    fiscal_year: year,
    fiscal_period: "FY",
    unit: "USD",
  });
  const series = (metricId, label, definition, base, growth) => ({
    metric_id: metricId,
    label,
    definition,
    expected_unit: "USD",
    concept_priority: [metricId],
    coverage_status: "complete",
    observations: years.map((year, index) => ({
      metric_id: metricId,
      value: Math.round(base * (1 + growth) ** index),
      unit: "USD",
      period_start: `${year}-01-01`,
      period_end: `${year}-12-31`,
      fiscal_year: year,
      knowledge_at: `${year + 1}-02-01T16:31:00-05:00`,
      citation: citation(year, metricId),
      quality_flags: [],
    })),
  });
  return {
    schema_version: "company-lens.fundamentals.v1",
    status: "available",
    template: "operating_company",
    requested_years: 5,
    knowledge_at: "2025-02-01T16:31:00-05:00",
    series_basis: "latest_restated",
    annual_periods: years.map((year) => ({
      fiscal_year: year,
      period_end: `${year}-12-31`,
      form: "10-K",
    })),
    reported_series: [
      series("Revenues", "Revenue", "Total revenue as filed.", 71_000_000_000, 0.09),
      series("NetIncomeLoss", "Net income", "Net income after tax, as filed.", 15_400_000_000, 0.07),
      series(
        "StockholdersEquity",
        "Shareholders' equity",
        "Total equity attributable to shareholders.",
        48_000_000_000,
        0.04,
      ),
    ],
    as_reported_series: [],
    derived_series: [
      {
        metric_id: "net_margin",
        label: "Net margin",
        definition: "Net income divided by revenue, from the two filed figures above.",
        unit: "ratio",
        observations: years.map((year, index) => ({
          metric_id: "net_margin",
          value: index === 0 ? null : 0.217 - index * 0.004,
          unit: "ratio",
          period_end: `${year}-12-31`,
          fiscal_year: year,
          status: index === 0 ? "missing_input" : "available",
          formula_version: "v1",
          components: {
            numerator: index === 0 ? null : `fact:NetIncomeLoss:${year}`,
            denominator: `fact:Revenues:${year}`,
          },
          quality_flags: [],
        })),
      },
    ],
    coverage: { years_available: 5, years_requested: 5 },
    warnings: [],
    provenance: {
      source: "SEC Company Facts",
      fetched_at: "2025-02-02T03:00:00+00:00",
    },
  };
}

function disclosureSignal(points) {
  return {
    state: "read_now",
    confidence: "standard",
    probability: 0.43,
    issuer_base_rate: 0.26,
    eligible_history: 38,
    reasons: [
      "pre-filing volume above 84% of its own history",
      "item mix differs from this issuer's usual 8-K",
    ],
    points,
    model: {
      estimator: "random_forest",
      calibration: "isotonic",
      evaluated_through: "2024-12-31",
    },
  };
}

function volatilityForecast() {
  return {
    as_of: "2024-12-31",
    horizon_sessions: 20,
    median: 0.25,
    band_low: 0.17,
    band_high: 0.38,
    issuer_median: 0.24,
    vs_issuer: 1.04,
    state: "typical for this issuer",
    forecaster: "har",
    coverage_80: 0.774,
  };
}

function headlines() {
  return [
    {
      headline: "SYN112 files fourth-quarter results",
      publisher: "Fixture Newswire",
      published_at: "2024-12-30T13:02:00+00:00",
      fetched_at: "2024-12-31T01:00:00+00:00",
      url: "https://example.invalid/fixture/syn112-q4",
      source_type: "company_news",
      ticker: "SYN112",
      topic: null,
      citation: "headline:1",
    },
    {
      headline: "SYN112 names a new chief financial officer",
      publisher: "Fixture Wire",
      published_at: "2024-12-18T20:45:00+00:00",
      fetched_at: "2024-12-19T01:00:00+00:00",
      url: "https://example.invalid/fixture/syn112-cfo",
      source_type: "company_news",
      ticker: "SYN112",
      topic: null,
      citation: "headline:2",
    },
  ];
}

function marketHeadlines() {
  return [
    {
      headline: "Index futures steady before the December reading",
      publisher: "Fixture Market Desk",
      published_at: "2024-12-30T11:00:00+00:00",
      fetched_at: "2024-12-31T01:00:00+00:00",
      url: "https://example.invalid/fixture/market-steady",
      source_type: "market_news",
      ticker: null,
      topic: "macro",
      citation: "market:1",
    },
  ];
}

fs.mkdirSync(target, { recursive: true });

// The populated page.
const rich = thinSnapshot(read("SYN112"));
rich.financial_results = financialResults();
rich.fundamentals = fundamentals();
rich.disclosure_signal = disclosureSignal(
  (rich.filing_timeline ?? []).slice(0, 8).map((point, index, all) => ({
    novelty: 0.2 + (index / Math.max(1, all.length)) * 0.7,
    reaction: Math.abs(point.reaction?.benchmark_adjusted_move ?? 0.01) * 100,
    date: point.accepted_at.slice(0, 10),
    items: point.item_code,
    current: index === 0,
  })),
);
rich.volatility_forecast = volatilityForecast();
rich.evidence_scope = {
  status: "available",
  source_types: ["sec_filing", "company_news", "fundamentals"],
  query: "SYN112 recent disclosures",
  max_chunks: 12,
  selected_chunks: 9,
  published_after: "2024-10-01",
  generated_at: "2024-12-31T02:00:00+00:00",
};
rich.headlines = headlines();
rich.market_headlines = marketHeadlines();

// The sparse page: prices and filings, and an honest absence everywhere else.
const sparse = thinSnapshot(read("SYN071"));
sparse.financial_results = { status: "unavailable", metrics: [], reason: "no_report" };
delete sparse.fundamentals;
delete sparse.disclosure_signal;
delete sparse.volatility_forecast;
delete sparse.evidence_scope;
sparse.headlines = [];
sparse.market_headlines = [];

for (const snapshot of [rich, sparse]) {
  const file = path.join(target, `${snapshot.ticker.toLowerCase()}.json`);
  fs.writeFileSync(file, `${JSON.stringify(snapshot, null, 2)}\n`);
  console.log(`${snapshot.ticker} -> ${path.relative(appRoot, file)}`);
}
