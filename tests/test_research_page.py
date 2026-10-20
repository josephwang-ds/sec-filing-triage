"""The findings page, and why none of its numbers live in its source.

A hand-written summary of a measured result is a copy, and a copy drifts. This
project's whole argument is that numbers drift when nothing is watching, so the
page that makes that argument publicly cannot itself be a transcription: it is
generated from `evidence/real_run` at build time, and it fails loudly rather
than rendering a stale figure when the export is missing.
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

from build_research_page import load, render  # noqa: E402  (needs the path above)

EVIDENCE = ROOT / "evidence" / "real_run"


@pytest.fixture(scope="module")
def page() -> str:
    if not (EVIDENCE / "metrics.json").exists():
        pytest.skip("no exported evidence in this checkout")
    return render(load(EVIDENCE))


@pytest.fixture(scope="module")
def evidence() -> dict:
    if not (EVIDENCE / "metrics.json").exists():
        pytest.skip("no exported evidence in this checkout")
    with (EVIDENCE / "leakage_study.csv").open() as handle:
        ladder = list(csv.DictReader(handle))
    return {
        "metrics": json.loads((EVIDENCE / "metrics.json").read_text()),
        "ladder": ladder,
    }


class TestNothingIsTranscribed:
    def test_the_source_hard_codes_no_result(self):
        """The check that keeps this page honest. A three-decimal literal in the
        generator is a number that stopped tracking the evidence the moment it
        was typed."""
        source = (ROOT / "scripts" / "build_research_page.py").read_text()
        # Strip the CSS block, where decimals are line-heights and opacities.
        code = re.sub(r"<style>.*?</style>", "", source, flags=re.S)
        literals = set(re.findall(r"(?<![\w.\-])0\.\d{3}(?![\w])", code))
        assert not literals, (
            f"{sorted(literals)} are written into the generator; they must be "
            "read from evidence/real_run instead"
        )

    def test_it_refuses_to_render_without_the_export(self, tmp_path):
        """Silently rendering a page with blanks where the findings should be is
        worse than not rendering: the page would still look finished."""
        with pytest.raises(SystemExit, match="make evidence"):
            load(tmp_path)


class TestThePageCarriesTheFindings:
    def test_the_ladder_endpoints_appear(self, page, evidence):
        ladder = evidence["ladder"]
        assert f"{float(ladder[0]['average_precision']):.3f}" in page
        assert f"{float(ladder[-1]['average_precision']):.3f}" in page

    def test_the_headline_carries_its_interval(self, page, evidence):
        m = evidence["metrics"]
        assert f"{m['average_precision']:.3f}" in page
        assert f"{m['average_precision_ci_low']:.3f}" in page
        assert f"{m['average_precision_ci_high']:.3f}" in page

    def test_precision_is_shown_against_its_ceiling(self, page, evidence):
        """The number alone invites reading 19.8% as failure. The ceiling is what
        makes it readable."""
        m = evidence["metrics"]
        assert f"{m['daily_precision_at_5']:.1%}" in page
        assert f"{m['daily_oracle_precision_at_5']:.1%}" in page
        assert f"{m['daily_span_captured_at_5']:.0%}" in page

    def test_the_impossible_entry_count_appears(self, page, evidence):
        naive = evidence["ladder"][0]
        assert f"{int(float(naive['impossible_entries'])):,}" in page

    def test_the_page_states_its_own_limitation(self, page):
        """Everything else on the page is real, which makes the survivorship
        caveat exactly the one a reader would assume away."""
        assert "survivorship" in page.lower() or "survivor" in page.lower()

    def test_it_links_back_into_the_site(self, page):
        assert 'href="index.html"' in page
        assert 'href="report.html"' in page


class TestTheIndexLinksToIt:
    def test_the_entry_points_exist_in_the_renderer(self):
        """A page nobody can reach is not published. The index carries both
        links, in both languages."""
        source = (ROOT / "src" / "company_lens" / "web" / "page.py").read_text()
        assert 'href="research.html"' in source
        assert 'href="earnings.html"' in source
        for key in ("method.research", "method.earnings"):
            assert source.count(f"'{key}'") >= 2, (
                f"{key} needs an English and a Chinese string"
            )


@pytest.fixture(scope="module")
def self_relative() -> dict:
    path = EVIDENCE / "self_relative_metrics.json"
    if not path.exists():
        pytest.skip("no issuer-relative export in this checkout")
    return json.loads(path.read_text())


class TestTheIssuerRelativeSectionsCarryTheirEvidence:
    """The second model's results reach the page the same way the first's do:
    read from the export, never typed."""

    def test_the_base_rate_it_has_to_beat_is_shown(self, page, self_relative):
        assert f"{self_relative['target']['base_rate']:.1%}" in page

    def test_the_shipped_calibration_is_marked_as_the_pick(self, page):
        assert "Leave the scores alone" in page
        assert "<em>(shipped)</em>" in page

    def test_the_calibration_error_comes_from_the_export(self, page, self_relative):
        assert f"{self_relative['calibration']['ece']:.3f}" in page

    def test_the_read_now_threshold_is_the_selected_one(self, page, self_relative):
        assert f"{self_relative['recommendation']['read_now_threshold']:.2f}" in page

    def test_abstention_is_described_rather_than_hidden(self, page):
        """An issuer with too little history is told so. A page that showed only
        the states it could score would describe a different product."""
        assert "too short" in page

    def test_it_says_the_target_carries_no_direction(self, page):
        """The one claim on the page that a reader could most damagingly
        misread."""
        assert "direction cannot be recovered" in page


class TestTheTransformerResultIsReportedEitherWay:
    def test_the_ablation_interval_appears_when_it_was_run(self, page):
        if "financial transformer" not in page:
            pytest.skip("no text cache in this checkout")
        with (EVIDENCE / "nlp_feature_ablation.csv").open() as handle:
            rows = {r["group"]: r for r in csv.DictReader(handle)}
        row = rows["transformer_text"]
        assert f"{float(row['diff_ci_low']):+.4f}" in page

    def test_the_section_is_absent_without_a_text_cache(self):
        """The page is generated from evidence; a section describing an encode
        that never happened would be its one hand-written claim."""
        from build_research_page import _transformer_section

        assert _transformer_section({"ablation": [], "metrics": {}}) == ""
        assert _transformer_section(
            {"ablation": [{"group": "transformer_text"}], "metrics": {}}) == ""

    def test_a_partial_issuer_relative_export_fails_loudly(self, tmp_path):
        """Half of it is worse than none: the page would render a calibration
        table beside a policy fitted in a different run."""
        from build_research_page import _self_relative

        (tmp_path / "calibration_comparison.csv").write_text("method\n")
        with pytest.raises(SystemExit, match="partial issuer-relative"):
            _self_relative(tmp_path, lambda name: [])

    def test_no_issuer_relative_export_simply_omits_the_sections(self, tmp_path):
        from build_research_page import _issuer_relative, _self_relative

        assert _self_relative(tmp_path, lambda name: []) == {"self_relative": None}
        assert _issuer_relative({"self_relative": None}) == ""


@pytest.fixture(scope="module")
def volatility() -> dict:
    path = EVIDENCE / "volatility_metrics.json"
    if not path.exists():
        pytest.skip("no volatility export in this checkout")
    return json.loads(path.read_text())


class TestTheVolatilitySectionStatesItsOwnLimits:
    def test_the_horizon_is_named(self, page, volatility):
        assert f"{volatility['task']['horizon']} sessions" in page

    def test_the_shipped_forecaster_is_the_one_that_passed_the_gate(self, page,
                                                                    volatility):
        shipped = volatility["shipped"]
        assert volatility["gates"][shipped]["calibrated"] is True
        assert f"Vs {volatility['reference'].upper()}" in page

    def test_the_foundation_model_result_is_reported_not_omitted(self, page,
                                                                 volatility):
        if "chronos" not in volatility["gates"]:
            pytest.skip("no foundation-model forecasts in this checkout")
        with (EVIDENCE / "volatility_paired.csv").open() as handle:
            paired = {r["forecaster"]: r for r in csv.DictReader(handle)}
        assert f"{float(paired['chronos']['difference']):+.4f}" in page

    def test_the_regime_split_is_shown_not_only_the_average(self, page):
        """A forecaster can hit its nominal coverage overall by being too wide
        when calm and too narrow when turbulent, which is backwards for a risk
        card."""
        assert "turbulent" in page
        assert "widen enough" in page

    def test_it_says_the_forecast_never_reaches_the_ranker(self, page):
        assert "reaches the ranker" in page

    def test_a_partial_volatility_export_fails_loudly(self, tmp_path):
        from build_research_page import _volatility

        (tmp_path / "volatility_paired.csv").write_text("forecaster\n")
        with pytest.raises(SystemExit, match="partial volatility"):
            _volatility(tmp_path, lambda name: [])

    def test_no_volatility_export_omits_the_section(self, tmp_path):
        from build_research_page import _volatility, _volatility_section

        assert _volatility(tmp_path, lambda name: []) == {"volatility": None}
        assert _volatility_section(None) == ""


class TestTheIssuerRelativeAblationIsShownEitherWay:
    """The layer's own contribution, reported whichever way it came out. It came
    out neutral, and a page that measured the transformer but assumed this one
    would be applying its standard selectively."""

    def test_the_ablation_reference_row_is_present(self, page):
        assert "Market state and filing metadata" in page

    def test_the_neutral_result_is_stated_not_buried(self, prose):
        assert "add nothing measurable" in prose

    def test_the_page_says_where_the_columns_do_earn_their_place(self, page):
        """They are what a Read now cites, which is a different job from being a
        model input."""
        assert "cites" in page

    def test_the_interval_comes_from_the_export(self, page):
        with (EVIDENCE / "self_relative_ablation.csv").open() as handle:
            rows = {r["group"]: r for r in csv.DictReader(handle)}
        row = rows["base_plus_self_relative"]
        assert f"{float(row['diff_ci_low']):+.4f}" in page

    def test_per_fold_results_are_shown(self, page):
        with (EVIDENCE / "self_relative_fold_metrics.csv").open() as handle:
            folds = list(csv.DictReader(handle))
        assert f"Fold {int(folds[0]['fold']) + 1}" in page
        assert f"{float(folds[-1]['pr_auc']):.3f}" in page


@pytest.fixture(scope="module")
def prose(page) -> str:
    """The page with tags and line breaks collapsed.

    Prose assertions must not depend on where the source happened to wrap: a
    sentence broken across two lines in the f-string is the same sentence to a
    reader, and a test that failed on it would be testing the formatter.
    """
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page))


class TestTheWorkedCasesKeepTheMisses:
    def test_both_outcomes_appear(self, page):
        """A cases block showing only the hits would claim a reliability the
        precision figure directly contradicts."""
        assert "as expected" in page
        assert "missed" in page

    def test_a_real_missed_read_now_is_shown(self, page):
        path = EVIDENCE / "recommendation_cases.json"
        cases = json.loads(path.read_text())["cases"]
        missed = [c for c in cases.get("read_now", [])
                  if c["outcome"] != "as expected"]
        assert missed, "the export produced no Read now failures to show"
        assert missed[0]["ticker"] in page

    def test_the_note_explains_what_the_precision_means(self, prose):
        assert "wrong more often than it is right" in prose


class TestTheLiveSectionIsHonestAtEveryStage:
    """The prospective log reaches the page the same way the evidence does.

    Every other section on this page renders a finished result. This one has to
    render an unfinished one for months -- no outcomes at all at first, then a
    sample far too small to mean anything -- and still be legible. The tests
    below are mostly about the states the section passes through, because a page
    that only reads well once the numbers are flattering is the thing this
    project argues against.
    """

    @staticmethod
    def _written(tmp_path, *, outcomes, rank_from=1, count=6):
        from filing_triage import prediction_log

        records = []
        for i in range(count):
            record = {
                "accession": f"0000320193-26-00001{i}",
                "cik": 320193, "ticker": "AAPL", "issuer": "Apple Inc.",
                "acceptance_time": "2026-10-16T20:05:00+00:00",
                "entry_session": "2026-10-19",
                "rank": rank_from + i,
                "score": 0.9 - i / 10,
            }
            if outcomes:
                record[prediction_log.OUTCOME_FIELD] = {
                    "measured": True, "material": i == 0,
                    "reaction": 2.4 if i == 0 else 0.4,
                }
            records.append(record)
        payload = {
            "schema_version": prediction_log.SCHEMA_VERSION,
            "date": "2026-10-17",
            "written_at": "2026-10-17T07:21:00+00:00",
            "predicts_session": "2026-10-19",
            "model": {"estimator": "random_forest"},
            "predictions": records,
        }
        prediction_log.write_once(tmp_path / "2026-10-17.json", payload)
        return tmp_path

    def test_no_log_omits_the_section(self, tmp_path):
        """Before the first refresh writes a file there is nothing to say, and a
        section with nothing behind it is the one hand-written claim on a page
        generated from evidence."""
        from build_research_page import _live, _live_section

        assert _live(None) == {"live": None}
        assert _live(tmp_path) == {"live": None}
        assert _live_section({"live": None}, {}) == ""

    def test_a_log_with_no_outcomes_still_renders(self, tmp_path, evidence):
        """The state the first weeks are in. Hiding it until it reads well is
        how a live tally becomes a highlight reel."""
        from build_research_page import _live, _live_section

        data = _live(self._written(tmp_path, outcomes=False))
        section = _live_section(data, evidence["metrics"])
        assert "Not yet answerable" in section
        assert "Nothing above is a result" in section

    def test_a_scored_log_shows_the_rate_against_both_references(self, tmp_path,
                                                                 evidence):
        from build_research_page import _live, _live_section

        m = evidence["metrics"]
        section = _live_section(_live(self._written(tmp_path, outcomes=True)), m)
        # One material filing in the top five of the one published session.
        assert f"{1 / 5:.1%}" in section
        assert f"{m['daily_precision_at_5']:.1%}" in section
        assert f"{m['daily_random_precision_at_5']:.1%}" in section

    def test_the_rate_is_quoted_with_an_interval_and_a_sample_size(self, tmp_path,
                                                                   evidence):
        """A hit rate over a handful of filings without its interval is the
        error this project exists to point at, committed by this project."""
        from build_research_page import _live, _live_section

        from filing_triage.prediction_log import wilson_interval

        section = _live_section(_live(self._written(tmp_path, outcomes=True)),
                                evidence["metrics"])
        low, high = wilson_interval(1, 5)
        assert f"[{low:.1%}, {high:.1%}]" in section
        assert "small and early" in section

    def test_only_the_top_five_reach_the_tally(self, tmp_path, evidence):
        """The published number is a top-five read, so a record ranked sixth is
        in the log and out of the rate."""
        from build_research_page import _live

        deep = _live(self._written(tmp_path, outcomes=True, rank_from=6))
        assert deep["live"]["tally"]["scored_at_k"] == 0
        assert deep["live"]["days"][0]["records"] == 6

    def test_a_pending_record_is_not_counted_as_a_miss(self, tmp_path):
        """Counting an unresolved prediction as wrong understates the live
        number, which is the same class of error as overstating it."""
        from build_research_page import _live

        tally = _live(self._written(tmp_path, outcomes=False))["live"]["tally"]
        assert tally["pending_at_k"] == 5
        assert tally["hit_rate"] is None

    def test_it_says_which_sessions_the_log_can_cover(self, tmp_path, evidence):
        """The limitation a reader cannot see from the hit rate: a weekly
        Saturday refresh can only ever publish the following Monday's queue, so
        the live sample is weekend filings and the backtest beside it is every
        session of the week."""
        from build_research_page import _live, _live_section

        section = _live_section(_live(self._written(tmp_path, outcomes=True)),
                                evidence["metrics"])
        assert "not a random sample of sessions" in section
        # 2026-10-19, the entry session every fixture record carries.
        assert "every session in this log is a Monday" in section
