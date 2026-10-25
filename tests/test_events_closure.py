"""Entry, pointer, evidence, budget, and monitor closures. Mock storage, not a live Blob call."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tests.test_events_a1 import NOW, ScriptedSource, _row

from company_lens.events.blob_store import (
    BlobRequestError,
    MemoryBlob,
    publish_releases,
    pull_checkpoint,
    read_published,
)
from company_lens.events.evidence import build_event_evidence
from company_lens.events.health import execute_rerun, monitor_action
from company_lens.events.public import public_feed
from company_lens.events.refresh import FetchResult
from company_lens.events.run import BlobDurable, DurablePull, run_refresh_entry
from company_lens.events.store import FileEventStore

ROOT = Path(__file__).resolve().parents[1]


class Clock:
    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment

    def advance(self, seconds: float) -> None:
        self.moment += timedelta(seconds=seconds)


def _source(rows: dict) -> ScriptedSource:
    source = ScriptedSource(rows)
    source.max_window_days = 30
    return source


def _run(root, blob, sources, tickers, now, **kwargs):
    return run_refresh_entry(
        local_root=root,
        durable=BlobDurable(blob),
        datasets=kwargs.pop("datasets", ("news", "sec_index")),
        tickers=list(tickers),
        now=now,
        sources=sources,
        supported=set(tickers),
        sleep=kwargs.pop("sleep", lambda _seconds: None),
        clock=kwargs.pop("clock", None),
        publish_transport=blob,
        **kwargs,
    )


def test_a_second_runner_restores_news_and_sec_watermarks(tmp_path):
    blob = MemoryBlob()
    news = _source({"AAPL": [_row("AAPL", 1)]})
    sec = _source({"AAPL": [_row("AAPL", 1, title="SEC index row")]})
    first = tmp_path / "runner-a"
    _run(first, blob, {"news": news, "sec_index": sec}, ["AAPL"], NOW)
    saved, _etag = pull_checkpoint(blob)
    assert saved["datasets"]["news"]["states"]["AAPL"]["coverage_through"] == NOW.isoformat()
    assert saved["datasets"]["sec_index"]["states"]["AAPL"]["coverage_through"] == NOW.isoformat()
    later = NOW + timedelta(days=2)
    news.calls.clear()
    sec.calls.clear()
    _run(tmp_path / "runner-b", blob, {"news": news, "sec_index": sec}, ["AAPL"], later)
    earliest = min(start for _ticker, start, _end in news.calls)
    assert earliest >= NOW - timedelta(hours=25)
    assert earliest > later - timedelta(days=6)
    assert FileEventStore(tmp_path / "runner-b").read_state("sec_index", "AAPL")["coverage_through"]


def test_a_checkpoint_read_error_does_not_start_from_empty(tmp_path):
    blob = MemoryBlob()
    blob.put(
        "lens-events/checkpoint.json",
        b'{"schema_version":1,"datasets":{}}',
        if_match=None,
        overwrite=False,
    )

    class Boom(BlobDurable):
        def pull(self):
            return DurablePull("read_error")

        def push(self, payload, expected_etag):
            raise AssertionError("read failure must not publish a new checkpoint")

    news = _source({"AAPL": [_row("AAPL", 1)]})
    result = run_refresh_entry(
        local_root=tmp_path / "runner",
        durable=Boom(blob),
        datasets=("news",),
        tickers=["AAPL"],
        now=NOW,
        sources={"news": news},
        supported={"AAPL"},
        sleep=lambda _seconds: None,
        publish_transport=blob,
    )
    assert result.status == "read_error"
    assert news.calls == []
    assert blob.objects["lens-events/checkpoint.json"]["body"] == b'{"schema_version":1,"datasets":{}}'


def test_stale_publish_keeps_the_pointer_and_the_reader_on_new(tmp_path):
    del tmp_path
    blob = MemoryBlob()
    new_feed = {"events": [{"title": "new headline"}], "manifest_version": "new", "ticker": "AAPL"}
    new_evidence = {"evidence": {"event_version": "new", "events": [{"title": "new headline"}]}}
    first = publish_releases(
        blob,
        {"AAPL": {"evidence": new_evidence, "feed": new_feed, "version_id": "new"}},
        observed_etag=None,
    )
    old_feed = {"events": [{"title": "old headline"}], "manifest_version": "old", "ticker": "AAPL"}
    try:
        publish_releases(
            blob,
            {"AAPL": {"evidence": {"evidence": {"event_version": "old"}}, "feed": old_feed, "version_id": "old"}},
            observed_etag="stale-etag",
        )
    except BlobRequestError as exc:
        assert exc.status == 412
    else:
        raise AssertionError("stale etag was accepted")
    blob.put(
        "lens-events/public/AAPL.json",
        json.dumps(old_feed).encode(),
        if_match=None,
        overwrite=True,
    )
    served = read_published(blob, "AAPL")
    assert served["manifest_version"] == "new"
    assert served["events"][0]["title"] == "new headline"
    assert first["manifest"]["tickers"]["AAPL"]["version_id"] == "new"
    jpm = {"events": [], "manifest_version": "jpm-1", "ticker": "JPM"}
    publish_releases(
        blob,
        {"JPM": {"evidence": {"evidence": {"event_version": "jpm-1"}}, "feed": jpm, "version_id": "jpm-1"}},
        observed_etag=pull_etag(blob),
    )
    assert read_published(blob, "AAPL")["manifest_version"] == "new"
    assert read_published(blob, "JPM")["manifest_version"] == "jpm-1"


def pull_etag(blob: MemoryBlob) -> str:
    _manifest, etag = __import__(
        "company_lens.events.blob_store", fromlist=["read_pointer"]
    ).read_pointer(blob)
    assert etag
    return etag


def test_ask_reads_a_newly_published_version_without_rebuilding_the_function(tmp_path):
    blob = MemoryBlob()
    old = _bundle("version-old", "Old version headline")
    new = _bundle("version-new", "New version headline")
    publish_releases(blob, {"AAPL": old}, observed_etag=None)
    publish_releases(blob, {"AAPL": new}, observed_etag=pull_etag(blob))
    blob.put(
        "lens-events/evidence/AAPL/version-shadow.json",
        json.dumps({"evidence": {"event_version": "version-shadow", "events": [{"title": "shadow headline"}]}}).encode(),
        if_match=None,
        overwrite=False,
    )
    dump = {
        path: {"body": item["body"].decode(), "pathname": path, "url": item["url"]}
        for path, item in blob.objects.items()
    }
    store_path = tmp_path / "blobs.json"
    store_path.write_text(json.dumps(dump), encoding="utf-8")
    function = tmp_path / "ask"
    function.mkdir()
    (function / "index.js").write_text((ROOT / "ops/vercel/ask/index.js").read_text())
    (function / "evidence.json").write_text(json.dumps({"companies": {}, "default_scope": "core", "scopes": []}))
    (function / "event_evidence.json").write_text(json.dumps({"companies": {}}))
    script = function / "chain.js"
    script.write_text(
        "const fs = require('node:fs');\n"
        "const store = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));\n"
        "global.fetch = async (url) => {\n"
        "  const text = String(url);\n"
        "  if (text.includes('vercel.com/api/blob')) {\n"
        "    const prefix = new URL(text).searchParams.get('prefix') || '';\n"
        "    const blobs = Object.values(store).filter((item) => item.pathname.startsWith(prefix));\n"
        "    return { ok: true, status: 200, json: async () => ({ blobs }) };\n"
        "  }\n"
        "  const found = Object.values(store).find((item) => item.url === text);\n"
        "  if (!found) return { ok: false, status: 404, json: async () => ({}) };\n"
        "  return { ok: true, status: 200, json: async () => JSON.parse(found.body) };\n"
        "};\n"
        "const handler = require('./index.js');\n"
        "(async () => {\n"
        "  const fresh = await handler.resolveEventPacket({\n"
        "    ticker: 'AAPL', event_version: 'version-new', event_id: 'evt-new',\n"
        "    question: 'What does the evidence say about this event?'});\n"
        "  const prior = await handler.resolveEventPacket({\n"
        "    ticker: 'AAPL', event_version: 'version-old', event_id: 'evt-old',\n"
        "    question: 'What does the evidence say about this event?'});\n"
        "  if (fresh.record.evidence.event_version !== 'version-new') process.exit(2);\n"
        "  if (fresh.record.evidence.events.some((event) => event.title === 'Old version headline')) process.exit(3);\n"
        "  if (prior.record.evidence.events.some((event) => event.title === 'New version headline')) process.exit(4);\n"
        "  const shadow = await handler.resolveEventPacket({\n"
        "    ticker: 'AAPL', event_version: 'version-shadow', event_id: 'evt-shadow',\n"
        "    question: 'What does the evidence say about this event?'});\n"
        "  if (!shadow.payload || shadow.payload.error !== 'event_version_unavailable') process.exit(5);\n"
        "  process.stdout.write(fresh.record.evidence.events[0].title);\n"
        "})().catch((error) => { console.error(error); process.exit(1); });\n"
    )
    env = os.environ.copy()
    env["BLOB_READ_WRITE_TOKEN"] = "test-token"
    for name in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "DASHSCOPE_API_KEY"):
        env.pop(name, None)
    result = subprocess.run(
        ["node", str(script), str(store_path)],
        cwd=function,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "New version headline"
    assert "test-token" not in result.stdout


def _bundle(version: str, title: str) -> dict:
    document = {
        "events": [{
            "excerpt": None,
            "id": "evt-" + version.split("-")[-1],
            "publisher": "Wire",
            "source_published_at": "2026-10-20",
            "source_url": "https://example.com/" + version,
            "time_precision": "date",
            "title": title,
            "title_only": True,
        }],
        "generated_at": NOW.isoformat(),
        "ticker": "AAPL",
        "version_id": version,
    }
    evidence = build_event_evidence(document)
    feed = public_feed(
        ticker="AAPL",
        tier="high_frequency",
        document={**document, "evidence_ready": True},
        state={"last_successful_check_at": NOW.isoformat(), "status": "current"},
        storage="blob",
    )
    return {"evidence": evidence, "feed": feed, "version_id": version}


def test_due_policy_budget_retry_and_timeout_survive_a_new_runner(tmp_path):
    blob = MemoryBlob()
    news = _source({"AAPL": [_row("AAPL", 1)], "JPM": [_row("JPM", 1)]})
    sec = _source({"AAPL": [_row("AAPL", 2, title="filing")]})
    _run(
        tmp_path / "one",
        blob,
        {"news": news},
        ["AAPL"],
        NOW,
        datasets=("news",),
        daily_request_budget=1,
    )
    assert news.calls
    news.calls.clear()
    skipped = _run(
        tmp_path / "early",
        blob,
        {"news": news, "sec_index": sec},
        ["AAPL"],
        NOW + timedelta(minutes=1),
    )
    assert news.calls == []
    assert any(item["reason"] == "not_due" and item["dataset"] == "news" for item in skipped.skipped)
    assert sec.calls
    sec.calls.clear()
    blocked = _run(
        tmp_path / "budget",
        blob,
        {"news": news},
        ["AAPL"],
        NOW + timedelta(minutes=31),
        datasets=("news",),
        daily_request_budget=1,
    )
    assert news.calls == []
    assert blocked.reports[0].outcomes[0].error_class == "budget"
    saved, _etag = pull_checkpoint(blob)
    assert saved["budget"]["used"]["news"] == 1
    assert saved["budget"]["day"] == NOW.date().isoformat()

    clock = Clock(datetime.now(UTC))
    waiting = _source({"NVDA": [_row("NVDA", 1)]})
    waiting.fail["NVDA"] = [FetchResult(ok=False, error_class="rate_limit", retryable=True, retry_after=30)]
    sleeps: list[float] = []
    report = _run(
        tmp_path / "wait",
        MemoryBlob(),
        {"news": waiting},
        ["NVDA"],
        NOW,
        datasets=("news",),
        clock=clock,
        sleep=sleeps.append,
        time_budget_seconds=10,
    )
    assert sleeps == []
    assert report.reports[0].outcomes[0].error_class == "retry_wait"
    assert FileEventStore(tmp_path / "wait").read_state("news", "NVDA").get("coverage_through") is None


def test_events_api_reads_the_pointer_not_a_mutable_ticker_file(tmp_path):
    blob = MemoryBlob()
    publish_releases(
        blob,
        {"AAPL": _bundle("version-new", "New version headline")},
        observed_etag=None,
    )
    blob.put(
        "lens-events/public/AAPL.json",
        json.dumps({"manifest_version": "old", "events": [{"title": "old headline"}], "ticker": "AAPL"}).encode(),
        if_match=None,
        overwrite=True,
    )
    dump = {
        path: {"body": item["body"].decode(), "pathname": path, "url": item["url"]}
        for path, item in blob.objects.items()
    }
    assert read_published(blob, "AAPL")["events"][0]["title"] == "New version headline"
    function = tmp_path / "events"
    function.mkdir()
    (function / "index.js").write_text((ROOT / "ops/vercel/events/index.js").read_text())
    (function / "public.json").write_text(json.dumps({"companies": {}, "health": None}))
    (function / "blobs.json").write_text(json.dumps(dump), encoding="utf-8")
    script = function / "read.js"
    script.write_text(
        "const fs = require('node:fs');\n"
        "const store = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));\n"
        "global.fetch = async (url) => {\n"
        "  const text = String(url);\n"
        "  if (text.includes('vercel.com/api/blob')) {\n"
        "    const prefix = new URL(text).searchParams.get('prefix') || '';\n"
        "    const blobs = Object.values(store).filter((item) => item.pathname.startsWith(prefix));\n"
        "    return { ok: true, status: 200, json: async () => ({ blobs }) };\n"
        "  }\n"
        "  const found = Object.values(store).find((item) => item.url === text);\n"
        "  if (!found) return { ok: false, status: 404, json: async () => ({}) };\n"
        "  return { ok: true, status: 200, json: async () => JSON.parse(found.body) };\n"
        "};\n"
        "const handler = require('./index.js');\n"
        "const response = { statusCode: 0, setHeader() {}, end(text) { this.body = text; } };\n"
        "handler({ method: 'GET', url: '/api/events?ticker=AAPL', headers: {}, query: { ticker: 'AAPL' } }, response)\n"
        "  .then(() => {\n"
        "    const payload = JSON.parse(response.body);\n"
        "    if (payload.events[0].title !== 'New version headline') process.exit(2);\n"
        "    if (JSON.stringify(payload).includes('old headline')) process.exit(3);\n"
        "  }).catch((error) => { console.error(error); process.exit(1); });\n"
    )
    env = os.environ.copy()
    env["BLOB_READ_WRITE_TOKEN"] = "test-token"
    result = subprocess.run(
        ["node", str(script), str(function / "blobs.json")],
        cwd=function,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    assert result.returncode == 0, result.stderr


def test_a_later_window_stops_when_the_deadline_passes(tmp_path):
    clock = Clock(datetime(2026, 10, 23, 18, tzinfo=UTC))
    source = _source({"AAPL": [_row("AAPL", 1)]})
    source.max_window_days = 1

    def fetch(ticker, start, end):
        del ticker, start, end
        clock.advance(30)
        return FetchResult(ok=True, items=[_row("AAPL", 1)])

    source.fetch = fetch
    result = _run(
        tmp_path / "stop",
        MemoryBlob(),
        {"news": source},
        ["AAPL"],
        NOW,
        datasets=("news",),
        clock=clock,
        time_budget_seconds=10,
    )
    assert result.reports[0].outcomes[0].error_class == "time_budget"
    assert result.reports[0].outcomes[0].pending is True
    state = FileEventStore(tmp_path / "stop").read_state("news", "AAPL")
    assert state.get("coverage_through") is None


def test_monitor_does_not_treat_empty_as_healthy_and_calls_the_executor_once():
    quiet = monitor_action({"ok": False, "overall": "critical"}, rerun_configured=False)
    assert quiet["rerun_requested"] is False
    assert quiet["independent_wake"] == "not_configured"
    calls = {"n": 0, "auth": False}

    def executor():
        calls["n"] += 1
        calls["auth"] = True
        return type("Response", (), {"status_code": 202})()

    decision = monitor_action({"ok": False, "overall": "critical"}, rerun_configured=True)
    first = execute_rerun(decision, executor=executor, now=NOW, cooldown_until=None)
    assert first["rerun_requested"] is True
    assert first["executor_status"] == 202
    assert calls["n"] == 1
    second = execute_rerun(
        decision,
        executor=executor,
        now=NOW + timedelta(minutes=5),
        cooldown_until=first["cooldown_until"],
    )
    assert second["rerun_requested"] is False
    assert second["reason"] == "cooldown"
    assert calls["n"] == 1
    workflow = (ROOT / ".github/workflows/events-monitor.yml").read_text()
    refresh = (ROOT / ".github/workflows/events-refresh.yml").read_text()
    assert "allow-empty" not in workflow
    assert 'cron: "4,19,34,49 * * * *"' in workflow
    assert 'cron: "7,37 * * * *"' in refresh
    assert "independent wake" in workflow
