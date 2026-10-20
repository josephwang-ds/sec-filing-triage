"""The prospective prediction log: the one claim a backtest cannot make.

Every other number this project publishes is retrospective. The leakage audit
makes them honest -- the ranking is scored on filings whose outcomes were walled
off from the model that ranked them -- but honesty about hindsight is still a
claim about process, and a reader is asked to believe it. "I never peeked" is
not verifiable from the artefact.

A prediction published before its outcome exists needs no such belief. You
cannot leak a future that has not happened into a file that already exists, and
a commit pushed by CI into a public repository timestamps itself: the proof is
the commit graph, not the author's word. That is the whole reason this log is
written by the scheduled refresh rather than by hand.

So the file has two halves and they are governed differently:

    the prediction half    the ranked filings, the scores, the fingerprint of
                           the model and data they came from. Written once, on
                           the day the ranking was made, and never rewritten.
    the outcome half       one `outcome` block per record, appended weeks later
                           when the reaction window has closed.

`record_digest` hashes the prediction half alone, which is what makes the two
halves separable by a test rather than by a convention. `tests/test_prediction_log.py`
is the guard; this module is only the format and the arithmetic, so the guard,
the writer and the scorer cannot disagree about what "the prediction half" means.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date
from pathlib import Path

DIRECTORY = Path("predictions")
MANIFEST = "manifest.json"
SCHEMA_VERSION = "1"

# A day's file is named for the day it was written, which is also the key the
# manifest and the immutability guard use.
FILENAME = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday")

# The fields fixed at prediction time. Exhaustive on purpose: the guard rejects
# an unknown key rather than ignoring it, so a field added later has to be
# added here -- and anyone adding one is forced past the comment explaining that
# a new prediction field cannot be backfilled onto records already published.
PREDICTION_FIELDS = (
    "accession",        # the SEC's own identifier for the submission
    "cik",
    "ticker",
    "issuer",
    "acceptance_time",  # the knowledge time everything in this project keys off
    "entry_session",
    "rank",             # within the entry session, as the queue would show it
    "score",
)
OUTCOME_FIELD = "outcome"

# Written by the scorer, excluded from the digest: it says when scoring last
# ran, which must be free to change without the prediction half appearing to.
SCORING_FIELD = "scoring"

HEADER_FIELDS = ("schema_version", "date", "written_at",
                 "predicts_session", "model")


class PredictionLogError(RuntimeError):
    """The log is in a shape no writer of it could have produced."""


# --------------------------------------------------------------------------- #
# The format
# --------------------------------------------------------------------------- #
def prediction_half(payload: dict) -> dict:
    """Everything that was fixed when the predictions were published.

    Taken by subtraction rather than by listing, so a key that appears in a file
    without passing through `PREDICTION_FIELDS` lands inside the digest and
    fails the guard. Listing the fields to keep would silently tolerate it.
    """
    records = []
    for record in payload.get("predictions", []):
        records.append({k: v for k, v in record.items() if k != OUTCOME_FIELD})
    header = {k: v for k, v in payload.items()
              if k not in ("predictions", SCORING_FIELD)}
    return {**header, "predictions": records}


def record_digest(payload: dict) -> str:
    """sha256 over the prediction half, rendered canonically.

    Canonical rather than over the file's bytes, for the same reason
    `fingerprint.frame_digest` is: an indent change or a key reordering by a
    different json writer is not a changed prediction, and a check that fires on
    one gets switched off before it ever catches a real edit.
    """
    rendered = json.dumps(prediction_half(payload), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(rendered.encode()).hexdigest()


def unexpected_fields(payload: dict) -> list[str]:
    """Keys no writer in this repository puts in a prediction file.

    Reported rather than raised, so the guard can name all of them at once.
    """
    strays = [key for key in payload
              if key not in (*HEADER_FIELDS, "predictions", SCORING_FIELD)]
    for i, record in enumerate(payload.get("predictions", [])):
        strays += [f"predictions[{i}].{key}" for key in record
                   if key not in (*PREDICTION_FIELDS, OUTCOME_FIELD)]
    return strays


def write_once(path: Path, payload: dict) -> None:
    """Write a day's predictions, refusing to touch a file that already exists.

    The refusal is the feature. A second refresh on the same day -- a manual
    `gh workflow run` after the weekly one -- would otherwise re-rank the same
    filings against a model trained on a few more hours of prices, and the
    second ranking would overwrite the first with no trace. That is the one
    thing a prospective log cannot survive, and it is an ordinary accident.
    """
    if path.exists():
        raise PredictionLogError(
            f"{path} already exists. A day's predictions are written once; "
            "re-ranking the same filings later and keeping the second answer is "
            "exactly the hindsight this log exists to rule out."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def rewrite_appending_outcomes(path: Path, payload: dict) -> None:
    """Write a file back, refusing if anything in the prediction half moved.

    The test suite's guard is what fails a build, and it is the check a reader
    should trust. This is the one that stops the damage being written at all: the
    scorer holds the whole payload in memory and a mistake there -- a key
    renamed, a score re-rounded, a record reordered -- would land on disk looking
    exactly like an honest append. Comparing the digest of what is about to be
    written against the digest of what is on disk costs one read and makes that
    class of mistake impossible rather than merely detectable later.
    """
    before = record_digest(read(path))
    after = record_digest(payload)
    if before != after:
        raise PredictionLogError(
            f"{path} would be rewritten with a different prediction half "
            f"({before[:12]} -> {after[:12]}); only outcome fields may be added"
        )
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def read(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def files(directory: Path = DIRECTORY) -> list[Path]:
    """Every day's prediction file, oldest first. Nothing else in the directory."""
    directory = Path(directory)
    if not directory.exists():
        return []
    return sorted(p for p in directory.glob("*.json") if FILENAME.match(p.name))


