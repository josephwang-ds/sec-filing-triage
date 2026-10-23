from __future__ import annotations

from pathlib import Path


def test_scheduled_refresh_updates_fundamentals_before_building_pages() -> None:
    script = Path("scripts/run_scheduled_refresh.sh").read_text(encoding="utf-8")

    fundamentals = script.index("scripts/refresh_fundamentals.py")
    page_build = script.index("scripts/build_company_pages.py")
    assert fundamentals < page_build
    assert "scripts/refresh_fundamentals.py --all" in script
    assert "COMPANY_LENS_FUNDAMENTALS_TICKERS:-AAPL" not in script
    workflow = Path(".github/workflows/refresh.yml").read_text(encoding="utf-8")
    assert "COMPANY_LENS_FUNDAMENTALS_TICKERS: AAPL" not in workflow


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


def test_scheduled_refresh_publishes_predictions_before_the_pages_read_them() -> None:
    """The log is written and scored in the chain, not beside it.

    Order is the whole content of this test. Scoring runs first because it reads
    the price panel the market refresh just updated, and because a prediction
    written this run has nothing to score. Both run before the research page,
    which renders the live-versus-backtest tally from the log -- run the other
    way round, every deploy would publish last week's tally while committing
    this week's predictions, and the page would be permanently one run stale
    with nothing saying so.
    """
    script = Path("scripts/run_scheduled_refresh.sh").read_text(encoding="utf-8")

    for generator in ("scripts/score_predictions.py", "scripts/write_predictions.py"):
        assert generator in script, f"{generator} never runs, so the log stalls"

    assert script.index("scripts/score_predictions.py") < script.index(
        "scripts/write_predictions.py")
    assert script.index("scripts/write_predictions.py") < script.index(
        "scripts/build_research_page.py")


def test_the_refresh_commits_the_prediction_log() -> None:
    """A ranking that is not pushed has not been published.

    The log's claim is that the file existed before the prices it is judged
    against, and a commit pushed by CI is what timestamps that. The receipt step
    also resets onto the remote tip, which is the one operation in this
    repository that can destroy a tracked file a refresh wrote, so it has to
    carry the log across.
    """
    workflow = Path(".github/workflows/refresh.yml").read_text(encoding="utf-8")

    assert "git add data/last-refresh.json predictions" in workflow
    reset = workflow.index("git reset --hard FETCH_HEAD")
    assert workflow.index("cp predictions/*.json") < reset, (
        "the log must be held aside before the reset that would discard it"
    )
    assert reset < workflow.index('cp "${{ runner.temp }}/log/"*.json predictions/')
