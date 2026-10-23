#!/usr/bin/env bash
set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${COMPANY_LENS_PYTHON:-$PROJECT_ROOT/.venv/bin/python}"
LOCK_FILE="${COMPANY_LENS_LOCK_FILE:-/tmp/company-lens-refresh.lock}"

cd "$PROJECT_ROOT" || exit 1
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "another Company Lens refresh is already running"
  exit 0
fi

status=0
PYTHONPATH=src "$PYTHON_BIN" scripts/refresh_filings.py || status=$?
PYTHONPATH=src "$PYTHON_BIN" scripts/refresh_market_data.py || status=$?
if [[ -n "${COMPANY_LENS_FUNDAMENTALS_TICKERS:-}" ]]; then
  read -r -a fundamentals_tickers <<< "$COMPANY_LENS_FUNDAMENTALS_TICKERS"
  PYTHONPATH=src "$PYTHON_BIN" scripts/refresh_fundamentals.py \
    --tickers "${fundamentals_tickers[@]}" || status=$?
else
  PYTHONPATH=src "$PYTHON_BIN" scripts/refresh_fundamentals.py --all || status=$?
fi
HEADLINE_INDEX="${COMPANY_LENS_HEADLINE_INDEX:-$PROJECT_ROOT/data/build/headlines.json}"
if [[ -n "${FINNHUB_API_KEY:-}" ]]; then
  PYTHONPATH=src "$PYTHON_BIN" scripts/refresh_headlines.py --out "$HEADLINE_INDEX" || status=$?
else
  echo "FINNHUB_API_KEY is not configured; skipping live headline refresh"
fi

# Always rebuild from the last good merged artifacts. A partial upstream failure
# remains visible in provenance without taking the static site offline.
build_args=()
if [[ -s "$HEADLINE_INDEX" ]]; then
  build_args+=(--headline-index "$HEADLINE_INDEX")
fi
PYTHONPATH=src "$PYTHON_BIN" scripts/build_company_pages.py "${build_args[@]}" || exit 1
PYTHONPATH=src "$PYTHON_BIN" scripts/evaluate_filing_changes.py || status=$?

# The prospective prediction log, before the pages that render it.
#
# Order matters in both directions here. Scoring runs first because it reads the
# price panel the step above just refreshed, and because a prediction written
# today has nothing to score -- the two scripts never touch the same file in one
# run. Both run before build_research_page.py, which reads the log to render the
# live-versus-backtest section, so a run publishes the tally it just extended
# rather than last week's.
#
# Neither aborts the chain. The log is the one artefact here that is committed
# rather than deployed, and a week where the ranker could not be fitted is a
# gap in it -- which is recoverable, and much better than a deploy skipped
# because of it. The failure shows up in the run log and in the log's own dates.
PYTHONPATH=src "$PYTHON_BIN" scripts/score_predictions.py || status=$?
PYTHONPATH=src "$PYTHON_BIN" scripts/write_predictions.py || status=$?

# The three site-level pages. build_vercel_output.py bundles every *.html in
# company_pages/, and these are the ones no other step writes -- so on a worker
# that keeps its disk between runs they survive from whenever someone last ran
# `make research-page` by hand, and the bundle silently carries them. On a clean
# runner they are simply absent, which is how the first successful hosted deploy
# published a site whose research page, overview and earnings calendar were all
# 404 -- including the three header links on all 194 company pages, and the
# README's own link to "the research page".
#
# Generated here so the chain produces the whole site rather than inheriting
# part of it from a machine's filesystem.
PYTHONPATH=src "$PYTHON_BIN" scripts/build_research_page.py || status=$?
PYTHONPATH=src "$PYTHON_BIN" scripts/build_overview_page.py || status=$?
PYTHONPATH=src "$PYTHON_BIN" scripts/build_earnings_calendar.py || status=$?

PYTHONPATH=src "$PYTHON_BIN" scripts/build_vercel_output.py || status=$?

if [[ "${VERCEL_DEPLOY_ENABLED:-0}" == "1" ]]; then
  scripts/deploy_vercel_frontend.sh || status=$?
fi

echo "Company Lens scheduled refresh finished with status $status"
exit "$status"
