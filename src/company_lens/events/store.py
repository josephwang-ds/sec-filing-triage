"""File checkpoints with a lease and a fencing sequence.

Versions are immutable. The manifest is the only current pointer. A writer that
read an older fence, or whose lease was replaced, cannot publish over a newer result.
Actions cache is not this store: callers pass an explicit root.
"""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from company_lens.events.calendar import as_utc
from company_lens.events.contracts import validate_version


class StaleWriter(RuntimeError):
    """A late or unlocked writer tried to replace a newer published result."""


class LeaseHeld(RuntimeError):
    """Another live owner already holds this ticker."""


class StoreError(RuntimeError):
    """The store could not complete a local read or write."""


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StoreError(f"unreadable checkpoint {path.name}") from exc
    if not isinstance(payload, dict):
        raise StoreError(f"checkpoint {path.name} is not an object")
    return payload


class FileEventStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _lock_path(self, dataset: str) -> Path:
        return self.root / "locks" / f"{dataset}.lock"

    def _state_path(self, dataset: str, key: str) -> Path:
        return self.root / "state" / dataset / f"{key}.json"

    def _lease_path(self, dataset: str, key: str) -> Path:
        return self.root / "leases" / dataset / f"{key}.json"

    def _version_path(self, dataset: str, version_id: str) -> Path:
        return self.root / "versions" / dataset / f"{version_id}.json"

    def _manifest_path(self, dataset: str) -> Path:
        return self.root / "manifests" / f"{dataset}.json"

    def _failure_path(self, dataset: str, key: str) -> Path:
        return self.root / "failures" / dataset / f"{key}.json"

    @contextmanager
    def _lock(self, dataset: str) -> Iterator[None]:
        path = self._lock_path(dataset)
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    def read_state(self, dataset: str, key: str) -> dict | None:
        return _read_json(self._state_path(dataset, key))

    def write_state(self, dataset: str, key: str, state: dict, expected_revision: int) -> dict:
        with self._lock(dataset):
            current = _read_json(self._state_path(dataset, key))
            actual = 0 if current is None else int(current.get("revision") or 0)
            if actual != expected_revision:
                raise StaleWriter("state revision mismatch")
            stored = {**state, "revision": actual + 1, "dataset": dataset, "key": key}
            _atomic_json(self._state_path(dataset, key), stored)
            return stored

    def read_manifest(self, dataset: str) -> dict:
        found = _read_json(self._manifest_path(dataset))
        if found is None:
            return {"dataset": dataset, "fence": 0, "schema_version": 1, "tickers": {}}
        found.setdefault("tickers", {})
        found.setdefault("fence", 0)
        return found

    def acquire_lease(
        self,
        dataset: str,
        key: str,
        owner: str,
        now: datetime,
        ttl_seconds: float,
    ) -> dict:
        now = as_utc(now)
        with self._lock(dataset):
            current = _read_json(self._lease_path(dataset, key))
            if current is not None:
                expires = datetime.fromisoformat(str(current["expires_at"]))
                if expires > now and current.get("owner") != owner:
                    raise LeaseHeld(f"{dataset}/{key} is leased")
            manifest = self.read_manifest(dataset)
            lease = {
                "expires_at": datetime.fromtimestamp(
                    now.timestamp() + ttl_seconds, tz=now.tzinfo
                ).isoformat(),
                "fence_seen": int(manifest.get("fence") or 0),
                "owner": owner,
                "token": os.urandom(16).hex(),
            }
            _atomic_json(self._lease_path(dataset, key), lease)
            return lease

    def release_lease(self, dataset: str, key: str, token: str) -> None:
        with self._lock(dataset):
            path = self._lease_path(dataset, key)
            current = _read_json(path)
            if current is None or current.get("token") != token:
                return
            path.unlink(missing_ok=True)

    def put_version(self, dataset: str, document: dict) -> dict:
        validate_version(document)
        version_id = str(document["version_id"])
        path = self._version_path(dataset, version_id)
        with self._lock(dataset):
            existing = _read_json(path)
            if existing is not None:
                if existing != document and existing.get("events") != document.get("events"):
                    raise StoreError("immutable version already has different events")
                return existing
            _atomic_json(path, document)
            return document

    def read_version(self, dataset: str, version_id: str) -> dict | None:
        return _read_json(self._version_path(dataset, version_id))

    def publish(
        self,
        dataset: str,
        *,
        ticker: str,
        version_id: str,
        expected_fence: int,
        lease_token: str,
        now: datetime,
    ) -> dict:
        now = as_utc(now)
        with self._lock(dataset):
            lease = _read_json(self._lease_path(dataset, ticker))
            if lease is None or lease.get("token") != lease_token:
                raise StaleWriter("lease token mismatch")
            expires = datetime.fromisoformat(str(lease["expires_at"]))
            if expires <= now:
                raise StaleWriter("lease expired")
            version = self.read_version(dataset, version_id)
            if version is None:
                raise StoreError("cannot publish a version that was not written")
            manifest = self.read_manifest(dataset)
            if int(manifest.get("fence") or 0) != expected_fence:
                raise StaleWriter("fence mismatch")
            tickers = dict(manifest.get("tickers") or {})
            tickers[ticker.upper()] = {
                "content_hash": version.get("content_hash") or version_id,
                "published_at": now.isoformat(),
                "version_id": version_id,
            }
            updated = {
                "dataset": dataset,
                "fence": expected_fence + 1,
                "schema_version": 1,
                "tickers": tickers,
                "updated_at": now.isoformat(),
            }
            _atomic_json(self._manifest_path(dataset), updated)
            return updated

    def current_version(self, dataset: str, ticker: str) -> dict | None:
        manifest = self.read_manifest(dataset)
        pointer = (manifest.get("tickers") or {}).get(ticker.upper())
        if not isinstance(pointer, dict):
            return None
        version_id = pointer.get("version_id")
        if not isinstance(version_id, str):
            return None
        return self.read_version(dataset, version_id)

    def write_failure(self, dataset: str, key: str, failure: dict) -> None:
        stored = {key_name: value for key_name, value in failure.items() if key_name != "secret"}
        _atomic_json(self._failure_path(dataset, key), stored)

    def read_failure(self, dataset: str, key: str) -> dict | None:
        return _read_json(self._failure_path(dataset, key))
