#!/usr/bin/env bash
# Build the Next.js front end from Python company snapshots.
#
# Intended order after a refresh has written real pages:
#   scripts/build_company_pages.py
#   scripts/export_ask_evidence.py
#   scripts/stage_lens_web.sh
#
# This does not deploy. The Python bundle deploy
# (scripts/deploy_vercel_frontend.sh) refuses the Next.js project lens-web,
# so a refresh cannot replace that front end with the old static site.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SNAPSHOT_DIR="${LENS_SNAPSHOT_DIR:-$ROOT/data/build/company_pages}"
export LENS_SNAPSHOT_DIR="$SNAPSHOT_DIR"
export LENS_REQUIRE_ENGINE=1
export LENS_REQUIRE_FINANCIALS=1
export LENS_REQUIRED_TICKERS="${LENS_REQUIRED_TICKERS:-AAPL,JPM,NVDA}"

if [[ "${LENS_REBUILD_FINANCIALS:-1}" == "1" && "$SNAPSHOT_DIR" == "$ROOT/data/build/company_pages" ]]; then
  # Structured figures from the Edgar cache. A miss fails here; this script
  # does not read the old site's HTML.
  PYTHONPATH=src python3 "$ROOT/scripts/refresh_fundamentals.py" \
    --data-dir "$ROOT/data/build" \
    --all \
    --offline \
    --require AAPL JPM NVDA
  PYTHONPATH=src python3 "$ROOT/scripts/build_company_pages.py" --data-dir "$ROOT/data/build"
fi

if [[ ! -d "$SNAPSHOT_DIR" ]]; then
  echo "No company snapshots at $SNAPSHOT_DIR" >&2
  exit 1
fi

if [[ -z "${LENS_ASK_EVIDENCE:-}" ]]; then
  export LENS_ASK_EVIDENCE="$ROOT/data/build/ask-evidence.json"
  PYTHONPATH=src python3 "$ROOT/scripts/export_ask_evidence.py" \
    --source "$SNAPSHOT_DIR" \
    --out "$LENS_ASK_EVIDENCE"
fi

cd "$ROOT/apps/lens-web"
npm run build
echo "Next.js app staged from $SNAPSHOT_DIR."
echo "Deploy the lens-web project separately. Do not send this build through deploy_vercel_frontend.sh."
