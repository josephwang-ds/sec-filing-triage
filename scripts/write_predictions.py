"""Publish this run's ranking before the reaction it predicts has happened.

Every figure on the research page is retrospective, and a retrospective figure
can only ever argue that it was measured honestly. This writes the other kind:
the filings the ranker puts at the top of a session whose prices do not exist
yet, committed by the scheduled refresh into a public repository. A prediction
that predates its outcome cannot be contaminated by it, and the commit is what
timestamps the claim -- nobody has to take the author's word for the order of
events.

Which filings qualify is the one decision here that matters.

    resolved    the filing's reaction window closed inside the price panel, so
                `build_labels` can measure it. These are the training set.
    published   the filing enters on the first session the panel does not hold.
                Not one price in its reaction window has printed.

The published set is deliberately narrow at both ends. The tempting looser rule
at one end -- rank the filings that entered on the last session the panel holds
-- would be comfortable, because their features are already joined and nothing
needs extending. It would also publish a "prediction" about a window whose first
session has already closed, and the first session is where most of the reaction
is. That file would still be timestamped and still be worthless as evidence.

At the other end, a filing entering two or more sessions out is genuinely
prospective and is still not published, which is the less obvious call. Its
trailing volume features cannot be computed: they read the session before entry,
and that session has not traded either. A record scored with half its inputs
missing is a prediction about a different model from the one the backtest
measured, and the only reason this log exists is to be comparable to that
backtest. This state is rare -- prices and filings refresh in the same chain, so
the panel normally lags the filings by exactly one session -- and when it happens
the run says how many filings it left out rather than quietly ranking them.

One consequence of this, worth knowing before reading any live number it
produces: the refresh runs weekly, so the log is structurally a log of Monday
queues. By the next Saturday every session except the coming Monday has
resolved, and a resolved filing is training data, not a prediction. The live
tally is therefore measured on filings released around a weekend while the
backtest averages over every session of the week. That is a property of the
cadence rather than of the ranker, it is invisible in the hit rate, and the
research page says so from the log's own entry sessions. The fix is a second
refresh on a weekday, not a footnote.

**The one piece of machinery below exists to keep the live features identical to
the backtest's.** `features._issuer_state_features` joins each filing's trailing
market state onto the price panel row for its entry session, and a session that
has not happened has no row -- so every pending filing would score with its
volatility, relative volume and turnover missing, and the live hit rate would
not be measuring the same model the backtest measured. The fix is not to fill
anything in: it is to give the join a row to land on. Every one of those
statistics is `.shift(1)`-ed, so a bar-shaped hole at the entry session yields
exactly the values the real bar will yield when it arrives, computed from
strictly earlier sessions -- which is what the feature already meant.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from filing_triage import prediction_log
from filing_triage.config import PipelineConfig
from filing_triage.features import build_features
from filing_triage.fingerprint import environment, input_fingerprints
from filing_triage.guards import LeakageAudit
from filing_triage.ingest.prices import load_prices, to_returns
from filing_triage.ingest.universe import load_membership, restrict_to_membership
from filing_triage.labels import build_labels
from filing_triage.model import TriageModel
from filing_triage.pit import CALENDAR, TradingClock

PANELS = ("events.parquet", "prices.parquet", "membership.csv")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, default=Path("data/build"))
    parser.add_argument("--out", type=Path, default=prediction_log.DIRECTORY)
    parser.add_argument("--date", default=None,
                        help="the log date to write (default: today, UTC)")
    parser.add_argument("--top", type=int, default=10,
                        help="how deep into each session's queue to publish")
    args = parser.parse_args()

    missing = [name for name in PANELS if not (args.build / name).exists()]
    if missing:
        print(f"no local event panel in {args.build} (missing {missing}); "
              "nothing to predict on. Run `make ingest` first.", file=sys.stderr)
        return 2

    date = args.date or f"{datetime.now(UTC):%Y-%m-%d}"
    path = args.out / f"{date}.json"
    # Not an error. The weekly refresh and a manual run on the same day are both
    # ordinary, and the second one finding the first one's file is the
    # append-only rule working rather than failing.
    if path.exists():
        print(f"{path} already exists; a day's predictions are written once")
        return 0

    events = pd.read_parquet(args.build / "events.parquet")
    prices = load_prices(args.build / "prices.parquet")
    membership = load_membership(args.build / "membership.csv")
    profile_path = args.build / "issuer_profile.csv"
    profile = pd.read_csv(profile_path) if profile_path.exists() else None

    config = PipelineConfig()
    if not config.is_honest:
        raise SystemExit("refusing to publish predictions from a leaking "
                         f"configuration: {config.describe_switches()}")

    ranked, summary = rank_pending(events, prices, membership, config,
                                   issuer_profile=profile, top=args.top)

    payload = {
        "schema_version": prediction_log.SCHEMA_VERSION,
        "date": date,
        "written_at": datetime.now(UTC).isoformat(),
        # Recorded even when the queue is empty, which is the whole reason it is
        # a header field: "nothing was filed for Monday" and "the run did not
        # produce a file" are different facts and a reader must be able to tell.
        "predicts_session": summary["entry_session"],
        "model": {
            "estimator": config.estimator,
            "switches": config.describe_switches(),
            "reaction_threshold": config.reaction_threshold,
            "event_window_sessions": config.event_window_sessions,
            "trained_on_events": summary["trained_on_events"],
            "last_session_in_panel": summary["last_session"],
            # The same fingerprint the evidence package records, for the same
            # reason: EDGAR grows and vendor prices are re-adjusted as of the
            # pull date, so a prediction no longer reproducible from today's
            # panel must be distinguishable from one computed by different code.
            "inputs": input_fingerprints(events, prices, membership),
            "environment": environment(),
        },
        "predictions": ranked,
    }

    prediction_log.write_once(path, payload)
    prediction_log.append_to_manifest(args.out, path.name, payload)

    print(f"predictions for {date}: {len(ranked)} filing(s) ranked for the "
          f"{summary['entry_session']} session, trained on "
          f"{summary['trained_on_events']:,} resolved filings "
          f"(panel through {summary['last_session']}) -> {path}")
    for note, count in sorted(summary["skipped"].items()):
        print(f"  not published: {count} ({note})")
    return 0


# --------------------------------------------------------------------------- #
def rank_pending(events: pd.DataFrame, prices: pd.DataFrame,
                 membership: pd.DataFrame, config: PipelineConfig, *,
                 issuer_profile: pd.DataFrame | None = None,
                 top: int = 10) -> tuple[list[dict], dict]:
    """Score the filings whose reaction has not started, on the resolved ones.

    The order mirrors `pipeline.run`: timing first, universe second, and nothing
    measured until both are settled, because every later step inherits whatever
    those two got wrong.
    """
    clock = TradingClock(embargo=config.embargo)
    events = events.copy()
    events["decision_time"] = events["acceptance_time"].map(clock.decision_time)
    events["session_state"] = events["acceptance_time"].map(clock.session_state)
    events["entry_session"] = events["acceptance_time"].map(clock.entry_session)
    events["event_date"] = events["entry_session"]
    events = events.sort_values("acceptance_time").reset_index(drop=True)
    events = restrict_to_membership(events, membership,
                                    ticker="ticker", when="event_date")

    last_session = max(prices["date"])
    # The session a reader would act on next, and the only one whose filings can
    # be scored on the same features the backtest uses. See the module docstring
    # for why the sessions beyond it are left out rather than ranked badly.
    next_session = CALENDAR.next_session(last_session)
    pending = events["entry_session"] == next_session

    skipped: dict[str, int] = {}
    further = events["entry_session"] > next_session
    if further.any():
        skipped["enters a session the panel cannot reach yet"] = int(further.sum())
    # An issuer with no bars at all cannot be ranked honestly: every trailing
    # feature would be missing and the score would be the imputer's opinion of
    # the corpus rather than a statement about this filing. Itemised rather than
    # dropped quietly, the way `build_labels` itemises its own attrition.
    priced = set(prices["ticker"].unique())
    unpriced = pending & ~events["ticker"].isin(priced)
    if unpriced.any():
        skipped["no price series for the issuer"] = int(unpriced.sum())
    pending &= events["ticker"].isin(priced)

    # Labels come from the real panel. The extended one below exists only so the
    # features have a row to join onto, and letting a placeholder session into
    # the label grid would move every `label_end_session` by a day.
    labels = build_labels(events, to_returns(prices), config)
    returns = to_returns(_with_pending_sessions(prices, events[pending]))
    features = build_features(events, returns, config, labels=labels,
                              profile=issuer_profile)

    _audit(events, features, membership).raise_if_failed()

    trainable = features.index.intersection(labels["event_id"])
    target = labels.set_index("event_id").loc[trainable, "label"]
    if target.nunique() < 2:
        raise SystemExit("the resolved filings carry only one class; there is "
                         "nothing for the ranker to learn from")

    model = TriageModel(config).fit_full(features.loc[trainable], target)

    queue = events[pending].set_index("event_id")
    if queue.empty:
        return [], {"trained_on_events": len(trainable),
                    "entry_session": str(next_session),
                    "last_session": str(last_session), "skipped": skipped}

    scored = pd.DataFrame({
        "score": model.predict_proba(
            features.loc[queue.index].to_numpy(dtype=float))[:, 1],
    }, index=queue.index)
    # Ranked within the entry session, because the product is one morning's
    # queue and that is what the backtest's daily precision@5 measures: five
    # filings out of that session's filings, not five out of everything pending.
    # Grouped rather than assumed single-session, so the rank stays the queue's
    # rank if the published set is ever widened.
    scored["entry_session"] = queue["entry_session"]
    scored["rank"] = (scored.groupby("entry_session")["score"]
                      .rank(ascending=False, method="first").astype(int))
    scored = scored[scored["rank"] <= top].sort_values(["entry_session", "rank"])

    names = _issuer_names(membership)
    ranked = [{
        "accession": str(queue.loc[event_id, "accession"]),
        "cik": int(queue.loc[event_id, "cik"]),
        "ticker": str(queue.loc[event_id, "ticker"]),
        "issuer": names.get(str(queue.loc[event_id, "ticker"])),
        "acceptance_time": queue.loc[event_id, "acceptance_time"].isoformat(),
        "entry_session": str(row.entry_session),
        "rank": int(row.rank),
        "score": round(float(row.score), 6),
    } for event_id, row in zip(scored.index, scored.itertuples(), strict=True)]

    return ranked, {
        "trained_on_events": len(trainable),
        "entry_session": str(next_session),
        "last_session": str(last_session),
        "skipped": skipped,
    }


def _with_pending_sessions(prices: pd.DataFrame,
                           pending: pd.DataFrame) -> pd.DataFrame:
    """Empty bars for every session between the panel's end and the last entry.

    Every column is NaN, which is the honest value: these sessions have not
    traded. What the rows buy is a position in the panel for the `.shift(1)`-ed
    trailing statistics to be computed at, so `rel_volume` on a filing entering
    tomorrow is today's volume over the baseline through today -- the same
    arithmetic the backtest will do when the bar arrives, not an approximation
    of it.

    Because the caller publishes one session, the span this fills is one
    session, and the values come out identical to the ones the backtest computes
    for the same filing once the real bar exists -- all of them read strictly
    earlier sessions, so there is nothing for the missing bar to change. The
    test suite asserts that equality rather than trusting this paragraph.

    Written as a contiguous span rather than as that one row on purpose. Pandas
    rolling windows are positional, so a panel with holes at some sessions and
    not others silently computes `shift(1)` against the wrong day: a panel
    running Friday, Tuesday, Thursday makes Thursday's twenty-day window start
    from Tuesday. The single-row case cannot show that, which is exactly why the
    general form is the one to keep here.
    """
    if pending.empty:
        return prices
    first = CALENDAR.next_session(max(prices["date"]))
    last = max(pending["entry_session"])
    sessions = CALENDAR.sessions_between(first, last)
    holes = pd.DataFrame(
        [(ticker, session) for ticker in sorted(prices["ticker"].unique())
         for session in sessions],
        columns=["ticker", "date"])
    for column in ("open", "high", "low", "close", "volume"):
        holes[column] = np.nan
    return pd.concat([prices, holes[prices.columns]], ignore_index=True)


def _audit(events: pd.DataFrame, features: pd.DataFrame,
           membership: pd.DataFrame) -> LeakageAudit:
    """The same checks the backtest runs, on the frame being published.

    A live run is where a leak would be least visible and most expensive: there
    is no held-out fold to look wrong, just a plausible queue. The entry-open
    check is the one that matters here -- it is the assertion that every filing
    in this file is being ranked for a session whose opening print had not
    happened when EDGAR accepted the document.
    """
    audit = LeakageAudit()
    audit.timezone_aware(events)
    audit.causal(events, fact="acceptance_time", decision="decision_time")
    audit.unique_events(events, ["cik", "accession"])
    audit.universe_pit(events, membership, ticker="ticker", when="event_date")
    audit.feature_matrix(features)

    tz = events["acceptance_time"].dt.tz
    audit.causal(
        pd.DataFrame({
            "acceptance_time": events["acceptance_time"],
            "entry_open": events["entry_session"].map(
                lambda d: CALENDAR.open_at(d).astimezone(tz)),
        }),
        fact="acceptance_time", decision="entry_open",
        label="entry opens after the EDGAR accepted timestamp",
        holds="no entry uses a price printed before EDGAR acceptance")
    return audit


def _issuer_names(membership: pd.DataFrame) -> dict[str, str]:
    """Ticker to issuer name, from the membership table the universe came from.

    The event panel carries no name -- it is keyed on CIK and ticker -- and a
    published record that only says "AMD" is harder for a reader to check
    against EDGAR than one that says Advanced Micro Devices.
    """
    named = membership.dropna(subset=["name"]).drop_duplicates("ticker")
    return dict(zip(named["ticker"].astype(str), named["name"].astype(str),
                    strict=True))


if __name__ == "__main__":
    raise SystemExit(main())
