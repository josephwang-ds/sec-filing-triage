# Cursor Handoff — Company Lens Phase 3.5

Updated: 2026-08-25
Repository: `sec-filing-triage`
Current branch: `claude/ai-quant-project-missing-lxcwzp`
Observed base commit: `7c41880`

## Your role

Continue the existing implementation. Do not redesign or rewrite the repository.
Work as a careful senior product engineer: preserve the evidence contracts, complete
one vertical slice, test it, and stop when the acceptance criteria below are met.

The user likes three additions and wants all three preserved in a controlled form:

1. bounded RAG / optional LangChain document import and reader rules;
2. source-linked company and market headline context; and
3. Local versioned persistence.

These are stretch capabilities inside Company Lens. They must not turn the project
into a generic chatbot, a live news feed, or an investment platform.

## Product promise

> Company Lens gives an ordinary reader one source-backed view of a public company:
> what happened historically, what the company disclosed, what changed, and what can
> be trusted. It does not predict prices or recommend trades.

Primary review audience: HR and hiring managers for data science, ML/LLM engineering,
analytics, and data-product roles.

The five-minute demo must remain understandable in this order:

1. company and freshness;
2. historical growth/risk versus SPY;
3. latest filing and source passages;
4. bounded AI explanation and its evidence scope;
5. methodology/trust proof.

## Read before changing code

Read these files in order:

1. `docs/SCOPE.md`
2. `docs/PRODUCT.md`
3. `docs/ARCHITECTURE.md`
4. `docs/ROADMAP.md`
5. `docs/LLM.md`
6. `src/company_lens/contracts.py`
7. `src/company_lens/snapshots/builder.py`
8. `src/company_lens/web/page.py`
10. `src/company_lens/llm/retrieval.py`
11. `src/company_lens/llm/headlines.py`
12. `src/company_lens/cli.py`

## Repository safety

The worktree is intentionally very dirty. Many important Company Lens files are
untracked relative to the observed base commit and are user work, not disposable
artifacts.

Before editing:

```bash
git status --short
```

Rules:

- Do not run `git reset`, `git checkout --`, `git clean`, or broad deletion commands.
- Do not revert, overwrite, or reformat unrelated `filing_triage` changes.
- Do not commit `.env`, API keys, raw provider responses containing secrets, or local
  user documents.
- Do not read or print populated secrets merely to verify configuration.
- Do not make paid LLM calls, provision infrastructure, deploy Vercel/Vultr, or contact a
  live news API without explicit user approval.
- Use `apply_patch`-style minimal edits and inspect overlapping changes first.

Baseline verification on 2026-08-25:

- `180` tests collected and passing;
- Ruff passes;
- 193 cached company pages are supported by the local evidence universe;
- the real GPT-5.6 Terra v1 benchmark scored 95% grounded pass, 98.6% material
  coverage, 100% citation precision, 100% numeric consistency, and zero advice
  violations;
- the one real failure was `xel-settlement-zh`, where the model omitted `million`
  after `$157`.

Run before and after work:

```bash
PYTHONPATH=src:. .venv/bin/pytest -q
.venv/bin/ruff check src tests scripts
git diff --check
```

## Already implemented — preserve and extend

### Grounded LLM

- switchable OpenAI, DeepSeek, Qwen, Anthropic, and Gemini providers;
- common structured output contract;
- citation, numeric, advice, and forecast validation;
- deterministic fallback and disk cache;
- frozen 20-case English/Chinese evaluation;
- resumable provider runner with `--case-id`, `--limit`, dry-run, usage, latency,
  and explicit pricing;
- prompt v2 requires preservation of `million`, `billion`, percent, and per-share
  units;
- prompt version is now included in the default provider-run filename. Never mix v1
  cached results with v2 results.

### Bounded retrieval

Implemented in `src/company_lens/llm/retrieval.py`:

- `ImportedDocument`, `RetrievalScope`, and `RetrievedChunk` contracts;
- ticker/source/tag/document/time/top-k/min-relevance/chunk controls;
- stable content/chunk citations;
- bilingual local TF-IDF retrieval with no API cost;
- optional LangChain `RecursiveCharacterTextSplitter` when installed;
- TXT, Markdown, HTML, JSON, CSV import and optional PDF via `pypdf`;
- 5 MB document and 5,000-row headline-index limits;
- safe reader rules that cannot override grounding, advice, or citation policy;
- retrieved text is explicitly untrusted evidence, never instructions;
- retrieved citations and number literals are added to allowlists only after
  deterministic selection.

