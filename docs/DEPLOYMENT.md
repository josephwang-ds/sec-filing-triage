# Scheduled deployment

The public HTML bundle is deployed at <https://lens.josephjwang.com>. The refresh
that keeps it current, and the production deploy at the end of it, run from
GitHub Actions: `.github/workflows/refresh.yml` on Saturday at 07:20 UTC,
with `.github/workflows/freshness.yml` checking the published pages weekly.
That Saturday job is the production schedule. It is not a weekday cron, and it
is not the news cadence in `docs/LENS_EVENTS_PLAN.md`. The event workflows are
manual until a durable store and an independent wake are enabled.

This replaced a systemd timer on a Vultr worker. What that arrangement was, and
why its failure is the reason the second workflow exists, is at the end of this
document.

## The shape

A hosted runner holds no state between runs, so the cache is the part worth
understanding. Everything else is the same chain the worker ran, in the same
order, and `scripts/run_scheduled_refresh.sh` is still the single definition of
that order -- the workflow sets the environment it expects and calls it, rather
than restating the steps where the two can drift apart.

```text
schedule on GitHub Actions
        |
        +-- restore data/cache and data/build/universe.csv from the run before
        +-- rebuild universe.csv if the cache did not carry one
        +-- cli doctor: fail in seconds on a rejected User-Agent
        +-- refresh mutable SEC submission heads
        +-- download only unseen accession documents
        +-- refresh configured SEC Company Facts fundamentals
        +-- refresh daily market histories
        +-- rebuild the static company pages, one per issuer
        +-- score the prediction log: outcomes for any window that has closed
        +-- write the prediction log: next session's ranking, before its prices
        +-- rebuild the research, overview and earnings pages
        +-- package public HTML only (no snapshot JSON/cache)
        +-- Vercel CLI deploys prebuilt output -> Vercel CDN/domain
        +-- save the cache, even if a step above failed
        +-- commit data/last-refresh.json and this run's predictions/ file
```

The local page directory is larger than what ships, because it includes the JSON
build artifacts; the Vercel bundle publishes only the HTML and the one function.
Measured on the 2026-10-20 run: 194 issuers in the rebuilt universe, 12,032
filings crawled, and a bundle of 196 HTML files at 56.3 MB -- under the 100 MB
Hobby static CLI upload limit, with less headroom than the 42.4 MB this document
recorded before, which is worth watching as the universe grows.

The issuer count moves because `universe.csv` is screened live rather than
pinned. It is not the 193 companies the README and the research page quote --
those come from the frozen evidence package, which does not change when the site
refreshes.

The cache is what makes a nightly run cheap: `edgar.py` skips any accession
document already on disk, so a warm cache turns a twelve-thousand-request crawl
into a handful of requests for whatever was filed since the last run. It is
restored by key prefix because a cache entry is immutable once written -- each
run saves under a new key and the restore picks the most recent. It is saved
even when the run failed, because a crawl that died at request 9,000 has 9,000
documents on disk and discarding them buys nothing.

A cache miss is survivable rather than fatal: no `universe.csv` rebuilds it, no
`data/cache/edgar` crawls from scratch. That costs 30 to 60 minutes once instead
of needing a human.

## One-time setup

Add these as repository secrets under **Settings -> Secrets and variables ->
Actions**. `EDGAR_USER_AGENT` is not a key and needs no registration: the SEC
fair-access policy asks clients to identify themselves, so the value is a real
name and email in one string.

```text
EDGAR_USER_AGENT     required; "Your Name you@example.com"
VERCEL_TOKEN         required to deploy; create it scoped to the one project
VERCEL_ORG_ID        required to deploy; team or personal account id
VERCEL_PROJECT_ID    required to deploy; prj_... of the project serving the domain
FINNHUB_API_KEY      optional; without it the headline refresh is skipped
```

Then run the workflow once by hand from the Actions tab with `full_ingest`
checked. There is nothing for an incremental refresh to be incremental against
until the cache exists, and the scheduled runs keep it warm from there.

Add a Finnhub key only if live headline context is wanted. The refresh queries
the current local universe rather than a hard-coded three-ticker list. It
requests company-news metadata once per ticker, waits between requests, adds a
bounded global-market set, keeps at most five cached rows per ticker for
fourteen days, and sends the API key in a request header. The public company
page still shows at most three exact-ticker/global-market rows. Review the
vendor terms for the final hosting context before enabling a public production
refresh.

## The Vercel frontend

To check a bundle before letting the schedule publish one, build and deploy it
from a local checkout:

```bash
make vercel-bundle
du -sh data/build/vercel_frontend/.vercel/output/static
vercel deploy --cwd data/build/vercel_frontend --prebuilt --archive=tgz
```

