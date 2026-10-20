from __future__ import annotations

from pathlib import Path


def test_scheduled_refresh_updates_fundamentals_before_building_pages() -> None:
    script = Path("scripts/run_scheduled_refresh.sh").read_text(encoding="utf-8")

    fundamentals = script.index("scripts/refresh_fundamentals.py")
    page_build = script.index("scripts/build_company_pages.py")
    assert fundamentals < page_build
    assert "COMPANY_LENS_FUNDAMENTALS_TICKERS:-AAPL" in script


def test_scheduled_refresh_generates_every_page_it_publishes() -> None:
    """The bundler ships whatever HTML it finds; the chain must write all of it.

    build_vercel_output.py bundles every *.html in data/build/company_pages, and
    build_company_pages.py does not write the three site-level pages. On a worker
    that keeps its disk they persisted from an earlier manual `make research-page`
    and got bundled anyway. On a clean runner they are absent, and the site went
    live with its research page, overview and earnings calendar all returning 404
    -- the pages the company-page header and the README link to.
    """
    script = Path("scripts/run_scheduled_refresh.sh").read_text(encoding="utf-8")

    bundle = script.index("scripts/build_vercel_output.py")
    for generator in (
        "scripts/build_research_page.py",
        "scripts/build_overview_page.py",
        "scripts/build_earnings_calendar.py",
    ):
        assert generator in script, f"{generator} is never run, so its page ships only by luck"
        assert script.index(generator) < bundle, f"{generator} runs after the bundle is packaged"
