# Real company data: Lens v2 verification and release

## Current publication status (2026-10-27)

Published at https://lens.josephjwang.com after the user explicitly authorized production publication and domain reassignment. Production deployment `dpl_74dtNYLQxLayYJ9dzagRgdfm3bWf` is READY; source `a6b7face25f401c1ffbd45275dadf2695a17fd4f` (application code unchanged from tested `0db3c21`). The production domain alias was independently checked against that exact deployment and project `prj_FZTMwbFl4fVES1HqAXn8LjvwnDpG`.

This is publication of the available feature set, not a claim that all previously listed feature gates have been completed: Ask has no provider configured; events currently expose an honest degraded status; queue/time-sweep remain unmigrated. Details and rollback instructions are below.

## Current release rules (2026-10-26)

`npm run build` is the publishing entry: it invokes `prepare-data.mjs --release`, always requires real engine snapshots and structured Company Facts for AAPL/JPM/NVDA, and cannot be weakened by setting `LENS_REQUIRE_FINANCIALS=0` or replacing `LENS_REQUIRED_TICKERS`. Additional required tickers can be added. Required reports must have available figures, a SEC Archives source, filing form and dates. Ordinary issuers such as KO/V may retain genuine unavailable or metadata-only states.

The same entry validates uploaded `.lens` snapshots when `LENS_USE_STAGED=1`; staging does not grant an exemption. `scripts/stage_lens_web.sh` uses this entry. The full-universe CI artifact is uploaded only after this strict build succeeds. `build:parity` is explicitly non-publishable page-function testing; `build:fixtures` is explicitly synthetic testing. Neither is a deployment source.

The historical 194-company Preview below exists, but it does not verify changes made after its source commit. Current-turn validation and remaining release gates are recorded at the end of this document.

## Historical result (2026-10-25)

