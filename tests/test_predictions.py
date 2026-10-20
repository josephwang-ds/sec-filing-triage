"""Writing and scoring the prospective log.

Two properties carry everything here, and they pull in opposite directions.

A published record must be *prospective*: no price inside its reaction window
may have printed when the file was written, or the log is a backtest with a
commit date on it.

A published record must also be *comparable*: it has to be scored by the same
model, on the same features, against the same definition of material as the
19.8% it is published beside. A live tally that is honest but measures a
differently-fed model answers a question nobody asked.

The feature test below is the one that was nearly got wrong. A filing entering
tomorrow has no price bar for tomorrow, so the trailing-state join finds nothing
and every volatility and volume feature arrives empty -- quietly, because the
estimator imputes them. The predictions would still be prospective and would no
longer be comparable to anything.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from filing_triage import prediction_log
from filing_triage.config import PipelineConfig
from filing_triage.features import build_features
from filing_triage.ingest.prices import to_returns
from filing_triage.labels import build_labels
from filing_triage.pit import CALENDAR, TradingClock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from score_predictions import score_file  # noqa: E402
from write_predictions import _with_pending_sessions, rank_pending  # noqa: E402

CONFIG = PipelineConfig()
TRAILING = ["vol_20", "abs_ret_5", "log_dollar_volume", "rel_volume"]


@pytest.fixture(scope="module")
def split(world):
    """The world as a refresh sees it: prices a week behind the filings.

    The real chain refreshes both in one run, so the panel normally ends one
    session before the filings do. A week is used here because it leaves enough
    pending filings to assert about.
    """
    sessions = sorted(world.prices["date"].unique())
    cutoff = sessions[-6]
    return {
        "events": world.events,
        "membership": world.membership,
        "prices": world.prices[world.prices["date"] <= cutoff].copy(),
        "later": world.prices,
        "cutoff": cutoff,
        "next_session": CALENDAR.next_session(cutoff),
    }


@pytest.fixture(scope="module")
def published(split):
    ranked, summary = rank_pending(split["events"], split["prices"],
                                   split["membership"], CONFIG)
    return {"ranked": ranked, "summary": summary}


class TestWhatGetsPublished:
    def test_the_run_ranks_something(self, published):
        """Every assertion below is vacuous on an empty queue."""
        assert published["ranked"]
        assert published["summary"]["trained_on_events"] > 0

    def test_only_the_next_session_is_published(self, published, split):
        sessions = {record["entry_session"] for record in published["ranked"]}
        assert sessions == {str(split["next_session"])}

    def test_no_price_in_the_window_had_printed(self, published, split):
        """The property the whole log rests on. The entry session is the first
        session of the reaction window, and it is not in the panel the ranking
        was computed from."""
        last = max(split["prices"]["date"])
        for record in published["ranked"]:
            assert pd.Timestamp(record["entry_session"]).date() > last

    def test_every_entry_open_postdates_its_acceptance_time(self, published):
        """The same invariant the backtest's guards enforce, on live records."""
        for record in published["ranked"]:
            accepted = pd.Timestamp(record["acceptance_time"])
            opens = CALENDAR.open_at(pd.Timestamp(record["entry_session"]).date())
            assert accepted <= pd.Timestamp(opens)

    def test_ranks_are_a_queue(self, published):
        ranks = sorted(record["rank"] for record in published["ranked"])
        assert ranks == list(range(1, len(ranks) + 1))
        scores = [record["score"] for record in
                  sorted(published["ranked"], key=lambda r: r["rank"])]
        assert scores == sorted(scores, reverse=True)

    def test_the_record_names_the_filing_a_reader_can_look_up(self, published):
        for record in published["ranked"]:
            assert record["accession"]
            assert record["ticker"]
            assert record["issuer"]

    def test_the_summary_names_the_panel_it_was_trained_on(self, published, split):
        assert published["summary"]["last_session"] == str(max(split["prices"]["date"]))


class TestTheLiveFeaturesMatchTheBacktest:
    """A prospective prediction scored on different inputs is not comparable.

    `_with_pending_sessions` fills the panel with empty bars so the trailing
    statistics -- every one of which is already shifted a session -- have a row
    to be joined onto. The claim is that this is not an approximation: the
    values are the ones the backtest will compute for the same filing once the
    real bar arrives, because none of them reads the entry session itself.
    """

    @pytest.fixture(scope="class")
    @staticmethod
    def features(split):
        clock = TradingClock(embargo=CONFIG.embargo)
        events = split["events"].copy()
        events["session_state"] = events["acceptance_time"].map(clock.session_state)
        events["entry_session"] = events["acceptance_time"].map(clock.entry_session)
        events = events.sort_values("acceptance_time").reset_index(drop=True)

        pending = events[events["entry_session"] == split["next_session"]]
        live = build_features(
            events, to_returns(_with_pending_sessions(split["prices"], pending)),
            CONFIG)
        later = build_features(events, to_returns(split["later"]), CONFIG)
        return {"ids": pending["event_id"], "live": live, "later": later}

    def test_the_trailing_features_are_computed_at_all(self, features):
        """Without the filled panel every one of these is missing, which is the
        failure this exists to prevent and the one an imputer hides."""
        assert not features["live"].loc[features["ids"], TRAILING].isna().any().any()

    def test_they_equal_what_the_real_bar_will_produce(self, features):
        live = features["live"].loc[features["ids"], TRAILING]
        later = features["later"].loc[features["ids"], TRAILING]
        pd.testing.assert_frame_equal(live, later)

    def test_an_unfilled_panel_would_have_lost_them(self, split, features):
        """The counterfactual, asserted rather than described: this is what the
        obvious implementation produces."""
        clock = TradingClock(embargo=CONFIG.embargo)
        events = split["events"].copy()
        events["session_state"] = events["acceptance_time"].map(clock.session_state)
        events["entry_session"] = events["acceptance_time"].map(clock.entry_session)
        events = events.sort_values("acceptance_time").reset_index(drop=True)
        bare = build_features(events, to_returns(split["prices"]), CONFIG)
        assert bare.loc[features["ids"], TRAILING].isna().all().all()


