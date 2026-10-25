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
3. Builds AAPL, JPM, NVDA with the unchanged Python engine.
4. Exports the original Ask evidence allow-lists.
5. Builds Next.js with `LENS_REQUIRE_ENGINE=1`, `LENS_REQUIRED_TICKERS=AAPL,JPM,NVDA`.
6. Compares both rendered pages in Chromium.
7. Uploads a short-lived artifact with public-company snapshot JSON and parity results, **not** raw cache panels, private tokens or credentials.

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
