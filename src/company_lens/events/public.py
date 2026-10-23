"""The document a browser may see. No credentials, raw cache, watchlist, or stack traces."""

from __future__ import annotations

from datetime import datetime

from company_lens.events.calendar import format_dual
from company_lens.events.policy import tier_copy

SIGNIFICANCE = {
    "new_provider_headline": {
        "en": "New headline from the configured news provider since the previous check. Not a trading signal.",
        "zh": "自上次检查后，配置的新闻源出现了新标题。这不是交易信号。",
    },
    "revised_headline": {
        "en": "The same source item changed. The earlier wording is kept in the revision list.",
        "zh": "同一条来源内容发生了变化。先前措辞保留在修订记录中。",
    },
    "title_only": {
        "en": "Only the title is available. No figure or detail was read from an article body.",
        "zh": "目前只有标题。没有从正文读取数值或细节。",
    },
    "sec_recent_filing": {
        "en": "A recent SEC filing index entry. The filing body was not parsed in this pass.",
        "zh": "SEC 最新披露索引中的一条。这一轮没有解析正文。",
    },
}

STATUS_COPY = {
    "current": {"en": "Checked", "zh": "已检查"},
    "no_new_events": {"en": "No new items", "zh": "没有新条目"},
    "partial": {"en": "Partial coverage", "zh": "覆盖不完整"},
    "stale": {"en": "Last good copy", "zh": "保留上次成功结果"},
    "degraded": {"en": "Checks are late", "zh": "检查已延迟"},
    "critical": {"en": "Checks are overdue", "zh": "检查已严重逾期"},
    "unavailable": {"en": "Feed unavailable", "zh": "事件源不可用"},
    "disabled": {"en": "Source not configured", "zh": "来源未配置"},
}


def _precision_copy(precision: str) -> dict[str, str] | None:
    if precision == "date":
        return {
            "en": "Date only. This is not an intraday timestamp.",
            "zh": "只有日期，不是盘中的精确时刻。",
        }
    return None


def _when_display(event: dict) -> dict[str, str]:
    published = str(event.get("source_published_at") or "")
    if event.get("time_precision") == "date" or "T" not in published:
        return {"en": published, "precision": "date", "shanghai": "", "new_york": ""}
    moment = datetime.fromisoformat(published)
    dual = format_dual(moment)
    return {"en": dual["utc"], "new_york": dual["new_york"], "precision": event.get("time_precision"), "shanghai": dual["shanghai"]}


def public_event(event: dict, *, manifest_version: str | None, ai_enabled: bool) -> dict:
    code = str(event.get("significance_code") or "new_provider_headline")
    return {
        "ask_enabled": bool(ai_enabled and manifest_version),
        "duplicate_group_id": event.get("duplicate_group_id"),
        "excerpt": event.get("excerpt") or None,
        "id": event["id"],
        "manifest_version": manifest_version,
        "precision_note": _precision_copy(str(event.get("time_precision") or "")),
        "publisher": event.get("publisher"),
        "significance": SIGNIFICANCE.get(code, SIGNIFICANCE["new_provider_headline"]),
        "source_kind": event.get("source_kind"),
        "source_published_at": event.get("source_published_at"),
        "source_url": event.get("source_url"),
        "status": event.get("status") or "reported",
        "time_precision": event.get("time_precision"),
        "title": event.get("title"),
        "title_language": "en",
        "title_only": bool(event.get("title_only")),
        "when": _when_display(event),
    }


def public_feed(
    *,
    ticker: str,
    tier: str,
    document: dict | None,
    state: dict | None,
    storage: str,
) -> dict:
    """One ticker's public feed. `storage` says whether this is live or the build snapshot."""
    version = None if document is None else document.get("version_id")
    events = [] if document is None else list(document.get("events") or [])
    ai_enabled = bool(version) and bool((document or {}).get("evidence_ready"))
    status = "unavailable" if document is None and not state else str((state or {}).get("status") or "current")
    if storage == "unavailable":
        status = "unavailable"
    checked = (state or {}).get("last_successful_check_at")
    checked_display = None
    if isinstance(checked, str) and "T" in checked:
        checked_display = format_dual(datetime.fromisoformat(checked))
    gaps = list((document or {}).get("coverage_gaps") or (state or {}).get("coverage_gaps") or [])
    return {
        "ai_enabled": ai_enabled,
        "checked_at": checked,
        "checked_at_display": checked_display,
        "coverage_gaps": gaps,
        "coverage_through": (state or {}).get("coverage_through"),
        "coverage_tier": tier,
        "events": [
            public_event(event, manifest_version=version, ai_enabled=ai_enabled) for event in events
        ],
        "initialization": bool((document or state or {}).get("initialization")),
        "manifest_version": version,
        "schema_version": "company-lens.events-public.v1",
        "status": status,
        "status_label": STATUS_COPY.get(status, STATUS_COPY["unavailable"]),
        "storage": storage,
        "ticker": ticker.upper(),
        "tier_label": tier_copy(tier),
        "upcoming": [],
    }


def unavailable_feed(ticker: str, *, tier: str = "ordinary") -> dict:
    feed = public_feed(ticker=ticker, tier=tier, document=None, state=None, storage="unavailable")
    feed["status"] = "unavailable"
    feed["status_label"] = STATUS_COPY["unavailable"]
    feed["ai_enabled"] = False
    return feed