Optional RAG dependencies:

```bash
.venv/bin/pip install -e '.[rag]'
```

Do not introduce a full LangChain agent or chain. LangChain is an optional ingestion
and splitting adapter, not the owner of grounding or business logic.

### Headline index

Implemented in `src/company_lens/llm/headlines.py`:

- JSON/CSV import;
- company and market source types;
- headline/title, legal source summary, publisher, published/fetched timestamps,
  URL, ticker(s), and topic/category metadata;
- stable headline IDs and citations;
- no article-body scraping or copied copyrighted articles.

Zero-cost inspection:

```bash
PYTHONPATH=src .venv/bin/python scripts/inspect_retrieval.py \
  --ticker EXMPL \
  --document data/sample/retrieval_note.md \
  --headlines data/sample/retrieval_headlines.json \
  --query "revenue management interest-rate context" \
  --published-after 2026-08-01 \
  --max-chunks 4
```

The two files under `data/sample/retrieval_*` are explicitly synthetic interface
fixtures. Never display them as real public-company news.

### Storage decision

Evidence persists to local versioned JSON, and that is the only backend. A
PostgREST adapter, a dual-write mode and `docs/STORAGE.md` describing a
three-tier split were removed on 2026-08-28: the code worked and had passed a
live write/read/cleanup test, but nothing selected it. It was carrying four
environment variables, a SQL migration, a page of operating documentation and a
credential class that must never reach a browser, for a path no run took.

```text
Vercel: static UI + the bounded Q&A function
Local:  SEC ingestion, parsing, scoring, evidence JSON
```

Local file-backed operation is the only mode; there is no remote backend to fall back from.

## Next milestone — implement this now

Build one read-only `Evidence Scope + Headlines` vertical slice on the company page.

### 1. Add snapshot contracts

Add explicit typed read models in `src/company_lens/contracts.py` rather than passing
loose UI-only dictionaries. Suggested optional shape (adapt names to existing style):

```text
EvidenceScopeSummary
  status: available | empty | stale | not_configured
  source_types: list[str]
  query: str | None
  max_chunks: int
  selected_chunks: int
  published_after: str | None
  generated_at: str | None

HeadlineBrief
  headline: str
  publisher: str
  published_at: str
  fetched_at: str | None
  url: str
  source_type: company_news | market_news
  ticker: str | None
  topic: str | None
  citation: str
```

Add them to the company snapshot as optional/backward-compatible fields. Preserve the
existing serialized contract for builds without retrieval/headline inputs.

### 2. Add a local, cached adapter

- Add an optional headline-index path to the single-company and multi-company build
  entry points.
- Parse through the existing `import_headline_index`; do not duplicate parsing.
- Filter company news by exact ticker. Market news may be global context.
- Enforce a maximum of **three displayed headlines total**.
- Prefer company-specific headlines before market context when relevance is tied.
- Preserve publisher, source URL, published time, fetched time, topic, and citation.
- Never infer missing timestamps, publisher, ticker, importance, sentiment, or article
  content.
- If no index is configured, emit an honest `not_configured`/empty state; do not show
  AAPL/MSFT/NVDA placeholders or synthetic fixtures.

Do not connect a live news vendor in this milestone.

### 3. Add the company-page UI

Add one compact section after filing evidence and before the final trust/methodology
section. It should support the interview story, not become a feed.

Required UI:

- title such as `Evidence Scope` or `Recent context`;
- a short sentence explaining that the LLM can only use the selected evidence;
- compact chips/metadata for selected source types, date floor, and selected chunk
  count when present;
- at most three headline rows/cards;
- visible `Company` or `Market` label;
- headline, publisher, human-readable published time, topic when available, and an
  external source link;
- visible freshness/fetched state;
- honest empty/not-configured/stale state;
- no sentiment meter, urgency badge, price impact, prediction, recommendation, infinite
  scroll, autoplay, or generic chat box.

Keep the visual hierarchy below the filing evidence. This feature is supporting
context, not the hero promise.

Escape every imported string. Do not insert headline text, publisher, topic, or URL
through unsafe HTML interpolation.

