"""Read event-task health. HTTP 200 is reported and is not treated as success."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from company_lens.events.config_status import presence
from company_lens.events.health import build_health, monitor_action, public_health
from company_lens.events.store import FileEventStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/events-store"))
    parser.add_argument("--dataset", default="news")
    parser.add_argument("--supported", nargs="*", default=())
    parser.add_argument("--http-status", type=int, default=200)
    parser.add_argument("--now", default=None)
    parser.add_argument("--allow-empty", action="store_true")
    args = parser.parse_args(argv)
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    store = FileEventStore(args.root)
    supported = {ticker.upper() for ticker in args.supported}
    states = {}
    manifest = store.read_manifest(args.dataset)
    for ticker in sorted(manifest.get("tickers") or {}):
        supported.add(ticker)
        states[ticker] = store.read_state(args.dataset, ticker)
    if not states and args.allow_empty:
        print(json.dumps({
            "action": {"action": "alert", "auto_repair": False, "configured": False},
            "note": "no checkpoints in this root; durable storage is not on the runner",
        }, sort_keys=True))
        return 0
    disabled = set()
    flags = presence()
    if args.dataset == "news" and not flags["FINNHUB_API_KEY"]:
        disabled.add("news")
    if args.dataset == "sec_index" and not flags["EDGAR_USER_AGENT"]:
        disabled.add("sec_index")
    report = build_health(
        {args.dataset: states},
        now=now,
        supported=supported,
        disabled=disabled,
        http_status=args.http_status,
    )
    action = monitor_action(report, rerun_configured=flags["EVENTS_RERUN_TOKEN"])
    payload = {"action": action, "health": public_health(report)}
    print(json.dumps(payload, indent=2, sort_keys=True))
    if action["action"] == "alert":
        print("auto_repair=false")
        print("recovery=workflow_dispatch events-refresh.yml")
        return 2
    if action["action"] == "rerun":
        print("auto_repair=false")
        print("rerun_requested=true")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