The first passing run of [Lens v2 real-data parity](https://github.com/josephwang-ds/sec-filing-triage/actions/runs/40206425919) recovered the **existing default-branch refresh cache** without any new SEC requests or credentials. It generated fresh engine snapshots for AAPL, JPM, NVDA using the cached research panels, then exported the original production Ask evidence contract.

| Issuer | Engine snapshot as of | Rendered Python vs Next.js parity |
| --- | --- | --- |
| AAPL | 2026-10-23 | 16/16 |
| JPM | 2026-10-23 | 16/16 |
| NVDA | 2026-10-23 | 16/16 |
| **Total** | | **48/48** |

The run also passed ESLint, Vitest (including real-data fail-closed tests), Next.js production build, TypeScript and Chromium DOM parity. The evidence bundle contained three companies and four scopes. Nothing in this verification calls a paid model, writes to Blob, deploys Vercel, or refreshes external financial feeds.

**Important distinctions:** These are *real-company parity checks against the Python renderer generated from the same cached dataset*, not a comparison against the current deployed HTML at a later timestamp. At that time the preview still displayed SYN fixtures; the later 2026-10-26 historical Preview below replaced them. The run does not prove the live Events API or a paid grounded Ask response works with the new deployment.

## Repeat the test automatically

Workflow: `.github/workflows/lens-v2-real-parity.yml`

It runs on pushes to `feat/lens-nextjs-v2` and can also be manually dispatched after the workflow is available on the default branch. It:

1. Restores the production refresh's *existing* `company-lens-cache-` panels.
2. **Fails immediately** if universe, events or price data are missing. It never crawls SEC or substitutes synthetic fixtures.
3. Rebuilds structured `financial_results` from cached Company Facts when those files are in the restored cache. A cache miss does not fail this page-function job and does not call SEC.
4. Builds AAPL, JPM, NVDA with the unchanged Python engine.
5. Exports the original Ask evidence allow-lists.
6. Runs the explicitly non-publishable `npm run build:parity` with `LENS_REQUIRE_ENGINE=1`, `LENS_REQUIRED_TICKERS=AAPL,JPM,NVDA`. This page-function build does not require filed figures, so a cache without Company Facts can still compare prices, filings and history.
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
  --name "lens-v2-full-real-snapshots-<RUN_ID>" \
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

- A historical real-data Preview exists; a new Preview from the final tested commit must be independently accepted.
- The historical 194-company build passed; the final commit must pass the full-universe strict release build again.
- Event feed and one permitted Ask request must be verified against that preview.
- Accessibility, Safari/WebKit, deployed legacy URLs and rate limits must be checked.
- Keep the current production domain, Blob storage and Python refresh workflows unchanged until approved.

## Historical Preview acceptance reported by previous executor, 2026-10-26

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

Previous executor reported this browser check (not a current-turn independent verification): Chinese and English, 390px with no document overflow, SPY/QQQ switch, live AAPL events (255, status current), research sections for capacity, tradability (45.7% already in the open), model comparison, calibration (`identity`) and volatility (`har`). Ask shows not configured and does not show the citation-checked badge. No provider key was set and no model was called.

Still absent: the standalone report's queue and time-sweep charts. Production domain `lens.josephjwang.com` was not moved. Project `company-lens-josephjwang` was not modified.

## Handoff, 2026-10-26

The protected preview `dpl_DwHQwMehZZiRXGi2Ka9VT3wY4DDr` showed filed figures that were read back from the published HTML. Those amounts are display-rounded. They are not the release source. `scripts/attach_published_financials.py` remains only as that marked fallback (`extraction=published_html_fallback`). A release build rejects it.

The release path is: cached Company Facts → `refresh_fundamentals.py --offline` → `financial_results/{ticker}.json` with `extraction=company_facts` → `build_company_pages.py` → the same snapshot for the page and for Ask evidence. Those JSON files are not a separate Actions cache path. `actions/cache` versions an entry by its path list, so adding the directory would hide every cache saved with the existing list. Company Facts already live under `data/cache`, and the offline rebuild reads them from there. The parity artifact is what carries the rebuilt `financial_results`.

`scripts/stage_lens_web.sh` rebuilds those structured results before the Next.js build when it is pointed at the default snapshot directory. `LENS_REBUILD_FINANCIALS=0` skips that for a directory that was already built. `LENS_USE_FIXTURES=1` is still the only fixture path.

Ask without a provider key stays unconfigured and does not show the “citation checked” badge. No provider was called. Configure only the key and model settings for the selected provider (for example `OPENAI_API_KEY` if OpenAI is selected); the five supported providers do not all need keys. No provider is selected or configured for this acceptance run.

The research page now renders capacity, tradability, model comparison, calibration and volatility from `evidence/real_run`, or an explicit unavailable state when a file in that group is missing. The standalone report’s queue and time-sweep charts are still absent. Production domain was not switched.

## Current-turn local verification (2026-10-26)

- Baseline: clean `feat/lens-nextjs-v2` at `d06ee193af2f1d6231345eace90cb66b9b118a73`; no root AGENTS.md exists; app AGENTS.md and installed Next CLI guide were read.
- Relevant regression tests: 30 passed. Frontend unit tests: 258 passed. ESLint and TypeScript passed after correcting a nullable test variable. Fixture Chromium suite: 225 passed; these are not real-provider Ask tests.
- Trusted input: artifact `lens-v2-full-real-snapshots-40282634069`, SHA-256 `eb80d45c624b4d6d60f7f267b4a16d318ddc53dfe02e732f2082001a16c5ffed`, recovered via the GitHub connector and verified locally. Strict default build passed with 194 real snapshots and a newly exported same-source Ask bundle.
- Python lint and full Python suite passed: 860 tests, 21 warnings. Both default and staged strict real-data builds passed.
- Code commit: `0db3c215242aa50cfe1ab03bb9de53b804d5e5f3`. New CI [40329308287](https://github.com/josephwang-ds/sec-filing-triage/actions/runs/40329308287): test, locked-environment, events-browser and leakage-audit all succeeded. New parity [40329300882](https://github.com/josephwang-ds/sec-filing-triage/actions/runs/40329300882): fixture-browser, publishable-financials, compare-real-issuers and full-universe-build all succeeded.
- Final deployment input is the NEW `lens-v2-full-real-snapshots-40329300882`, artifact ID `12655181827`, SHA-256 `bdbed32b2e7fbab98c13f2e05f4d8a983c24e97c86a87f7afaa251fa24d52d17`. Verified after download; 194 companies, as_of 2026-10-23. Ask evidence was re-exported from these exact snapshots; local strict build passed again.
- Local real-data Chromium/WebKit: five issuers in both languages at 390px, report dates, SEC links, all displayed financial metrics against Ask evidence, SPY/QQQ, research modules, legacy AAPL URL and basic Tab focus passed. Chromium console clean; WebKit logged intermittent navigation/prefetch access-control messages, to be checked on Preview.
- Local development missing-file test: removed each research module's input while keeping overview evidence; all five modules showed missing-state messages in both languages (10 checks). Files restored afterward. The initial whole-directory-removal attempt did not reach individual modules and was not counted as passing.
- No provider configuration was added, no paid Ask call was made, and queue/time-sweep remain outside this migration scope.

## Final Preview independently verified this turn (2026-10-26)

- URL: https://lens-o0xl7phqj-josewang-projects.vercel.app
- Deployment: `dpl_E5hELmbNLh3SzqGQxcV3pZUScavQ`, READY, project `lens-web`, Preview.
- Source: `0db3c215242aa50cfe1ab03bb9de53b804d5e5f3`; deployment metadata records both that SHA and `lens-v2-full-real-snapshots-40329300882`. This later handoff-only documentation commit does not change the deployed application.
- Remote build log confirms `node scripts/prepare-data.mjs --release && next build` and staged engine input: 194 snapshots, same-source Ask evidence, 20 research evidence files. No fixtures or HTML readback were used.
- Authenticated Chromium AND WebKit checks on the final URL: AAPL/JPM/NVDA/KO/V in English and Chinese at 390px; period end and filed dates; all displayed current financial metric values and YoY against the exported Ask evidence; currencies/units and exact SEC filing links; genuine KO/V missing-figure notices; SPY/QQQ controls; all five research modules; no horizontal document overflow; legacy `/aapl.html`; basic Tab focus. Both browser consoles had zero errors on this final run. Earlier local WebKit prefetch logs did not recur in this run with navigation allowed to settle. This is basic keyboard coverage, not a full accessibility audit or testing in the Safari application itself.
- Ask visibly reports no provider configured in both languages. No real provider request was made. Evidence parity is not model-response acceptance.
- Real events endpoint: AAPL returned 255 events with 255 source URLs, `status=critical`, `checked_at=2026-10-26T06:56:32.509286+00:00` (14:56 Shanghai). The UI truthfully reports overdue checks and the last good copy. The historical `current` result does not apply now. The upstream refresh was not modified or triggered.

### Pre-release cutover assessment (2026-10-26; historical)

Not ready for production cutover yet. Remaining gates: select/configure one approved model provider and perform a budgeted real Ask acceptance; investigate the upstream events freshness failure and verify a fresh successful check; complete any required full accessibility/Safari-application and rate-limit acceptance (only basic keyboard, Playwright WebKit and existing offline endpoint tests were exercised here). Queue/time-sweep remain intentionally unmigrated and documented. No production alias/domain was moved, no merge was performed, and the old Vercel project was untouched.

The Vercel connector returned team-scope 403. Existing authenticated CLI access to the specified team worked with the stale local proxy variables unset; Preview browser checks used a short-lived same-project OIDC token scoped to the Preview origin. Deployment Protection was not disabled, and no provider key or token was copied into the repository.

## Production publication and final acceptance (2026-10-27)

- User explicitly selected “发布新版生产站并切换域名”, superseding the earlier prohibition on domain cutover. No merge or changes to the old project's application/credentials were performed. Its domain association was changed only as necessary for this authorized migration.
- Staged production with `--prod --skip-domain`, using the same strict release entry and artifact `lens-v2-full-real-snapshots-40329300882`: 194 real companies, as_of 2026-10-23, structured Company Facts and newly staged same-source Ask evidence. Source `a6b7fac` had passing CI [40332212931](https://github.com/josephwang-ds/sec-filing-triage/actions/runs/40332212931); application parity and full-universe acceptance remain [40329300882](https://github.com/josephwang-ds/sec-filing-triage/actions/runs/40329300882).
- Candidate: https://lens-6z0wsi7sv-josewang-projects.vercel.app; deployment `dpl_74dtNYLQxLayYJ9dzagRgdfm3bWf`. CLI lost its waiting connection, but subsequent service-side inspection confirmed READY, no build error. No duplicate deployment was created.
- Promoted the production deployment, verified functionality at `lens-web-opal.vercel.app`, then reassigned `lens.josephjwang.com` to `lens-web`. Domain verified=true; alias API confirms the precise deployment ID above. HTTPS returned Next.js assets and expected filed figures without authentication.
- Final **public production domain** Chromium and WebKit acceptance passed: AAPL/JPM/NVDA/KO/V, both locales, 390px, dates, current metric values and YoY against Ask evidence, currency/unit display and SEC links, genuine absence messages, SPY/QQQ, all five research modules, document width, legacy AAPL link and basic keyboard focus. Both final browser console error lists were empty. Earlier prepublication Preview navigation timed out; the default production domain had transient WebKit prefetch messages; neither result was counted as a clean final-domain run.
- Production runtime error query for this deployment over the preceding hour returned zero entries. This is a bounded release-time check, not continuous monitoring or a full security/accessibility audit.
- Production Ask renders the unconfigured state. Only GET status was checked; no provider key was added and no model request was sent. Rate-limit configuration is exposed, but production quota exhaustion was not exercised.
- Production events: AAPL `status=degraded`, 298 events, checked_at `2026-10-27T04:52:08.131753+00:00` (12:52 Shanghai). The existing upstream is still `https://company-lens-josephjwang.vercel.app`; custom-domain migration therefore does not create an API recursion. Refresh degradation remains an upstream follow-up.
- Deployment Protection was not disabled. The old project `prj_0lwe9BxOY7VU0WjLlwTiijSFQokr` retains its verified `company-lens-josephjwang.vercel.app` domain.

### Rollback reference (recorded, not executed)

To restore the custom domain to the old site after an explicit rollback decision, run `vercel domains add lens.josephjwang.com company-lens-josephjwang --force --scope josewang-projects`, then verify the alias target, HTTPS and old-page content. The old project's application was not removed. New-site promotion and custom-domain reassignment are separate operations; merely rolling back a deployment in lens-web does not return the domain to the old project.
