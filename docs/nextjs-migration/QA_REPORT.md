# QA report

## Independent real-company verification — 2026-10-25

A separate read-only GitHub Actions job [passed](https://github.com/josephwang-ds/sec-filing-triage/actions/runs/40206425919) after restoring the existing production SEC/market panel cache **without any SEC request or provider credential**. The unmodified Python engine generated real AAPL/JPM/NVDA snapshots (each dated 2026-10-23) and the original Ask evidence packet. The new Next.js app built successfully with `LENS_REQUIRE_ENGINE=1` and required tickers AAPL/JPM/NVDA.

**Real-company rendered parity: AAPL 16/16; JPM 16/16; NVDA 16/16 — 48/48 values matched.** ESLint, TypeScript, Next.js build and unit tests passed. An isolated workflow now repeats these checks and uploads a temporary snapshot/parity artifact; see [REAL_DATA_VERIFICATION.md](REAL_DATA_VERIFICATION.md).

This is additional evidence **beyond** the original synthetic 40/40 result below. It does **not** mean the existing protected Preview was redeployed using live snapshots, nor does it certify the live Events integration or a paid AI answer. Production-domain cutover remains blocked.


Run 2026-10-25 on `feat/lens-nextjs-v2`, branched from `origin/main` `5b1048a`.

## Results

| Check | Command | Result |
| --- | --- | --- |
| Python lint | `ruff check src tests scripts` | pass |
| Python tests | `pytest` | pass — 847 collected, exit 0 |
| ESLint | `npm run lint` | pass, no warnings |
| TypeScript | `tsc --noEmit` (via `next build`) | pass |
| Production build | `npm run build` | pass — 26 routes prerendered |
| Unit and contract tests | `npx vitest run` | 31 passed |
| End-to-end | `npx playwright test` | 190 passed across 5 widths |
| Old/new data parity | `parity.mjs` | 40/40 values match |
| Preview deployment | `vercel deploy` | READY |

## End-to-end coverage

Five viewport projects — 375, 430, 768, 1280 and 1440 — over both languages.

- **Layout**: ten pages asserted to have no horizontal document overflow at
  every width, including the events card loaded with a deliberately long
  headline and publisher name.
- **Language**: switching keeps the company; language survives navigation and a
  reload; a bare path resolves to the language last chosen; the first server
  render already carries the right `lang`; filed text on a Chinese page is
  marked `lang="en"`.
- **Legacy URLs**: `/index.html`, `/overview.html`, `/research.html` and two
  `<ticker>.html` paths resolve 200; an Ask citation's `#performance` fragment
  survives the redirect; an unknown ticker returns 404 with the boundary page.
- **Events**, ten tests: uncovered company; read error; nothing new; no
  published version never rendering as a version; a real version only inside the
  technical fold; nothing-confirmed-ahead collapsing to one line with no second
  column; an expected date never shown as confirmed; a headline keeping its
  language; a broken payload offering a retry; no overflow with long content.
- **Ask**, six tests: unconfigured deployment; refused question; withheld
  answer; daily budget distinct from rate limit; an answer with its citations
  and boundaries; and the real endpoint refusing a question with no evidence
  bundle. **No test sends a question to a model provider** — a suite that costs
  money to run stops being run.

## Verified in a browser by hand

Chinese and English company pages at 1280 and 375; the events card's
not-covered state; the financial cards in Chinese (`243.18 亿美元`, `同比 +10.0%`,
`无同比` where the engine withheld growth); overview and research with the real
evidence figures (19.8% against 11.6% random, 766 sessions, the leakage ladder
from 31.2% to 19.8%, average precision 39.7%, ROC AUC 0.764).

## Known limitations of this run

1. **The existing Preview remains fixture-only.** Its SYNxxx pages are synthetic.
   A separate read-only CI job now generates AAPL/JPM/NVDA real-company snapshots
   from the existing cached research panels and passes 48/48 old/new checks.
   Those snapshots have **not yet been published to the Preview**, and this is
   not a live-production-HTML comparison.
2. **The preview has no live event feed.** No blob credentials, by design; the
   card renders its "not configured" state. Behaviour against a real feed is
   covered by routed E2E tests, not by the preview.
3. **The preview cannot answer a question.** No provider key, so no paid call is
   possible there.
4. **Ask's own ticker pattern rejects synthetic symbols.** The production
   handler validates `^[A-Z.]{1,6}$`, so `SYN112` returns `404
   ticker_not_available` — the handler running correctly on data it was not
   meant for. Real tickers pass.
5. **`/report.html` now redirects to Research**, because the old full report
   artifact is not shipped. This preserves navigation, not the full old report.
6. **No accessibility audit tool was run.** Semantics, focus order, roles, alt
   text and `lang` marking were built in and spot-checked; axe or Lighthouse has
   not been run.
7. **48-hour event refresh stability was not observed** — outside this work.
8. **Only Chromium.** The phone projects emulate touch at 375 and 430 rather
   than running WebKit, so Safari-specific rendering is unverified.

## Reproducing

```bash
cd apps/lens-web
npm ci
npm run lint && npm run typecheck && npx vitest run && npm run build
npx playwright install chromium && npx playwright test
```
