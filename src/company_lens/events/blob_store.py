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
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import requests

BLOB_API = "https://vercel.com/api/blob"
BLOB_API_VERSION = "12"
LIST_PAGE_CAP = 50
DELETE_BATCH = 100
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

    def list_prefix(self, prefix: str) -> list[dict]: ...

    def delete(self, urls: list[str]) -> None: ...


class BlobRequestError(RuntimeError):
    def __init__(self, status: int, pathname: str, detail: str = "") -> None:
        suffix = f" detail={detail}" if detail else ""
        super().__init__(f"blob request failed status={status} path={pathname}{suffix}")
        self.status = status
        self.pathname = pathname
        self.detail = detail


class HttpBlobTransport:
    def __init__(self, token: str, *, session: requests.Session | None = None) -> None:
        if not token.strip():
            raise ValueError("BLOB_READ_WRITE_TOKEN is empty")
        self._token = token.strip()
        self._session = session or requests.Session()

    def _detail(self, response: requests.Response) -> str:
        """One short line from the store's own refusal.

        "Your store is blocked" is a different failure from a missing object
        or a revoked token, and all three arrive as a bare status code. A
        scheduled job nobody watches has only its log, so the store's own
        words are kept. The token lives in a header, not in a body, and is
        redacted anyway.
        """
        text = ""
        try:
            payload = response.json()
        except ValueError:
            text = response.text or ""
        else:
            if isinstance(payload, dict):
                error = payload.get("error")
                if isinstance(error, dict):
                    text = str(error.get("code") or error.get("message") or "")
                elif error:
                    text = str(error)
        text = " ".join(text.split())[:120]
        return text.replace(self._token, "REDACTED") if self._token else text

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
            raise BlobRequestError(412, pathname, self._detail(response))
        if response.status_code >= 400:
            raise BlobRequestError(response.status_code, pathname, self._detail(response))
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
            raise BlobRequestError(response.status_code, prefix, self._detail(response))
        payload = response.json()
        blobs = payload.get("blobs") if isinstance(payload, dict) else None
        return [item for item in blobs or [] if isinstance(item, dict)]

    def list_prefix(self, prefix: str) -> list[dict]:
        """Every object under a prefix. ``get_prefix`` is one page of twenty.

        Each page is one Advanced Operation on the Blob bill, so this is for
        the retention sweep, not for a read on the refresh path.
        """
        found: list[dict] = []
        cursor: str | None = None
        for _page in range(LIST_PAGE_CAP):
            params = {"limit": "1000", "prefix": prefix}
            if cursor:
                params["cursor"] = cursor
            response = self._session.get(BLOB_API, params=params, headers=self._headers(), timeout=60)
            if response.status_code >= 400:
                raise BlobRequestError(response.status_code, prefix, self._detail(response))
            try:
                payload = response.json()
            except ValueError as exc:
                raise BlobRequestError(502, prefix) from exc
            if not isinstance(payload, dict):
                raise BlobRequestError(502, prefix)
            found.extend(item for item in payload.get("blobs") or [] if isinstance(item, dict))
            cursor = payload.get("cursor") if payload.get("hasMore") else None
            if not cursor:
                return found
        # A listing that never ends is not a complete listing. Deleting from a
        # partial one is safe, but reporting it as complete would not be.
        raise BlobRequestError(502, prefix, "listing did not finish")

    def delete(self, urls: list[str]) -> None:
        """The SDK's ``del``: POST /delete with the object URLs. Deletes are not billed."""
        for start in range(0, len(urls), DELETE_BATCH):
            response = self._session.post(
                f"{BLOB_API}/delete",
                data=json.dumps({"urls": urls[start : start + DELETE_BATCH]}),
                headers=self._headers({"content-type": "application/json"}),
                timeout=60,
            )
            if response.status_code >= 400:
                raise BlobRequestError(response.status_code, "delete", self._detail(response))

    def read_url(self, url: str) -> tuple[bytes, str]:
        # Match the official SDK's useCache=False for private Blob reads.
        # Cache-Control alone does not select the origin representation/ETag.
        parts = urlsplit(url)
        if (parts.hostname or "").endswith(".private.blob.vercel-storage.com"):
            query = dict(parse_qsl(parts.query))
            query["cache"] = "0"
            url = urlunsplit(parts._replace(query=urlencode(query)))
        response = self._session.get(
            url,
            headers=self._headers({"Cache-Control": "no-cache", "Accept-Encoding": "identity"}),
            timeout=30,
        )
        if response.status_code >= 400:
            raise BlobRequestError(response.status_code, "blob-url", self._detail(response))
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

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self.objects: dict[str, dict] = {}
        self._serial = 0
        self._clock = clock or (lambda: datetime.now(UTC))

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
            "uploadedAt": self._clock().isoformat(),
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

    def list_prefix(self, prefix: str) -> list[dict]:
        return [
            {
                "etag": item["etag"],
                "pathname": path,
                "size": len(item["body"]),
                "uploadedAt": item["uploadedAt"],
                "url": item["url"],
            }
            for path, item in self.objects.items()
            if path.startswith(prefix)
        ]

    def delete(self, urls: list[str]) -> None:
        doomed = set(urls)
        for path in [path for path, item in self.objects.items() if item["url"] in doomed]:
            del self.objects[path]

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



