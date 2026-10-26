# Real company data: Lens v2 read-only verification

## Confirmed result (2026-10-25)

The first passing run of [Lens v2 real-data parity](https://github.com/josephwang-ds/sec-filing-triage/actions/runs/40206425919) recovered the **existing default-branch refresh cache** without any new SEC requests or credentials. It generated fresh engine snapshots for AAPL, JPM, NVDA using the cached research panels, then exported the original production Ask evidence contract.

| Issuer | Engine snapshot as of | Rendered Python vs Next.js parity |
| --- | --- | --- |
| AAPL | 2026-10-23 | 16/16 |
| JPM | 2026-10-23 | 16/16 |
| NVDA | 2026-10-23 | 16/16 |
| **Total** | | **48/48** |

The run also passed ESLint, Vitest (including real-data fail-closed tests), Next.js production build, TypeScript and Chromium DOM parity. The evidence bundle contained three companies and four scopes. Nothing in this verification calls a paid model, writes to Blob, deploys Vercel, or refreshes external financial feeds.

**Important distinctions:** These are *real-company parity checks against the Python renderer generated from the same cached dataset*, not a comparison against the current deployed HTML at a later timestamp. The existing Vercel preview still displays SYN fixtures until a new preview is explicitly staged. The run does not prove the live Events API or a paid grounded Ask response works with the new deployment.

## Repeat the test automatically

Workflow: `.github/workflows/lens-v2-real-parity.yml`

It runs on pushes to `feat/lens-nextjs-v2` and can also be manually dispatched after the workflow is available on the default branch. It:

1. Restores the production refresh's *existing* `company-lens-cache-` panels.
2. **Fails immediately** if universe, events or price data are missing. It never crawls SEC or substitutes synthetic fixtures.
3. Rebuilds structured `financial_results` from cached Company Facts when those files are in the restored cache. A cache miss does not fail this page-function job and does not call SEC.
4. Builds AAPL, JPM, NVDA with the unchanged Python engine.
5. Exports the original Ask evidence allow-lists.
6. Builds Next.js with `LENS_REQUIRE_ENGINE=1`, `LENS_REQUIRED_TICKERS=AAPL,JPM,NVDA`. This page-function build does not require filed figures, so a cache without Company Facts can still compare prices, filings and history.
7. Compares both rendered pages in Chromium.
8. Uploads a short-lived artifact with public-company snapshot JSON and parity results, **not** raw cache panels, private tokens or credentials.

`publishable-financials` is the separate acceptance job. It runs the same offline rebuild with `--require AAPL JPM NVDA`, then builds Next.js with `LENS_REQUIRE_FINANCIALS=1`. It fails when a required issuer is absent, has no report, has a filing without figures, or only has the rounded HTML fallback. It does not call SEC and it does not read the old site.

If the cache has expired, the job intentionally fails: use an existing authorised `refresh.yml` process to warm it, rather than silently replacing actual data with fixtures.

## How to stage a new protected preview with those snapshots

After the latest successful job, from a trusted local checkout of this branch:

```bash
# Find the run ID from Actions > "Lens v2 real-data parity (read-only)".
gh run download <RUN_ID> \
  --repo josephwang-ds/sec-filing-triage \
  --name "lens-v2-real-parity-<RUN_ID>" \
  --dir /tmp/lens-v2-verified

# Downloaded ZIP content preserves the uploaded path hierarchy.
mkdir -p data/build/company_pages
cp /tmp/lens-v2-verified/data/build/company_pages/*.json data/build/company_pages/
PYTHONPATH=src python scripts/export_ask_evidence.py \
  --source data/build/company_pages \
  --out data/build/ask-evidence.json

# Refuse fixtures and require every issuer tested in CI.
cd apps/lens-web
LENS_REQUIRE_ENGINE=1 LENS_REQUIRED_TICKERS=AAPL,JPM,NVDA npm run build
```

A separate Vercel preview deployment should stage `.lens/` from that verified build with `LENS_USE_STAGED=1`. Do not use a build from the old fixture-only preview as proof that real data has been published. The existing preview project is `lens-web`, **not** `company-lens-josephjwang`. Keep Deployment Protection enabled.

To show **live** events read-only in an isolated preview, configure `LENS_EVENTS_UPSTREAM` to the legacy project's stable Vercel alias, `https://company-lens-josephjwang.vercel.app`, not to the custom `lens.josephjwang.com` domain that will eventually move to Next.js. Ensure the preview uses the real AAPL/JPM/NVDA snapshots before testing events. The new event route must never receive `BLOB_READ_WRITE_TOKEN`.

To test one **real** Ask response, the existing provider configuration must be explicitly authorised in an isolated environment with a reviewed request budget; the offline suite intentionally never calls a provider.

## Requirements before production cutover

- A separate live *real-data* preview deployment is still needed.
- Full (~194-company) engine data must be supplied and successfully built, not just these three companies.
- Event feed and one permitted Ask request must be verified against that preview.
- Accessibility, Safari/WebKit, deployed legacy URLs and rate limits must be checked.
- Keep the current production domain, Blob storage and Python refresh workflows unchanged until approved.

## Accepted preview, 2026-10-26

Source commit `6f6c246`. It includes `681ec94`, `08eb838`, `65e5455` and `b1b0cee`. The first parity run on `b1b0cee` ([40281602900](https://github.com/josephwang-ds/sec-filing-triage/actions/runs/40281602900)) missed the production cache because the path list had changed the cache version. `6f6c246` restores the saved path list. Company Facts stay inside `data/cache`.

Runs for this commit, not for `c1594f8`:

- CI [40282638587](https://github.com/josephwang-ds/sec-filing-triage/actions/runs/40282638587) succeeded.
- Parity [40282634069](https://github.com/josephwang-ds/sec-filing-triage/actions/runs/40282634069) succeeded, including `publishable-financials`, page comparison and the 194-company build.
- Cache hit: `company-lens-cache-40092399434`. Offline rebuild wrote `extraction=company_facts`.
- Artifact: `lens-v2-full-real-snapshots-40282634069`. `as_of` is `2026-10-23`. 194 companies, no SYN.
- Preview: `dpl_E3F63buv61bJTDf9xT6XeEb8gTpG`, https://lens-87edkuc5e-josewang-projects.vercel.app, target preview, project `lens-web`. The remote build used the uploaded staged engine directory, 194 snapshots.

| Issuer | Filing | Figures |
| --- | --- | --- |
| AAPL | 10-Q, period ended 2026-06-27, filed 2026-07-31, `aapl-20260627.htm` | Revenue 109,417,000,000 USD, shown as $109.42B / 1,094.17 亿美元, YoY +16.4% from 16.3565%. Net income, EPS and gross profit are present. |
| JPM | 10-Q, period ended 2026-06-30, filed 2026-08-06, `jpm-20260630.htm` | Net income 21,155,000,000 USD and EPS 7.70. No revenue or gross profit, because it is a financial issuer. |
| NVDA | 10-Q, period ended 2026-07-26, filed 2026-08-26, `nvda-20260726.htm` | Revenue 96,221,000,000 USD, shown as $96.22B, YoY +105.9% from 105.8511%. |
| KO, V | 10-Q located, `metadata_only`, zero metrics | The page says the report was found and the figures were not extractable, and links the filing. No approximate number is shown. |

The displayed AAPL and NVDA amounts match the previous HTML-readback preview because that readback had rounded these same facts. The stored YoY is now the filing ratio, not `displayed percent / 100`. Ask evidence for AAPL revenue is `$109.42B` from this same snapshot.

Browser check on the preview: Chinese and English, 390px with no document overflow, SPY/QQQ switch, live AAPL events (255, status current), research sections for capacity, tradability (45.7% already in the open), model comparison, calibration (`identity`) and volatility (`har`). Ask shows not configured and does not show the citation-checked badge. No provider key was set and no model was called.

Still absent: the standalone report's queue and time-sweep charts. Production domain `lens.josephjwang.com` was not moved. Project `company-lens-josephjwang` was not modified.

## Handoff, 2026-10-26

The protected preview `dpl_DwHQwMehZZiRXGi2Ka9VT3wY4DDr` showed filed figures that were read back from the published HTML. Those amounts are display-rounded. They are not the release source. `scripts/attach_published_financials.py` remains only as that marked fallback (`extraction=published_html_fallback`). A release build rejects it.

The release path is: cached Company Facts → `refresh_fundamentals.py --offline` → `financial_results/{ticker}.json` with `extraction=company_facts` → `build_company_pages.py` → the same snapshot for the page and for Ask evidence. Those JSON files are not a separate Actions cache path. `actions/cache` versions an entry by its path list, so adding the directory would hide every cache saved with the existing list. Company Facts already live under `data/cache`, and the offline rebuild reads them from there. The parity artifact is what carries the rebuilt `financial_results`.

`scripts/stage_lens_web.sh` rebuilds those structured results before the Next.js build when it is pointed at the default snapshot directory. `LENS_REBUILD_FINANCIALS=0` skips that for a directory that was already built. `LENS_USE_FIXTURES=1` is still the only fixture path.

Ask without a provider key stays unconfigured and does not show the “citation checked” badge. No provider was called. The variables that would be required on the `lens-web` Preview environment, and are not set, are `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `DASHSCOPE_API_KEY`, `ANTHROPIC_API_KEY` and `GEMINI_API_KEY`.

The research page now renders capacity, tradability, model comparison, calibration and volatility from `evidence/real_run`, or an explicit unavailable state when a file in that group is missing. The standalone report’s queue and time-sweep charts are still absent. Production domain was not switched.
