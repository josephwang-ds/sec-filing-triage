"""Optional Vercel Blob publisher. The token is a header, never an error string.

Immutable version objects are written once. The manifest pointer uses
``x-if-match`` so a stale writer cannot replace a newer pointer. This module
is not used unless ``BLOB_READ_WRITE_TOKEN`` is set.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Protocol
from urllib.parse import quote

import requests

BLOB_API = "https://vercel.com/api/blob"
BLOB_API_VERSION = "12"
PUBLIC_PREFIX = "lens-events/public"


class BlobTransport(Protocol):
    def put(
        self,
        pathname: str,
        body: bytes,
        *,
        if_match: str | None,
        overwrite: bool,
    ) -> dict: ...

    def get_prefix(self, prefix: str) -> list[dict]: ...

    def read_url(self, url: str) -> tuple[bytes, str]: ...


class BlobRequestError(RuntimeError):
    def __init__(self, status: int, pathname: str) -> None:
        super().__init__(f"blob request failed status={status} path={pathname}")
        self.status = status
        self.pathname = pathname


class HttpBlobTransport:
    def __init__(self, token: str, *, session: requests.Session | None = None) -> None:
        if not token.strip():
            raise ValueError("BLOB_READ_WRITE_TOKEN is empty")
        self._token = token.strip()
        self._session = session or requests.Session()

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "authorization": f"Bearer {self._token}",
            "x-api-version": BLOB_API_VERSION,
        }
        if extra:
            headers.update(extra)
        return headers

    def put(
        self,
        pathname: str,
        body: bytes,
        *,
        if_match: str | None,
        overwrite: bool,
    ) -> dict:
        headers = self._headers(
            {
                "content-type": "application/json",
                "x-content-type": "application/json",
                "x-vercel-blob-access": "private",
            }
        )
        if pathname.endswith(("/commit.json", "/monitor.json")):
            headers["x-cache-control-max-age"] = "60"
        if overwrite:
            headers["x-allow-overwrite"] = "1"
        if if_match:
            headers["x-if-match"] = if_match
            headers["x-allow-overwrite"] = "1"
        response = self._session.put(
            f"{BLOB_API}?pathname={quote(pathname)}",
            data=body,
            headers=headers,
            timeout=30,
        )
        if response.status_code == 412:
            raise BlobRequestError(412, pathname)
        if response.status_code >= 400:
            raise BlobRequestError(response.status_code, pathname)
        try:
            payload = response.json()
        except ValueError as exc:
            raise BlobRequestError(response.status_code, pathname) from exc
        if not isinstance(payload, dict):
            raise BlobRequestError(response.status_code, pathname)
        return payload

    def get_prefix(self, prefix: str) -> list[dict]:
        response = self._session.get(
            BLOB_API,
            params={"limit": "20", "prefix": prefix},
            headers=self._headers(),
            timeout=30,
        )
        if response.status_code >= 400:
            raise BlobRequestError(response.status_code, prefix)
        payload = response.json()
        blobs = payload.get("blobs") if isinstance(payload, dict) else None
        return [item for item in blobs or [] if isinstance(item, dict)]

    def read_url(self, url: str) -> tuple[bytes, str]:
        response = self._session.get(
            url, headers=self._headers({"Cache-Control": "no-cache"}), timeout=30
        )
        if response.status_code >= 400:
            raise BlobRequestError(response.status_code, "blob-url")
        etag = response.headers.get("etag") or response.headers.get("ETag") or ""
        return response.content, etag


DEFAULT_EVENTS_PREFIX = "lens-events"
COMMIT_PATH = f"{DEFAULT_EVENTS_PREFIX}/commit.json"
MONITOR_PATH = f"{DEFAULT_EVENTS_PREFIX}/monitor.json"
POINTER_PATH = COMMIT_PATH
FEED_PREFIX = f"{DEFAULT_EVENTS_PREFIX}/public/versions"
EVIDENCE_PREFIX = f"{DEFAULT_EVENTS_PREFIX}/evidence"
CHECKPOINT_PREFIX = f"{DEFAULT_EVENTS_PREFIX}/checkpoints"
CHECKPOINT_PATH = f"{DEFAULT_EVENTS_PREFIX}/checkpoint.json"


def events_prefix() -> str:
    """Blob namespace. A drill sets this so it does not publish over the live feed."""
    raw = os.environ.get("EVENTS_BLOB_PREFIX", DEFAULT_EVENTS_PREFIX).strip().strip("/")
    if not raw or not re.fullmatch(r"[A-Za-z0-9._-]+", raw):
        return DEFAULT_EVENTS_PREFIX
    return raw


def commit_path() -> str:
    return f"{events_prefix()}/commit.json"


def monitor_path() -> str:
    return f"{events_prefix()}/monitor.json"


def feed_prefix() -> str:
    return f"{events_prefix()}/public/versions"


def evidence_prefix() -> str:
    return f"{events_prefix()}/evidence"


def checkpoint_prefix() -> str:
    return f"{events_prefix()}/checkpoints"


class MemoryBlob:
    """In-memory stand-in for the Blob HTTP rules used by the publisher.

    A pathname written with ``overwrite`` false is not replaced. ``if_match``
    replaces a pathname only when the etag matches; a mismatch leaves the body
    untouched. This is the SDK's documented put behavior, not a live store call.
    """

    def __init__(self) -> None:
        self.objects: dict[str, dict] = {}
        self._serial = 0

    def put(self, pathname: str, body: bytes, *, if_match: str | None, overwrite: bool) -> dict:
        current = self.objects.get(pathname)
        if current is not None and if_match is None and not overwrite:
            raise BlobRequestError(409, pathname)
        if if_match is not None and (current is None or current["etag"] != if_match):
            raise BlobRequestError(412, pathname)
        if current is not None and not overwrite and if_match is None:
            raise BlobRequestError(409, pathname)
        self._serial += 1
        etag = f"etag-{self._serial}"
        stored = {
            "body": body,
            "etag": etag,
            "pathname": pathname,
            "url": f"https://blob.test/{pathname}",
        }
        self.objects[pathname] = stored
        return {"etag": etag, "pathname": pathname, "url": stored["url"]}

    def get_prefix(self, prefix: str) -> list[dict]:
        return [
            {"etag": item["etag"], "pathname": path, "url": item["url"]}
            for path, item in self.objects.items()
            if path.startswith(prefix)
        ]

    def read_url(self, url: str) -> tuple[bytes, str]:
        for item in self.objects.values():
            if item["url"] == url:
                return item["body"], item["etag"]
        raise BlobRequestError(404, "blob-url")


def checkpoint_document(store_root_payload: dict) -> bytes:
    return json.dumps(store_root_payload, ensure_ascii=False, sort_keys=True).encode()


def _exact_blob(found: list[dict], pathname: str) -> dict | None:
    for item in found:
        if item.get("pathname") == pathname or str(item.get("url") or "").endswith(pathname):
            return item
    return None


def _read_exact(transport: BlobTransport, pathname: str) -> tuple[dict, str | None]:
    """Return one object. Missing is an empty document, not a read failure."""
    try:
        found = transport.get_prefix(pathname)
    except BlobRequestError as exc:
        if exc.status == 404:
            return {}, None
        raise
    chosen = _exact_blob(found, pathname)
    if chosen is None or not chosen.get("url"):
        return {}, None
    body, etag = transport.read_url(str(chosen["url"]))
    payload = json.loads(body.decode())
    if not isinstance(payload, dict):
        raise BlobRequestError(502, pathname)
    # The listing and the GET can observe different generations. Only the
    # ETag returned WITH this body can authorize a write based on this body.
    if not etag:
        raise BlobRequestError(502, pathname)
    return payload, str(etag)


def read_commit(transport: BlobTransport) -> tuple[dict, str | None]:
    """The only mutable publication record. Missing means nothing is committed."""
    return _read_exact(transport, commit_path())


def read_pointer(transport: BlobTransport) -> tuple[dict, str | None]:
    """Page reads use the commit record. There is no second feed pointer."""
    return read_commit(transport)


def read_generation(transport: BlobTransport) -> tuple[dict | None, str | None, dict]:
    """Checkpoint body, commit etag, and the commit record from one generation.

    The checkpoint object is immutable. Its identity is the commit etag, not a
    second compare-and-swap token.
    """
    commit, etag = read_commit(transport)
    if not commit:
        return None, None, {}
    url = commit.get("checkpoint_url")
    if not url:
        return None, etag, commit
    body, _read_etag = transport.read_url(str(url))
    payload = json.loads(body.decode())
    if not isinstance(payload, dict):
        raise BlobRequestError(502, commit_path())
    return payload, etag, commit


def pull_checkpoint(transport: BlobTransport) -> tuple[dict | None, str | None]:
    """Return the committed checkpoint and the commit etag. A missing commit is an empty start."""
    payload, etag, _commit = read_generation(transport)
    return payload, etag


def push_checkpoint(transport: BlobTransport, payload: dict, *, expected_etag: str | None) -> dict:
    """Store a checkpoint by committing it. The etag is the caller's generation."""
    return commit_generation(
        transport,
        expected_etag=expected_etag,
        checkpoint_payload=payload,
    )