class TestAppendingOutcomes:
    @pytest.fixture
    def log(self, tmp_path, published, split):
        payload = {
            "schema_version": prediction_log.SCHEMA_VERSION,
            "date": str(split["cutoff"]),
            "written_at": "2024-01-01T00:00:00+00:00",
            "predicts_session": str(split["next_session"]),
            "model": {"estimator": CONFIG.estimator},
            "predictions": [dict(record) for record in published["ranked"]],
        }
        path = tmp_path / f"{split['cutoff']}.json"
        prediction_log.write_once(path, payload)
        prediction_log.append_to_manifest(tmp_path, path.name, payload)
        return path

    def test_a_closed_window_gets_its_outcome(self, log, split):
        counts = score_file(log, to_returns(split["later"]),
                            max(split["later"]["date"]), CONFIG)
        assert counts["scored"]
        for record in prediction_log.read(log)["predictions"]:
            outcome = record[prediction_log.OUTCOME_FIELD]
            assert outcome["measured"] is True
            assert isinstance(outcome["material"], bool)
            assert outcome["reaction_threshold"] == CONFIG.reaction_threshold

    def test_an_open_window_is_left_alone(self, log, split):
        """Scored against the panel the prediction was written from, nothing can
        resolve -- and an unresolved record must stay unresolved rather than
        acquiring an outcome measured from half a window."""
        counts = score_file(log, to_returns(split["prices"]),
                            max(split["prices"]["date"]), CONFIG)
        assert counts["scored"] == 0
        assert counts["pending"] == len(prediction_log.read(log)["predictions"])
        for record in prediction_log.read(log)["predictions"]:
            assert prediction_log.OUTCOME_FIELD not in record

    def test_the_prediction_half_survives_scoring(self, log, split):
        pinned = prediction_log.read_manifest(log.parent)["files"][log.name]["sha256"]
        score_file(log, to_returns(split["later"]), max(split["later"]["date"]),
                   CONFIG)
        assert prediction_log.record_digest(prediction_log.read(log)) == pinned

    def test_scoring_twice_appends_nothing_new(self, log, split):
        returns, last = to_returns(split["later"]), max(split["later"]["date"])
        score_file(log, returns, last, CONFIG)
        first = prediction_log.read(log)["predictions"]
        again = score_file(log, returns, last, CONFIG)
        assert again["appended"] == 0
        assert prediction_log.read(log)["predictions"] == first

    def test_the_outcome_is_the_pipelines_own_measurement(self, log, split):
        """Not a second implementation of the event study. A live tally scored by
        a reimplementation would be comparing two definitions of material."""
        score_file(log, to_returns(split["later"]), max(split["later"]["date"]),
                   CONFIG)
        records = prediction_log.read(log)["predictions"]
        frame = pd.DataFrame([{"event_id": r["accession"], "ticker": r["ticker"],
                               "entry_session": pd.Timestamp(
                                   r["entry_session"]).date()} for r in records])
        expected = build_labels(frame, to_returns(split["later"]),
                                CONFIG).set_index("event_id")
        for record in records:
            outcome = record[prediction_log.OUTCOME_FIELD]
            row = expected.loc[record["accession"]]
            assert outcome["reaction"] == pytest.approx(float(row["reaction"]),
                                                        abs=1e-6)
            assert outcome["material"] == bool(int(row["label"]))

    def test_a_reanchored_entry_session_stops_the_run(self, log, split):
        """The entry session is re-derived from the acceptance time rather than
        trusted. If the clock ever moves, scoring an old prediction against the
        new window would measure something nobody predicted."""
        payload = prediction_log.read(log)
        moved = CALENDAR.next_session(
            pd.Timestamp(payload["predictions"][0]["entry_session"]).date())
        payload["predictions"][0]["entry_session"] = str(moved)
        log.write_text(json.dumps(payload, indent=2))
        with pytest.raises(SystemExit, match="nobody predicted"):
            score_file(log, to_returns(split["later"]),
                       max(split["later"]["date"]), CONFIG)
