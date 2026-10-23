"""Task health. An HTTP 200 from the site is not evidence that a job ran."""

from __future__ import annotations

import copy
import secrets
from datetime import datetime, timedelta
from typing import Any

from company_lens.events.blob_store import BlobRequestError
from company_lens.events.calendar import as_utc, price_status
from company_lens.events.policy import coverage_tier, freshness_level, missed_windows

MONITORED_DATASETS = ("news", "sec_index")

PUBLIC_HEALTH_FIELDS = (
    "dataset",
    "key",
    "last_attempt_at",
    "last_error_class",
    "last_successful_check_at",
    "level",
    "missed_windows",
    "pending",
    "status",
)


def assess_source(
    state: dict[str, Any] | None,
    *,
    dataset: str,
    tier: str,
    now: datetime,
    disabled: bool = False,
    failed: bool = False,
) -> dict[str, Any]:
    last_success = None
    if state and state.get("last_successful_check_at"):
        last_success = datetime.fromisoformat(str(state["last_successful_check_at"]))
    status_name = (state or {}).get("status")
    gaps = (state or {}).get("coverage_gaps") or []
    has_gaps = isinstance(gaps, list) and bool(gaps)
    failed = failed or bool(state and (state.get("last_error_class") or status_name == "stale"))
    missed = None
    if not disabled:
        missed = missed_windows(
            dataset,
            tier,
            last_success,
            as_utc(now),
            quota_degraded=bool(state and state.get("quota_degraded")),
        )
    level = freshness_level(missed, failed=failed, disabled=disabled)
    if state and level == "current" and (state.get("pending") or has_gaps or status_name == "partial"):
        level = "partial"
    status = "disabled" if disabled else status_name or level
    return {
        "dataset": dataset,
        "key": (state or {}).get("key"),
        "last_attempt_at": (state or {}).get("last_attempt_at"),
        "last_error_class": (state or {}).get("last_error_class"),
        "last_successful_check_at": (state or {}).get("last_successful_check_at"),
        "level": level,
        "missed_windows": missed,
        "pending": bool((state or {}).get("pending")),
        "status": status,
        "tier": tier,
    }