def load(directory: Path = DIRECTORY) -> list[dict]:
    return [read(path) for path in files(directory)]


# --------------------------------------------------------------------------- #
# The manifest
# --------------------------------------------------------------------------- #
def read_manifest(directory: Path = DIRECTORY) -> dict:
    path = Path(directory) / MANIFEST
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "files": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def append_to_manifest(directory: Path, name: str, payload: dict) -> dict:
    """Pin one new day's digest, refusing to repin a day already in the manifest.

    The manifest is a convenience, not the proof: it is committed by the same
    process that writes the file it pins, so an editor who changes both still
    passes it. What makes it worth having is that it works in a shallow clone,
    an sdist or a zip download, where there is no commit graph to ask -- see the
    guard's docstring for which check carries the weight.
    """
    manifest = read_manifest(directory)
    entries = manifest.setdefault("files", {})
    if name in entries:
        raise PredictionLogError(
            f"{name} is already pinned in {MANIFEST}; a published digest is not "
            "repinned, because repinning is how an edited prediction passes"
        )
    entries[name] = {
        "sha256": record_digest(payload),
        "records": len(payload.get("predictions", [])),
        "written_at": payload.get("written_at"),
    }
    manifest["schema_version"] = SCHEMA_VERSION
    path = Path(directory) / MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    return manifest


# --------------------------------------------------------------------------- #
# Reading the log back
# --------------------------------------------------------------------------- #
def top_k_outcomes(payloads: list[dict], k: int = 5) -> dict:
    """The live tally: of the top `k` published each day, how many were material.

    Only records whose outcome has arrived count in the numerator or the
    denominator. A prediction still waiting for its window to close is neither a
    hit nor a miss, and quietly counting it as a miss is how a live number gets
    made to look worse than it is -- the same class of error, pointed the other
    way, as the ones the leakage ladder prices.
    """
    published = scored = material = 0
    pending = unmeasurable = 0
    dates: list[str] = []
    weekdays: set[str] = set()
    for payload in payloads:
        date = payload.get("date")
        if date:
            dates.append(date)
        for record in payload.get("predictions", []):
            session = record.get("entry_session")
            if session:
                weekdays.add(_weekday(session))
            if int(record.get("rank", 0)) > k:
                continue
            published += 1
            outcome = record.get(OUTCOME_FIELD)
            if outcome is None:
                pending += 1
            elif not outcome.get("measured"):
                unmeasurable += 1
            else:
                scored += 1
                material += int(bool(outcome.get("material")))

    low, high = wilson_interval(material, scored)
    return {
        "k": k,
        "dates": sorted(dates),
        # Which weekdays the log actually covers, which is a property of the
        # refresh cadence and not of the model. A weekly Saturday run can only
        # publish the queue for the following Monday: by the next Saturday every
        # other session's windows have closed, so those filings are training
        # data rather than predictions. Reported because a live tally measured
        # on weekend filings is not measured on the same population as the
        # backtest's all-sessions average, and a reader cannot see that from
        # the hit rate.
        # In week order, not alphabetical: the page prints them in a sentence.
        "weekdays": sorted(weekdays, key=WEEKDAYS.index),
        "files": len(payloads),
        "records": sum(len(p.get("predictions", [])) for p in payloads),
        "published_at_k": published,
        "scored_at_k": scored,
        "material_at_k": material,
        "pending_at_k": pending,
        "unmeasurable_at_k": unmeasurable,
        "hit_rate": material / scored if scored else None,
        "hit_rate_ci_low": low,
        "hit_rate_ci_high": high,
    }


def _weekday(session: str) -> str:
    year, month, day = (int(part) for part in str(session).split("-")[:3])
    return WEEKDAYS[date(year, month, day).weekday()]


def wilson_interval(successes: int, trials: int, z: float = 1.96) -> tuple:
    """A 95% interval for a proportion, by the Wilson score method.

    Not the normal approximation, and the reason is this log's whole situation:
    the first months of it are a handful of trials, and at n=7 the textbook
    interval runs past 0 and 1 and collapses to width zero when every trial is a
    hit. Wilson stays inside the unit interval and stays wide where the evidence
    is thin, which is what a reader needs from the early rows of a live tally
    far more than they need the point estimate.
    """
    if trials <= 0:
        return (None, None)
    p = successes / trials
    denominator = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denominator
    spread = (z * math.sqrt(p * (1 - p) / trials
                            + z * z / (4 * trials * trials)) / denominator)
    return (max(0.0, centre - spread), min(1.0, centre + spread))
