"""Regressions from the second review of the event refresh entry. Mock storage only."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta

from tests.test_events_a1 import NOW, _row
from tests.test_events_closure import ROOT, Clock, _run, _source

from company_lens.events.blob_store import (
    MemoryBlob,
    pull_checkpoint,
    push_checkpoint,
    read_pointer,
    read_published,
)
from company_lens.events.health import judge_checkpoint, request_monitor_rerun
from company_lens.events.policy import HIGH_FREQUENCY_TICKERS
from company_lens.events.refresh import FetchResult
from company_lens.events.run import BlobDurable


def test_an_older_refresh_cannot_replace_a_newer_published_page(tmp_path):
    blob = MemoryBlob()
    nested = {}

    class OlderSource:
        name = "older"
        max_window_days = 30

        def __init__(self):
            self.started = False

        def lookback_floor(self, now):
            del now
            return None

        def fetch(self, ticker, start, end):
            del ticker, start, end
            if not self.started:
                self.started = True
                fresh = _source({"AAPL": [_row("AAPL", 1, title="new headline")]})
                nested["result"] = _run(
                    tmp_path / "fresh",
                    blob,
                    {"news": fresh},
                    ["AAPL"],
                    NOW,
                    datasets=("news",),
                )
            return FetchResult(ok=True, items=[_row("AAPL", 1, title="old headline")])

    older = _run(
        tmp_path / "older",
        blob,
        {"news": OlderSource()},
        ["AAPL"],
        NOW,
        datasets=("news",),
    )
    assert nested["result"].status == "stored"
    assert older.status == "stale_writer"
    page = read_published(blob, "AAPL")
    pointer, _etag = read_pointer(blob)
    saved, _etag = pull_checkpoint(blob)
    fresh_version = nested["result"].reports[0].outcomes[0].version_id
    assert page["events"][0]["title"] == "new headline"
    assert "old headline" not in json.dumps(page)
    assert pointer["tickers"]["AAPL"]["version_id"] == fresh_version
    assert page["manifest_version"] == fresh_version
    assert saved["datasets"]["news"]["states"]["AAPL"]["version_id"] == fresh_version
    assert saved["datasets"]["news"]["versions"][fresh_version]["events"][0]["title"] == "new headline"


def test_news_only_refresh_keeps_sec_state_and_monitor_metadata(tmp_path):
    blob = MemoryBlob()
    news = _source({"AAPL": [_row("AAPL", 1)], "MSFT": [_row("MSFT", 1)]})
    sec = _source({"AAPL": [_row("AAPL", 2, title="filing")]})
    sec.fail["MSFT"] = [FetchResult(ok=False, error_class="upstream", retryable=False)]
    _run(tmp_path / "both", blob, {"news": news, "sec_index": sec}, ["AAPL", "MSFT"], NOW)
    saved, etag = pull_checkpoint(blob)
    saved["monitor"] = {"claim_token": "held", "cooldown_until": "2026-10-24T00:00:00+00:00"}
    push_checkpoint(blob, saved, expected_etag=etag)
    coverage = saved["datasets"]["sec_index"]["states"]["AAPL"]["coverage_through"]
    version_id = saved["datasets"]["sec_index"]["states"]["AAPL"]["version_id"]
    news.calls.clear()
    later = _run(
        tmp_path / "news-only",
        blob,
        {"news": news},
        ["AAPL"],
        NOW + timedelta(minutes=1),
        datasets=("news",),
    )
    assert news.calls == []
    assert any(item["reason"] == "not_due" for item in later.skipped)
    current, _etag = pull_checkpoint(blob)
    sec_index = current["datasets"]["sec_index"]
    assert sec_index["states"]["AAPL"]["coverage_through"] == coverage
    assert sec_index["states"]["AAPL"]["version_id"] == version_id
    assert version_id in sec_index["versions"]
    assert sec_index["states"]["MSFT"]["last_error_class"] == "upstream"
    assert sec_index["failures"]["MSFT"]["error_class"] == "upstream"
    assert current["monitor"]["cooldown_until"] == "2026-10-24T00:00:00+00:00"
    assert current["monitor"]["claim_token"] == "held"


def test_retry_after_is_waited_in_full_when_the_budget_allows_it(tmp_path):
    clock = Clock(NOW)
    sleeps: list[float] = []
    source = _source({"AAPL": [_row("AAPL", 1)]})
    source.fail["AAPL"] = [
        FetchResult(ok=False, error_class="rate_limit", retryable=True, retry_after=300)
    ]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.advance(seconds)

    result = _run(
        tmp_path / "full-wait",
        MemoryBlob(),
        {"news": source},
        ["AAPL"],
        NOW,
        datasets=("news",),
        clock=clock,
        sleep=sleep,
        time_budget_seconds=600,
    )
    assert sleeps and min(sleeps) >= 300
    assert result.status == "stored"
    assert result.reports[0].outcomes[0].error_class is None


def test_a_short_budget_persists_retry_not_before_for_the_next_runner(tmp_path):
    blob = MemoryBlob()
    clock = Clock(NOW)
    sleeps: list[float] = []
    source = _source({"AAPL": [_row("AAPL", 1)]})
    source.fail["AAPL"] = [
        FetchResult(ok=False, error_class="rate_limit", retryable=True, retry_after=300)
    ]
    first = _run(
        tmp_path / "short",
        blob,
        {"news": source},
        ["AAPL"],
        NOW,
        datasets=("news",),
        clock=clock,
        sleep=sleeps.append,
        time_budget_seconds=100,
    )
    assert sleeps == []
    assert first.reports[0].outcomes[0].error_class == "retry_wait"
    saved, _etag = pull_checkpoint(blob)
    not_before = datetime.fromisoformat(saved["datasets"]["news"]["states"]["AAPL"]["retry_not_before"])
    assert not_before - NOW >= timedelta(seconds=300)
    source.calls.clear()
    early = _run(
        tmp_path / "early",
        blob,
        {"news": source},
        ["AAPL"],
        NOW + timedelta(seconds=120),
        datasets=("news",),
    )
    assert source.calls == []
    assert any(item["reason"] == "not_due" for item in early.skipped)
    source.calls.clear()
    _run(
        tmp_path / "due",
        blob,
        {"news": source},
        ["AAPL"],
        not_before + timedelta(seconds=1),
        datasets=("news",),
    )
    assert source.calls


def _checked(moment: datetime, **extra) -> dict:
    state = {
        "key": "AAPL",
        "last_successful_check_at": moment.isoformat(),
        "status": "current",
        "cadence_seconds": 1800,
    }
    state.update(extra)
    return state


def _checkpoint(news: dict, sec: dict | None = None, ticker: str = "AAPL") -> dict:
    return {
        "schema_version": 1,
        "datasets": {
            "news": {"states": {ticker: news}},
            "sec_index": {"states": {ticker: dict(sec if sec is not None else news)}},
        },
    }


def _view(report: dict) -> dict:
    return {
        "ok": report["ok"],
        "overall": report["overall"],
        "sources": {
            (source["dataset"], source["key"]): {
                "level": source["level"],
                "missed_windows": source["missed_windows"],
            }
            for source in report["sources"]
        },
    }


def test_public_health_matches_the_python_monitor_judgment(tmp_path):
    recent = NOW
    soon = NOW + timedelta(minutes=10)
    weekend_last = datetime.fromisoformat("2026-10-24T16:00:00+00:00")
    weekend_now = datetime.fromisoformat("2026-10-25T03:00:00+00:00")
    holiday_last = datetime.fromisoformat("2026-11-26T17:00:00+00:00")
    holiday_now = datetime.fromisoformat("2026-11-26T23:00:00+00:00")
    active_now = datetime.fromisoformat("2026-10-23T19:40:00+00:00")
    quota_last = datetime.fromisoformat("2026-10-23T14:00:00+00:00")
    quota_now = datetime.fromisoformat("2026-10-23T19:00:00+00:00")
    healthy = _checked(recent)
    cases = [
        {
            "name": "weekend_policy",
            "now": weekend_now.isoformat(),
            "expected": ["AAPL"],
            "checkpoint": _checkpoint(_checked(weekend_last), _checked(weekend_last)),
        },
        {
            "name": "holiday_policy",
            "now": holiday_now.isoformat(),
            "expected": ["AAPL"],
            "checkpoint": _checkpoint(_checked(holiday_last), _checked(holiday_last)),
        },
        {
            "name": "active_window",
            "now": active_now.isoformat(),
            "expected": ["AAPL"],
            "checkpoint": _checkpoint(_checked(recent), _checked(recent)),
        },
        {
            "name": "status_stale",
            "now": soon.isoformat(),
            "expected": ["AAPL"],
            "checkpoint": _checkpoint(_checked(recent, status="stale"), healthy),
        },
        {
            "name": "status_partial",
            "now": soon.isoformat(),
            "expected": ["AAPL"],
            "checkpoint": _checkpoint(_checked(recent, status="partial"), healthy),
        },
        {
            "name": "coverage_gaps",
            "now": soon.isoformat(),
            "expected": ["AAPL"],
            "checkpoint": _checkpoint(
                _checked(recent, coverage_gaps=[{"reason": "provider_lookback"}]),
                healthy,
            ),
        },
        {
            "name": "pending",
            "now": soon.isoformat(),
            "expected": ["AAPL"],
            "checkpoint": _checkpoint(_checked(recent, pending=True), healthy),
        },
        {
            "name": "last_error_class",
            "now": soon.isoformat(),
            "expected": ["AAPL"],
            "checkpoint": _checkpoint(_checked(recent, last_error_class="upstream"), healthy),
        },
        {
            "name": "missing_expected",
            "now": soon.isoformat(),
            "expected": ["AAPL", "JPM"],
            "checkpoint": _checkpoint(healthy, healthy),
        },
        {
            "name": "quota_degraded",
            "now": quota_now.isoformat(),
            "expected": ["AAPL"],
            "checkpoint": _checkpoint(
                _checked(quota_last, quota_degraded=True),
                _checked(quota_last),
            ),
        },
        {
            "name": "default_expected",
            "now": soon.isoformat(),
            "expected": list(HIGH_FREQUENCY_TICKERS),
            "use_default": True,
            "checkpoint": _checkpoint(healthy, healthy),
        },
    ]
    python_views = {
        item["name"]: _view(
            judge_checkpoint(
                item["checkpoint"],
                now=datetime.fromisoformat(item["now"]),
                expected=set(item["expected"]),
            )
        )
        for item in cases
    }
    weekend = python_views["weekend_policy"]
    assert weekend["ok"] is True
    assert weekend["sources"][("news", "AAPL")] == {"level": "current", "missed_windows": 2}
    assert weekend["sources"][("sec_index", "AAPL")]["missed_windows"] == 1
    holiday = python_views["holiday_policy"]
    assert holiday["overall"] == "attention"
    assert holiday["sources"][("news", "AAPL")] == {"level": "degraded", "missed_windows": 3}
    assert holiday["sources"][("sec_index", "AAPL")]["missed_windows"] == 1
    assert python_views["active_window"]["sources"][("news", "AAPL")]["missed_windows"] == 3
    assert python_views["active_window"]["sources"][("news", "AAPL")]["level"] == "degraded"
    assert python_views["status_stale"]["ok"] is False
    assert python_views["status_stale"]["sources"][("news", "AAPL")]["level"] == "stale"
    assert python_views["status_partial"]["sources"][("news", "AAPL")]["level"] == "partial"
    assert python_views["coverage_gaps"]["sources"][("news", "AAPL")]["level"] == "partial"
    assert python_views["pending"]["sources"][("news", "AAPL")]["level"] == "partial"
    assert python_views["last_error_class"]["sources"][("news", "AAPL")]["level"] == "stale"
    assert python_views["missing_expected"]["ok"] is False
    assert python_views["missing_expected"]["sources"][("news", "JPM")]["level"] == "unavailable"
    assert python_views["missing_expected"]["sources"][("sec_index", "JPM")]["level"] == "unavailable"
    assert python_views["quota_degraded"]["sources"][("news", "AAPL")] == {
        "level": "current",
        "missed_windows": 0,
    }
    assert python_views["default_expected"]["ok"] is False
    assert python_views["default_expected"]["sources"][("news", "WMT")]["level"] == "unavailable"
    source = (ROOT / "ops/vercel/events/index.js").read_text()
    assert "cadence_seconds" not in source
    payload = tmp_path / "cases.json"
    payload.write_text(json.dumps(cases), encoding="utf-8")
    script = tmp_path / "compare.js"
    script.write_text(
        "const fs = require('node:fs');\n"
        "const handler = require(process.argv[2]);\n"
        "const cases = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));\n"
        "const summarized = (health) => ({\n"
        "  ok: health.ok,\n"
        "  overall: health.overall,\n"
        "  sources: health.sources.map((source) => ({\n"
        "    dataset: source.dataset,\n"
        "    key: source.key,\n"
        "    level: source.level,\n"
        "    missed_windows: source.missed_windows,\n"
        "  })),\n"
        "});\n"
        "const out = cases.map((item) => {\n"
        "  const health = item.use_default\n"
        "    ? handler.healthFromCheckpoint(item.checkpoint, Date.parse(item.now))\n"
        "    : handler.healthFromCheckpoint(item.checkpoint, Date.parse(item.now), item.expected);\n"
        "  return { name: item.name, health: summarized(health) };\n"
        "});\n"
        "const stale = cases.find((item) => item.name === 'status_stale');\n"
        "Date.now = () => Date.parse(stale.now);\n"
        "global.fetch = async (url) => {\n"
        "  const text = String(url);\n"
        "  if (text.includes('vercel.com/api/blob')) {\n"
        "    return { ok: true, status: 200, json: async () => ({ blobs: [{ pathname: 'lens-events/checkpoint.json', url: 'https://blob.test/checkpoint' }] }) };\n"
        "  }\n"
        "  if (text === 'https://blob.test/checkpoint') {\n"
        "    return { ok: true, status: 200, json: async () => stale.checkpoint };\n"
        "  }\n"
        "  return { ok: false, status: 404, json: async () => ({}) };\n"
        "};\n"
        "const response = { statusCode: 0, setHeader() {}, end(text) { this.body = text; } };\n"
        "handler({ method: 'GET', url: '/api/events?view=health', headers: {}, query: { view: 'health' } }, response)\n"
        "  .then(() => {\n"
        "    process.stdout.write(JSON.stringify({ cases: out, handler: summarized(JSON.parse(response.body)) }));\n"
        "  }).catch((error) => { console.error(error); process.exit(1); });\n"
    )
    env = os.environ.copy()
    env["BLOB_READ_WRITE_TOKEN"] = "test-token"
    result = subprocess.run(
        ["node", str(script), str(ROOT / "ops/vercel/events/index.js"), str(payload)],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    rendered = json.loads(result.stdout)
    for item in rendered["cases"]:
        node_view = _view(item["health"])
        assert node_view == python_views[item["name"]], item["name"]
    public_now = datetime.fromisoformat(soon.isoformat())
    public_python = _view(
        judge_checkpoint(
            cases[3]["checkpoint"],
            now=public_now,
            expected=set(HIGH_FREQUENCY_TICKERS),
        )
    )
    assert _view(rendered["handler"]) == public_python
    assert public_python["sources"][("news", "AAPL")]["level"] == "stale"
    assert public_python["ok"] is False


def test_two_monitors_claim_before_post_and_only_one_requests_a_rerun():
    blob = MemoryBlob()
    payload = {
        "schema_version": 1,
        "datasets": {
            "news": {
                "states": {
                    "AAPL": {
                        "key": "AAPL",
                        "last_successful_check_at": (NOW - timedelta(hours=6)).isoformat(),
                        "status": "current",
                    }
                }
            }
        },
    }
    push_checkpoint(blob, payload, expected_etag=None)
    durable = BlobDurable(blob)
    pulled = durable.pull()
    calls: list[str] = []

    def executor():
        current, _etag = pull_checkpoint(blob)
        assert current["monitor"]["claim_until"]
        assert "cooldown_until" not in current["monitor"]
        calls.append("post")
        return type("Response", (), {"status_code": 202})()

    decision = {"action": "rerun_eligible", "rerun_requested": False}
    first = request_monitor_rerun(durable, pulled, decision, executor=executor, now=NOW)
    second = request_monitor_rerun(durable, pulled, decision, executor=executor, now=NOW)
    assert first["rerun_requested"] is True
    assert first["cooldown_persisted"] is True
    assert second["rerun_requested"] is False
    assert second["reason"] == "conflict"
    assert calls == ["post"]
    third = request_monitor_rerun(
        durable,
        durable.pull(),
        decision,
        executor=executor,
        now=NOW + timedelta(minutes=5),
    )
    assert third["rerun_requested"] is False
    assert third["reason"] == "cooldown"
    assert calls == ["post"]
    saved, _etag = pull_checkpoint(blob)
    assert saved["monitor"]["cooldown_until"]
    assert saved["monitor"]["claim_token"]
