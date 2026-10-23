"""Task health. An HTTP 200 from the site is not evidence that a job ran."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from company_lens.events.calendar import as_utc, price_status
from company_lens.events.policy import coverage_tier, freshness_level, missed_windows

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
    missed = None if disabled else missed_windows(dataset, tier, last_success, as_utc(now))
    level = freshness_level(missed, failed=failed, disabled=disabled)
    if state and state.get("pending") and level == "current":
        level = "partial"
    status = "disabled" if disabled else (state or {}).get("status") or level
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
    """A missed schedule is an alert unless a separate rerun credential is configured.

    This function does not call the network. A caller that sees ``action=rerun``
    may invoke the protected workflow; without the credential it must not claim
    that repair already happened.
    """
    if report.get("ok"):
        return {"action": "none", "auto_repair": False, "overall": report.get("overall")}
    if rerun_configured and report.get("overall") in {"critical", "attention", "degraded"}:
        return {
            "action": "rerun",
            "auto_repair": False,
            "configured": True,
            "overall": report.get("overall"),
            "recovery": "workflow_dispatch events-refresh.yml",
        }
    return {
        "action": "alert",
        "auto_repair": False,
        "configured": False,
        "overall": report.get("overall"),
        "recovery": "workflow_dispatch events-refresh.yml",
    }
