"""Checkpoint retention. Mock storage, not a live Blob call.

The store filled its gigabyte in four days: every commit wrote the whole
workspace, every version it had ever held included, to a new immutable object
and nothing deleted the one before. These tests hold both halves of the fix --
a checkpoint carries only what something still points at, and superseded
checkpoint objects are swept without ever touching the live one.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from tests.test_events_a1 import NOW, ScriptedSource, _row

from company_lens.events.blob_store import (
    BLOB_API,
    BlobRequestError,
    HttpBlobTransport,
    MemoryBlob,
    prune_checkpoints,
    pull_checkpoint,
    push_checkpoint,
    read_commit,
)
from company_lens.events.run import BlobDurable, run_refresh_entry

ROOT = Path(__file__).resolve().parents[1]
DAY = timedelta(days=1)


class Clock:
    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _source(rows: dict) -> ScriptedSource:
    source = ScriptedSource(rows)
    source.max_window_days = 30
    return source


def _run(root, blob, news, now):
    return run_refresh_entry(
        local_root=root,
        durable=BlobDurable(blob),
        datasets=("news",),
        tickers=["AAPL"],
        now=now,
        sources={"news": news},
        supported={"AAPL"},
        sleep=lambda _seconds: None,
        publish_transport=blob,
    )


def _generations(count: int, *, step: timedelta = DAY):
    """Commit ``count`` checkpoints, one per ``step``. Pathnames come back oldest first."""
    clock = Clock(NOW)
    blob = MemoryBlob(clock)
    etag = None
    paths = []
    for number in range(count):
        if number:
            clock.moment += step
        committed = push_checkpoint(
            blob,
            {"datasets": {}, "generation": number, "schema_version": 1},
            expected_etag=etag,
        )
        etag = committed["etag"]
        paths.append(committed["manifest"]["checkpoint_pathname"])
    return blob, clock, paths


def _checkpoints(blob: MemoryBlob) -> list[str]:
    return sorted(path for path in blob.objects if "/checkpoints/" in path)


# -- what a checkpoint carries -------------------------------------------------


def test_a_checkpoint_carries_only_the_versions_something_points_at(tmp_path):
    """The working copy may keep every version. The checkpoint must not."""
    blob = MemoryBlob()
    root = tmp_path / "runner"
    rows = [_row("AAPL", 1)]
    news = _source({"AAPL": rows})
    seen: list[str] = []
    for day in range(4):
        result = _run(root, blob, news, NOW + day * DAY)
        assert result.status == "stored"
        saved, _etag = pull_checkpoint(blob)
        body = saved["datasets"]["news"]
        pointer = body["manifest"]["tickers"]["AAPL"]["version_id"]
        assert list(body["versions"]) == [pointer]
        seen.append(pointer)
        rows.append(_row("AAPL", day + 2))
    assert len(set(seen)) == 4, "each day should have published a different version"
    # The same root was reused, so the superseded versions are still on disk.
    # That is the state every checkpoint used to be a copy of.
    assert len(list((root / "versions" / "news").glob("*.json"))) == 4


def test_a_runner_restored_from_a_slim_checkpoint_still_refreshes_and_publishes(tmp_path):
    blob = MemoryBlob()
    rows = [_row("AAPL", 1)]
    news = _source({"AAPL": rows})
    _run(tmp_path / "runner-a", blob, news, NOW)
    rows.append(_row("AAPL", 2))
    result = _run(tmp_path / "runner-b", blob, news, NOW + DAY)
    assert result.status == "stored"
    commit, _etag = read_commit(blob)
    feed_url = commit["tickers"]["AAPL"]["feed_url"]
    feed = json.loads(blob.read_url(feed_url)[0].decode())
    assert len(feed["events"]) == 2
    # Evidence for the version the first run published is still resolvable.
    assert len(commit["tickers"]["AAPL"]["versions"]) == 2


# -- the sweep -----------------------------------------------------------------


def test_prune_deletes_superseded_checkpoints_and_never_the_committed_one():
    blob, clock, paths = _generations(5)
    clock.moment += 2 * DAY
    report = prune_checkpoints(blob, now=clock(), apply=True)
    assert report["status"] == "pruned"
    assert [row["pathname"] for row in report["deleted"]] == paths[:4]
    assert _checkpoints(blob) == [paths[4]]
    payload, _etag = pull_checkpoint(blob)
    assert payload["generation"] == 4


def test_prune_is_a_dry_run_unless_told_to_apply():
    blob, clock, paths = _generations(5)
    clock.moment += 2 * DAY
    before = dict(blob.objects)
    report = prune_checkpoints(blob, now=clock())
    assert report["status"] == "dry_run"
    assert report["applied"] is False
    assert [row["pathname"] for row in report["deleted"]] == paths[:4]
    assert report["freed_bytes"] == sum(len(before[path]["body"]) for path in paths[:4])
    assert blob.objects == before


def test_prune_keeps_anything_uploaded_recently():
    """A candidate whose pointer has not moved yet, and the generation a reader may still hold."""
    blob, clock, paths = _generations(5, step=timedelta(hours=10))
    report = prune_checkpoints(blob, now=clock(), apply=True)
    kept = {row["pathname"]: row["reason"] for row in report["kept"]}
    assert kept == {paths[4]: "current", paths[3]: "recent", paths[2]: "recent"}
    assert _checkpoints(blob) == sorted(paths[2:])


def test_prune_keeps_an_object_whose_upload_time_cannot_be_read():
    blob, clock, paths = _generations(3)
    clock.moment += 2 * DAY
    blob.objects[paths[0]]["uploadedAt"] = "not a date"
    prune_checkpoints(blob, now=clock(), apply=True)
    assert _checkpoints(blob) == sorted([paths[0], paths[2]])


def test_prune_leaves_feeds_and_evidence_alone():
    blob, clock, paths = _generations(3)
    for pathname in (
        "lens-events/evidence/AAPL/v1/aaaaaaaaaaaaaaaaaaaa.json",
        "lens-events/public/versions/AAPL/v1/bbbbbbbbbbbbbbbbbbbb.json",
        "lens-events/monitor.json",
        "lens-events/checkpoints-other/cccccccccccccccccccc.json",
    ):
        blob.put(pathname, b"{}", if_match=None, overwrite=False)
    clock.moment += 30 * DAY
    prune_checkpoints(blob, now=clock(), apply=True)
    assert sorted(blob.objects) == sorted(
        [
            "lens-events/checkpoints-other/cccccccccccccccccccc.json",
            "lens-events/commit.json",
            "lens-events/evidence/AAPL/v1/aaaaaaaaaaaaaaaaaaaa.json",
            "lens-events/monitor.json",
            "lens-events/public/versions/AAPL/v1/bbbbbbbbbbbbbbbbbbbb.json",
            paths[2],
        ]
    )


def test_prune_deletes_nothing_without_a_commit_record():
    clock = Clock(NOW)
    blob = MemoryBlob(clock)
    blob.put("lens-events/checkpoints/orphan.json", b"{}", if_match=None, overwrite=False)
    clock.moment += 30 * DAY
    report = prune_checkpoints(blob, now=clock(), apply=True)
    assert report["status"] == "no_commit"
    assert report["deleted"] == []
    assert _checkpoints(blob) == ["lens-events/checkpoints/orphan.json"]


def test_prune_deletes_nothing_when_the_pointer_is_not_in_the_listing():
    blob, clock, paths = _generations(3)
    clock.moment += 2 * DAY
    del blob.objects[paths[2]]
    report = prune_checkpoints(blob, now=clock(), apply=True)
    assert report["status"] == "pointer_not_listed"
    assert report["deleted"] == []
    assert _checkpoints(blob) == sorted(paths[:2])


def test_prune_stands_down_when_a_commit_lands_during_the_sweep():
    blob, clock, _paths = _generations(3)
    clock.moment += 2 * DAY

    class Racing(MemoryBlob):
        def list_prefix(self, prefix):
            listing = super().list_prefix(prefix)
            _commit, etag = read_commit(self)
            newer = {"datasets": {}, "generation": 99, "schema_version": 1}
            push_checkpoint(self, newer, expected_etag=etag)
            return listing

    racing = Racing(clock)
    racing.objects = blob.objects
    racing._serial = blob._serial
    report = prune_checkpoints(racing, now=clock(), apply=True)
    assert report["status"] == "commit_moved"
    assert report["deleted"] == []
    assert len(_checkpoints(racing)) == 4


def test_a_blocked_store_cannot_be_pruned_by_pointer_but_can_by_upload_time():
    """Content reads return 403 on a paused store. Listing and delete do not need them."""
    blob, clock, paths = _generations(6)
    clock.moment += 10 * DAY

    class Paused(MemoryBlob):
        def read_url(self, url):
            raise BlobRequestError(403, "blob-url", "Your store is blocked")

    paused = Paused(clock)
    paused.objects = blob.objects
    with pytest.raises(BlobRequestError):
        prune_checkpoints(paused, now=clock(), apply=True)
    assert len(_checkpoints(paused)) == 6

    report = prune_checkpoints(paused, now=clock(), keep_newest=2, apply=True)
    assert report["status"] == "pruned"
    assert report["mode"] == "newest"
    assert _checkpoints(paused) == sorted(paths[4:])
    with pytest.raises(ValueError):
        prune_checkpoints(paused, now=clock(), keep_newest=0)


# -- the HTTP shape ------------------------------------------------------------


class _Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload) if payload is not None else ""
        self.headers = {}

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _Session:
    def __init__(self, pages):
        self.pages = list(pages)
        self.gets = []
        self.posts = []

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        return self.pages.pop(0)

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return _Response(200, {})


def test_list_prefix_follows_the_cursor_to_the_end():
    session = _Session(
        [
            _Response(200, {"blobs": [{"pathname": "a"}], "cursor": "next", "hasMore": True}),
            _Response(200, {"blobs": [{"pathname": "b"}], "hasMore": False}),
        ]
    )
    transport = HttpBlobTransport("token", session=session)
    listed = transport.list_prefix("lens-events/checkpoints/")
    assert [item["pathname"] for item in listed] == ["a", "b"]
    assert [call[1]["params"].get("cursor") for call in session.gets] == [None, "next"]
    assert all(call[0] == BLOB_API for call in session.gets)


def test_a_refused_listing_is_an_error_not_an_empty_store():
    session = _Session([_Response(403, {"error": {"code": "forbidden"}})])
    with pytest.raises(BlobRequestError) as caught:
        HttpBlobTransport("token", session=session).list_prefix("lens-events/checkpoints/")
    assert caught.value.status == 403
    assert caught.value.detail == "forbidden"


def test_delete_posts_urls_the_way_the_sdk_does_and_in_batches():
    session = _Session([])
    urls = [f"https://blob.test/{number}" for number in range(250)]
    HttpBlobTransport("token", session=session).delete(urls)
    assert [call[0] for call in session.posts] == [f"{BLOB_API}/delete"] * 3
    sent = [json.loads(call[1]["data"])["urls"] for call in session.posts]
    assert [len(batch) for batch in sent] == [100, 100, 50]
    assert [url for batch in sent for url in batch] == urls
    headers = session.posts[0][1]["headers"]
    assert headers["content-type"] == "application/json"
    assert headers["authorization"] == "Bearer token"


# -- the command ---------------------------------------------------------------


def _command(monkeypatch, transport, name):
    module = _load(name, ROOT / "scripts" / "prune_event_blobs.py")
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "vercel_blob_rw_test")
    monkeypatch.delenv("EVENTS_BLOB_PREFIX", raising=False)
    monkeypatch.setattr(module, "open_transport", lambda _token: transport)
    return module


def test_the_command_reports_and_deletes_nothing_by_default(monkeypatch, capsys):
    blob, clock, paths = _generations(4)
    module = _command(monkeypatch, blob, "prune_dry")
    code = module.main(["--now", (clock() + 2 * DAY).isoformat()])
    out = capsys.readouterr().out
    assert code == 0
    assert "prune=dry_run mode=pointer listed=4" in out
    assert "would_delete=3" in out
    assert "action=keep reason=current" in out and paths[3] in out
    assert len(_checkpoints(blob)) == 4

    code = module.main(["--apply", "--now", (clock() + 2 * DAY).isoformat()])
    out = capsys.readouterr().out
    assert code == 0
    assert "prune=pruned" in out and "deleted=3" in out
    assert _checkpoints(blob) == [paths[3]]


def test_the_command_names_a_blocked_store_and_exits_3(monkeypatch, capsys):
    blob, clock, _paths = _generations(3)

    class Paused(MemoryBlob):
        def read_url(self, url):
            raise BlobRequestError(403, "blob-url", "Your store is blocked")

    paused = Paused(clock)
    paused.objects = blob.objects
    module = _command(monkeypatch, paused, "prune_blocked")
    assert module.main(["--apply"]) == 3
    out = capsys.readouterr().out
    assert "prune=failed blob_status=403 path=blob-url detail=Your store is blocked" in out
    assert len(_checkpoints(paused)) == 3


def test_the_command_refuses_to_run_without_a_token(monkeypatch, capsys):
    module = _load("prune_no_token", ROOT / "scripts" / "prune_event_blobs.py")
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    assert module.main([]) == 2
    assert "config_error=blob_missing" in capsys.readouterr().out
