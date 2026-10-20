"""The guard on the prediction log: published predictions do not move.

`test_guards.py` points at the past -- it asks whether a number could have been
computed by someone standing at the decision time. This file points the same
question at the future. A prospective log's entire value is that each record
existed before its outcome did, and that value survives exactly one edit: the
first silent one. So the prediction half of every record already in the
repository is checked against what it said when it was published, and only an
appended `outcome` is allowed to be new.

**How it is pinned, and why that choice is the sound one.**

Two mechanisms are available and they are not equally strong, so both run.

`predictions/manifest.json` holds a digest per file. It is cheap, it works in a
shallow clone, an sdist or a zip download, and it catches the realistic failure:
a scoring run with a bug in it, a merge resolved the wrong way, an editor
reflowing JSON. What it cannot do is survive a determined author, because the
manifest is committed by the same process that writes the file it pins -- one
commit can move both and this check still passes. A guard whose strength is
overstated is worse than a weak guard, so it is named here for what it is.

The commit graph is the mechanism that actually carries the claim. Git is asked
what the file said in the commit that introduced it, and the prediction half
must still say precisely that. Changing a past commit's content means rewriting
public history and force-pushing: GitHub records it, every existing clone
contradicts it, and the CI run that pushed the original commit is still in the
Actions log with its own timestamp. That is a different kind of assurance from a
checked-in hash: it does not rest on the author having left the file alone. It
is also the reason this log is written by a scheduled workflow rather than from
a laptop.

The git check needs history, so it is skipped in a shallow checkout and the
workflows fetch full history to stop that being the normal case. It is skipped
rather than failed because a shallow clone is a legitimate way to have this
repository, and the manifest check still runs there; but the skip is reported,
because a check that quietly does not run is decoration.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from filing_triage import prediction_log

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "predictions"


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def _history_is_available() -> bool:
    """A full clone, with the commit that introduced each file still reachable."""
    shallow = _git("rev-parse", "--is-shallow-repository")
    return shallow.returncode == 0 and shallow.stdout.strip() == "false"


def _as_published(path: Path) -> dict | None:
    """The file's content in the commit that added it, or None if git cannot say."""
    relative = path.relative_to(ROOT).as_posix()
    introduced = _git("log", "--diff-filter=A", "--format=%H", "--", relative)
    commits = [line for line in introduced.stdout.split() if line]
    if introduced.returncode != 0 or not commits:
        return None
    blob = _git("show", f"{commits[-1]}:{relative}")
    return json.loads(blob.stdout) if blob.returncode == 0 else None


@pytest.fixture(scope="module")
def published() -> list[Path]:
    return prediction_log.files(LOG)


class TestThePublishedLogIsImmutable:
    def test_the_manifest_pins_every_published_file(self, published):
        """A file with no digest beside it is outside the guard entirely, which
        is the state an accidental `git add` of a hand-written day produces."""
        pinned = set(prediction_log.read_manifest(LOG).get("files", {}))
        assert {path.name for path in published} <= pinned, (
            f"not pinned in {prediction_log.MANIFEST}: "
            f"{sorted({p.name for p in published} - pinned)}"
        )

    def test_every_file_still_matches_its_pinned_digest(self, published):
        entries = prediction_log.read_manifest(LOG).get("files", {})
        for path in published:
            expected = entries[path.name]["sha256"]
            actual = prediction_log.record_digest(prediction_log.read(path))
            assert actual == expected, (
                f"{path.name} no longer hashes to its pinned digest. Only "
                f"`outcome` blocks may be added to a published prediction; the "
                f"prediction half is fixed on the day it was written."
            )

    def test_every_file_still_matches_the_commit_that_introduced_it(self, published):
        """The check that does not rest on the author not having edited anything.

        See this module's docstring: the manifest is pinned by a commit that
        could also have moved the file, the commit graph is not.
        """
        if not published:
            pytest.skip("the log is empty; nothing has been published yet")
        if not _history_is_available():
            pytest.skip("shallow checkout: no commit history to compare against")

        compared = 0
        for path in published:
            original = _as_published(path)
            if original is None:
                continue        # written in the working tree, not yet committed
            assert (prediction_log.prediction_half(original)
                    == prediction_log.prediction_half(prediction_log.read(path))), (
                f"{path.name} differs from the commit that introduced it in a "
                f"prediction field, not only in appended outcomes"
            )
            compared += 1
        assert compared or len(published), "nothing was compared"

    def test_no_record_carries_a_field_this_repository_never_writes(self, published):
        """An unknown key is either a new prediction field that was never pinned
        or an outcome smuggled in under another name. Both defeat the split the
        digest relies on, so the digest covers them and this names them."""
        for path in published:
            strays = prediction_log.unexpected_fields(prediction_log.read(path))
            assert not strays, f"{path.name} carries unknown fields: {strays}"


