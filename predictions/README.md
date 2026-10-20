# The prospective prediction log

One file per refresh run, named for the day it was written:

```
predictions/2026-10-24.json      written by scripts/write_predictions.py
predictions/manifest.json        a digest of each file's prediction half
```

Every other number this project publishes is retrospective. The leakage audit is
what makes them honest, and it is a real argument — but it is still an argument
about how carefully the past was handled, and a reader is being asked to accept
it. This directory is the other kind of claim. Each file holds the filings the
ranker put at the top of a session whose prices did not exist yet, committed to
a public repository by a scheduled workflow before any price in their reaction
windows had printed. You cannot leak a future that has not happened into a file
that already exists, and the commit timestamps itself.

## The two halves

A record is written once and appended to once.

```json
{
  "accession": "0000320193-26-000012",
  "cik": 320193,
  "ticker": "AAPL",
  "issuer": "Apple Inc.",
  "acceptance_time": "2026-10-16T20:05:00+00:00",
  "entry_session": "2026-10-19",
  "rank": 1,
  "score": 0.712345,

  "outcome": {                                 ← appended weeks later
    "measured": true,
    "label_end_session": "2026-10-20",
    "car": 0.0412,
    "reaction": 2.41,
    "material": true,
    "reaction_threshold": 2.0
  }
}
```

The prediction half is fixed on the day it is written. The `outcome` block is
added by `scripts/score_predictions.py` once the reaction window has closed,
measured by the same market-model event study — and at the same 2.0σ threshold —
that produces the backtest's labels, so the live tally and the published 19.8%
mean the same thing by "material".

Nothing else may change. `tests/test_prediction_log.py` fails the build if any
published prediction field moves, and that test's docstring explains how the
files are pinned and why the commit graph, not the manifest beside them, is the
part that carries the claim.

## What it is not, yet

A small sample, honestly. The first months hold a few dozen scored filings at
best, the 95% interval on a hit rate that size spans both the backtest and a
random queue, and the filings are not independent draws — one morning's top five
share a market. The research page publishes it in that state on purpose: a live
tally first shown once it reads well is a highlight reel, not evidence.

It is also not a random sample of sessions. The refresh runs weekly on a
Saturday, and a filing is only publishable while no price in its reaction window
has printed — so by the next run, every session except the coming Monday has
resolved and those filings are training data. The log is therefore a log of
Monday queues, measured on filings released around a weekend, while the backtest
it is shown beside averages over every session of the week. That is a property
of the schedule, not of the ranker; a second weekday refresh would widen it.
The research page states it, read from the log's own entry sessions.

It compounds by one session a week. That is the only thing that fixes it.
