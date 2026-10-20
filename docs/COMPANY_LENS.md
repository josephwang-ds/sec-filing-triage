# Company Lens — what the product does and how it is operated

Split out of the README, which had grown to open with two pages of storage
backends and environment-variable names before reaching a single result. The
repository's headline finding is a measurement; this file is the operating
manual that sits behind it.

See also [scope](SCOPE.md), [product definition](PRODUCT.md),
[architecture](ARCHITECTURE.md), [roadmap](ROADMAP.md),
[grounded LLM strategy](LLM.md), and [deployment](DEPLOYMENT.md).

The first vertical slice is runnable against the existing local real-data build:

```bash
make company        # -> one AAPL JSON snapshot + self-contained HTML page
make company-featured # -> quick AAPL/MSFT/NVDA showcase build
make company-pages  # -> all 193 locally available company pages + index
make refresh-filings # -> check SEC heads, append unseen 8-Ks, rebuild pages
make refresh-fundamentals # -> refresh the AAPL annual Company Facts pilot
make refresh-all    # -> locked SEC + market refresh for scheduled operation
make vercel-bundle  # -> static pages + private-evidence Q&A function
make vercel-deploy  # -> publish that bundle to Vercel production
make nlp-eval       # -> labeled prior-filing change-detection metrics
```

It produces a versioned company snapshot containing a growth-of-$10,000 series,
same-period SPY comparison, return, CAGR, volatility, beta, correlation, drawdown,
worst day, a bounded business profile, latest 8-Ks, SEC source links, deterministic
passage ranking, causal novelty, prior-comparable-filing changes, typed cited entities
with source spans, retrospective benchmark-adjusted filing reactions compared only
with earlier issuer filings, and a no-LLM explanation fallback. An optional local
JSON/CSV headline index can add an Evidence Scope section with at most three
source-linked company or market headlines; normal builds use the honest
not-configured state and make no live-news request. The production worker refreshes
that bounded index from Finnhub on weekdays, keeps the last good cache on upstream
failure, and then rebuilds all 193 pages. Opt-in grounded retrieval runs
persist their documents, selected chunks, safe reader rules, and run provenance to
local versioned JSON. No database is required, and none is supported:

```bash
company-lens AAPL --llm --storage-backend local
```

A PostgREST adapter and a dual-write mode lived here until 2026-08-28. Both were
removed rather than kept, and the reasoning is worth recording because the code
worked: it had passed a controlled live write/read/cleanup test. What it never
had was a caller. Nothing in the repository selected it, so it was carrying four
environment variables, a SQL migration, a page of operating documentation and a
credential class that must never reach a browser — all for a path no run took.
Unused code with a security surface is not free.
The entry searches every company in the current local evidence universe while
keeping AAPL/MSFT/NVDA as featured examples. The count is not written down here:
`universe.csv` is screened live, so it moves between refreshes, and the page
states its own figure. It states when a company is genuinely
outside that universe. It makes no forecast or recommendation.

Each company page also includes a controlled **Ask the evidence** experience. A
visitor can choose GPT, DeepSeek, Qwen, Claude, or Gemini and ask a company-specific
question in English or Chinese. The server sends only that ticker's frozen snapshot
evidence, requires structured claims with citation IDs, and withholds any response
that introduces an unsupported citation or number, investment advice, or a price
forecast. Answers show their evidence links, limitations, selected model, latency,
and validator result. Provider keys stay in Vercel sensitive environment variables;
they are never shipped to the browser or included in the public static bundle.

## Evidence scope

A reader also chooses **how wide** the model is allowed to look. Four scopes,
selectable beside the model and language:

| Scope | Contains |
|---|---|
| **Core financials** (核心财务) | SEC filings and long-term fundamentals only |
| **Company news** (公司动态) | core, plus recent headlines about this company |
| **Market context** (市场背景) | core, plus broad market and sector headlines |
| **All evidence** (全部证据) | core, company news and market context together |

Core is the default and is present in every scope: the selector controls what is
*added*, never what is taken away from the source-backed foundation.

Market context does not include company news, and that is deliberate. Read
cumulatively the four would collapse to three — the widest would be identical to
the one below it — so each scope is a distinct question a reader might have:
the company's own numbers, what is being written about the company, what is
happening around it, or all of that at once.

**A scope is not a display filter.** Each one carries its own
`allowed_citations` and `allowed_number_literals`, built from the sections it
actually contains, and those two lists are what the response validator enforces.
A model answering in *Core financials* cannot cite a headline it was never
shown — the citation is rejected and the answer withheld — even though that
headline exists elsewhere in the build. Sending narrow evidence while validating
against wide lists would defeat the entire mechanism, so the scopes are
materialised in full at build time rather than assembled per request: the
evidence a model reads and the lists it is judged against are produced together,
by one function, in one language.

Narrowed scopes also tell the model they are narrowed, and an empty section still
declares itself — "no company headlines are available in this scope" is a fact
worth stating, where a silently missing key invites an answer from memory.
Market headlines carry an extra instruction not to attribute a market development
to the issuer.

An unrecognised scope is refused with `422 scope_not_available` rather than
quietly falling back to the default: a typo must not answer from a different
evidence set than the reader chose. `tests/test_ask_function.py` runs the
deployed handler under Node to hold that behaviour down.

## Demo boundaries

The production Q&A endpoint is intentionally a portfolio-demo boundary: a strict
model allowlist, 280-character questions, short outputs, same-origin requests, a
per-IP hourly window, and a hard global daily budget on paid calls. A plain local
static preview remains fully usable. If the Ask function returns no
models, the page says live Q&A is not configured and keeps the evidence readable.
A failed model check is a separate retryable error.

The per-IP window and the budget are only global when a shared counter store is
configured; without one they live in a single serverless instance's memory and
reset on cold start. [DEPLOYMENT.md](DEPLOYMENT.md#what-actually-bounds-the-spend)
is precise about which control does what.
