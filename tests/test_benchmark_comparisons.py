from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from company_lens.snapshots import build_snapshot
from company_lens.snapshots import builder as snapshot_builder
from company_lens.web.page import render_company_page


def _series(symbol: str, dates: pd.DatetimeIndex, drift: float, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    closes = 100 * np.cumprod(1 + drift + rng.normal(0, 0.01, len(dates)))
    return [
        {"ticker": symbol, "date": date.date(), "open": close, "high": close,
         "low": close, "close": close, "volume": 1_000}
        for date, close in zip(dates, closes, strict=True)
    ]


def _artifacts(tmp_path, qqq_dates: pd.DatetimeIndex | None) -> pd.DatetimeIndex:
    pd.DataFrame([{"ticker": "ABC", "cik": 123, "name": "ABC Corp"}]).to_csv(
        tmp_path / "universe.csv", index=False
    )
    dates = pd.bdate_range("2013-01-02", "2024-12-31")
    rows = _series("ABC", dates, 0.0006, 1) + _series("SPY", dates, 0.0003, 2)
    if qqq_dates is not None:
        rows += _series("QQQ", qqq_dates, 0.0004, 3)
    pd.DataFrame(rows).to_parquet(tmp_path / "prices.parquet", index=False)
    pd.DataFrame(
        {
            "ticker": pd.Series(dtype="object"),
            "cik": pd.Series(dtype="int64"),
            "accession": pd.Series(dtype="object"),
            "primary_document": pd.Series(dtype="object"),
            "form": pd.Series(dtype="object"),
            "items": pd.Series(dtype="object"),
            "acceptance_time": pd.Series(dtype="datetime64[ns, America/New_York]"),
            "text": pd.Series(dtype="object"),
        }
    ).to_parquet(tmp_path / "events.parquet", index=False)
    (tmp_path / "provenance.json").write_text(json.dumps({"source": "edgar"}))
    return dates


def test_qqq_comparison_uses_only_dates_both_series_traded(tmp_path) -> None:
    dates = _artifacts(tmp_path, None)
    qqq_dates = dates[(np.arange(len(dates)) % 7) != 3].append(
        pd.DatetimeIndex(["2024-12-28"])  # a Saturday ABC never traded
    )
    _artifacts(tmp_path, qqq_dates)

    view = build_snapshot("ABC", data_dir=tmp_path).benchmark_comparisons["QQQ"]["periods"]["1Y"]

    window = dates[dates >= pd.Timestamp("2023-12-31")]
    shared = window.intersection(qqq_dates)
    assert view["status"] == "available"
    assert view["performance"]["observations"] == len(shared)
    assert view["coverage"] == {
        "status": "full", "requested_start": "2023-12-31",
        "start": shared[0].date().isoformat(), "end": "2024-12-31",
        "observations": len(shared),
    }
    charted = {row["date"] for row in view["growth"]}
    assert charted <= {date.date().isoformat() for date in shared}


def test_missing_qqq_disables_pair_and_leaves_spy_contract_unchanged(tmp_path) -> None:
    _artifacts(tmp_path, None)

    snapshot = build_snapshot("ABC", data_dir=tmp_path)
    spy_only = build_snapshot("ABC", data_dir=tmp_path, comparison_benchmarks=())

    assert snapshot.benchmark_comparisons["QQQ"] == {
        "symbol": "QQQ", "status": "unavailable", "reason": "missing_prices", "periods": {},
    }
    assert snapshot.benchmark == "SPY"
    assert snapshot.performance == spy_only.performance
    assert snapshot.period_options == spy_only.period_options
    assert snapshot.performance == snapshot.period_options["5Y"]["performance"]
    assert "benchmark_comparisons" not in spy_only.to_dict()


def test_late_benchmark_inception_is_disclosed_never_backfilled(tmp_path) -> None:
    dates = _artifacts(tmp_path, None)
    _artifacts(tmp_path, dates[dates >= pd.Timestamp("2021-06-01")])

    periods = build_snapshot("ABC", data_dir=tmp_path).benchmark_comparisons["QQQ"]["periods"]

    assert periods["3Y"]["coverage"]["status"] == "full"
    ten = periods["10Y"]
    assert ten["coverage"]["status"] == "partial"
    assert ten["coverage"]["requested_start"] == "2014-12-31"
    assert ten["coverage"]["start"] == "2021-06-01"
    assert min(row["date"] for row in ten["growth"]) == "2021-06-01"
    assert ten["growth"][0]["benchmark_value"] == pytest.approx(10_000)


def test_overlap_too_short_for_any_period_disables_the_pair(tmp_path) -> None:
    _artifacts(tmp_path, pd.DatetimeIndex(["2024-12-31"]))

    comparison = build_snapshot("ABC", data_dir=tmp_path).benchmark_comparisons["QQQ"]

    assert comparison["status"] == "unavailable"
    assert comparison["reason"] == "insufficient_overlap"
    assert {view["status"] for view in comparison["periods"].values()} == {"unavailable"}


def test_stale_qqq_cache_is_withheld_rather_than_charted_short(tmp_path) -> None:
    dates = _artifacts(tmp_path, None)
    _artifacts(tmp_path, dates[dates <= pd.Timestamp("2024-11-29")])

    comparison = build_snapshot("ABC", data_dir=tmp_path).benchmark_comparisons["QQQ"]

    assert comparison["status"] == "unavailable"
    assert comparison["reason"] == "stale_prices"
    assert comparison["price_end"] == "2024-11-29"
    assert comparison["company_end"] == "2024-12-31"
    assert comparison["periods"] == {}


def test_two_shared_sessions_do_not_break_page_json(tmp_path) -> None:
    _artifacts(tmp_path, pd.bdate_range(end="2024-12-31", periods=2))
    snapshot = build_snapshot("ABC", data_dir=tmp_path)
    comparison = snapshot.benchmark_comparisons["QQQ"]

    assert comparison["status"] == "unavailable"
    assert comparison["reason"] == "insufficient_overlap"
    # Strict serialization is required: JSON.parse rejects Python's NaN literal.
    json.dumps(snapshot.to_dict(), allow_nan=False)
    page = render_company_page(snapshot, tmp_path / "abc.html").read_text()
    payload = page.split('<script type="application/json" id="benchmark-data">', 1)[1]
    json.loads(payload.split("</script>", 1)[0], parse_constant=pytest.fail)
    assert 'data-benchmark="QQQ"' in page


@pytest.mark.parametrize("target,value", [
    ("metric", float("nan")), ("metric", float("inf")), ("growth", -float("inf")),
])
def test_nonfinite_optional_comparison_is_withheld(tmp_path, monkeypatch, target, value) -> None:
    dates = _artifacts(tmp_path, None)
    _artifacts(tmp_path, dates)
    original = snapshot_builder.historical_picture

    def corrupt_comparison(prices, ticker, benchmark, years, initial_investment):
        metrics, growth = original(prices, ticker, benchmark, years, initial_investment)
        if benchmark == "QQQ":
            if target == "metric":
                metrics["asset"]["annualized_volatility"] = value
            else:
                growth[-1]["benchmark_value"] = value
        return metrics, growth

    monkeypatch.setattr(snapshot_builder, "historical_picture", corrupt_comparison)
    snapshot = build_snapshot("ABC", data_dir=tmp_path)

    assert snapshot.benchmark_comparisons["QQQ"]["status"] == "unavailable"
    assert snapshot.benchmark == "SPY"
    assert snapshot.performance["observations"] > 3
    json.dumps(snapshot.to_dict(), allow_nan=False)


def test_page_offers_one_benchmark_at_a_time_and_keeps_spy_elsewhere(tmp_path) -> None:
    dates = _artifacts(tmp_path, None)
    _artifacts(tmp_path, dates)
    page = render_company_page(
        build_snapshot("ABC", data_dir=tmp_path), tmp_path / "abc.html"
    ).read_text()

    assert 'data-benchmark="SPY" type="button" aria-pressed="true"' in page
    qqq_button = page.split('data-benchmark="QQQ"', 1)[1].split(">", 1)[0]
    assert "disabled" not in qqq_button
    payload = json.loads(
        page.split('<script type="application/json" id="benchmark-data">', 1)[1]
        .split("</script>", 1)[0]
    )
    assert payload["QQQ"]["periods"]["5Y"]["status"] == "available"
    assert "not a pure technology index" in page
    assert "不是纯科技指数" in page
    assert 'data-benchmark-scope="history"' in page
    # The filing reactions and the AI request keep the snapshot benchmark.
    request = page.split("method: 'POST'", 1)[1].split("});", 1)[0]
    assert "historyBenchmark" not in request
    assert "benchmark" not in request.split("body:", 1)[1]
    assert "const brief = periods[label].performance;" in page


def test_page_disables_unavailable_pair_with_reason(tmp_path) -> None:
    _artifacts(tmp_path, None)
    page = render_company_page(
        build_snapshot("ABC", data_dir=tmp_path), tmp_path / "abc.html"
    ).read_text()

    qqq_button = page.split('data-benchmark="QQQ"', 1)[1].split(">", 1)[0]
    assert 'data-unavailable-reason="missing_prices"' in qqq_button
    assert "disabled" in qqq_button
    assert '"benchmark.unavailable.missing_prices"' in page


def test_spy_only_snapshot_renders_without_a_benchmark_selector(tmp_path) -> None:
    _artifacts(tmp_path, None)
    page = render_company_page(
        build_snapshot("ABC", data_dir=tmp_path, comparison_benchmarks=()),
        tmp_path / "abc.html",
    ).read_text()

    assert 'class="benchmark-control"' not in page
    assert '<script type="application/json" id="benchmark-data">{}</script>' in page
