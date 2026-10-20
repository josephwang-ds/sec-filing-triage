# Company Lens — Implementation Roadmap

This roadmap converts the current Filing Triage project into the product defined
in [PRODUCT.md](PRODUCT.md) without restoring the old Quant Research OS. The MVP
boundary and demo narrative are defined in [SCOPE.md](SCOPE.md); stretch features
must not displace those acceptance criteria.

## MVP delivery order

The phase numbers below describe dependency, not parallel feature tracks. Finish in
this order:

1. correct and freeze the Filing Triage evidence;
2. finish the deterministic AAPL/MSFT/NVDA company snapshots;
3. ingest an earnings exhibit and compare it with the prior comparable filing;
4. add the validated cited brief;
5. build and polish one company page;
6. add minimal cached refresh automation; and
7. stop unless every item in the scope definition is demonstrably complete.

Portfolio, broad Q&A, bilingual output, and additional SEC forms remain stretch work.

## Delivery principle

Build one complete company page before adding breadth. A smaller product with a
clear source-to-answer chain is more useful and more credible than many partially
connected research modules.

## Phase 0 — Make the current evidence trustworthy ✅

Completed 2026-08-24. The public result now uses a fixed 2.0-sigma ex-ante
threshold, causal missing-value handling, an exact 120-session estimation window,
matched-session random/arrival/Item-2.02 baselines, held-out-fold permutation
importance, a committed real-run evidence package, 153 passing tests, and a clean
Ruff run. The decision target is explicitly the abnormal reaction after the next
market-open queue, not a claim about first-publication reaction or tradability.

Purpose: preserve Filing Triage as the quantitative and data-quality foundation.

### Work

- define one consistent decision cutoff for the filing-ranking use case;
- prefer a morning queue of post-close and pre-market filings, or explicitly rename
  the target if intraday filings remain in scope;
- replace the global reaction-quantile label with a fixed ex-ante threshold or a
  continuous ranking target;
- remove full-sample median imputation from temporal validation;
- report operational baselines:
  - arrival order;
  - random within the same eligible session; and
  - a simple item-code heuristic;
- calculate feature importance out of sample;
- fix the estimation-window off-by-one;
- reconcile README claims with the real run;
- commit a small, non-sensitive evidence package containing provenance, metrics,
  fold results, audit results, and leakage-study results;
- make tests and Ruff pass in CI.

### Acceptance

- no full-sample statistic is used to construct test-fold features or targets;
- the product metric is compared with at least two realistic baselines;
- all published headline figures can be traced to committed evidence artifacts;
- data source, sample period, universe limitation, and decision cutoff are explicit;
- tests and lint pass locally and in CI.

## Phase 1 — Single-company overview ✅

Completed 2026-08-24. Snapshot v1.2 now includes a bounded company profile and
observable evidence coverage. The self-contained entry searches every company in
the current local evidence universe, reports genuinely unavailable companies
honestly, and keeps AAPL/MSFT/NVDA as featured examples. Every local company page
uses four selectable periods, complete declared risk metrics, five recent 8-Ks,
source passages, and deterministic fallback explanations.

Purpose: ship the ordinary user's main experience before adding more AI.

### Work

- ticker search and supported-company resolution;
- company identity and business profile;
- latest market observation and freshness;
- historical adjusted-price series;
- growth-of-$10,000 chart against SPY;
- total return, CAGR, volatility, beta, correlation, max drawdown, current drawdown,
  worst periods, and recovery duration;
- latest filing list with form, item codes, acceptance time, and SEC links;
- a cached company snapshot contract consumed by the UI.

### Acceptance

- one ticker produces a complete page from source data;
- all metrics use the same selected period and declared benchmark;
- historical return is clearly separated from forecast or advice;
- missing data produces an explanation rather than zero or a fabricated value;
- the page remains useful without an LLM key.

## Phase 2 — Filing intelligence and NLP (in progress)