### 4. Wire retrieval provenance, not LLM secrets

- Snapshot/page output may contain scope metadata, selected citation IDs, headline
  metadata, provider/model name, cache/fallback status, and prompt version.
- It must never contain API keys, Authorization headers, raw `.env` content, database
  service-role keys, or full local filesystem paths.
- A headline or uploaded chunk enters the LLM factual universe only through the existing
  `extend_request_with_retrieval` path.
- Keep the deterministic fallback usable when no provider key, database, headline
  index, or optional LangChain dependency exists.

### 5. Tests required

Add focused tests before declaring completion:

- no headline index -> honest empty/not-configured UI;
- more than three matching rows -> exactly three displayed;
- AAPL page excludes MSFT/NVDA company headlines;
- market headline can appear as market context;
- published/fetched time, publisher, URL, topic, and citation survive serialization;
- unsafe HTML in headline/publisher/topic is escaped;
- invalid/non-HTTP URL remains rejected by the importer;
- retrieval scope appears only when configured;
- no fixture headline appears in normal production page builds;
- no secrets or absolute local paths appear in generated HTML;
- existing company-page and Vercel-bundle tests continue passing.

### 6. Update scope documentation honestly

The user explicitly chose to keep the three additions. Update `docs/SCOPE.md` without
silently expanding the product into a feed:

- add **bounded source-linked headline context, maximum three, cached daily** as a
  stretch capability;
- keep social feeds, infinite news streams, real-time news infrastructure, sentiment
  trading signals, and general web research agents out of scope;
- describe bounded document import/rules as a demonstration of controllable RAG;
- describe a database as deployment infrastructure that dynamic uploads/history would need,
  not an MVP user feature.

Update `docs/ROADMAP.md`, `docs/LLM.md`, and README only where the implemented behavior
actually changes. Do not claim a live vendor, database, upload UI, or deployed service
until it exists.

## Following milestone — prepare, do not provision

Only after the UI milestone and tests pass, prepare a storage boundary without
requiring network access:

1. Define a small storage protocol for documents, chunks, headlines, rulesets,
   retrieval runs, and LLM-run provenance.
2. Keep a local JSON/file implementation as the default.
3. Add reviewed SQL migrations for metadata/chunks/runs and row-level security
   policy comments or tests.
4. Do not choose a vector dimension until an embedding model is selected and evaluated.
5. Do not add authentication, watchlists, alerts, social features, realtime
   subscriptions, or user-profile scope.
6. Do not create or connect a real database without explicit user approval.

Stop and report after preparing this boundary. Actual cloud credentials and deployment
belong to a later user-guided step.

## LLM evaluation warning

The old paid Terra result is a prompt-v1 artifact at:

```text
data/build/llm_eval/openai_gpt-5.6-terra.json
data/build/llm_eval/openai_gpt-5.6-terra_scorecard.json
```

Prompt v2 has a new default filename containing the prompt version. Do not reuse or
overwrite the v1 checkpoint.

The runner supports a single-case retry:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_llm_eval.py \
  --provider openai \
  --model gpt-5.6-terra \
  --case-id xel-settlement-zh \
  --input-cost-per-million 2 \
  --output-cost-per-million 12
```

This command can make a paid external API call. Do not run it without explicit user
approval. A dry-run is safe:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_llm_eval.py \
  --provider openai \
  --model gpt-5.6-terra \
  --case-id xel-settlement-zh \
  --dry-run
```

## Completion criteria

Do not say the milestone is complete until all are true:

- the existing 180 tests plus new tests pass;
- Ruff and `git diff --check` pass;
- one generated company page visibly shows the bounded scope/headline section using a
  non-production test fixture;
- normal production builds show no synthetic headline fixture;
- company-specific headlines never leak across tickers;
- headline count is capped at three;
- all source links and imported strings are safe;
- no provider/database secrets or local absolute paths appear in page output;
- the page remains fully useful without LangChain, an LLM key, a database, or a news
  index;
- product documentation describes only what is implemented;
- no unrelated user work was reverted.

## Required handback

When finished, report:

1. outcome in plain language;
2. files changed;
3. exact tests/lint/smoke commands and results;
4. screenshots or local page paths used for visual verification;
5. remaining limitations;
6. any action that still requires user approval, especially paid API calls, databases,
   news-vendor credentials, Vercel, or Vultr deployment.