def pull_monitor(transport: BlobTransport) -> tuple[dict | None, str | None]:
    """Monitor claim and cooldown. This object is not part of a publication."""
    payload, etag = _read_exact(transport, monitor_path())
    if not payload:
        return None, None
    return payload, etag


def push_monitor(transport: BlobTransport, payload: dict, *, expected_etag: str | None) -> dict:
    """CAS the monitor record. A mismatch does not change the committed feed."""
    try:
        return transport.put(
            monitor_path(),
            checkpoint_document(payload),
            if_match=expected_etag,
            overwrite=expected_etag is not None,
        )
    except BlobRequestError as exc:
        if exc.status in {409, 412}:
            raise BlobRequestError(exc.status, monitor_path()) from None
        raise


def read_published(transport: BlobTransport, ticker: str) -> dict | None:
    """Read the feed URL stored on the commit. A candidate file is not a publication."""
    manifest, _etag = read_commit(transport)
    entry = (manifest.get("tickers") or {}).get(ticker.upper())
    if not isinstance(entry, dict) or not entry.get("feed_url"):
        return None
    body, _etag = transport.read_url(str(entry["feed_url"]))
    payload = json.loads(body.decode())
    if not isinstance(payload, dict):
        return None
    if payload.get("manifest_version") != entry.get("version_id"):
        return None
    return payload


