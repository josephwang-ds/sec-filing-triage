# The fixture repeats the published page, including its Chinese punctuation.
# ruff: noqa: E501, RUF001
"""The published page's own attributes, read back without recomputing a figure."""

import importlib.util
import json
from pathlib import Path

import pytest

MODULE = Path(__file__).parents[1] / "scripts" / "attach_published_financials.py"
spec = importlib.util.spec_from_file_location("attach_published_financials", MODULE)
published = importlib.util.module_from_spec(spec)
spec.loader.exec_module(published)


def _card() -> str:
    return """
<section id="earnings" aria-label="Financial results">
<p data-i18n-en="Quarterly period ended 2026-06-27 · filed 2026-07-31 · 10-Q" data-i18n-zh="季度截至 2026-06-27 · 披露于 2026-07-31 · 10-Q">x</p>
<p data-i18n-en="SEC industry registration: Electronic Computers (SIC 3571). SIC is a broad classification, not a curated peer list." data-i18n-zh="行业">x</p>
<article class="result-card">
<h3 data-i18n-en="Revenue" data-i18n-zh="收入">Revenue</h3>
<strong data-i18n-en="$109.42B" data-i18n-zh="1,094.17 亿美元">$109.42B</strong>
<p data-i18n-en="Prior year (2025-06-28): $94.04B" data-i18n-zh="上年同期（2025-06-28）：940.36 亿美元">prior</p>
<strong data-i18n-en="Year over year: +16.4%" data-i18n-zh="同比：+16.4%">yoy</strong>
<small data-i18n-en="Current: 2026-03-29 — 2026-06-27 · USD" data-i18n-zh="本期">current</small>
<p data-i18n-en="Prior year: 2025-03-30 — 2025-06-28" data-i18n-zh="上年同期">bounds</p>
<p data-i18n-en="Category reference unavailable. Only 1 eligible companies; at least 5 required." data-i18n-zh="暂无">ref</p>
<code>RevenueFromContractWithCustomerExcludingAssessedTax</code>
<a href="https://www.sec.gov/Archives/edgar/data/1262039/000126203926000021/ftnt-20260630.htm">FTNT · 2026-06-30 · +6.1%</a>
</article>
<a href="https://www.sec.gov/Archives/edgar/data/320193/000032019326000020/aapl-20260627.htm"><span data-i18n-en="Read the financial report ↗" data-i18n-zh="查看财报原文 ↗">Read the financial report ↗</span></a>
</section>
"""


def test_published_card_keeps_the_rendered_figure_and_period():
    report = published.parse_financial_section(_card())
    assert report["status"] == "available"
    assert report["form"] == "10-Q"
    assert report["period_end"] == "2026-06-27"
    assert report["filed"] == "2026-07-31"
    assert report["source_url"].endswith("aapl-20260627.htm")
    metric = report["metrics"][0]
    assert metric["id"] == "revenue"
    assert metric["concept"] == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert metric["value"] == 1_094.17 * 1e8
    assert metric["prior_value"] == 940.36 * 1e8
    assert metric["yoy"] == pytest.approx(0.164)
    assert metric["change"] is None
    assert report["extraction"] == "published_html_fallback"
    assert report["value_precision"] == "display_rounded"
    assert metric["start"] == "2026-03-29"
    assert metric["prior_start"] == "2025-03-30"
    assert metric["reference"]["reason"] == "insufficient_sample"
    assert f"${metric['value'] / 1e9:,.2f}B" == "$109.42B"


def test_a_filing_without_extracted_figures_stays_a_real_report():
    html = """
<section id="earnings">
<p data-i18n-en="Quarterly period ended 2026-07-03 · filed 2026-07-29 · 10-Q" data-i18n-zh="季度">x</p>
<p data-i18n-en="The filing is available; comparable numeric facts have not been extracted." data-i18n-zh="已取得">x</p>
<a href="https://www.sec.gov/Archives/edgar/data/21344/ko.htm"><span data-i18n-en="Read the financial report ↗" data-i18n-zh="查看">Read the financial report ↗</span></a>
</section>
"""
    report = published.parse_financial_section(html)
    assert report["status"] == "available"
    assert report["metrics"] == []
    assert report["form"] == "10-Q"


def _write(directory: Path, ticker: str, body: str | None = None) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{ticker.lower()}.json").write_text(
        json.dumps({"ticker": body or ticker, "profile": {"display_name": ticker}})
    )


def test_an_empty_source_reports_every_required_ticker(tmp_path):
    with pytest.raises(SystemExit, match="absent from source: AAPL, JPM"):
        published.attach_tree(tmp_path / "empty", tmp_path / "out", "https://example.test", ["JPM", "AAPL"])