# --------------------------------------------------------------------------- #
# A guard that cannot fail is decoration, so the next class edits a log on
# purpose and requires each check to catch it.
# --------------------------------------------------------------------------- #
PREDICTION = {
    "accession": "0000320193-26-000012",
    "cik": 320193,
    "ticker": "AAPL",
    "issuer": "Apple Inc.",
    "acceptance_time": "2026-10-16T20:05:00+00:00",
    "entry_session": "2026-10-19",
    "rank": 1,
    "score": 0.712345,
}

OUTCOME = {
    "measured": True,
    "measured_at": "2026-10-24T07:21:00+00:00",
    "label_end_session": "2026-10-20",
    "car": 0.0412,
    "reaction": 2.41,
    "material": True,
    "reaction_threshold": 2.0,
}


@pytest.fixture
def log(tmp_path) -> Path:
    payload = {
        "schema_version": prediction_log.SCHEMA_VERSION,
        "date": "2026-10-17",
        "written_at": "2026-10-17T07:21:00+00:00",
        "model": {"estimator": "random_forest", "trained_on_events": 9721},
        "predictions": [PREDICTION, {**PREDICTION, "accession": "x-2", "rank": 2,
                                     "score": 0.5}],
    }
    prediction_log.write_once(tmp_path / "2026-10-17.json", payload)
    prediction_log.append_to_manifest(tmp_path, "2026-10-17.json", payload)
    return tmp_path


def _pinned(directory: Path, name: str = "2026-10-17.json") -> str:
    return prediction_log.read_manifest(directory)["files"][name]["sha256"]


def _rewrite(path: Path, mutate) -> dict:
    payload = prediction_log.read(path)
    mutate(payload)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return payload


class TestTheDigestCatchesWhatItMustCatch:
    def test_appending_an_outcome_leaves_the_digest_alone(self, log):
        path = log / "2026-10-17.json"
        payload = _rewrite(path, lambda p: p["predictions"][0].update(
            {prediction_log.OUTCOME_FIELD: OUTCOME}))
        assert prediction_log.record_digest(payload) == _pinned(log)

    def test_a_changed_score_is_caught(self, log):
        path = log / "2026-10-17.json"
        payload = _rewrite(path, lambda p: p["predictions"][0].update(
            {"score": 0.9}))
        assert prediction_log.record_digest(payload) != _pinned(log)

    def test_a_reranked_queue_is_caught(self, log):
        """The edit with the strongest motive and the weakest trace: the scores
        stay, the ranks swap, and the top five becomes the five that worked."""
        path = log / "2026-10-17.json"
        payload = _rewrite(path, lambda p: [
            p["predictions"][0].update({"rank": 2}),
            p["predictions"][1].update({"rank": 1}),
        ])
        assert prediction_log.record_digest(payload) != _pinned(log)

    def test_a_dropped_record_is_caught(self, log):
        path = log / "2026-10-17.json"
        payload = _rewrite(path, lambda p: p["predictions"].pop())
        assert prediction_log.record_digest(payload) != _pinned(log)

    def test_a_record_added_after_the_fact_is_caught(self, log):
        path = log / "2026-10-17.json"
        payload = _rewrite(path, lambda p: p["predictions"].append(
            {**PREDICTION, "accession": "x-3", "rank": 3, "score": 0.4}))
        assert prediction_log.record_digest(payload) != _pinned(log)

    def test_a_retimed_prediction_is_caught(self, log):
        """`written_at` is in the digest because a prediction's value is when it
        was made; a file that can be backdated is not a prospective log."""
        path = log / "2026-10-17.json"
        payload = _rewrite(path, lambda p: p.update(
            {"written_at": "2026-10-24T07:21:00+00:00"}))
        assert prediction_log.record_digest(payload) != _pinned(log)

    def test_reformatting_the_file_is_not_an_edit(self, log):
        """A digest that fires on an indent change gets switched off, and then
        it is not there for the edit that matters."""
        path = log / "2026-10-17.json"
        payload = prediction_log.read(path)
        path.write_text(json.dumps(payload, indent=8, sort_keys=True))
        assert prediction_log.record_digest(prediction_log.read(path)) == _pinned(log)

    def test_the_scoring_summary_is_outside_the_digest(self, log):
        path = log / "2026-10-17.json"
        payload = _rewrite(path, lambda p: p.update(
            {prediction_log.SCORING_FIELD: {"scored_at": "2026-10-24T07:21:00+00:00"}}))
        assert prediction_log.record_digest(payload) == _pinned(log)

    def test_an_outcome_hidden_under_a_new_key_is_caught(self, log):
        """The way round the split, if the digest only covered known fields."""
        path = log / "2026-10-17.json"
        payload = _rewrite(path, lambda p: p["predictions"][0].update(
            {"realised_reaction": 2.4}))
        assert prediction_log.record_digest(payload) != _pinned(log)
        assert prediction_log.unexpected_fields(payload) == [
            "predictions[0].realised_reaction"]


