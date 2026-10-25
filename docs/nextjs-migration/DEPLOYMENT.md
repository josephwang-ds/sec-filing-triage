# Deployment, cutover and rollback

## The preview

| | |
| --- | --- |
| URL | https://lens-gkuplozwd-josewang-projects.vercel.app |
| Vercel project | `lens-web` (`prj_FZTMwbFl4fVES1HqAXn8LjvwnDpG`), scope `josewang-projects` |
| Inspector | https://vercel.com/josewang-projects/lens-web/BhB1RyzF44kYkj2k2qpL92uC9Tey |
| Branch | `feat/lens-nextjs-v2` |
| Data | the committed fixtures plus the real research evidence package |
| Access | behind Vercel Deployment Protection — opens for anyone signed into the account |

Two things to be plain about:

- **Vercel labelled it "production".** That is this new project's production
  alias, because it is the project's first deployment. It is not the live site:
  `lens.josephjwang.com` belongs to `company-lens-josephjwang`, which was not
  touched. Later deploys to `lens-web` will be previews unless `--prod` is passed.
- **A first attempt created a stray project.** Deploying from the repository
  root failed Next.js detection and left an empty project named
  `sec-filing-triage-lens-v2` with one failed deployment. It serves nothing.
  Deleting it is a judgement call left to the account owner.

Deployment Protection was left on. Turning it off is a security setting and is
the owner's to change; while it is on, the URL is reachable by the account and
not by the public.

### How it was deployed

```bash
cd apps/lens-web
LENS_USE_FIXTURES=1 node scripts/prepare-data.mjs   # stage snapshots + evidence
cd ../..
vercel deploy --cwd apps/lens-web --yes --archive=tgz --build-env LENS_USE_STAGED=1
```

`LENS_USE_STAGED=1` tells `prepare-data` to keep the uploaded `.lens/` directory
rather than rebuild it from repository paths that do not exist when only the app
directory is uploaded. `apps/lens-web/.vercelignore` is what lets that staged
directory be uploaded although it is not committed.

### Environment variables

None are set on the preview, deliberately.

| Variable | Effect when set | Set on the preview? |
| --- | --- | --- |
| `LENS_SNAPSHOT_DIR` | read engine snapshots from a directory | no — fixtures are used |
| `LENS_USE_FIXTURES` | force fixtures even when engine output exists | at staging time |
| `LENS_USE_STAGED` | keep the uploaded `.lens/` | yes, as a build env |
| `LENS_ASK_DIR` | where the staged Ask handler lives | no — resolved automatically |
| `LENS_EVENTS_UPSTREAM` | origin whose `/api/events` to proxy | **no — no live feed** |
| `LENS_FEATURED` | featured tickers on the home page | no |
| `OPENAI_API_KEY` etc. | enable a model provider for Ask | **no — no paid call is possible** |
| `COMPANY_LENS_ASK_*` | origin check, daily budget, shared counters | no |
| `BLOB_READ_WRITE_TOKEN` | **not read by this app at all** | no |

No credential of any kind is read in client code. The Ask handler reads provider
keys inside the Node runtime; the events route reads no token and has no write
path.

## Real-company data: no new SEC credential needed for parity

The [real-company verification workflow](REAL_DATA_VERIFICATION.md) now restores the
existing production research cache **read-only**, builds genuine AAPL/JPM/NVDA
engine snapshots, stages the existing Ask evidence contract and compares the
legacy Python renderer with Next.js in Chromium. The first successful run
([Actions #40206425919](https://github.com/josephwang-ds/sec-filing-triage/actions/runs/40206425919))
passed **48/48** rendered checks and did not make new SEC requests.

New deployments must use `LENS_REQUIRE_ENGINE=1` and an explicit required
ticker list; without these the development frontend intentionally falls back
to clearly marked synthetic fixtures. The `lens-web` Preview shown above
**has not yet been rebuilt with real snapshots**. Download the short-lived
verified snapshot artifact and stage a separate protected preview, as documented
in `REAL_DATA_VERIFICATION.md`.

The old stable Vercel alias `company-lens-josephjwang.vercel.app` can be used
as a **read-only** `LENS_EVENTS_UPSTREAM` for the new protected preview. Do not
point this variable at the movable `lens.josephjwang.com` hostname or
a later cutover could proxy the site into itself.

## Before production

Not satisfied yet, and each is checkable:

1. Build against production snapshots rather than fixtures, so all ~194
   companies exist (`LENS_SNAPSHOT_DIR`, or run the refresh in the deployment).
2. AAPL/JPM/NVDA real-company parity against newly generated Python pages passed 48/48; still verify the *deployed preview* and compare it against the existing production release.
3. Set `LENS_EVENTS_UPSTREAM`, or port the events function, and confirm the
   three covered companies render live feeds — and that one uncovered company
   with a normal snapshot still reads correctly.
4. Configure one provider key and confirm a grounded answer, a refusal and a
   rate-limit response.
5. `/report.html` now redirects to Research; decide separately whether to migrate the archived full HTML report.
6. Confirm every published `<ticker>.html` redirects — the current rule accepts
   1–6 letters, digits or dots.
7. Decide how the engine's output reaches the build: the refresh job writes
   `data/build/company_pages/`, which the app needs at build time.
8. Run an accessibility audit.

## Cutover

The production project stays as it is until then. When the list above is met:

1. Deploy `lens-web` with `--prod` and verify on its own URL.
2. Record the current production deployment URL of
   `company-lens-josephjwang` — that is the rollback target.
3. Move `lens.josephjwang.com` to `lens-web` in the Vercel dashboard.
4. Verify in both languages: home, three company pages, overview, research,
   earnings, five legacy URLs, `/api/ask` GET, `/api/events` for a covered and
   an uncovered company.
5. Watch the function logs for an hour.

Only step 3 is irreversible-feeling, and it is the one that needs the owner's
explicit go-ahead.

## Rollback

The old project keeps all of its deployments, so rollback is a domain move, not
a rebuild:

1. Reassign `lens.josephjwang.com` to `company-lens-josephjwang` in the
   dashboard. The last good deployment serves immediately.
2. If that project's alias also needs restoring:
   `vercel alias set <recorded-deployment-url> lens.josephjwang.com`.
3. The Python pipeline is untouched by this migration, so
   `make vercel-bundle && make vercel-deploy` still rebuilds and republishes the
   old site from source at any time.

Nothing in this migration deletes or rewrites engine output, blob data, or any
existing Vercel project.
