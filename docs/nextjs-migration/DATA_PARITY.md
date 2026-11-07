# Data parity — the old page against the new one

## What is compared, and why this way

Both front ends read one snapshot, so a number that differs between them is a
migration defect rather than a difference of opinion.

`scripts/compare_lens_pages.py` renders the Python page from a snapshot and
writes the display literals the engine produces from it.
`apps/lens-web/scripts/parity.mjs` then opens **both pages in a browser**, reads
the rendered text and links out of each, and reports anything not present on
both.

In a browser because neither page can be compared as static HTML. The Python
page's history section is empty in the file it serves and is filled in from an
inline JSON block on load, so its numbers are not in the HTML at all. Both pages
also collapse older filings behind a disclosure control, and `innerText` does
not see hidden content — a closed `<details>` would read as a missing value on
both sides, and the comparison would pass by agreeing about nothing. So the
harness expands every `<details>` first.

## Result

```
SYN071 (3Y): 16/16 values match between pages
SYN112 (3Y): 24/24 values match between pages
```

Compared per company: latest adjusted close, ending value, total return,
benchmark return, return gap in percentage points, annualised volatility,
maximum drawdown, period start and end, snapshot date, the three most recent
filing accessions and their SEC source links, and — where the snapshot carries a
filed report — revenue, net income, diluted EPS, gross profit and each one's
period end.

Full output: `data/build/parity/parity.json`.

## Differences found, and what they were

Three, all of them in the new front end, all presentation rather than value:

| Difference | Old page | First version here | Resolution |
| --- | --- | --- | --- |
| Ending value precision | `$10,352` | `$10,351.70` | the history section is rendered in the browser with `Intl.NumberFormat(..., {maximumFractionDigits: 0})`; the new page now uses the same |
| Trailing zero on a percentage | `+49%` | `+49.0%` | same cause: `maximumFractionDigits: 1` drops the trailing zero. Matched. |
| Unit of the return gap | `-24.3 percentage points` | `-24.3%` | a difference of two cumulative returns is points, not a percentage. Writing it with a percent sign invites the reader to read it as a relative change. The label and the formatting now follow the Python page. |

The default period also differed: the Python page opens on the snapshot's own
span rounded to whole years, and the new page opened on 5Y. Aligned, so both
open on the same period and a comparison is not explaining away a default.

## Rounding

Python's format spec rounds half to even; JavaScript's `toFixed` does not. The
server-rendered helpers in `src/lib/format.ts` reproduce half-to-even, with
tests over the boundary cases, so the two front ends print the same literal
rather than differing by one in the last digit. The history section uses `Intl`
on both sides.

## What this run does not establish

- It was run on the two committed fixtures, whose issuers are synthetic. It
  proves the two front ends agree given a snapshot; it does not exercise a real
  issuer's data, because none is available locally.
- **AAPL, JPM and NVDA have not been compared.** The brief asks for them
  specifically. Doing it needs either `EDGAR_USER_AGENT` set so the engine can
  build their snapshots here, or a copy of `data/build/company_pages/` from the
  machine that publishes the site. The harness takes a `--snapshots` directory
  and will run against them unchanged.
- It compares rendered values, not pixels. Layout is covered by the E2E suite.

## Re-running it

```bash
# 1. snapshots -> old pages + expected literals
PYTHONPATH=src python scripts/compare_lens_pages.py --snapshots data/build/company_pages

# 2. serve the new front end over the same snapshots
cd apps/lens-web && npm run build && npx next start --port 4320

# 3. compare what each page shows
node apps/lens-web/scripts/parity.mjs --base-url http://127.0.0.1:4320
```

Exit code 1 if any value is not on both pages.