Open the preview URL and verify `index.html`, one normal ticker, one
single-letter ticker, and the 404 page. `--prod` promotes it.

The deploy the workflow performs is `scripts/deploy_vercel_frontend.sh`, which
requires `VERCEL_TOKEN`, `VERCEL_ORG_ID` and `VERCEL_PROJECT_ID` and uses a
compressed prebuilt deployment. It lets the Vercel CLI read the token from the
environment instead of placing the credential in the process command line. The
IDs are in **Project -> Settings -> General** and in the owning scope's settings;
for non-interactive runs Vercel recommends supplying both so project linking is
not required.

`VERCEL_PROJECT_ID` must be the project that serves the public site. That is
**`company-lens-josephjwang`**, carrying `https://lens.josephjwang.com` and
`https://company-lens-josephjwang.vercel.app`. It is the only one; a second
project, `company-lens-demo`, existed until 2026-08-27 and was retired precisely
because two of them is an unstable arrangement -- deploying to one leaves the
other serving whatever it last received, and both report success while the two
public URLs drift apart. A stale ID reintroduces that failure, which is why the
ID is worth re-checking rather than copied forward.

## Ask AI provider keys (Vercel, not the refresh job)

Live Q&A is a Vercel serverless function. It discovers providers only from API keys
present in that project's environment. An empty environment returns `models: []` and
the company page labels Q&A as not configured; it does not treat that as a network
failure. These keys belong to the Vercel project and never reach the refresh job,
so nothing here is a repository secret.

Add these as sensitive Production variables on the linked Vercel project. Never put
them in Git, in a runner environment, in generated HTML, or in browser JavaScript:

```dotenv
DEEPSEEK_API_KEY="replace-with-deepseek-key"
DASHSCOPE_API_KEY="replace-with-qwen-key"
COMPANY_LENS_ASK_ORIGIN="https://lens.josephjwang.com"
COMPANY_LENS_ASK_DAILY_BUDGET="300"
COMPANY_LENS_ASK_KV_REST_URL="replace-with-a-redis-rest-endpoint"
COMPANY_LENS_ASK_KV_REST_TOKEN="replace-with-that-endpoint-s-token"
```

### What actually bounds the spend

The endpoint is unauthenticated and five paid provider keys sit behind it, so it
is worth being precise about which control does what.

`COMPANY_LENS_ASK_ORIGIN` compares the `Origin` header to a string. A browser
sets that header honestly; `curl` sets it to whatever you like. It keeps the
demo from being embedded in someone else's page and it is not a spending control.

`COMPANY_LENS_ASK_DAILY_BUDGET` is the ceiling that matters: a count of paid
calls per UTC day for the whole function, checked before the per-IP window and
before any provider is contacted. Exhausting it returns
`429 daily_budget_exhausted` and the static evidence on the page stays readable.

**Both counters are only global if the KV variables are set.** Without them the
counts live in one serverless instance's memory: they reset on every cold start,
and concurrent instances each keep their own, so the effective allowance is the
configured limit multiplied by however many instances are live. That is a speed
bump for one visitor clicking repeatedly, not a bound on what the endpoint can
spend. Any Redis-compatible REST endpoint works and the function reaches it with
plain `fetch`, so no dependency is added. If the store is unreachable the
function degrades to the per-instance counters rather than failing open -- a bad
minute at the counter store must not become an unmetered spend window.

`GET /api/ask` reports `daily_budget` and `shared_counters`, so the deployed
configuration can be checked without a paid call.

`index.js` also knows how to reach OpenAI, Anthropic and Gemini, and exposes
none of them, because the keys are not in this project's environment. That is
the deliberate configuration, not an omission: the endpoint is unauthenticated,
and the cheapest adequate providers are the ones worth leaving reachable behind
a public demo. Adding a key is all it takes to put a provider back.

Set an explicit model env var per provider rather than relying on the function's
defaults -- a default model name goes stale and a stale one fails at request
time. Environment-variable changes do not repair an already-running deployment;
redeploy production after any change here, which `gh workflow run refresh.yml`
does at the end of a refresh.

After deploy, `GET https://lens.josephjwang.com/api/ask` lists exactly the
providers whose keys are present. A bounded POST is a paid provider call and
needs a separate check.

Add the production domain under Vercel **Project -> Domains**, then create the DNS
record Vercel shows. TLS is issued and renewed by Vercel. Nothing in this
architecture should point the public domain anywhere else.

## Running it

`refresh.yml` runs weekly, on Saturday at 07:20 UTC, and whenever you run it:

