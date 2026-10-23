"""Optional Vercel Blob publisher. The token is a header, never an error string.

Immutable version objects are written once. The manifest pointer uses
``x-if-match`` so a stale writer cannot replace a newer pointer. This module
is not used unless ``BLOB_READ_WRITE_TOKEN`` is set.
"""

from __future__ import annotations

import hashlib
import json
from typing import Protocol
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
        response = self._session.get(url, headers=self._headers(), timeout=30)
        if response.status_code >= 400:
            raise BlobRequestError(response.status_code, "blob-url")
        etag = response.headers.get("etag") or response.headers.get("ETag") or ""
        return response.content, etag


CHECKPOINT_PATH = "lens-events/checkpoint.json"
POINTER_PATH = "lens-events/public/manifest.json"
FEED_PREFIX = "lens-events/public/versions"
EVIDENCE_PREFIX = "lens-events/evidence"


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


def push_checkpoint(transport: BlobTransport, payload: dict, *, expected_etag: str | None) -> dict:
    """CAS-publish the checkpoint. A 412 means a newer writer already stored one."""
    try:
        meta = transport.put(
            CHECKPOINT_PATH,
            checkpoint_document(payload),
            if_match=expected_etag,
            overwrite=expected_etag is not None,
        )
    except BlobRequestError as exc:
        if exc.status == 412:
            raise BlobRequestError(412, CHECKPOINT_PATH) from None
        raise
    return meta


def pull_checkpoint(transport: BlobTransport) -> tuple[dict | None, str | None]:
    """Return the checkpoint and its etag. Missing objects are an empty start, not an error."""
    try:
        found = transport.get_prefix(CHECKPOINT_PATH)
    except BlobRequestError as exc:
        if exc.status == 404:
            return None, None
        raise
    if not found:
        return None, None
    url = found[0].get("url")
    etag = found[0].get("etag")
    if not url:
        return None, etag if isinstance(etag, str) else None
    body, read_etag = transport.read_url(str(url))
    payload = json.loads(body.decode())
    if not isinstance(payload, dict):
        raise BlobRequestError(502, CHECKPOINT_PATH)
    return payload, str(read_etag or etag or "") or None


def _exact_blob(found: list[dict], pathname: str) -> dict | None:
    for item in found:
        if item.get("pathname") == pathname or str(item.get("url") or "").endswith(pathname):
            return item
    return None


def read_pointer(transport: BlobTransport) -> tuple[dict, str | None]:
    """The only current-feed pointer. Missing means nothing has been published."""
    try:
        found = transport.get_prefix(POINTER_PATH)
    except BlobRequestError as exc:
        if exc.status == 404:
            return {}, None
        raise
    chosen = _exact_blob(found, POINTER_PATH)
    if chosen is None or not chosen.get("url"):
        return {}, None
    body, etag = transport.read_url(str(chosen["url"]))
    payload = json.loads(body.decode())
    if not isinstance(payload, dict):
        raise BlobRequestError(502, POINTER_PATH)
    return payload, str(chosen.get("etag") or etag or "") or None


def read_published(transport: BlobTransport, ticker: str) -> dict | None:
    """Read the feed URL stored on the pointer. Never a mutable per-ticker path."""
    manifest, _etag = read_pointer(transport)
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
        if exc.status != 409:
            raise
        found = _exact_blob(transport.get_prefix(pathname), pathname)
        if found is None or not found.get("url"):
            raise
        existing, _etag = transport.read_url(str(found["url"]))
        if existing != body:
            raise BlobRequestError(409, pathname) from None
        return {"etag": found.get("etag"), "pathname": pathname, "url": found.get("url")}


def publish_releases(
    transport: BlobTransport,
    releases: dict[str, dict],
    *,
    observed_etag: str | None,
) -> dict:
    """Write immutable version objects, then swing the pointer with ``if_match``.

    A stale ``observed_etag`` fails before any served object is replaced. Other
    tickers already on the pointer stay there when this batch publishes a subset.
    """
    current, etag = read_pointer(transport)
    if (etag or None) != (observed_etag or None):
        raise BlobRequestError(412, POINTER_PATH)
    tickers = dict(current.get("tickers") or {})
    for ticker, release in sorted(releases.items()):
        symbol = ticker.upper()
        version_id = str(release["version_id"])
        feed = dict(release["feed"])
        feed["ai_enabled"] = True
        feed["manifest_version"] = version_id
        evidence_path = f"{EVIDENCE_PREFIX}/{symbol}/{version_id}.json"
        feed_body = json.dumps(feed, ensure_ascii=False, sort_keys=True).encode()
        evidence_body = json.dumps(release["evidence"], ensure_ascii=False, sort_keys=True).encode()
        feed_path = f"{FEED_PREFIX}/{symbol}/{version_id}/{hashlib.sha256(feed_body).hexdigest()[:20]}.json"
        feed_meta = _put_immutable(transport, feed_path, feed_body)
        evidence_meta = _put_immutable(transport, evidence_path, evidence_body)
        tickers[symbol] = {
            "evidence_pathname": evidence_path,
            "evidence_url": evidence_meta.get("url"),
            "feed_pathname": feed_path,
            "feed_url": feed_meta.get("url"),
            "version_id": version_id,
        }
    manifest = {"schema_version": "company-lens.events-pointer.v1", "tickers": tickers}
    body = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode()
    try:
        pointer = transport.put(
            POINTER_PATH,
            body,
            if_match=etag,
            overwrite=etag is not None,
        )
    except BlobRequestError as exc:
        if exc.status == 412:
            raise BlobRequestError(412, POINTER_PATH) from None
        raise
    return {"etag": pointer.get("etag"), "manifest": manifest}
