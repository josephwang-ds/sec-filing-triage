# Baseline — the system as found

Recorded 2026-10-25, before any front-end change.

## What was verified here, and what was taken from the brief

| Fact | Source |
| --- | --- |
| `origin/main` is `5b1048a` ("Publish durable Lens events…", PR #35) | verified with `git fetch` in this checkout |
| The working checkout at `~/dev/sec-filing-triage` was on `23b01c1`, which is **not** an ancestor of `origin/main` | verified |
| The live `lens.josephjwang.com` build is `06e01bb`, a different SHA from source `main` | taken from the brief; **not** independently verified |
| Dynamic event coverage is AAPL, JPM, NVDA | taken from the brief |
| Production holds 194 company snapshots / 199 pages | taken from the brief |

The local checkout being behind mattered. It predates PR #35, so it has no
`src/company_lens/events/`, no `web/financials.py` and no `financial_results`
on the snapshot. Work started there would have migrated a front end for an
engine that no longer exists. This migration is therefore developed in a
separate worktree cut from `origin/main`; the original checkout and its
uncommitted engine edits were left exactly as they were.

## How the site is published today

```
EDGAR + prices + Company Facts
        ↓  scripts/refresh_*.py        (GitHub Actions, Sat + Wed 07:20 UTC)
   data/build/*.parquet, financial_results/
        ↓  scripts/build_company_pages.py
   data/build/company_pages/<ticker>.html  +  <ticker>.json
        ↓  scripts/build_vercel_output.py
   .vercel/output/  (static HTML + /api/ask function + evidence.json)
        ↓  scripts/deploy_vercel_frontend.sh --prod
   lens.josephjwang.com   (Vercel project company-lens-josephjwang)
```

Two consequences shape the migration:

- **The deployed site is a prebuilt bundle, not a build of `main`.** The
  packager copies HTML it did not render, so the live pages are only as current
  as the last `make company-pages`. `build_vercel_output.py` has an explicit
  staleness guard for exactly this. Comparing the new front end against `main`
  alone would therefore compare it against something nobody is serving.
- **The snapshot JSON is not published.** `build_vercel_output` copies only
  `*.html` into the bundle, so `<ticker>.json` exists in the build directory and
  never on the web. Anything reading snapshots has to read them from the engine's
  output directory, which is what `apps/lens-web/scripts/prepare-data.mjs` does.

## Routes published today

| URL | Produced by |
| --- | --- |
| `/index.html` | `render_index` in `web/page.py` |
| `/<ticker>.html` (one per covered company) | `render_company_page` |
| `/404.html` | `render_unsupported` |
| `/overview.html` | `scripts/build_overview_page.py` |
| `/research.html` | `scripts/build_research_page.py` |
| `/report.html` | copied from `data/build/report.html` when present |
| `/earnings.html` | `scripts/build_earnings_calendar.py` — **a retirement notice**, not a calendar |
| `/api/ask` | `ops/vercel/ask/index.js` (Node 22 function) |
| `/api/events` | `ops/vercel/events/index.js` (Node function, private Blob) |

`earnings.html` is worth stating plainly because the brief lists an earnings
calendar as a feature to migrate: the file on the live site says the estimated
calendar was withdrawn and filed results moved to company pages. What is
migrated is that notice, not a calendar.

## Contracts the front end depends on

### Company snapshot — `company_lens.contracts.CompanySnapshot`

Schema version `2.0`. Always present: `ticker`, `company_name`, `as_of`,
`benchmark`, `period`, `profile`, `market`, `performance`, `growth`,
`period_options`, `latest_filings`, `explanation`, `provenance`, `warnings`,
`filing_timeline`.

Optional, and **omitted from the document rather than set to null** when absent:
`evidence_scope` (with `headlines` and `market_headlines`), `fundamentals`,
`financial_results`, `disclosure_signal`, `volatility_forecast`,
`benchmark_comparisons`.

`benchmark_comparisons` is keyed by symbol, with periods nested underneath:

```json
{ "QQQ": { "symbol": "QQQ", "status": "unavailable",
           "reason": "missing_prices", "periods": {} } }
```

Reasons the engine records: `missing_prices`, `stale_prices`,
`insufficient_overlap`, `invalid_values`.

### `/api/ask`

- `GET` → `{schema_version: "company-lens.ask-models.v2", models[], scopes[],
  default_scope, limits}`. `models` lists only providers whose key is present in
  the environment, so an empty list means no question can be asked.
- `POST {ticker, provider, question, language, depth, scope}` →
  `{schema_version: "company-lens.grounded-answer.v1", answer[], boundaries[],
  meta}`.
- Status codes carry meaning: `400 model_not_available` / `invalid_json`,
  `403 origin_not_allowed`, `404 ticker_not_available`, `422 scope_not_available`
  / `question_length` / `question_scope`, `429 rate_limited` /
  `daily_budget_exhausted`, `502 grounding_validation_failed`.
- Scopes: `core`, `company`, `market`, `all`.
- The handler validates every citation ID and number literal against the scope's
  own allow-list, retries once with the validation errors, and withholds the
  answer if it still fails.

### `/api/events`

`GET ?ticker=` → the public feed from `company_lens.events.public.public_feed`:
`{schema_version: "company-lens.events-public.v1", ticker, status, status_label{en,zh},
storage, coverage_tier, tier_label{en,zh}, coverage_through, coverage_gaps[],
checked_at, checked_at_display{utc,new_york,shanghai}, initialization, pending,
quota_degraded, manifest_version, ai_enabled, events[], upcoming[]}`.

`GET ?view=health` → `{naive_http_ok, ok, overall, sources[]}`.

Statuses: `current`, `no_new_events`, `partial`, `stale`, `degraded`,
`critical`, `unavailable`, `disabled`. Coverage tiers: `high_frequency`,
`ordinary`, `unsupported`. The endpoint answers `200` for an absent feed; it
does not use a `404` to mean "no events".

## The defects this migration is answering

From the screenshot of the events card, and confirmed in
`src/company_lens/events/render.py`:

| ID | Defect | Cause in the current code |
| --- | --- | --- |
| UI-01 | Content overflows / columns misproportioned | fixed two-column grid, grid children without `min-width: 0` |
| UI-02 | A large empty region when there is no data | the second column is always rendered, at full height |
| UI-03 | `事件版本 none` shown to readers | `render.py:150` prints `manifest_version` with a `"none"` fallback |
| UI-04 | "Not supported", "unavailable" and "nothing new" look identical | one empty message for eight pipeline states |
| UI-05 | No hierarchy between heading, status and body | heading, status and body at similar weight |
| I18N-01 | Overview / research have no language switch | they are separate generated HTML files with no toggle |
| I18N-02 | Language state is per page | `localStorage` key read by each page's own script |
| ARCH-01 | The renderer is hard to change | one 3,061-line module, a 210 KB f-string, a 289-key translation table inside a `<script>` |

## Data available locally

None of the production snapshots. `data/build/` was empty of engine output and
rebuilding it needs `EDGAR_USER_AGENT` — an identifying name and email sent to
the SEC, which is the user's to provide. Development therefore runs on a
deterministic synthetic world (`filing_triage.cli demo`), whose issuers are
named `SYNxxx` and are not companies. Every page states when it is reading
fixture data.