def build_health(
    states: dict[str, dict[str, dict | None]],
    *,
    now: datetime,
    supported: set[str],
    disabled: set[str] | None = None,
    http_status: int = 200,
    price_bars: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """`states` is dataset -> ticker -> checkpoint. Prices use session dates, not the news clock."""
    disabled = disabled or set()
    sources: list[dict[str, Any]] = []
    for dataset, tickers in states.items():
        for ticker, state in tickers.items():
            sources.append(
                assess_source(
                    state,
                    dataset=dataset,
                    tier=coverage_tier(ticker, supported),
                    now=now,
                    disabled=dataset in disabled,
                    failed=bool(state and state.get("last_error_class")),
                )
            )
    prices = []
    for ticker, last_bar in (price_bars or {}).items():
        prices.append(
            {
                "dataset": "prices",
                "key": ticker,
                "level": price_status(last_bar, now),
                "tier": coverage_tier(ticker, supported),
            }
        )
    levels = [source["level"] for source in sources] + [row["level"] for row in prices]
    if any(level == "critical" for level in levels):
        overall = "critical"
    elif any(level in {"degraded", "stale", "partial", "unavailable"} for level in levels):
        overall = "attention"
    elif any(level == "disabled" for level in levels):
        overall = "disabled"
    elif levels:
        overall = "current"
    else:
        overall = "unavailable"
    return {
        "http_status": http_status,
        "naive_http_ok": http_status == 200,
        "ok": overall == "current",
        "overall": overall,
        "prices": prices,
        "sources": [{field: source.get(field) for field in (*PUBLIC_HEALTH_FIELDS, "tier")} for source in sources],
    }


def checkpoint_states(payload: dict, expected: set[str]) -> dict[str, dict[str, dict | None]]:
    """Dataset states plus every expected news and SEC ticker, even with no file yet."""
    raw: dict[str, dict[str, dict | None]] = {}
    for dataset, body in (payload.get("datasets") or {}).items():
        if not isinstance(body, dict):
            continue
        states = body.get("states") or {}
        raw[str(dataset)] = {
            str(ticker): state if isinstance(state, dict) else {"key": str(ticker)}
            for ticker, state in states.items()
        }
    for dataset in MONITORED_DATASETS:
        bucket = raw.setdefault(dataset, {})
        for ticker in sorted(expected):
            bucket.setdefault(ticker, {"key": ticker})
    return raw


def judge_checkpoint(
    payload: dict,
    *,
    now: datetime,
    expected: set[str],
    disabled: set[str] | None = None,
    http_status: int = 200,
) -> dict[str, Any]:
    """The monitor's reading of a checkpoint. Missing expected tasks are not current."""
    return build_health(
        checkpoint_states(payload, expected),
        now=now,
        supported=set(expected),
        disabled=disabled,
        http_status=http_status,
    )


def public_health(report: dict[str, Any]) -> dict[str, Any]:
    """Drop anything a public reader should not see, including traces and secrets."""
    allowed = {"http_status", "naive_http_ok", "ok", "overall", "prices", "sources"}
    published = {key: report[key] for key in allowed if key in report}
    published["sources"] = [
        {field: source.get(field) for field in (*PUBLIC_HEALTH_FIELDS, "tier")}
        for source in report.get("sources") or []
        if isinstance(source, dict)
    ]
    return published


def monitor_action(report: dict[str, Any], *, rerun_configured: bool) -> dict[str, Any]:
    """Eligibility only. Calling the executor is a separate step with its own response.

    A GitHub workflow is not an independent wake. ``rerun_configured`` means an
    external executor URL and credential exist.
    """
    if report.get("ok"):
        return {
            "action": "none",
            "auto_repair": False,
            "overall": report.get("overall"),
            "rerun_requested": False,
        }
    if rerun_configured and report.get("overall") in {"critical", "attention", "degraded"}:
        return {
            "action": "rerun_eligible",
            "auto_repair": False,
            "configured": True,
            "overall": report.get("overall"),
            "rerun_requested": False,
        }
    return {
        "action": "alert",
        "auto_repair": False,
        "configured": False,
        "independent_wake": "not_configured",
        "overall": report.get("overall"),
        "rerun_requested": False,
    }


def execute_rerun(
    decision: dict[str, Any],
    *,
    executor: Any | None,
    now: datetime,
    cooldown_until: str | None,
    cooldown_seconds: int = 1800,
) -> dict[str, Any]:
    """Call the external executor once. Cooldown and a missing executor do not claim a rerun."""
    if decision.get("action") != "rerun_eligible" or executor is None:
        return {**decision, "rerun_requested": False}
    if cooldown_until:
        until = datetime.fromisoformat(cooldown_until)
        if as_utc(now) < as_utc(until):
            return {
                **decision,
                "reason": "cooldown",
                "rerun_requested": False,
            }
    response = executor()
    status_code = int(getattr(response, "status_code", 0) or 0)
    accepted = 200 <= status_code < 300
    return {
        **decision,
        "action": "rerun" if accepted else "rerun_failed",
        "auto_repair": False,
        "cooldown_until": (as_utc(now) + timedelta(seconds=cooldown_seconds)).isoformat(),
        "executor_status": status_code,
        "rerun_requested": accepted,
    }


def acquire_monitor_turn(
    durable: Any,
    pulled: Any,
    now: datetime,
    *,
    claim_seconds: int = 120,
) -> dict[str, Any]:
    """Persist the right to call the executor. A lost compare-and-swap must not POST."""
    payload = copy.deepcopy(pulled.payload or {})
    now = as_utc(now)
    cooldown = payload.get("cooldown_until")
    if cooldown and now < as_utc(datetime.fromisoformat(str(cooldown))):
        return {"acquired": False, "reason": "cooldown"}
    claim_until = payload.get("claim_until")
    if claim_until and now < as_utc(datetime.fromisoformat(str(claim_until))):
        return {"acquired": False, "reason": "claimed"}
    token = secrets.token_hex(8)
    payload["claim_token"] = token
    payload["claim_until"] = (now + timedelta(seconds=claim_seconds)).isoformat()
    try:
        pushed = durable.push(payload, pulled.etag)
    except BlobRequestError as exc:
        if exc.status in {409, 412}:
            return {"acquired": False, "reason": "conflict"}
        raise
    return {
        "acquired": True,
        "etag": pushed.get("etag"),
        "payload": payload,
        "token": token,
    }


def request_monitor_rerun(
    durable: Any,
    pulled: Any,
    decision: dict[str, Any],
    *,
    executor: Any | None,
    now: datetime,
    claim_seconds: int = 120,
    cooldown_seconds: int = 1800,
) -> dict[str, Any]:
    """Claim a durable turn, then POST. Cooldown is written only after an accepted POST."""
    if decision.get("action") != "rerun_eligible" or executor is None:
        return {**decision, "rerun_requested": False}
    claim = acquire_monitor_turn(durable, pulled, now, claim_seconds=claim_seconds)
    if not claim["acquired"]:
        return {**decision, "reason": claim["reason"], "rerun_requested": False}
    outcome = execute_rerun(
        decision,
        executor=executor,
        now=now,
        cooldown_until=None,
        cooldown_seconds=cooldown_seconds,
    )
    if outcome.get("rerun_requested") and outcome.get("cooldown_until"):
        payload = claim["payload"]
        payload["cooldown_until"] = outcome["cooldown_until"]
        try:
            durable.push(payload, claim["etag"])
            outcome = {**outcome, "cooldown_persisted": True}
        except BlobRequestError:
            outcome = {**outcome, "cooldown_persisted": False}
    return outcome
