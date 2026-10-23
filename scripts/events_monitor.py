"""Read durable event checkpoints. An empty directory or HTTP 200 is not healthy."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime

from company_lens.events.blob_store import BlobRequestError, HttpBlobTransport
from company_lens.events.config_status import presence
from company_lens.events.health import build_health, execute_rerun, monitor_action, public_health
from company_lens.events.policy import HIGH_FREQUENCY_TICKERS
from company_lens.events.run import BlobDurable


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--supported", nargs="*", default=list(HIGH_FREQUENCY_TICKERS))
    parser.add_argument("--http-status", type=int, default=200)
    parser.add_argument("--now", default=None)
    parser.add_argument("--cooldown-until", default=None)
    args = parser.parse_args(argv)
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    flags = presence()
    supported = {ticker.upper() for ticker in args.supported}
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
    durable = BlobDurable(HttpBlobTransport(os.environ["BLOB_READ_WRITE_TOKEN"]))
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
    states = _states(pulled.payload)
    disabled = set()
    if not flags["FINNHUB_API_KEY"]:
        disabled.add("news")
    if not flags["EDGAR_USER_AGENT"]:
        disabled.add("sec_index")
    report = build_health(
        states,
        now=now,
        supported=supported,
        disabled=disabled,
        http_status=args.http_status,
    )
    configured = bool(flags["EVENTS_RERUN_TOKEN"] and flags["EVENTS_RERUN_URL"])
    decision = monitor_action(report, rerun_configured=configured)
    cooldown = args.cooldown_until or (pulled.payload.get("monitor") or {}).get("cooldown_until")
    if configured and decision.get("action") == "rerun_eligible":
        def executor() -> object:
            return _post_rerun(os.environ["EVENTS_RERUN_URL"], os.environ["EVENTS_RERUN_TOKEN"])

        decision = execute_rerun(
            decision,
            executor=executor,
            now=now,
            cooldown_until=cooldown,
        )
        if decision.get("rerun_requested") and decision.get("cooldown_until"):
            payload = dict(pulled.payload)
            payload["monitor"] = {"cooldown_until": decision["cooldown_until"]}
            try:
                durable.push(payload, pulled.etag)
            except BlobRequestError:
                decision["cooldown_persisted"] = False
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


def _states(payload: dict) -> dict[str, dict[str, dict | None]]:
    datasets = payload.get("datasets") or {}
    return {
        dataset: dict((body or {}).get("states") or {})
        for dataset, body in datasets.items()
        if isinstance(body, dict)
    }


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
