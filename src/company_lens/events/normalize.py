"""Turn provider rows into stable events. Titles are data, not instructions."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from company_lens.events.contracts import (
    SCHEMA_VERSION,
    content_hash,
    duplicate_group_id,
    event_identity,
    safe_http_url,
)

_WHITESPACE = re.compile(r"\s+")


def _clean(value: Any, limit: int) -> str:
    text = _WHITESPACE.sub(" ", str(value or "")).strip()
    return text[:limit]


def _from_unix(value: Any) -> tuple[str, str, str] | None:
    try:
        parsed = datetime.fromtimestamp(int(value), tz=UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    return parsed.isoformat(), "second", "UTC"


def _from_text(value: Any) -> tuple[str, str, str | None] | None:
    text = str(value or "").strip()
    if not text:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text, "date", None
    if re.fullmatch(r"\d{8}", text):
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}", "date", None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # A clock time without a zone is not a precise instant.
        return parsed.date().isoformat(), "date", None
    precision = "second" if parsed.second or parsed.microsecond else "minute"
    return parsed.astimezone(UTC).isoformat(), precision, "UTC"


def published_parts(payload: dict[str, Any]) -> tuple[str, str, str | None] | None:
    """Prefer an exact source instant. A bare date stays a date — midnight is not inferred."""
    for key in ("datetime", "published_unix"):
        if payload.get(key) not in (None, ""):
            parsed = _from_unix(payload.get(key))
            if parsed is not None:
                return parsed
    for key in ("source_published_at", "published_at", "acceptanceDateTime", "date", "filingDate"):
        if payload.get(key):
            parsed = _from_text(payload.get(key))
            if parsed is not None:
                return parsed
    return None


def normalize_item(payload: dict[str, Any], *, ticker: str, seen_at: str) -> dict[str, Any] | None:
    title = _clean(payload.get("headline") or payload.get("title"), 400)
    publisher = _clean(payload.get("source") or payload.get("publisher"), 160)
    url = safe_http_url(str(payload.get("url") or payload.get("source_url") or ""))
    published = published_parts(payload)
    if not title or not publisher or url is None or published is None:
        return None
    published_at, precision, zone = published
    excerpt = _clean(payload.get("summary") or payload.get("excerpt"), 400)
    source_event_id = _clean(payload.get("id") or payload.get("source_event_id") or "", 80) or None
    if payload.get("accession"):
        source_event_id = _clean(payload.get("accession"), 40)
    event_type = _clean(payload.get("type") or "news", 40) or "news"
    source_kind = _clean(payload.get("source_kind") or "news_provider", 40) or "news_provider"
    core = {
        "excerpt": excerpt,
        "source_published_at": published_at,
        "source_url": url,
        "time_precision": precision,
        "title": title,
    }
    digest = content_hash(core)
    event = {
        "content_hash": digest,
        "duplicate_group_id": duplicate_group_id(url, source_event_id),
        "excerpt": excerpt,
        "first_seen_at": seen_at,
        "id": event_identity(ticker, url, source_event_id),
        "publisher": publisher,
        "revisions": [{"content_hash": digest, "title": title, "updated_at": seen_at}],
        "schema_version": SCHEMA_VERSION,
        "significance_code": _clean(payload.get("significance_code"), 40)
        or ("title_only" if not excerpt else "new_provider_headline"),
        "source_event_id": source_event_id,
        "source_kind": source_kind,
        "source_published_at": published_at,
        "source_url": url,
        "status": "reported",
        "ticker": ticker.upper(),
        "time_precision": precision,
        "timezone": zone,
        "title": title,
        "title_only": not bool(excerpt),
        "type": event_type,
        "updated_at": seen_at,
    }
    return event


def merge_events(previous: list[dict], incoming: list[dict], *, seen_at: str) -> list[dict]:
    """Same identity updates in place. A new hash keeps a revision. Titles never fuzzy-merge."""
    by_id = {str(event["id"]): dict(event) for event in previous}
    for item in incoming:
        current = by_id.get(item["id"])
        if current is None:
            by_id[item["id"]] = item
            continue
        if current.get("content_hash") == item["content_hash"]:
            continue
        revisions = list(current.get("revisions") or [])
        revisions.append(
            {
                "content_hash": item["content_hash"],
                "title": item["title"],
                "updated_at": seen_at,
            }
        )
        by_id[item["id"]] = {
            **current,
            **item,
            "first_seen_at": current.get("first_seen_at") or seen_at,
            "revisions": revisions,
            "significance_code": "revised_headline",
            "updated_at": seen_at,
        }
    return sorted(
        by_id.values(),
        key=lambda event: (str(event.get("source_published_at") or ""), str(event["id"])),
        reverse=True,
    )
