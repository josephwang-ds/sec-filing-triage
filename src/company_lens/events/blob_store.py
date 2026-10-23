"""Optional Vercel Blob publisher. The token is a header, never an error string.

Immutable version objects are written once. The manifest pointer uses
``x-if-match`` so a stale writer cannot replace a newer pointer. This module
is not used unless ``BLOB_READ_WRITE_TOKEN`` is set.
"""

from __future__ import annotations

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


def publish_public_feeds(
    transport: BlobTransport,
    feeds: dict[str, dict],
    *,
    expected_etag: str | None,
) -> dict:
    """Write one private object per ticker and CAS-update the manifest pointer."""
    written = []
    for ticker, feed in sorted(feeds.items()):
        pathname = f"{PUBLIC_PREFIX}/{ticker.upper()}.json"
        body = json.dumps(feed, ensure_ascii=False, sort_keys=True).encode()
        meta = transport.put(pathname, body, if_match=None, overwrite=True)
        written.append({"pathname": pathname, "url": meta.get("url")})
    manifest = {
        "feeds": written,
        "schema_version": "company-lens.events-blob.v1",
        "tickers": sorted(feeds),
    }
    body = json.dumps(manifest, sort_keys=True).encode()
    try:
        pointer = transport.put(
            f"{PUBLIC_PREFIX}/manifest.json",
            body,
            if_match=expected_etag,
            overwrite=expected_etag is not None,
        )
    except BlobRequestError as exc:
        if exc.status == 412:
            raise BlobRequestError(412, f"{PUBLIC_PREFIX}/manifest.json") from None
        raise
    return {"etag": pointer.get("etag"), "manifest": manifest}
