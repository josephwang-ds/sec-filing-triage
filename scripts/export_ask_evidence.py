"""Write the Ask evidence bundle on its own, for a front end that is not the prebuilt bundler.

`scripts/build_vercel_output.py` builds this same document as part of packaging
the Python site. The Next.js front end needs it without the rest of that
packaging, and the one thing that must not happen is a second implementation of
the evidence packet: the allow-lists in it are what stop a grounded answer from
citing something it was never shown. So this calls the same
`company_lens.web.ask.build_ask_evidence` and writes the same structure.

    python scripts/export_ask_evidence.py --source data/build/company_pages \
        --out data/build/ask-evidence.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from company_lens.web.ask import (
    ASK_EVIDENCE_VERSION,
    DEFAULT_SCOPE,
    build_ask_evidence,
    evidence_scopes,
)

REQUIRED_FIELDS = {"ticker", "benchmark", "performance", "profile"}


def build(source: Path) -> dict:
    companies: dict[str, dict] = {}
    for path in sorted(source.glob("*.json")):
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(snapshot, dict) or not REQUIRED_FIELDS.issubset(snapshot):
            continue
        companies[str(snapshot["ticker"]).upper()] = build_ask_evidence(snapshot)
    return {
        "schema_version": ASK_EVIDENCE_VERSION,
        "default_scope": DEFAULT_SCOPE,
        "scopes": evidence_scopes(),
        "companies": companies,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("data/build/company_pages"))
    parser.add_argument("--out", type=Path, default=Path("data/build/ask-evidence.json"))
    args = parser.parse_args()

    payload = build(args.source)
    if not payload["companies"]:
        print(f"no snapshots in {args.source}; nothing written")
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    size = args.out.stat().st_size / 1024
    print(
        f"ask evidence: {len(payload['companies'])} companies, "
        f"{len(payload['scopes'])} scopes, {size:.0f} KB -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
