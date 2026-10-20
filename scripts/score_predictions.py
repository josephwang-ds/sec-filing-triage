"""Fill in what actually happened, weeks after the prediction was published.

Separate from `write_predictions.py` on purpose, and the separation is not
tidiness. One script may only create a day's file and one may only append to it,
so "the outcomes were written by the same code that could have rewritten the
prediction" is not a thing a reader has to rule out by reading carefully. The
guard in `tests/test_prediction_log.py` enforces the half this script may touch;
this docstring records which half that is: `outcome`, one block per record, and
the `scoring` summary at the top of the file.

Nothing is re-measured. The reaction comes from `labels.build_labels` -- the
same market-model event study the backtest's labels come from, at the same
threshold -- because a live tally scored by a second implementation of the
measurement would be comparing two different definitions of "material" and
calling the difference performance.

The anchoring is re-derived rather than inherited. Each record carries the
acceptance time EDGAR stamped and the entry session that was published from it;
this recomputes the second from the first through the same `TradingClock`, and
refuses to score the record if they disagree. A disagreement means the calendar
or the clock has moved since the prediction was published, and silently
re-anchoring an old prediction onto a new rule would score it against a window
nobody predicted.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from filing_triage import prediction_log
from filing_triage.config import PipelineConfig
from filing_triage.ingest.prices import load_prices, to_returns
from filing_triage.labels import build_labels
from filing_triage.pit import CALENDAR, TradingClock


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, default=Path("data/build"))
    parser.add_argument("--log", type=Path, default=prediction_log.DIRECTORY)
    args = parser.parse_args()

    paths = prediction_log.files(args.log)
    if not paths:
        print(f"no prediction files in {args.log}; nothing to score")
        return 0

    panel = args.build / "prices.parquet"
    if not panel.exists():
        print(f"no price panel at {panel}; outcomes cannot be measured yet",
              file=sys.stderr)
        return 2

    config = PipelineConfig()
    prices = load_prices(panel)
    returns = to_returns(prices)
    last_session = max(prices["date"])

    # `scored` is each file's running total and `added` is what this run did.
    # Reported separately because most runs add nothing to most files, and a
    # summary that counted the running total as this run's work would make a
    # no-op look like progress every week.
    total = {"scored": 0, "unmeasurable": 0, "pending": 0, "added": 0}
    for path in paths:
        counts = score_file(path, returns, last_session, config)
        for key in total:
            total[key] += counts[key]
        print(f"{path.name}: {counts['scored']} scored, "
              f"{counts['unmeasurable']} unmeasurable, "
              f"{counts['pending']} still inside its window"
              + (" (unchanged)" if not counts["appended"] else ""))

    print(f"outcomes appended to {total['added']} record(s) this run; "
          f"{total['scored']} scored in all, "
          f"{total['pending']} waiting for a window to close")
    return 0


def score_file(path: Path, returns: pd.DataFrame, last_session,
               config: PipelineConfig) -> dict:
    """Append outcomes to one day's file, leaving every prediction field alone."""
    payload = prediction_log.read(path)
    records = payload.get("predictions", [])
    unscored = [r for r in records if prediction_log.OUTCOME_FIELD not in r]

    counts = {"scored": 0, "unmeasurable": 0, "pending": 0,
              "added": 0, "appended": 0}
    counts["scored"] = sum(
        1 for r in records
        if (r.get(prediction_log.OUTCOME_FIELD) or {}).get("measured"))
    counts["unmeasurable"] = sum(
        1 for r in records
        if prediction_log.OUTCOME_FIELD in r
        and not (r[prediction_log.OUTCOME_FIELD] or {}).get("measured"))
    if not unscored:
        return counts

    closed, open_still = [], 0
    for record in unscored:
        if _window_end(record, config) > last_session:
            open_still += 1
            continue
        closed.append(record)
    counts["pending"] = open_still

    if not closed:
        return counts

    frame = pd.DataFrame([{
        "event_id": record["accession"],
        "ticker": record["ticker"],
        "entry_session": _verified_entry_session(record, config, path),
    } for record in closed])
    measured = build_labels(frame, returns, config).set_index("event_id")

    threshold = float(config.reaction_threshold)
    stamp = datetime.now(UTC).isoformat()
    for record in closed:
        accession = record["accession"]
        if accession not in measured.index:
            # The window closed and the panel still cannot measure it -- a gap in
            # the issuer's bars, or too little history before the event. Recorded
            # rather than left pending, because a record that stays unscored
            # forever is indistinguishable from one nobody got round to, and the
            # live tally's denominator would quietly never settle.
            record[prediction_log.OUTCOME_FIELD] = {
                "measured": False,
                "measured_at": stamp,
                "note": ("the reaction window closed but the price panel could "
                         "not measure it; see build_labels attrition"),
            }
            counts["unmeasurable"] += 1
            counts["added"] += 1
            continue
        row = measured.loc[accession]
        record[prediction_log.OUTCOME_FIELD] = {
            "measured": True,
            "measured_at": stamp,
            "label_end_session": str(row["label_end_session"]),
            "car": round(float(row["car"]), 6),
            "reaction": round(float(row["reaction"]), 6),
            "material": bool(int(row["label"])),
            "reaction_threshold": threshold,
        }
        counts["scored"] += 1
        counts["added"] += 1

    summary = {
        "scored_at": stamp,
        "records": len(records),
        "scored": counts["scored"],
        "unmeasurable": counts["unmeasurable"],
        "pending": counts["pending"],
        "price_panel_last_session": str(last_session),
    }
    payload[prediction_log.SCORING_FIELD] = summary
    prediction_log.rewrite_appending_outcomes(path, payload)
    counts["appended"] = 1
    return counts


def _verified_entry_session(record: dict, config: PipelineConfig, path: Path):
    """The entry session, recomputed from the acceptance time and checked.

    The published value is what was predicted and the recomputed value is what
    the current clock says; scoring against either one silently would be wrong
    in a different way, so a disagreement stops the run instead.
    """
    clock = TradingClock(embargo=config.embargo)
    accepted = pd.Timestamp(record["acceptance_time"])
    derived = clock.entry_session(accepted.to_pydatetime())
    published = pd.Timestamp(record["entry_session"]).date()
    if derived != published:
        raise SystemExit(
            f"{path.name}: {record['accession']} was published with entry "
            f"session {published}, but the clock now derives {derived} from the "
            f"same acceptance time. Scoring it against the new window would "
            f"measure something nobody predicted."
        )
    return published


def _window_end(record: dict, config: PipelineConfig):
    """The last session of the record's reaction window.

    `build_labels` would also refuse an unfinished window -- it drops anything
    running past the end of the panel -- but it refuses it the same way it
    refuses a missing bar, and those two must not be confused: one resolves next
    week and the other never will.
    """
    entry = pd.Timestamp(record["entry_session"]).date()
    return CALENDAR.shift(entry, config.event_window_sessions - 1)


if __name__ == "__main__":
    raise SystemExit(main())