class TestTheWritersRefuseTheObviousAccidents:
    def test_a_days_file_is_not_rewritten(self, log):
        with pytest.raises(prediction_log.PredictionLogError, match="written once"):
            prediction_log.write_once(log / "2026-10-17.json", {"predictions": []})

    def test_a_days_digest_is_not_repinned(self, log):
        with pytest.raises(prediction_log.PredictionLogError, match="already pinned"):
            prediction_log.append_to_manifest(log, "2026-10-17.json",
                                              {"predictions": []})

    def test_the_scorer_refuses_to_write_a_moved_prediction(self, log):
        """The scorer holds the whole payload in memory, so a bug there would
        land on disk looking like an honest append."""
        path = log / "2026-10-17.json"
        payload = prediction_log.read(path)
        payload["predictions"][0]["score"] = 0.9
        with pytest.raises(prediction_log.PredictionLogError,
                           match="only outcome fields"):
            prediction_log.rewrite_appending_outcomes(path, payload)

    def test_the_scorer_writes_an_honest_append(self, log):
        path = log / "2026-10-17.json"
        payload = prediction_log.read(path)
        payload["predictions"][0][prediction_log.OUTCOME_FIELD] = OUTCOME
        prediction_log.rewrite_appending_outcomes(path, payload)
        assert prediction_log.record_digest(prediction_log.read(path)) == _pinned(log)


class TestTheLiveTally:
    def test_only_resolved_records_reach_the_denominator(self):
        payload = {"date": "2026-10-17", "predictions": [
            {**PREDICTION, "rank": 1, prediction_log.OUTCOME_FIELD:
                {**OUTCOME, "material": True}},
            {**PREDICTION, "rank": 2, prediction_log.OUTCOME_FIELD:
                {**OUTCOME, "material": False}},
            {**PREDICTION, "rank": 3},                       # window still open
            {**PREDICTION, "rank": 4, prediction_log.OUTCOME_FIELD:
                {"measured": False}},
            {**PREDICTION, "rank": 9, prediction_log.OUTCOME_FIELD: OUTCOME},
        ]}
        tally = prediction_log.top_k_outcomes([payload], k=5)
        assert tally["published_at_k"] == 4          # rank 9 is outside the read
        assert tally["scored_at_k"] == 2
        assert tally["material_at_k"] == 1
        assert tally["pending_at_k"] == 1
        assert tally["unmeasurable_at_k"] == 1
        assert tally["hit_rate"] == 0.5

    def test_an_empty_log_reports_no_rate_rather_than_zero(self):
        tally = prediction_log.top_k_outcomes([], k=5)
        assert tally["hit_rate"] is None
        assert tally["hit_rate_ci_low"] is None

    def test_the_interval_stays_inside_the_unit_interval(self):
        """The case the normal approximation gets wrong, and the first months of
        this log will be exactly it: a handful of trials, all of them hits."""
        low, high = prediction_log.wilson_interval(5, 5)
        assert 0.0 <= low < 1.0
        assert high == 1.0

    def test_the_interval_narrows_as_the_sample_grows(self):
        narrow = prediction_log.wilson_interval(20, 100)
        wide = prediction_log.wilson_interval(2, 10)
        assert (narrow[1] - narrow[0]) < (wide[1] - wide[0])
