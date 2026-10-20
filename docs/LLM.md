# Grounded LLM Strategy

Company Lens treats the model as a replaceable explanation layer. SEC passages,
market metrics, allowed citation IDs, and allowed numeric literals are assembled by
deterministic code before any request. The provider may explain that packet; it may
not fetch facts, calculate authoritative metrics, or issue investment advice.

## Provider choice

The runtime defaults to `gpt-5.6-terra`, while every provider uses the same evidence,
response, validation, cache, and evaluation contract. Provider choice is a backend
configuration decision; it is never exposed as a browser-side key or direct API call.

| Provider key | Default model | Role in evaluation |
|---|---|---|
| `openai` | `gpt-5.6-terra` | Current default grounded brief |
| `deepseek` | `deepseek-v4-flash` | Cost-sensitive independent challenger |
| `qwen` | `qwen3.8-max` | Chinese-output challenger |
| `anthropic` | `claude-sonnet-5` | Balanced frontier challenger |
| `gemini` | `gemini-3.6-flash` | Low-cost/latency challenger |

Current capability and pricing references are the providers' official pages:
[OpenAI models](https://developers.openai.com/api/docs/models),
[DeepSeek models and pricing](https://api-docs.deepseek.com/quick_start/pricing/),
[Qwen structured output](https://help.aliyun.com/en/model-studio/qwen-structured-output),
[Claude structured output](https://platform.claude.com/docs/en/build-with-claude/structured-outputs),
and [Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output).
Model IDs and prices are configuration, not application constants, because providers
can update aliases, availability, and pricing.

## Implemented runtime boundary

```text
deterministic evidence packet
  ├── allowed passage anchors
  ├── allowed metric citations
  ├── allowed numeric literals
  └── requested language and depth
                │
                v
        provider adapter
                │
                v
       common JSON response
                │
                v
 schema + citation + number + advice validator
        │ pass                 │ fail
        v                      v
 versioned cache       deterministic fallback
```

In the planned deployment, the Vercel frontend never receives provider keys. Scheduled
generation would run in the refresh job, validate output, write a cache keyed by
accession, prompt version, provider, model, and evidence hash, then rebuild the static
snapshot. That deployment is not connected yet.

The provider adapters use each vendor's native structured-output path: OpenAI and
DeepSeek Responses, Qwen Chat Completions, Anthropic Messages, and Gemini Interactions.
The OpenAI request uses `store: false` and a stable prompt-cache key. The evidence
packet contains only the latest ranked filing passages, current-vs-prior changes,
deterministic historical metrics, and filing-reaction context. The shared validator
independently rejects unknown citations, invented number literals, extra schema fields,
and English or Chinese advice/forecast language before anything reaches a page.

Generation is opt-in for a single company, so the ordinary 193-company build remains
offline and free of provider cost:

```bash
export OPENAI_API_KEY="..."
PYTHONPATH=src .venv/bin/python -m company_lens.cli AAPL \
  --llm --llm-provider openai --llm-language English --llm-depth beginner
```

Switching provider changes only the provider flag and its server-side key:

```bash
export DEEPSEEK_API_KEY="..."       # --llm-provider deepseek
export DASHSCOPE_API_KEY="..."      # --llm-provider qwen
export ANTHROPIC_API_KEY="..."      # --llm-provider anthropic
export GEMINI_API_KEY="..."         # --llm-provider gemini
```

`COMPANY_LENS_LLM_PROVIDER` can set the backend default. `--llm-model` or a provider-
specific `COMPANY_LENS_*_MODEL` variable can override the model. Without the selected
provider's key, the command records a safe fallback status in provenance
and produces the deterministic explanation. A valid response is cached under
`data/build/llm_cache/`; keys and provider errors are never sent to the frontend.

This is deliberately not enabled in `make company-pages` yet. A committed pilot
evaluation set now freezes three filing types in paired English/Chinese cases. Run it
without an API key or network access:

```bash
make llm-eval
```

The frozen set now contains 10 distinct local filing events paired across English and
Chinese, for 20 reviewed cases covering earnings, agreements, acquisition financing,
governance, leadership, dividends, debt redemption, and a regulatory settlement.
The reference fixture must achieve 100% grounded-contract pass, citation precision,
numeric consistency, and cited-claim coverage; material-concept coverage must be at
least 80%, and advice/forecast violations must be zero. The reference response is a
hand-authored evaluator test, not a provider result. It marks the evaluation set as
ready but keeps `production_decision_ready: false` until a real provider run records
valid output, latency, and cost for every case.

Inspect the paid-run scope without a key or network call:

```bash
make llm-eval-openai-dry-run
```

When ready to benchmark a model, pass the current prices explicitly rather than
hard-coding a potentially stale price table into the application:

```bash
export OPENAI_API_KEY="..."
PYTHONPATH=src .venv/bin/python scripts/run_llm_eval.py \
  --provider openai \
  --model gpt-5.6-terra \
  --input-cost-per-million INPUT_PRICE \
  --output-cost-per-million OUTPUT_PRICE
```

The runner checkpoints after every case, resumes completed outputs, and writes the raw
run plus a separate scorecard under `data/build/llm_eval/`. Raw provider failure remains
a failure in the benchmark; the deterministic product fallback does not mask it.

The same command accepts `deepseek`, `qwen`, `anthropic`, or `gemini`. Outputs are
separated by provider and model, so comparisons never overwrite one another.

After a real provider passes that gate, a future scheduled refresh could generate
briefs only for newly changed accessions.

## Bounded retrieval and reader controls

The optional retrieval layer expands the factual universe only with chunks selected by
server-enforced scope. It is not an open web agent. A request can restrict ticker,
source type (`uploaded`, `company_news`, or `market_news`), tags, publication time,
document IDs, maximum documents/chunks, minimum relevance, chunk size, and overlap.

Local development uses deterministic TF-IDF retrieval. Installing the optional RAG
dependencies enables LangChain's `RecursiveCharacterTextSplitter` and PDF import while
preserving the same Company Lens contracts:

```bash
.venv/bin/pip install -e '.[rag]'
```

Inspect the selected evidence without an API key or LLM cost:

```bash
PYTHONPATH=src .venv/bin/python scripts/inspect_retrieval.py \
  --ticker EXMPL \
  --document data/sample/retrieval_note.md \
  --headlines data/sample/retrieval_headlines.json \
  --query "revenue, management, and interest-rate context" \
  --published-after 2026-08-01 \
  --max-chunks 4
```

Pass the same controls into a grounded generation:

```bash
PYTHONPATH=src .venv/bin/python -m company_lens.cli AAPL \
  --llm --llm-provider openai \
  --llm-document /path/to/company-note.pdf \
  --llm-headlines /path/to/headline-index.json \
  --llm-search-query "management changes and regulatory risk" \
  --llm-search-source uploaded \
  --llm-search-source company_news \
  --llm-news-after 2026-08-01 \
  --llm-max-chunks 6 \
  --llm-rule "Explain legal terminology in plain language."
```

Reader rules can alter emphasis or style but are rejected if they ask to bypass
citations, numbers, uncertainty, advice, or forecast guards. Uploaded text is explicitly
marked as untrusted evidence so instructions embedded in a document never become model
instructions. Each selected document/headline chunk receives a stable citation, and
only its number literals are added to the validator allowlist.

The same CLI flow persists imported document/headline metadata, selected chunks,
validated reader rules, retrieval scope, and LLM-run provenance through
`EvidenceStorage`. `LocalJsonStorage` is the default and requires no API key or
database; use `--storage-dir PATH` to isolate the JSON collections. Raw provider
errors, authorization headers, keys, and local source paths are not persisted.

Headline indexes store publisher, publication/fetch time, URL, ticker/entity, topic, and
a legal headline or supplied summary—not copied article bodies. Company and market news
remain separate source types so the UI can expose clear scope and freshness controls.
The company-page builder can render that cached metadata with
`--headline-index PATH`; it filters company rows by exact ticker, permits global market
context, and displays no more than three source-linked rows. Normal production builds
do not configure the synthetic sample index, and an omitted index renders an honest
not-configured state. `scripts/refresh_headlines.py` can create this bounded cache from
Finnhub's company-news and market-news endpoints. It stores only provider-supplied
metadata and short summaries—never article bodies or vendor sentiment—and retains the
last good rows through an upstream failure.

Evidence persists to local versioned JSON; there is no remote storage backend.

## Selection by evaluation, not reputation

Each candidate receives the same frozen filing packets. The report records:

- schema pass rate;
- citation precision and unsupported-citation rate;
- numeric consistency;
- coverage of labeled material changes;
- investment-advice and forecast violations;
- English and Chinese reviewer scores;
- latency, input/output tokens, and estimated cost; and
- fallback rate after validation.

Production uses one primary model, not a four-model ensemble. A challenger replaces
the default only after it improves the frozen evaluation set at an acceptable cost.
