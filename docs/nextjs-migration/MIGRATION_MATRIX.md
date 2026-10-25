# Migration matrix

Status: **done** = built and covered by a test; **parity** = additionally
compared against the Python page value by value; **not migrated** = stated here
with the reason.

## Routes

| Old | New | Status |
| --- | --- | --- |
| `/index.html` | `/zh`, `/en` | done — 308 redirect tested |
| `/<ticker>.html` | `/zh/company/<ticker>`, `/en/company/<ticker>` | parity |
| `/404.html` | `/[locale]/not-found` | done — unknown ticker returns 404 with the boundary page |
| `/overview.html` | `/zh/overview`, `/en/overview` | done — figures read from the evidence package |
| `/research.html` | `/zh/research`, `/en/research` | done — figures read from the evidence package |
| `/earnings.html` | `/zh/earnings`, `/en/earnings` | done — migrated as the retirement notice it is |
| `/report.html` | — | **not migrated**: the full generated report is a `make run` artifact that is not in this build. The old URL is not yet redirected. |
| `/api/ask` | `/api/ask` | done — the same handler, adapted |
| `/api/events` | `/api/events` | done — read-only proxy |
| — | `/api/events?view=health` | done — passed through |

## Company page, module by module

| Module | Content | Status |
| --- | --- | --- |
| A — Snapshot | name, ticker, business line, category, latest adjusted close **with its observation date**, return gap, filings in snapshot, price coverage, CIK, SEC record link, engine warnings | parity |
| — Brief | the engine's three-part explanation, each labelled observed / calculated / interpreted | done |
| B — Financial results | revenue, net income, diluted EPS, gross profit; current and prior period; YoY or a stated absence; peer-sample median and gap or the recorded reason; the us-gaap concept; link to the filing | parity |
| C — History and risk | 1Y/3Y/5Y/10Y, SPY/QQQ, chart with hover, ending value, return gap, total return, CAGR, volatility, max drawdown, beta, correlation, matched sessions, partial-coverage note, scope note | parity |
| — Volatility | 20-session band against the issuer's usual level, out-of-sample coverage | done — absent when the engine supplies none |
| D — SEC filings | per filing: form, items, acceptance time, quoted passages, key numbers, prior-filing comparison with change counts and text similarity, post-filing move with percentile; plus an eight-filing timeline | parity (accessions and source links compared) |
| — Disclosure signal | issuer-relative state, probability, issuer base rate, history depth, reasons, model and calibration | done — absent when the scoring run has not happened |
| E — Events | eight states, recent list, confirmed-next list, coverage tier, last successful check, technical fold | done — 10 E2E tests |
| — News | company and market headlines, kept apart, in their published language | done |
| F — Ask AI | model and scope discovery, question, suggestions, scope/model/language/depth controls, stop, citations, boundaries, every error state | done — 6 E2E tests, none calling a provider |

## Features carried across

| Feature | Status |
| --- | --- |
| Snapshot contract and schema version | parity |
| Filed financial results, same basis and periods | parity |
| SEC filings, citations and source URLs | parity |
| Historical return, volatility, drawdown, beta, correlation | parity |
| SPY default, QQQ comparison, per-period availability reasons | done |
| Filing-reaction percentiles, issuer-relative only | done |
| Evidence scopes and citation validation | done — unchanged handler |
| Refusal when evidence is missing or the question asks for a price call | done — unchanged handler |
| Event version binding (`ask_enabled` / `ai_enabled`) | done — surfaced, never overridden |
| Company search by symbol and name | done |
| Boundary page for an uncovered company | done |
| Bilingual UI | done — 505 keys each |

## Not migrated, with reasons

| Thing | Why |
| --- | --- |
| `/report.html` | A `make run` artifact absent from this build. Needs a redirect before cutover. |
| Estimated earnings calendar | Already withdrawn upstream. The page explains the withdrawal; publishing inferred dates again would reintroduce the defect it was withdrawn for. |
| Live event data on the preview | The preview has no blob credentials by design. The card renders its "not configured" state. |
| Ask answers on the preview | No provider key, so no paid call is possible. Configuration, validation and error states are covered. |
| Production company data | `EDGAR_USER_AGENT` is the user's identity to supply; development runs on a synthetic world. |