DEFAULT_CHECKPOINT_MIN_AGE = timedelta(hours=24)


def _uploaded_at(item: dict) -> datetime | None:
    raw = item.get("uploadedAt")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def prune_checkpoints(
    transport: BlobTransport,
    *,
    now: datetime,
    min_age: timedelta = DEFAULT_CHECKPOINT_MIN_AGE,
    keep_newest: int | None = None,
    apply: bool = False,
) -> dict:
    """Delete superseded checkpoint objects. Nothing else wrote a retention rule.

    Every commit stores its checkpoint at a new content-hashed pathname and
    moves the pointer; the object it replaced stayed forever. This sweep is the
    other half. It only ever touches ``<prefix>/checkpoints/``: feeds and
    evidence stay, because the commit record still lists older versions and
    Ask resolves evidence through it.

    Kept, always: the checkpoint the commit record points at; anything
    uploaded within ``min_age``, which covers a candidate whose pointer has not
    moved yet and a reader holding the previous generation; anything whose
    upload time cannot be read. If the commit record is missing, names no
    checkpoint, or names one the listing does not contain, nothing is deleted:
    the sweep does not guess which object is live. A commit that lands during
    the sweep also cancels it.

    ``keep_newest`` is for a store whose content reads are refused (a paused
    store still lists). The commit record cannot be read then, so the newest
    ``keep_newest`` objects by upload time stand in for the pointer. That is an
    inference, not a read, which is why it is never the default.

    ``apply`` false reports what would go and deletes nothing.
    """
    if keep_newest is not None and keep_newest < 1:
        raise ValueError("keep_newest must be at least 1")
    prefix = f"{checkpoint_prefix()}/"
    report: dict[str, Any] = {
        "applied": False,
        "deleted": [],
        "freed_bytes": 0,
        "kept": [],
        "listed": 0,
        "listed_bytes": 0,
        "mode": "pointer" if keep_newest is None else "newest",
    }
    current: str | None = None
    etag: str | None = None
    if keep_newest is None:
        commit, etag = read_commit(transport)
        current = commit.get("checkpoint_pathname") if commit else None
        if not current:
            return {**report, "status": "no_commit"}
    listed = [
        item
        for item in transport.list_prefix(prefix)
        if item.get("pathname") and item.get("url")
    ]
    report["listed"] = len(listed)
    report["listed_bytes"] = sum(int(item.get("size") or 0) for item in listed)
    if current is not None and current not in {item["pathname"] for item in listed}:
        return {**report, "status": "pointer_not_listed"}
    newest: set[str] = set()
    if keep_newest is not None:
        dated = [(stamp, item["pathname"]) for item in listed if (stamp := _uploaded_at(item))]
        newest = {path for _stamp, path in sorted(dated, reverse=True)[:keep_newest]}
    doomed: list[dict] = []
    for item in sorted(listed, key=lambda entry: str(entry.get("uploadedAt") or "")):
        uploaded = _uploaded_at(item)
        if item["pathname"] == current:
            reason = "current"
        elif item["pathname"] in newest:
            reason = "newest"
        elif uploaded is None:
            reason = "undated"
        elif now - uploaded < min_age:
            reason = "recent"
        else:
            reason = None
        row = {
            "pathname": item["pathname"],
            "size": int(item.get("size") or 0),
            "uploaded_at": item.get("uploadedAt"),
        }
        if reason is None:
            doomed.append(item)
            report["deleted"].append(row)
            report["freed_bytes"] += row["size"]
        else:
            report["kept"].append({**row, "reason": reason})
    if not apply:
        return {**report, "status": "dry_run"}
    if doomed:
        if keep_newest is None:
            _again, etag_now = read_commit(transport)
            if etag_now != etag:
                return {**report, "deleted": [], "freed_bytes": 0, "status": "commit_moved"}
        transport.delete([str(item["url"]) for item in doomed])
    return {**report, "applied": True, "status": "pruned"}
