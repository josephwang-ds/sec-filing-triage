#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE_ROOT="${VERCEL_BUNDLE_ROOT:-$PROJECT_ROOT/data/build/vercel_frontend}"
GLOBAL_CONFIG="${VERCEL_GLOBAL_CONFIG:-$PROJECT_ROOT/data/vercel-cli}"

for variable in VERCEL_TOKEN VERCEL_ORG_ID VERCEL_PROJECT_ID; do
  if [[ -z "${!variable:-}" ]]; then
    echo "$variable is required for non-interactive Vercel deployment" >&2
    exit 1
  fi
done
if ! command -v vercel >/dev/null 2>&1; then
  echo "Vercel CLI is not installed" >&2
  exit 1
fi
if [[ ! -f "$BUNDLE_ROOT/.vercel/output/config.json" ]]; then
  echo "Vercel prebuilt output is missing; run scripts/build_vercel_output.py" >&2
  exit 1
fi
mkdir -p "$GLOBAL_CONFIG"

# Say which project this is about to publish to, and refuse when the environment
# and the linked bundle disagree.
#
# `vercel deploy` takes the project from VERCEL_PROJECT_ID, silently ignoring the
# .vercel/project.json sitting in the bundle. When the two point at different
# projects the deploy still succeeds -- against the wrong one -- and the URL you
# then check is served by whatever that project last received. Two projects for
# this site drifted apart for days exactly this way, each deploy reporting
# success. So: print the target every time, and stop when they disagree.
LINK="$BUNDLE_ROOT/.vercel/project.json"
json_field() {  # tolerate whitespace after the colon; writers differ on it
  sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" "$2"
}
if [[ -f "$LINK" ]]; then
  linked_project="$(json_field projectId "$LINK")"
  linked_name="$(json_field projectName "$LINK")"
  if [[ -z "$linked_project" ]]; then
    # Proceeding here would be this guard failing the way it exists to prevent:
    # unable to check the target, and saying nothing about it.
    echo "$LINK exists but no projectId could be read from it." >&2
    echo "The deploy target cannot be verified, so it is not attempted." >&2
    exit 1
  fi
  if [[ "$linked_project" != "$VERCEL_PROJECT_ID" ]]; then
    echo "VERCEL_PROJECT_ID does not match the project this bundle is linked to." >&2
    echo "  environment: $VERCEL_PROJECT_ID" >&2
    echo "  bundle link: $linked_project (${linked_name:-unnamed})" >&2
    echo >&2
    echo "Deploying would publish to the environment's project and report success." >&2
    echo "Fix the ID, or relink the bundle, before deploying." >&2
    exit 1
  fi
  echo "deploying to ${linked_name:-$VERCEL_PROJECT_ID} ($VERCEL_PROJECT_ID)"
else
  echo "deploying to $VERCEL_PROJECT_ID (bundle carries no project link)"
fi

# This script publishes the Python static bundle with --prod. lens-web is the
# Next.js project. A matching id is not enough: the bundle must not be the
# target that replaces that front end.
if [[ "${linked_name:-}" == "lens-web" || "$VERCEL_PROJECT_ID" == "prj_FZTMwbFl4fVES1HqAXn8LjvwnDpG" ]]; then
  echo "Refusing to publish the Python static bundle to the Next.js project (lens-web)." >&2
  echo "The scheduled refresh keeps publishing the Python site. The Next.js app is deployed separately." >&2
  exit 1
fi

vercel deploy \
  --cwd "$BUNDLE_ROOT" \
  --global-config "$GLOBAL_CONFIG" \
  --prebuilt \
  --archive=tgz \
  --prod \
  --yes
