"""Event documents, hashes, and the checks that run before anything becomes current."""

from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

SCHEMA_VERSION = "company-lens.events.v1"
DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REQUIRED_EVENT_FIELDS = (
    "id",
    "schema_version",
    "ticker",
    "type",
    "title",
    "source_url",
    "publisher",
    "source_kind",
    "time_precision",
    "status",
    "content_hash",
)


class DocumentRejected(ValueError):
    """A candidate failed validation and must not replace last-good."""


def canonical_url(url: str) -> str:
    parsed = urlparse(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
    ]
    cleaned = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        fragment="",
        query=urlencode(query),
    )
    return urlunparse(cleaned)


def safe_http_url(url: str) -> str | None:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.username or parsed.password:
        return None
    return url.strip()


def event_identity(ticker: str, url: str, source_event_id: str | None) -> str:
    symbol = ticker.strip().upper()
    if source_event_id and source_event_id.strip():
        key = f"{symbol}|id|{source_event_id.strip()}"
    else:
        key = f"{symbol}|url|{canonical_url(url)}"
    return hashlib.sha256(key.encode()).hexdigest()[:20]


def duplicate_group_id(url: str, source_event_id: str | None = None) -> str:
    """Reprints of one URL share a group. The ticker stays out, so companies are not merged."""
    if source_event_id and source_event_id.strip():
        key = f"src|{source_event_id.strip()}"
    else:
        key = f"url|{canonical_url(url)}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def content_hash(core: dict) -> str:
    payload = {
        "title": core.get("title") or "",
        "excerpt": core.get("excerpt") or "",
        "url": canonical_url(str(core.get("source_url") or "")),
        "published": core.get("source_published_at"),
        "precision": core.get("time_precision"),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def version_id(ticker: str, events: list[dict]) -> str:
    core = [{"content_hash": event["content_hash"], "id": event["id"]} for event in events]
    raw = json.dumps(
        {"events": core, "ticker": ticker.upper()},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def validate_event(event: dict, *, ticker: str) -> None:
    missing = [field for field in REQUIRED_EVENT_FIELDS if not event.get(field)]
    if missing:
        raise DocumentRejected(f"event missing {', '.join(missing)}")
    if event["schema_version"] != SCHEMA_VERSION:
        raise DocumentRejected("unexpected event schema")
    if str(event["ticker"]).upper() != ticker.upper():
        raise DocumentRejected("event ticker does not match the document")
    if safe_http_url(str(event["source_url"])) is None:
        raise DocumentRejected("event source URL is not http(s)")
    precision = event["time_precision"]
    published = event.get("source_published_at")
    if precision == "date":
        if not isinstance(published, str) or DATE_ONLY.fullmatch(published) is None:
            raise DocumentRejected("date-only events must keep a calendar date")
        if "T" in published:
            raise DocumentRejected("date-only events must not invent a clock time")
    elif published and "T00:00:00" in str(published) and precision == "date":
        raise DocumentRejected("midnight was used as a precise timestamp")
    if event["time_precision"] not in {"date", "minute", "second"}:
        raise DocumentRejected("unknown time precision")


def validate_version(document: dict) -> None:
    if document.get("schema_version") != SCHEMA_VERSION:
        raise DocumentRejected("unexpected version schema")
    ticker = str(document.get("ticker") or "")
    if not ticker:
        raise DocumentRejected("version has no ticker")
    events = document.get("events")
    if not isinstance(events, list):
        raise DocumentRejected("version events must be a list")
    expected = version_id(ticker, events)
    if document.get("version_id") != expected:
        raise DocumentRejected("version id does not match its events")
    for event in events:
        validate_event(event, ticker=ticker)