Snapshot v1.6 adds causal prior-comparable-filing resolution keyed by form and
primary SEC item, anchored changed/added/removed sentences, full change counts,
typed amount/percentage/date entities with passage-relative source spans, and an
honest missing-comparison state. It also adds retrospective filing-reaction context:
the issuer's open-to-close move on the first eligible session after acceptance,
less SPY for that same session, with a magnitude percentile computed only against
earlier measurable issuer filings. The first evaluation artifact contains four
hand-labeled smoke cases and currently scores 1.000 precision/recall/F1; it proves
the harness and basic behaviors, not production-level generalization. Exhibit
ingestion, table anchors, and broader labeled evaluation cases remain. The issuer
timeline now links the latest eight filings to their benchmark-adjusted reaction
context in chronological order.

Purpose: turn Filing Triage into a source-reading product.

### Work

- preserve document structure and stable paragraph anchors during ingestion;
- classify filing sections and event types;
- extract named entities, dates, amounts, and percentages with source spans;
- rank key passages;
- compare a filing with the issuer's prior comparable filing;
- expose novelty, changed passages, and historical reaction percentile;
- add an issuer filing timeline aligned with price context;
- create a small labeled evaluation set for event and passage extraction.

### Acceptance

- every extracted fact links to a stable source span;
- numeric extraction passes consistency checks against the cited text;
- changed and unchanged statements are evaluated separately;
- sentiment is not used as a substitute for event classification or materiality;
- duplicate accession processing is idempotent.

## Phase 3 — Grounded LLM explanation

Purpose: make the evidence understandable without turning the product into a generic
chatbot.

The provider-neutral request/validation/cache contract and first OpenAI Responses
adapter are now in place. Single-company generation is opt-in and always falls back
to the deterministic brief when configuration, transport, schema, citation, number,
or advice checks fail. The initial default is `gpt-5.6-terra`, with `gpt-5.6-luna`, `deepseek-v4-pro`,
`qwen3.7-plus`, and `claude-sonnet-5` evaluated against the same frozen evidence
packets rather than selected by reputation. See `docs/LLM.md`.

### Implemented

- deterministic evidence packet with filing passages, prior-filing changes,
  historical metrics, reaction context, citation allowlist, and numeric allowlist;
- strict common response shape plus provider-independent validation;
- switchable OpenAI, DeepSeek, Qwen, Anthropic, and Gemini structured-output adapters;
- disk cache keyed by accession, prompt version, provider, model, and evidence;
- English/Chinese advice and directional-forecast guards;
- safe deterministic fallback and provenance for provider failure;
- opt-in `company-lens TICKER --llm` path, without changing the offline batch build;
- 20 frozen English/Chinese cases across 10 distinct local filing events, with an
  offline scorecard and explicit pass thresholds;
- resumable raw-provider benchmark runner with per-case checkpointing, usage, latency,
  optional explicit pricing, and a no-request dry-run.
- bounded document/headline retrieval with ticker, source, tag, time, relevance, and
  top-k controls;
- safe reader rules, stable retrieved-chunk citations, local TF-IDF fallback, optional
  LangChain splitting/PDF import, and a zero-cost retrieval inspection command.
- a read-only company-page Evidence Scope section plus at most three source-linked
  company/market headlines from an explicitly configured local cached index.
- local JSON persistence of imported evidence, chunks, reader rules, retrieval runs,
  and LLM provenance through the backend-neutral storage protocol.

### Remaining work

- structured filing brief with `what changed`, `why it matters`, `key numbers`,
  `uncertainties`, and citations;
- current-vs-prior filing comparison;
- beginner and professional explanation depth;
- bilingual English/Chinese output;
- read-only `Ask this company` API/UI over the implemented bounded retrieval contract;
- source-linked headline ingestion from Finnhub is implemented behind an explicit API
  key and bounded daily cache; production activation and vendor-terms review remain;
- keep evidence persistence local; the remote adapter was removed as unused;
- run the same frozen scorecard against Terra and Luna with current explicit prices;
- review failed concepts and extend cases only when they add a distinct event pattern;
- scheduled generation for only new/changed accessions after the evaluation gate.

### Acceptance

