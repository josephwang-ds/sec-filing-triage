# Architecture — old, new, and the line between them

## The rule

The Python research engine owns every number. The front end reads its output
and displays it. There is no second implementation of a financial or model
calculation anywhere in `apps/lens-web`, and the places where that could creep
in are called out in the code that would be the natural home for it.

```
SEC EDGAR · adjusted daily prices · Company Facts
                     │
                     ▼
        Python research engine  (unchanged)
   company_lens.{snapshots,performance,filings,fundamentals,financial_results,events}
                     │
                     ▼
      versioned snapshot documents + evidence package
   data/build/company_pages/*.json · evidence/real_run/* · ask-evidence.json
                     │
                     ▼  scripts/prepare-data.mjs   (copies; transforms nothing)
                  apps/lens-web/.lens/
                     │
                     ▼  zod contracts            (validate; a mismatch fails the build)
            Next.js server components
                     │
                     ▼
        React UI · charts · tables · both languages
```

Runtime, rather than build-time, data has its own path:

```
private Vercel Blob ──► /api/events (existing function) ──► Next route (read-only proxy) ──► Events UI
user question ──► Next route ──► the production ask handler ──► evidence validation ──► answer or refusal
```

## What stayed in Python

Everything that computes something: `snapshots/builder.py`, `performance/`,
`filings/`, `fundamentals/`, `financial_results.py`, `financial_context.py`,
`reactions.py`, `profiles.py`, `universe.py`, `refresh.py`, `llm/`, `events/`,
`web/ask.py`, the whole of `filing_triage/`, and the generators of the evidence
package. One script was added — `scripts/export_ask_evidence.py` — and it calls
the same `build_ask_evidence` the production bundler calls rather than
reimplementing it.

`src/company_lens/web/page.py` and the three page builders are untouched. They
still produce the live site. Nothing in this migration changes what the current
production pipeline does.

## What the front end is

| Layer | Where | Responsibility |
| --- | --- | --- |
| Staging | `scripts/prepare-data.mjs` | Copy engine output into `.lens/`. No transformation. |
| Contract | `src/lib/contracts/{snapshot,events}.ts` | zod schemas mirroring the Python contracts. Loose about unknown fields, strict about the ones the UI reads. |
| Data | `src/lib/data/{snapshots,research}.ts` | Parse once, hand out typed read models. Fails the build on a contract mismatch. |
| Format | `src/lib/format.ts` | Digits only. Never derives, never fills in. |
| Routing | `src/i18n/*`, `src/proxy.ts` | Locale negotiation and locale-aware links. |
| UI | `src/components/**` | Server components by default; client only where there is state. |
| API | `src/app/api/{ask,events}/route.ts` | Adapter and proxy. No business logic. |

### Why the contracts are loose about unknown fields and strict about known ones

The engine adds fields faster than a front end needs them. A snapshot carrying
something new must still render. But a field the UI *reads* has to mean what the
UI thinks it means, so those are validated and a mismatch stops the build. This
earned itself on the first run: `benchmark_comparisons` is keyed by symbol with
periods nested under `periods`, not keyed by period. The build said so instead of
rendering an empty QQQ selector.

### Why `/api/ask` loads the production handler instead of reimplementing it

`ops/vercel/ask/index.js` is the grounding boundary: the evidence allow-lists,
the citation and number-literal validation, the refusal patterns, the per-IP
window and the daily spend ceiling. Two copies of that rule means one of them
drifts, and the one that drifts is the one serving readers. So the file is
staged next to its evidence bundle and the route adapts Next's request and
response to the Node pair the handler expects. Validation, status codes and
bodies are the live site's, unchanged.

The one addition is `503 ask_not_configured`, for a deployment with no evidence
bundle. It is additive: the existing codes keep their meanings.

### Why `/api/events` is a proxy and has no write path

The published feed lives in a private Vercel Blob that one scheduled job owns. A
preview deployment able to write there could corrupt the live feed, so this
route has no write path at all and reads no blob token. With
`LENS_EVENTS_UPSTREAM` set it proxies, server-side, from the origin that serves
the real endpoint; without it, it returns the engine's own shape for "no
published feed" with the `200` the upstream itself uses for that case.

### Why the chart is hand-drawn SVG

The series is pre-sampled by the engine to at most a few hundred points and the
design is two lines on a grid. A charting library would arrive with its own
styling to fight, its own opinion about what to do with a null, and ~100 KB of
client JavaScript. The component maps engine values to coordinates; it does not
interpolate a missing session or rebase a series.

## Rendering and routing

Every page is statically generated for both locales. `/zh` and `/en` are each
addressable, and a bare path is negotiated by the proxy to the reader's language
— cookie first, then `Accept-Language`, then Chinese.

Dynamic at request time: only the two API routes.

Legacy URLs redirect (308) to the unprefixed route so the proxy can apply the
reader's language, rather than pinning every old link to one language. The
in-page fragment survives the redirect, which matters because Ask citations
point at `/<ticker>.html#performance`.

## Where a second implementation could creep in, and does not

| Temptation | What happens instead |
| --- | --- |
| Recompute a return for a period the snapshot lacks | the period is absent from `period_options` and the control is disabled with the engine's recorded reason |
| Derive YoY when the engine withheld it | `yoy: null` renders "No YoY"; the engine withholds it when the prior base was zero or a loss |
| Average peer growth client-side | `reference.status` decides; below five eligible issuers the engine records `insufficient_sample` and the card says so |
| Fill a gap in the growth series | the chart draws the points it is given |
| Translate a filed passage or a headline | kept in the source language with `lang` set |
| Show `manifest_version` as a version | `publishedVersion()` maps null, `""` and `"none"` to absence |
