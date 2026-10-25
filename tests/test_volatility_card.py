"""The volatility card, and the gate that decides whether it exists at all.

Plan §5.5 makes the card conditional: it ships only if the forecast intervals are
calibrated out of sample. That condition is enforced in one place -- the export
writes the card file for a forecaster that passed and deletes it otherwise -- so
these check that the single place works and that the page follows it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from company_lens.web.page import _nav_links, _volatility_forecast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from export_volatility_evidence import _gate, _risk_state, _write_cards  # noqa: E402

CARD = {"as_of": "2026-07-31", "horizon_sessions": 20, "median": 0.25,
        "band_low": 0.17, "band_high": 0.38, "issuer_median": 0.24,
        "vs_issuer": 1.04, "state": "typical for this issuer",
        "forecaster": "har", "coverage_80": 0.774}


def _minimal(**kwargs):
    """A stand-in for the parts of a snapshot these renderers read.

    Building a whole `CompanySnapshot` here would couple every one of these
    tests to fields none of them touch, so a change to an unrelated section
    would break them.
    """
    class Stub:
        disclosure_signal = None
        volatility_forecast = None
        evidence_scope = None
    stub = Stub()
    for key, value in kwargs.items():
        setattr(stub, key, value)
    return stub


class TestTheGateIsTheCardsPrecondition:
    def test_a_well_covered_forecaster_passes(self):
        assert _gate({"coverage_50": 0.49, "coverage_80": 0.79})["calibrated"]

    def test_an_overconfident_forecaster_fails(self):
        """Narrow bands that hold three quarters of outcomes while claiming four
        fifths are the failure this gate exists for."""
        assert not _gate({"coverage_50": 0.45, "coverage_80": 0.755})["calibrated"]

    def test_an_overly_wide_forecaster_also_fails(self):
        """Calibration is two-sided. A band that never misses is not a forecast."""
        assert not _gate({"coverage_50": 0.70, "coverage_80": 0.97})["calibrated"]

    def test_the_error_is_reported_beside_the_verdict(self):
        gate = _gate({"coverage_50": 0.44, "coverage_80": 0.74})
        assert gate["coverage_50_error"] == pytest.approx(0.06)
        assert gate["coverage_80_error"] == pytest.approx(0.06)


class TestTheCardFileFollowsTheGate:
    @pytest.fixture
    def frame(self):
        return pd.DataFrame(
            {"ticker": ["AAPL", "AAPL"],
             "entry_session": pd.to_datetime(["2026-06-01", "2026-07-31"]),
             "trailing_vol": [0.22, 0.26], "actual": [0.24, float("nan")]},
            index=["e1", "e2"])

    @pytest.fixture
    def forecasts(self, frame):
        table = pd.DataFrame(
            {"q10": [0.16, 0.17], "q25": [0.2, 0.21], "q50": [0.24, 0.25],
             "q75": [0.29, 0.3], "q90": [0.36, 0.38], "actual": frame["actual"]},
            index=frame.index)
        return {"har": table}

    def test_no_calibrated_forecaster_writes_no_card(self, tmp_path, frame,
                                                     forecasts):
        path = tmp_path / "volatility_cards.json"
        assert _write_cards(path, frame, forecasts, None, {}) == 0
        assert not path.exists()

    def test_a_stale_card_is_removed_rather_than_left(self, tmp_path, frame,
                                                      forecasts):
        """A card whose evidence stopped supporting it is worse than none: the
        page around it still looks finished."""
        path = tmp_path / "volatility_cards.json"
        path.write_text('{"cards": {"AAPL": {}}}')
        _write_cards(path, frame, forecasts, None, {})
        assert not path.exists()

    def test_the_card_comes_from_the_issuers_latest_filing(self, tmp_path, frame,
                                                           forecasts):
        path = tmp_path / "volatility_cards.json"
        gates = {"har": {"coverage_50": 0.48, "coverage_80": 0.77}}
        assert _write_cards(path, frame, forecasts, "har", gates) == 1
        card = json.loads(path.read_text())["cards"]["AAPL"]
        assert card["as_of"] == "2026-07-31"
        assert card["median"] == pytest.approx(0.25)

    def test_a_filing_without_a_complete_window_still_gets_a_card(self, tmp_path,
                                                                  frame, forecasts):
        """The latest filing is exactly the one whose outcome is unknown. A card
        that waited for the target window would always be a month stale."""
        path = tmp_path / "volatility_cards.json"
        _write_cards(path, frame, forecasts, "har",
                     {"har": {"coverage_50": 0.48, "coverage_80": 0.77}})
        assert pd.isna(frame.loc["e2", "actual"])
        assert json.loads(path.read_text())["cards"]["AAPL"]["as_of"] == "2026-07-31"

    def test_the_stored_coverage_is_coverage_not_its_error(self, tmp_path, frame,
                                                           forecasts):
        path = tmp_path / "volatility_cards.json"
        _write_cards(path, frame, forecasts, "har",
                     {"har": {"coverage_50": 0.48, "coverage_80": 0.77}})
        assert json.loads(path.read_text())["coverage_80"] == pytest.approx(0.77)


class TestTheStateIsARatioNotAThreshold:
    def test_the_same_gap_means_different_things_at_different_levels(self):
        """Six points on a 15% stock and on a 60% stock are not the same news."""
        assert _risk_state(0.21, 0.15) == "elevated"
        assert _risk_state(0.66, 0.60) == "typical for this issuer"

    def test_a_small_move_is_not_a_finding(self):
        assert _risk_state(0.252, 0.24) == "typical for this issuer"

    def test_an_unusually_quiet_forecast_is_named(self):
        assert _risk_state(0.15, 0.30) == "unusually calm"

    def test_no_history_is_unknown_rather_than_calm(self):
        assert _risk_state(0.25, 0.0) == "unknown"


class TestThePageFollowsTheData:
    def test_no_forecast_renders_nothing(self):
        assert _volatility_forecast(_minimal()) == ""

    def test_a_forecast_without_a_median_renders_nothing(self):
        assert _volatility_forecast(
            _minimal(volatility_forecast={"median": None})) == ""

    def test_the_card_never_states_a_direction(self):
        html = _volatility_forecast(_minimal(volatility_forecast=CARD))
        assert "nothing about which way" in html or "says nothing about" in html
        for word in ("buy", "sell", "target price", "upside"):
            assert word not in html.lower()

    def test_the_band_is_drawn_inside_the_track(self):
        html = _volatility_forecast(_minimal(volatility_forecast=CARD))
        import re
        for value in re.findall(r"(?:left|width):([\d.]+)%", html):
            assert 0.0 <= float(value) <= 100.0

    def test_the_forecaster_is_named_in_words_not_in_jargon(self):
        html = _volatility_forecast(_minimal(volatility_forecast=CARD))
        assert "trailing-volatility regression" in html

    def test_the_nav_numbers_what_the_page_actually_has(self):
        """Conditional sections mean a hand-numbered list either skips a number
        or links to a section that is not there."""
        bare = _nav_links(_minimal())
        assert "#volatility" not in bare
        assert "#events" in bare
        assert bare.count("<a ") == 5

        full = _nav_links(_minimal(volatility_forecast=CARD,
                                   disclosure_signal={"state": "routine"}))
        assert "#volatility" in full
        assert "<span>05</span>" in full