def test_a_required_ticker_missing_from_the_source_fails(tmp_path, monkeypatch):
    _write(tmp_path / "src", "MSFT")
    monkeypatch.setattr(published, "fetch", lambda _origin, _ticker: _card())
    with pytest.raises(SystemExit, match="absent from source: AAPL"):
        published.attach_tree(tmp_path / "src", tmp_path / "out", "https://example.test", ["AAPL"])


def test_a_required_unavailable_report_fails_without_dropping_other_issuers(tmp_path, monkeypatch):
    _write(tmp_path / "src", "AAPL")
    _write(tmp_path / "src", "KO")
    pages = {
        "AAPL": (
            '<section id="earnings"><p data-i18n-en="A current financial report is not available in this snapshot." '
            'data-i18n-zh="无">x</p></section>'
        ),
        "KO": _card().replace("Revenue", "Revenue"),
    }
    monkeypatch.setattr(published, "fetch", lambda _origin, ticker: pages[ticker])
    with pytest.raises(SystemExit, match="report unavailable: AAPL"):
        published.attach_tree(tmp_path / "src", tmp_path / "out", "https://example.test", ["AAPL"])
    ko = json.loads((tmp_path / "out" / "ko.json").read_text())
    assert ko["financial_results"]["metrics"]


def test_a_required_filing_without_figures_fails_and_an_ordinary_one_is_kept(tmp_path, monkeypatch):
    _write(tmp_path / "src", "AAPL")
    _write(tmp_path / "src", "KO")
    filing_only = """
<section id="earnings">
<p data-i18n-en="Quarterly period ended 2026-07-03 · filed 2026-07-29 · 10-Q" data-i18n-zh="季度">x</p>
<p data-i18n-en="The filing is available; comparable numeric facts have not been extracted." data-i18n-zh="已取得">x</p>
<a href="https://www.sec.gov/Archives/edgar/data/21344/ko.htm"><span data-i18n-en="Read the financial report ↗" data-i18n-zh="查看">Read the financial report ↗</span></a>
</section>
"""
    monkeypatch.setattr(published, "fetch", lambda _origin, ticker: filing_only if ticker == "KO" else _card())
    published.attach_tree(tmp_path / "src", tmp_path / "out", "https://example.test", ["AAPL"])
    ko = json.loads((tmp_path / "out" / "ko.json").read_text())
    assert ko["financial_results"]["status"] == "available"
    assert ko["financial_results"]["metrics"] == []
    with pytest.raises(SystemExit, match="filing without displayable figures: KO"):
        published.attach_tree(tmp_path / "src", tmp_path / "out2", "https://example.test", ["KO"])


def test_duplicate_and_mismatched_tickers_fail(tmp_path, monkeypatch):
    source = tmp_path / "src"
    _write(source, "AAPL")
    (source / "aapl-copy.json").write_text(json.dumps({"ticker": "AAPL"}))
    monkeypatch.setattr(published, "fetch", lambda _origin, _ticker: _card())
    with pytest.raises(SystemExit, match=r"ticker mismatch: aapl-copy\.json"):
        published.attach_tree(source, tmp_path / "out", "https://example.test", [])
    (source / "aapl-copy.json").unlink()
    (source / "extra.json").write_text(json.dumps({"ticker": "AAPL"}))
    (source / "aapl.json").write_text(json.dumps({"ticker": "AAPL"}))
    # extra.json stem is EXTRA, body is AAPL: mismatch, not a second AAPL file named aapl.
    with pytest.raises(SystemExit, match=r"ticker mismatch: extra\.json contains AAPL"):
        published.attach_tree(source, tmp_path / "out", "https://example.test", [])


def test_two_files_for_one_ticker_fail(tmp_path, monkeypatch):
    class _File:
        def __init__(self, name: str, ticker: str) -> None:
            self.name = name
            self.stem = ticker

        def __lt__(self, other: "_File") -> bool:
            return self.name < other.name

        def read_text(self, encoding: str = "utf-8") -> str:
            return json.dumps({"ticker": self.stem})

    class _Dir:
        def is_dir(self) -> bool:
            return True

        def glob(self, _pattern: str):
            return [_File("aapl.json", "AAPL"), _File("aapl-again.json", "AAPL")]

    monkeypatch.setattr(published, "fetch", lambda _origin, _ticker: _card())
    with pytest.raises(SystemExit, match="duplicate ticker AAPL"):
        published.attach_tree(_Dir(), tmp_path / "out", "https://example.test", [])


def test_a_page_without_a_report_stays_unavailable():
    html = (
        '<section id="earnings"><p data-i18n-en="A current financial report is not available in this snapshot." '
        'data-i18n-zh="当前快照尚未取得可核对的财报信息。">x</p></section>'
    )
    assert published.parse_financial_section(html)["status"] == "unavailable"
