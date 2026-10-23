"""Read durable event checkpoints. An empty directory or HTTP 200 is not healthy."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime

from company_lens.events.blob_store import HttpBlobTransport
from company_lens.events.config_status import presence
from company_lens.events.health import (
    judge_checkpoint,
    monitor_action,
    public_health,
    request_monitor_rerun,
)
from company_lens.events.policy import HIGH_FREQUENCY_TICKERS
from company_lens.events.run import BlobDurable, MonitorDurable


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--supported",
        nargs="*",
        default=None,
        help="Expected tickers. Defaults to the checkpoint list, then the full high-frequency set.",
    )
    parser.add_argument("--http-status", type=int, default=200)
    parser.add_argument("--now", default=None)
    parser.add_argument("--cooldown-until", default=None)
    args = parser.parse_args(argv)
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    flags = presence()
    if not flags["BLOB_READ_WRITE_TOKEN"]:
        payload = {
            "action": {
                "action": "alert",
                "auto_repair": False,
                "independent_wake": "not_configured",
                "rerun_requested": False,
            },
            "health": {"naive_http_ok": True, "ok": False, "overall": "not_configured", "sources": []},
            "note": "durable checkpoint is not configured",
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        print("independent_wake=not_configured")
        print("rerun_requested=false")
        return 2
    transport = HttpBlobTransport(os.environ["BLOB_READ_WRITE_TOKEN"])
    durable = BlobDurable(transport)
    monitor = MonitorDurable(transport)
    pulled = durable.pull()
    if pulled.status == "read_error":
        print(json.dumps({
            "health": {"naive_http_ok": True, "ok": False, "overall": "read_error"},
            "note": "checkpoint read failed; this run did not assume an empty store",
        }, sort_keys=True))
        return 3
    if pulled.status != "ok" or pulled.payload is None:
        print(json.dumps({
            "health": {"naive_http_ok": True, "ok": False, "overall": "never_run", "sources": []},
            "note": "no durable checkpoint has been stored",
        }, sort_keys=True))
        return 2
    supported = _expected(args.supported, pulled.payload)
    disabled = set()
    if not flags["FINNHUB_API_KEY"]:
        disabled.add("news")
    if not flags["EDGAR_USER_AGENT"]:
        disabled.add("sec_index")
    report = judge_checkpoint(
        pulled.payload,
        now=now,
        expected=supported,
        disabled=disabled,
        http_status=args.http_status,
    )
    configured = bool(flags["EVENTS_RERUN_TOKEN"] and flags["EVENTS_RERUN_URL"])
    decision = monitor_action(report, rerun_configured=configured)
    if configured and decision.get("action") == "rerun_eligible":
        override = args.cooldown_until
        if override and now < _aware(override):
            decision = {**decision, "reason": "cooldown", "rerun_requested": False}
        else:
            held = monitor.pull()
            if held.status == "read_error":
                decision = {**decision, "reason": "monitor_unreadable", "rerun_requested": False}
            else:
                def executor() -> object:
                    return _post_rerun(os.environ["EVENTS_RERUN_URL"], os.environ["EVENTS_RERUN_TOKEN"])

                decision = request_monitor_rerun(
                    monitor,
                    held,
                    decision,
                    executor=executor,
                    now=now,
                )
    elif not configured:
        decision = {**decision, "rerun_requested": False, "independent_wake": "not_configured"}
    public = {
        "action": {key: value for key, value in decision.items() if key != "headers"},
        "health": public_health(report),
    }
    print(json.dumps(public, indent=2, sort_keys=True))
    print("rerun_requested=" + ("true" if decision.get("rerun_requested") else "false"))
    print("independent_wake=" + str(decision.get("independent_wake") or "external_url"))
    return 0 if report.get("ok") else 2


def _expected(explicit: list[str] | None, payload: dict) -> set[str]:
    if explicit:
        return {ticker.strip().upper() for ticker in explicit if ticker.strip()}
    recorded = payload.get("expected_tickers") or []
    if isinstance(recorded, list) and recorded:
        return {str(ticker).strip().upper() for ticker in recorded if str(ticker).strip()}
    return set(HIGH_FREQUENCY_TICKERS)


def _aware(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _post_rerun(url: str, token: str) -> object:
    import requests

    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"source": "events-monitor"},
        timeout=15,
    )
    return response


if __name__ == "__main__":
    sys.exit(main())
