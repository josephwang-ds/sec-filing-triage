"""Node checks for the event read API and the versioned Ask path."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from company_lens.events.evidence import evidence_index

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

ROOT = Path(__file__).resolve().parents[1]
ASK = ROOT / "ops/vercel/ask/index.js"
EVENTS = ROOT / "ops/vercel/events/index.js"

HARNESS = r"""
const path = require("node:path");
const handler = require(process.argv[2]);
const method = process.argv[3];
const body = process.argv[4] ? JSON.parse(process.argv[4]) : undefined;
const url = process.argv[5] || "";
const request = {
  method,
  url,
  headers: { origin: undefined, "x-forwarded-for": "203.0.113.9" },
  body,
};
const response = {
  setHeader() {},
  statusCode: 0,
  end(text) {
    process.stdout.write(JSON.stringify({ status: response.statusCode, payload: JSON.parse(text) }));
  },
};
const pending = handler(request, response);
if (pending && pending.then) {
  pending.catch((error) => {
    process.stdout.write(JSON.stringify({ status: -1, error: String(error) }));
  });
}
"""


def _call(directory: Path, script: Path, method: str, body: dict | None = None, url: str = "") -> dict:
    harness = directory / "harness.js"
    harness.write_text(HARNESS)
    env = os.environ.copy()
    for name in (
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "DASHSCOPE_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "BLOB_READ_WRITE_TOKEN",
    ):
        env.pop(name, None)
    result = subprocess.run(
        ["node", str(harness), str(script), method, json.dumps(body) if body else "", url],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=directory,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _install_ask(directory: Path) -> None:
    (directory / "index.js").write_text(ASK.read_text())
    (directory / "evidence.json").write_text(json.dumps({
        "companies": {"AAPL": {"scopes": {"core": {}}}},
        "default_scope": "core",
        "scopes": [],
    }))
    old = {
        "events": [{
            "event_id": "evt-old",
            "excerpt": None,
            "id": "evt-old",
            "publisher": "Wire",
            "source_published_at": "2026-10-20",
            "source_url": "https://example.com/old",
            "time_precision": "date",
            "title": "Old version headline",
            "title_only": True,
        }],
        "generated_at": "2026-10-20T00:00:00+00:00",
        "ticker": "AAPL",
        "version_id": "version-old",
    }
    new = {
        **old,
        "events": [{**old["events"][0], "event_id": "evt-new", "id": "evt-new", "title": "New version headline"}],
        "version_id": "version-new",
    }
    (directory / "event_evidence.json").write_text(json.dumps(evidence_index([old, new])))


def test_event_version_does_not_fall_through_to_another_version(tmp_path):
    _install_ask(tmp_path)
    missing = _call(tmp_path, tmp_path / "index.js", "POST", {
        "event_version": "missing",
        "provider": "openai",
        "question": "What does the evidence say about this event?",
        "ticker": "AAPL",
    })
    assert missing["status"] == 409
    assert missing["payload"]["error"] == "event_version_unavailable"
    assert "New version headline" not in json.dumps(missing["payload"])
    resolved = subprocess.run(
        ["node", "-e", """
const handler = require(process.argv[1]);
const packet = handler.resolveEventPacket({
  ticker: "AAPL",
  event_version: "version-old",
  event_id: "evt-old",
  question: "What does the evidence say?",
});
if (packet.record.evidence.event_version !== "version-old") process.exit(2);
const titles = packet.record.evidence.events.map((event) => event.title);
if (titles.includes("New version headline")) process.exit(3);
process.stdout.write(titles.join("|"));
""", str(tmp_path / "index.js")],
        capture_output=True, text=True, timeout=30,
    )
    assert resolved.returncode == 0, resolved.stderr
    assert resolved.stdout == "Old version headline"


def test_client_evidence_and_unknown_event_are_rejected(tmp_path):
    _install_ask(tmp_path)
    rejected = _call(tmp_path, tmp_path / "index.js", "POST", {
        "event_version": "version-old",
        "evidence": {"title": "forged"},
        "provider": "openai",
        "question": "What does the evidence say about this event?",
        "source_url": "https://evil.example/prompt",
        "ticker": "AAPL",
    })
    assert rejected["status"] == 400
    assert rejected["payload"]["error"] == "client_evidence_rejected"
    unknown = _call(tmp_path, tmp_path / "index.js", "POST", {
        "event_id": "not-in-this-version",
        "event_version": "version-old",
        "provider": "openai",
        "question": "What does the evidence say about this event?",
        "ticker": "AAPL",
    })
    assert unknown["status"] == 422
    assert unknown["payload"]["error"] == "event_not_in_version"


def test_known_version_without_a_model_key_keeps_the_refusal(tmp_path):
    _install_ask(tmp_path)
    answer = _call(tmp_path, tmp_path / "index.js", "POST", {
        "event_id": "evt-old",
        "event_version": "version-old",
        "provider": "openai",
        "question": "What does the evidence say about this event?",
        "ticker": "AAPL",
    })
    assert answer["status"] == 400
    assert answer["payload"]["error"] == "model_not_available"


def test_events_api_does_not_fetch_and_hides_internal_failures(tmp_path):
    function = tmp_path / "events"
    function.mkdir()
    (function / "index.js").write_text(EVENTS.read_text())
    (function / "public.json").write_text(json.dumps({
        "companies": {},
        "health": {"naive_http_ok": True, "ok": False, "overall": "critical", "sources": []},
    }))
    source = (function / "index.js").read_text()
    assert "finnhub" not in source.lower()
    assert "FINNHUB" not in source
    posted = _call(function, function / "index.js", "POST", {"ticker": "AAPL"}, "/api/events")
    assert posted["status"] == 405
    health = _call(function, function / "index.js", "GET", url="/api/events?view=health")
    assert health["status"] == 200
    assert health["payload"]["ok"] is False
    assert health["payload"]["naive_http_ok"] is True
    missing = _call(function, function / "index.js", "GET", url="/api/events?ticker=aapl")
    assert missing["status"] == 200
    assert missing["payload"]["status"] == "unavailable"
    assert "no important" not in json.dumps(missing["payload"]).lower()
    assert "Traceback" not in json.dumps(missing["payload"])