def _put_immutable(transport: BlobTransport, pathname: str, body: bytes) -> dict:
    try:
        return transport.put(pathname, body, if_match=None, overwrite=False)
    except BlobRequestError as exc:
        # Blob may report an existing pathname as HTTP 400. Only accept it
        # after reading the exact object and verifying identical bytes.
        if exc.status not in {400, 409}:
            raise
        found = _exact_blob(transport.get_prefix(pathname), pathname)
        if found is None or not found.get("url"):
            raise
        existing, _etag = transport.read_url(str(found["url"]))
        if existing != body:
            raise BlobRequestError(409, pathname) from None
        return {"etag": found.get("etag"), "pathname": pathname, "url": found.get("url")}


def commit_generation(
    transport: BlobTransport,
    *,
    expected_etag: str | None,
    checkpoint_payload: dict | None = None,
    releases: dict[str, dict] | None = None,
    base_tickers: dict | None = None,
    base_checkpoint: dict | None = None,
    before_commit: Any = None,
) -> dict:
    """Write immutable candidates, then swing the commit pointer once.

    ``expected_etag`` is the generation the caller already read. This function
    does not adopt a newer etag. When ``base_tickers`` is omitted, the commit
    record is read only to copy that same generation, and a mismatch fails
    before the pointer moves. A failed compare-and-swap leaves candidates in
    place and leaves the previous commit as the publication.
    """
    if base_tickers is None:
        current, etag = read_commit(transport)
        if (etag or None) != (expected_etag or None):
            raise BlobRequestError(412, commit_path())
        base_tickers = current.get("tickers") or {}
        base_checkpoint = {
            "pathname": current.get("checkpoint_pathname"),
            "url": current.get("checkpoint_url"),
        }
    tickers = json.loads(json.dumps(base_tickers or {}))
    checkpoint_pathname = (base_checkpoint or {}).get("pathname")
    checkpoint_url = (base_checkpoint or {}).get("url")
    if checkpoint_payload is not None:
        raw = checkpoint_document(checkpoint_payload)
        digest = hashlib.sha256(raw).hexdigest()[:20]
        checkpoint_pathname = f"{checkpoint_prefix()}/{digest}.json"
        stored = _put_immutable(transport, checkpoint_pathname, raw)
        checkpoint_url = stored.get("url")
    for ticker, release in sorted((releases or {}).items()):
        symbol = ticker.upper()
        version_id = str(release["version_id"])
        feed = dict(release["feed"])
        feed["ai_enabled"] = True
        feed["manifest_version"] = version_id
        feed_body = json.dumps(feed, ensure_ascii=False, sort_keys=True).encode()
        evidence_body = json.dumps(release["evidence"], ensure_ascii=False, sort_keys=True).encode()
        evidence_path = (
            f"{evidence_prefix()}/{symbol}/{version_id}/"
            f"{hashlib.sha256(evidence_body).hexdigest()[:20]}.json"
        )
        feed_path = f"{feed_prefix()}/{symbol}/{version_id}/{hashlib.sha256(feed_body).hexdigest()[:20]}.json"
        feed_meta = _put_immutable(transport, feed_path, feed_body)
        evidence_meta = _put_immutable(transport, evidence_path, evidence_body)
        previous = tickers.get(symbol) if isinstance(tickers.get(symbol), dict) else {}
        versions = dict(previous.get("versions") or {})
        versions[version_id] = {
            "evidence_pathname": evidence_path,
            "evidence_url": evidence_meta.get("url"),
        }
        tickers[symbol] = {
            "evidence_pathname": evidence_path,
            "evidence_url": evidence_meta.get("url"),
            "feed_pathname": feed_path,
            "feed_url": feed_meta.get("url"),
            "version_id": version_id,
            "versions": versions,
        }
    manifest = {
        "checkpoint_pathname": checkpoint_pathname,
        "checkpoint_url": checkpoint_url,
        "schema_version": "company-lens.events-commit.v1",
        "tickers": tickers,
    }
    if before_commit is not None:
        before_commit()
    body = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode()
    try:
        pointer = transport.put(
            commit_path(),
            body,
            if_match=expected_etag,
            overwrite=expected_etag is not None,
        )
    except BlobRequestError as exc:
        if exc.status in {409, 412}:
            raise BlobRequestError(exc.status, commit_path()) from None
        raise
    return {"etag": pointer.get("etag"), "manifest": manifest}


def publish_releases(
    transport: BlobTransport,
    releases: dict[str, dict],
    *,
    observed_etag: str | None,
) -> dict:
    """Commit feed and evidence objects. The observed etag is not refreshed."""
    return commit_generation(
        transport,
        expected_etag=observed_etag,
        releases=releases,
    )

