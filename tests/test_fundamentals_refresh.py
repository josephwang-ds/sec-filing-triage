"""Fundamentals refresh writes artifacts from an injected client, never the network."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from company_lens.refresh import refresh_fundamentals

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sec"


class FakeFactsClient:
    def __init__(self) -> None:
        self.facts_calls: list[tuple[int, bool]] = []
        self.submission_calls: list[int] = []
        self.facts_payload = json.loads((FIXTURES / "aapl_companyfacts_2016_2025.json").read_text())
        self.submissions_payload = json.loads(
            (FIXTURES / "aapl_submissions_fundamentals.json").read_text()
        )

    def company_facts(self, cik: int, *, refresh: bool = False) -> dict:
        self.facts_calls.append((cik, refresh))
        return self.facts_payload

    def submissions(self, cik: int, *, refresh: bool = False) -> dict:
        self.submission_calls.append(cik)
        return self.submissions_payload


def test_refresh_fundamentals_defaults_to_aapl_and_writes_atomically(tmp_path) -> None:
    pd.DataFrame(
        [{"ticker": "AAPL", "cik": 320193, "name": "Apple Inc."}]
    ).to_csv(tmp_path / "universe.csv", index=False)
    (tmp_path / "provenance.json").write_text(json.dumps({"source": "edgar"}))
    client = FakeFactsClient()

    result = refresh_fundamentals(data_dir=tmp_path, client=client)

    artifact = tmp_path / "fundamentals" / "aapl.json"
    assert result.status == "current"
    assert result.refreshed_tickers == ["AAPL"]
    assert artifact.exists()
    payload = json.loads(artifact.read_text())
    assert payload["status"] == "available"
    assert payload["schema_version"] == "company-lens.fundamentals.v1"
    results = json.loads((tmp_path / "financial_results" / "aapl.json").read_text())
    assert results["period_kind"] == "annual"
    assert results["source_url"].startswith("https://www.sec.gov/Archives/")
    assert client.facts_calls == [(320193, True)]
    provenance = json.loads((tmp_path / "provenance.json").read_text())
    assert provenance["fundamentals_refresh"]["refreshed_tickers"] == ["AAPL"]
    assert not (tmp_path / "fundamentals" / ".aapl.json.part").exists()


def test_refresh_fundamentals_isolates_unknown_tickers_when_universe_present(
    tmp_path,
) -> None:
    pd.DataFrame(
        [{"ticker": "AAPL", "cik": 320193, "name": "Apple Inc."}]
    ).to_csv(tmp_path / "universe.csv", index=False)
    with pytest.raises(ValueError, match="MSFT"):
        refresh_fundamentals(data_dir=tmp_path, tickers=["MSFT"], client=FakeFactsClient())


class ExplodingFactsClient(FakeFactsClient):
    def company_facts(self, cik: int, *, refresh: bool = False) -> dict:
        raise RuntimeError("Authorization: Bearer SUPER_SECRET_TOKEN failed")


def test_offline_refresh_uses_cached_facts_and_does_not_call_the_client(tmp_path) -> None:
    build = tmp_path / "build"
    build.mkdir()
    pd.DataFrame(
        [{"ticker": "AAPL", "cik": 320193, "name": "Apple Inc."}]
    ).to_csv(build / "universe.csv", index=False)
    cache = tmp_path / "edgar"
    (cache / "companyfacts").mkdir(parents=True)
    (cache / "submissions").mkdir()
    (cache / "companyfacts" / "CIK0000320193.json").write_text(
        (FIXTURES / "aapl_companyfacts_2016_2025.json").read_text()
    )
    (cache / "submissions" / "CIK0000320193.json").write_text(
        (FIXTURES / "aapl_submissions_fundamentals.json").read_text()
    )

    result = refresh_fundamentals(
        data_dir=build, offline=True, cache_dir=cache, client=ExplodingFactsClient()
    )

    assert result.status == "current"
    report = json.loads((build / "financial_results" / "aapl.json").read_text())
    assert report["extraction"] == "company_facts"
    assert report["status"] == "available"
    assert report["metrics"]
    assert report["source_url"].startswith("https://www.sec.gov/Archives/")


def test_offline_cache_miss_is_not_a_network_fetch(tmp_path) -> None:
    build = tmp_path / "build"
    build.mkdir()
    pd.DataFrame(
        [{"ticker": "AAPL", "cik": 320193, "name": "Apple Inc."}]
    ).to_csv(build / "universe.csv", index=False)

    result = refresh_fundamentals(
        data_dir=build, offline=True, cache_dir=tmp_path / "empty", client=ExplodingFactsClient()
    )

    assert result.status == "partial"
    assert result.failures[0]["exception_type"] == "CacheMiss"
    assert "SUPER_SECRET" not in result.failures[0]["message"]
    assert not (build / "financial_results" / "aapl.json").exists()


def test_refresh_fundamentals_records_safe_per_company_failures(tmp_path, capsys) -> None:
    pd.DataFrame(
        [{"ticker": "AAPL", "cik": 320193, "name": "Apple Inc."}]
    ).to_csv(tmp_path / "universe.csv", index=False)
    (tmp_path / "provenance.json").write_text(json.dumps({"source": "edgar"}))

    result = refresh_fundamentals(data_dir=tmp_path, client=ExplodingFactsClient())

    assert result.status == "partial"
    assert result.failed_tickers == ["AAPL"]
    assert result.failures
    failure = result.failures[0]
    assert failure["ticker"] == "AAPL"
    assert failure["exception_type"] == "RuntimeError"
    assert "SUPER_SECRET_TOKEN" not in failure["message"]
    assert "[redacted]" in failure["message"]
    logged = capsys.readouterr().out
    assert "ticker=AAPL" in logged
    assert "RuntimeError" in logged
    assert "SUPER_SECRET_TOKEN" not in logged
