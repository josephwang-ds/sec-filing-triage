"""Package only public HTML into Vercel's prebuilt static-output format."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from company_lens.web.ask import (
    ASK_EVIDENCE_VERSION,
    DEFAULT_SCOPE,
    build_ask_evidence,
    evidence_scopes,
)

DEFAULT_ASK_FUNCTION = Path("ops/vercel/ask/index.js")
DEFAULT_EVENTS_FUNCTION = Path("ops/vercel/events/index.js")

# What the pages are generated *from*. If any of this is newer than the newest
# generated page, the pages predate the code that renders them.
RENDERER_SOURCES = (Path("src/company_lens/web"), Path("src/company_lens/snapshots"))


def staleness(source: Path, renderer_sources=RENDERER_SOURCES) -> tuple[float, Path] | None:
    """The newest renderer file that postdates every generated page, if any.

    `build_vercel_output` copies HTML; it never renders it. So a bundle is only
    as current as whenever `company-lens`/`build_company_pages.py` last ran, and
    deploying after editing the renderer ships the previous build with nothing
    saying so -- the deploy succeeds, the pages are valid, and the change is
    simply absent. That is how this project's own site served an evidence-scope
    build for days after the scopes were written.

    Compared against the newest page rather than each page individually: pages
    are written in one pass, and a per-file comparison would fire on an issuer
    whose page happens to be rebuilt less often.
    """
    pages = sorted(Path(source).glob("*.html"))
    if not pages:
        return None
    newest_page = max(path.stat().st_mtime for path in pages)
    newer = [
        (path.stat().st_mtime, path)
        for root in renderer_sources
        if root.exists()
        for path in root.rglob("*.py")
        if path.stat().st_mtime > newest_page
    ]
    return max(newer) if newer else None


def build_vercel_output(
    source: Path,
    output_root: Path,
    *,
    ask_function_source: Path = DEFAULT_ASK_FUNCTION,
) -> Path:
    source = Path(source)
    output_root = Path(output_root)
    html_files = sorted(source.glob("*.html"))
    if not html_files or not (source / "index.html").exists() or not (source / "404.html").exists():
        raise ValueError(f"source is not a complete Company Lens site: {source}")

    build_output = output_root / ".vercel" / "output"
    temporary = output_root / ".vercel" / ".output.next"
    if temporary.exists():
        shutil.rmtree(temporary)
    static = temporary / "static"
    static.mkdir(parents=True)
    for path in html_files:
        shutil.copy2(path, static / path.name)
    _build_events_function(source, temporary)
    _build_ask_function(source, temporary, ask_function_source)
    config = {
        "version": 3,
        "routes": [
            {"src": "/", "dest": "/index.html"},
            {"handle": "filesystem"},
            {"src": "/.*", "dest": "/404.html", "status": 404},
        ],
    }
    (temporary / "config.json").write_text(
        json.dumps(config), encoding="utf-8"
    )

    if build_output.exists():
        shutil.rmtree(build_output)
    temporary.replace(build_output)
    return build_output


def _build_ask_function(
    source: Path,
    output: Path,
    function_source: Path,
) -> None:
    companies = {}
    for path in sorted(source.glob("*.json")):
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(snapshot, dict) or not {
            "ticker",
            "benchmark",
            "performance",
            "profile",
        }.issubset(snapshot):
            continue
        companies[str(snapshot["ticker"]).upper()] = build_ask_evidence(snapshot)
    if not companies:
        return
    if not function_source.is_file():
        raise ValueError(f"Company Lens ask function is missing: {function_source}")

    function = output / "functions" / "api" / "ask.func"
    function.mkdir(parents=True)
    shutil.copy2(function_source, function / "index.js")
    evidence_path = source / "event_evidence.json"
    event_evidence = (
        json.loads(evidence_path.read_text(encoding="utf-8"))
        if evidence_path.is_file()
        else {"companies": {}, "schema_version": "company-lens.event-evidence.v1"}
    )
    (function / "event_evidence.json").write_text(
        json.dumps(event_evidence, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    (function / "evidence.json").write_text(
        json.dumps(
            {
                "schema_version": ASK_EVIDENCE_VERSION,
                "default_scope": DEFAULT_SCOPE,
                "scopes": evidence_scopes(),
                "companies": companies,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    (function / ".vc-config.json").write_text(
        json.dumps(
            {
                "runtime": "nodejs22.x",
                "handler": "index.js",
                "maxDuration": 45,
                "memory": 512,
                "launcherType": "Nodejs",
                "shouldAddHelpers": True,
            }
        ),
        encoding="utf-8",
    )


def _build_events_function(source: Path, output: Path) -> None:
    """Public event read API. It does not fetch providers or deploy the site."""
    source_file = DEFAULT_EVENTS_FUNCTION
    if not source_file.is_file():
        raise ValueError(f"Company Lens events function is missing: {source_file}")
    function = output / "functions" / "api" / "events.func"
    function.mkdir(parents=True)
    shutil.copy2(source_file, function / "index.js")
    public_path = source / "events_public.json"
    public = (
        json.loads(public_path.read_text(encoding="utf-8"))
        if public_path.is_file()
        else {"companies": {}, "health": None, "schema_version": "company-lens.events-public.v1"}
    )
    (function / "public.json").write_text(
        json.dumps(public, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    (function / ".vc-config.json").write_text(
        json.dumps(
            {
                "runtime": "nodejs22.x",
                "handler": "index.js",
                "launcherType": "Nodejs",
                "maxDuration": 15,
                "memory": 512,
                "shouldAddHelpers": True,
            }
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("data/build/company_pages"))
    parser.add_argument(
        "--out", type=Path, default=Path("data/build/vercel_frontend")
    )
    parser.add_argument(
        "--ask-function-source",
        type=Path,
        default=DEFAULT_ASK_FUNCTION,
    )
    parser.add_argument(
        "--allow-stale",
        action="store_true",
        help="bundle pages that predate the renderer that generates them",
    )
    args = parser.parse_args()

    stale = staleness(args.source)
    if stale is not None and not args.allow_stale:
        mtime, path = stale
        print(
            f"{args.source} was generated before {path} was last edited "
            f"({datetime.fromtimestamp(mtime, UTC).astimezone():%Y-%m-%d %H:%M}).\n"
            "\n"
            "This packager copies HTML, it does not render it, so bundling now "
            "ships the older pages\n"
            "and the deploy reports success either way.\n"
            "\n"
            "  make company-pages      rebuild the pages, then bundle\n"
            "  --allow-stale           bundle them as they are",
            file=sys.stderr,
        )
        return 1

    output = build_vercel_output(
        args.source,
        args.out,
        ask_function_source=args.ask_function_source,
    )
    files = list((output / "static").glob("*.html"))
    functions = list((output / "functions").glob("**/*.func"))
    size = sum(path.stat().st_size for path in files)
    print(
        f"Vercel frontend: {len(files)} HTML files, {len(functions)} function, "
        f"{size / 1024 / 1024:.1f} MB -> {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
