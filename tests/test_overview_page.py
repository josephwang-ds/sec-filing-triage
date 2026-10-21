"""The plain-language page, and the two ways it would stop being one.

It would stop being plain if jargon crept back in, and it would stop being true
if a number were typed into it. The page it replaces failed the second way: a
hand-written write-up that still claimed an ROC AUC of 0.888 and 123 tests long
after both had moved.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_overview_page import load, render  # noqa: E402  (needs the path above)

EVIDENCE = ROOT / "evidence" / "real_run"

# Terms a reader without a background in finance or machine learning would have
# to look up. The page exists to not need them.
JARGON = (
    "average precision", "ROC AUC", "AUC", "precision@", "PR-AUC",
    "calibration", "bootstrap", "walk-forward", "quantile", "pinball",
    "embargo", "purged", "out-of-sample", "ablation", "p-value", "percentile",
)


@pytest.fixture(scope="module")
def page() -> str:
    if not (EVIDENCE / "metrics.json").exists():
        pytest.skip("no exported evidence in this checkout")
    return render(load(EVIDENCE, ROOT))


@pytest.fixture(scope="module")
def prose(page) -> str:
    body = page[page.index("<body"):]
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))


class TestItIsActuallyPlain:
    @pytest.mark.parametrize("term", JARGON)
    def test_the_jargon_is_absent_not_merely_softened(self, prose, term):
        assert term.lower() not in prose.lower(), (
            f"{term!r} is on the page a non-specialist is supposed to read"
        )

    def test_it_opens_with_the_problem_not_the_method(self, prose):
        opening = prose[:400].lower()
        assert "disclosures" in opening
        assert "analyst" in opening

    def test_it_is_short_enough_to_finish(self, prose):
        """A page a recruiter will not finish has not communicated anything."""
        assert len(prose.split()) < 1200


class TestNothingIsTranscribed:
    def test_the_source_hard_codes_no_result(self):
        """The failure that killed the page this one replaces."""
        source = (ROOT / "scripts" / "build_overview_page.py").read_text()
        code = re.sub(r"<style>.*?</style>", "", source, flags=re.S)
        literals = set(re.findall(r"(?<![\w.\-])0\.\d{3}(?![\w])", code))
        assert not literals, f"{sorted(literals)} are written into the generator"

    def test_it_refuses_to_render_without_the_evidence(self, tmp_path):
        with pytest.raises(SystemExit, match="make evidence"):
            load(tmp_path, ROOT)

    def test_the_headline_numbers_come_from_the_ladder(self, page):
        with (EVIDENCE / "leakage_study.csv").open() as handle:
            ladder = list(csv.DictReader(handle))
        assert f"{float(ladder[0]['average_precision']):.3f}" in page
        assert f"{float(ladder[-1]['average_precision']):.3f}" in page

    def test_the_impossible_entry_count_comes_from_the_ladder(self, page):
        with (EVIDENCE / "leakage_study.csv").open() as handle:
            naive = next(csv.DictReader(handle))
        assert f"{int(float(naive['impossible_entries'])):,}" in page

    def test_the_test_count_tracks_the_readme(self, page):
        """One number is not in the evidence package. It is read from the README,
        which a test keeps accurate, rather than typed here as a second place to
        be wrong."""
        stated = re.search(r"(\d+) tests", (ROOT / "README.md").read_text())
        assert stated and f"{int(stated.group(1)):,}" in page


class TestTheBoundariesSurviveTheSimplification:
    def test_it_still_says_direction_is_not_predicted(self, prose):
        """The claim most worth misreading, and the one a plain-language page is
        most tempted to drop."""
        assert "never which direction" in prose

    def test_it_still_refuses_recommendations(self, prose):
        assert "no buy or sell recommendations" in prose.lower()

    def test_it_states_the_ceiling_beside_the_headline(self, prose):
        """20% sounds unimpressive alone and is most of what is achievable. Both
        halves have to be on the page or the number misleads in one direction or
        the other."""
        assert "if you somehow knew in advance" in prose
        assert "cannot find what is not there" in prose
        assert "average share of selected filings" in prose
        assert "not the chance of finding at least one material filing" in prose
        assert "of the time, the top five contained" not in prose

    def test_the_failures_are_reported_not_only_the_successes(self, prose):
        assert "did not work" in prose
        metrics = json.loads((EVIDENCE / "self_relative_metrics.json").read_text())
        if metrics.get("text"):
            assert "worse" in prose