- every externally checkable claim is cited;
- unsupported claims are blocked or visibly marked;
- the model cannot emit buy/sell advice or price forecasts;
- AI-generated numbers match supplied deterministic facts or quoted source text;
- evaluation reports validity, citation support, numeric consistency, latency, and
  cost.

## Phase 4 — Automation

Purpose: make the product update itself without pretending to be real-time trading
infrastructure.

### Work

- scheduled SEC update check;
- accession-based processing queue and run state;
- on-demand refresh with cached-first responses;
- retry, backoff, and resumable document ingestion;
- company-snapshot invalidation when a new filing lands;
- run provenance, warnings, versions, and output hashes;
- monitoring for stale data, extraction failure, and LLM failure.

### Acceptance

- processing the same filing twice does not duplicate it;
- one issuer failure does not stop other issuers;
- stale snapshots are visibly dated;
- a failed AI step does not hide deterministic data or cited source passages;
- the user can see whether a refresh is cached, processing, current, partial, or
  failed.

## Phase 5 — Optional portfolio picture

Purpose: extend the same transparent historical context to a user-entered portfolio.

### Work

- tickers and user-entered weights;
- historical portfolio value and benchmark comparison;
- contribution by holding;
- volatility, max drawdown, concentration, correlation, and sector exposure;
- recent filing timeline across holdings; and
- a cited portfolio update summarizing supplied company evidence.

### Explicit exclusions

- optimized weights;
- automated rebalance suggestions;
- expected return forecasts;
- paper trading;
- broker connectivity; and
- investment recommendations.

## Reuse from the pre-rewrite Git history

Reuse behavior and tested calculations, not the old information architecture.

| Historical module | Decision | New role |
|---|---|---|
| `backend/app/data_providers/` | Reuse selectively | Market-data adapters behind one provider contract |
| `backend/app/features/technical_indicators.py` | Adapt | Plain historical context; keep only interpretable metrics |
| `backend/app/backtest/metrics.py` | Extract and rename | Buy-and-hold performance calculations, not a backtest engine |
| `backend/app/factor_validation/capm.py` | Adapt | Beta/benchmark context only |
| `backend/app/insights/` | Reuse selectively | NLP baselines, provider handling, and optional FinBERT evaluation |
| `backend/app/research_copilot/citations.py` | Reuse | Stable citation contracts |
| `backend/app/research_copilot/context_assembler.py` | Adapt | Filing/company evidence assembly |
| strict LLM schemas and provider adapters | Reuse | Bounded cited explanation |
| `MarketWatchPage` and price charts | Redesign | Components inside one company page |
| research agent / lifecycle / registries | Do not restore | Replace with a small filing-processing workflow |
| factor research, alpha lab, strategy backtests | Do not restore | Outside product scope |
| paper trading and risk-profile actions | Do not restore | Outside product scope |

The relevant historical reference point is the pre-rewrite tree before commit
`ff9c81c`; code should be recovered file by file rather than by reverting the
repository.

## Proposed package boundaries

```text
src/company_lens/
  sources/          SEC, XBRL, company identity, market data
  filings/          normalization, anchors, comparison, provenance
  nlp/              classification, extraction, novelty, passage ranking
  performance/      return, benchmark, drawdown, recovery, beta
  events/           filing reaction and attention ranking
  llm/              evidence contract, prompts, validation, provider adapters
  snapshots/        company-page read model and cache
  workflows/        scheduled and on-demand processing
  api/              company, filing, refresh, and ask endpoints
```

The existing `filing_triage` package remains intact during Phase 0. Components are
extracted only after their corrected contracts and regression tests are stable.

## Recommended first vertical slice

Build one end-to-end AAPL page using the existing real SEC and price artifacts:

1. company header and freshness;
2. growth of $10,000 versus SPY;
3. return and risk cards;
4. latest five 8-K filings;
5. deterministic key passages and novelty;
6. one cited LLM brief; and
7. no-LLM fallback.

This slice exercises the full source-to-user chain without requiring a portfolio,
watchlist, research workspace, or autonomous agent.
