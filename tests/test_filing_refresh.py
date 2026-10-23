from __future__ import annotations

import json

import pandas as pd

from company_lens.refresh import refresh_filings, refresh_market_data


def _payload(accessions: list[str]) -> dict:
    return {
        "filings": {
            "recent": {
                "accessionNumber": accessions,
                "filingDate": ["2024-01-02", "2024-04-02"][: len(accessions)],
                "reportDate": ["2023-12-31", "2024-03-31"][: len(accessions)],
                "acceptanceDateTime": [
                    "2024-01-02T17:00:00.000Z",
                    "2024-04-02T17:00:00.000Z",
                ][: len(accessions)],
                "form": ["8-K"] * len(accessions),
                "items": ["2.02,9.01"] * len(accessions),
                "primaryDocument": ["filing.htm"] * len(accessions),
            }
        }
    }


class FakeClient:
    def __init__(self) -> None:
        self.documents: list[str] = []

    def submissions(self, cik: int, *, refresh: bool = False) -> dict:
        assert cik == 123
        assert refresh is True
        return _payload(["0000000123-24-000001", "0000000123-24-000002"])

    def document_text(self, cik: int, accession: str, document: str) -> str:
        self.documents.append(accession)
        return f"Revenue was $120 million in {accession}."


def _seed(tmp_path) -> None:
    pd.DataFrame(
        [{"ticker": "ABC", "cik": 123, "name": "ABC Corp"}]
    ).to_csv(tmp_path / "universe.csv", index=False)
    events = pd.DataFrame(
        [
            {
                "cik": 123,
                "accession": "0000000123-24-000001",
                "form": "8-K",
                "items": "2.02,9.01",
                "primary_document": "filing.htm",
                "acceptance_time": pd.Timestamp(
                    "2024-01-02 17:00", tz="America/New_York"
                ),
                "filing_date": pd.Timestamp("2024-01-02").date(),
                "period_of_report": pd.Timestamp("2023-12-31").date(),
                "ticker": "ABC",
                "text": "Revenue was $100 million.",
                "event_id": "0000000123-24-000001",
            }
        ]
    )
    events.to_parquet(tmp_path / "events.parquet", index=False)
    (tmp_path / "provenance.json").write_text(json.dumps({"source": "edgar"}))


def test_refresh_appends_only_unseen_accessions_and_records_freshness(tmp_path) -> None:
    _seed(tmp_path)
    client = FakeClient()

    result = refresh_filings(data_dir=tmp_path, client=client)

    events = pd.read_parquet(tmp_path / "events.parquet")
    provenance = json.loads((tmp_path / "provenance.json").read_text())
    assert result.status == "current"
    assert result.new_filings == 1
    assert result.changed_tickers == ["ABC"]
    assert client.documents == ["0000000123-24-000002"]
    assert events["accession"].is_unique
    assert len(events) == 2
    assert provenance["filing_refresh"]["checked_at"] == result.checked_at
    assert provenance["filing_refresh"]["latest_acceptance_time"].startswith("2024-04-02")


def test_refresh_is_idempotent(tmp_path) -> None:
    _seed(tmp_path)
    client = FakeClient()
    refresh_filings(data_dir=tmp_path, client=client)

    second = refresh_filings(data_dir=tmp_path, client=client)

    events = pd.read_parquet(tmp_path / "events.parquet")
    assert second.new_filings == 0
    assert len(events) == 2
    assert events["accession"].is_unique


def test_market_refresh_replaces_successful_symbols_and_keeps_failures(
    tmp_path, monkeypatch
) -> None:
    pd.DataFrame(
        [
            {"ticker": "ABC", "cik": 123, "name": "ABC Corp"},
            {"ticker": "BAD", "cik": 456, "name": "Bad Corp"},
        ]
    ).to_csv(tmp_path / "universe.csv", index=False)
    old_date = pd.Timestamp("2024-01-02").date()
    current = pd.DataFrame(
        [
            {"ticker": ticker, "date": old_date, "open": 10.0, "high": 11.0,
             "low": 9.0, "close": 10.0, "volume": 100.0}
            for ticker in ("ABC", "BAD", "SPY")
        ]
    )
    current.to_parquet(tmp_path / "prices.parquet", index=False)
    (tmp_path / "provenance.json").write_text(json.dumps({"source": "edgar"}))

    def fake_fetch(symbol, **kwargs):
        assert kwargs["refresh"] is True
        if symbol == "BAD":
            raise RuntimeError("vendor unavailable")
        return pd.DataFrame(
            [{"ticker": symbol, "date": pd.Timestamp("2024-01-03").date(),
              "open": 11.0, "high": 12.0, "low": 10.0, "close": 11.0,
              "volume": 110.0}]
        )

    monkeypatch.setattr("company_lens.refresh.fetch_daily", fake_fetch)

    result = refresh_market_data(data_dir=tmp_path, cache_dir=tmp_path / "cache")
    prices = pd.read_parquet(tmp_path / "prices.parquet")

    assert result.status == "partial"
    assert result.failed_tickers == ["BAD"]
    assert set(result.refreshed_tickers) == {"ABC", "QQQ", "SPY"}
    assert prices.loc[prices["ticker"] == "BAD", "date"].iloc[0] == old_date
    assert prices.loc[prices["ticker"] == "ABC", "date"].iloc[0] > old_date


def test_market_refresh_keeps_last_good_qqq_when_its_fetch_fails(
    tmp_path, monkeypatch
) -> None:
    pd.DataFrame([{"ticker": "ABC", "cik": 123, "name": "ABC Corp"}]).to_csv(
        tmp_path / "universe.csv", index=False
    )
    old_date = pd.Timestamp("2024-01-02").date()
    pd.DataFrame(
        [
            {"ticker": ticker, "date": old_date, "open": 10.0, "high": 11.0,
             "low": 9.0, "close": 10.0, "volume": 100.0}
            for ticker in ("ABC", "QQQ", "SPY")
        ]
    ).to_parquet(tmp_path / "prices.parquet", index=False)
    requested = []

    def fake_fetch(symbol, **kwargs):
        requested.append(symbol)
        if symbol == "QQQ":
            raise RuntimeError("vendor unavailable")
        return pd.DataFrame(
            [{"ticker": symbol, "date": pd.Timestamp("2024-01-03").date(),
              "open": 11.0, "high": 12.0, "low": 10.0, "close": 11.0,
              "volume": 110.0}]
        )

    monkeypatch.setattr("company_lens.refresh.fetch_daily", fake_fetch)

    result = refresh_market_data(
        data_dir=tmp_path, cache_dir=tmp_path / "cache", tickers=["ABC"]
    )
    prices = pd.read_parquet(tmp_path / "prices.parquet")

    assert sorted(requested) == ["ABC", "QQQ", "SPY"]
    assert result.status == "partial"
    assert result.failed_tickers == ["QQQ"]
    assert prices.loc[prices["ticker"] == "QQQ", "date"].tolist() == [old_date]
    assert prices.loc[prices["ticker"] == "SPY", "date"].max() > old_date