```bash
gh workflow run refresh.yml
```

Saturday morning UTC is after Friday's close with hours to spare, so a run sees
the whole trading week and Friday's settled prices, and it lands before the
Monday watchdog, so what the watchdog checks is at most two days old. The minute
is off the hour because that is GitHub's worst window for `schedule`.

A nightly cron was the first shape, inherited from the systemd timer this
replaced, and it was too much: crawling 12,000 filings to publish a page nobody
opened that day is rude to the SEC and buys nothing. On demand alone was too
little, and not for a reason about freshness -- see the 60-day note below.
`full_ingest` forces a crawl from scratch; leave it off and a warm cache makes
the run incremental.

One interaction to know about: an Actions cache is evicted after 7 days without
access, and a weekly cadence sits exactly on that boundary, so a late run can
miss and crawl from scratch -- 45 minutes rather than a few. The run detects the
miss and ingests rather than failing. If that becomes frequent, a second weekday
run would keep the cache warm.

A `concurrency` group gives what the worker's file lock gave: a second run waits
rather than fetching the same accessions twice and racing the same cache.

Every run commits `data/last-refresh.json`, success or failure, with a link to
its log. A run that does not happen leaves no trace in this repository, which is
exactly why the previous arrangement could stop for 53 days unnoticed.

The same commit carries that run's `predictions/` file, and for the prediction
log this step is not bookkeeping -- it is the artefact. The log's whole claim is
that a ranking existed publicly before the prices it is judged against did, and
a commit pushed by Actions is what timestamps it; a run that ranked filings and
could not push them has produced nothing. The two reasons this is slightly
fiddly are both in `refresh.yml`: the receipt step resets `--hard` onto the
remote tip to avoid a non-fast-forward, which is the one operation here that can
destroy a tracked file a refresh wrote, so the log is copied aside and back
across it; and `predictions/` is the only tracked output of a refresh, so it is
named explicitly in the `git add` rather than relying on everything else being
gitignored.

`freshness.yml` runs weekly and does no work at all: it fetches one company
page, reads the `data-freshness-date` the page already carries, and fails when
the newest is more than 30 days old. On demand means stale by choice, so this is
not asking "is it current" but "has it rotted past the point a reader following
the README link would notice".

GitHub disables scheduled workflows in a public repository after 60 days with no
repository activity, which is the real argument for the refresh having a
schedule at all: its receipt commit is what resets that clock, for itself and
for the watchdog. With the refresh on demand only, both schedules depended on
someone happening to commit -- which, in a finished portfolio project, is
exactly the assumption that does not hold.

The receipt is pushed after a rebase onto main, because a run takes the better
part of an hour and anything landing meanwhile makes the push a
non-fast-forward. A receipt that still cannot land warns rather than failing the
run: the refresh's own result is the conclusion, not the bookkeeping.

```bash
gh run list --workflow refresh.yml
gh run view --log-failed
gh secret list
```

## Failure behavior

- Accessions are unique keys, so running the job twice does not duplicate filings.
- A failed issuer retains its last good filing and price history.
- Pages are rebuilt from the merged last-good artifacts even when a source is partial.
- Vercel deployment runs only after the HTML build and public bundle both succeed.
- Snapshot JSON, accession text, Parquet files, and SEC identity never enter the
  Vercel bundle.
- A partial refresh exits non-zero after rebuilding, so the run is recorded as a
  visible failure while the last usable site remains online.
- Each page separately displays the latest filing date and the last SEC check time.
- The cache is saved on failure, so a partial crawl is not paid for twice.

## What this replaced, and what it cost

A Vultr worker in Tokyo -- Ubuntu 24.04, 1 vCPU, 1 GB RAM -- held the code and
roughly 336 MB of accession and price caches under `/opt/company-lens` and ran
the same chain from a systemd timer on weekdays at 23:30 UTC. It worked. A full
193-page build took about five minutes there and peaked near 560 MB resident.

It stopped, and the way it stopped is the argument for everything above. Every
page on the live site served `collected 2026-08-27` for 53 days. The deploy
credential's last activity was 2026-09-03 -- so for a week the build and deploy
chain kept running, kept reporting success, and kept publishing a cache that had
stopped advancing. Nothing anywhere went red. The site was wrong in the one way
the project claims to be careful about: confidently, and with a timestamp on the
page saying so to anyone who read it.

Two things follow from that, and both are in the workflows rather than in this
document: a run now leaves a committed trace whether or not anyone is watching,
and something independent reads the published page and fails when it is stale.
The systemd unit and the Nginx fallback that went with this shape were deleted
once the box was gone; `git log` has them if the VPS arrangement is ever wanted
back.
