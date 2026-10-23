"""Clean-directory drill entry. No live Finnhub, SEC, or Blob calls."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from datetime import timedelta
from pathlib import Path

from tests.test_events_a1 import NOW

from company_lens.events.blob_store import MemoryBlob, commit_path, pull_checkpoint
from company_lens.events.health import judge_checkpoint
from company_lens.events.refresh import FetchResult
from company_lens.events.run import BlobDurable

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _adapters(seen: dict):
    class News:
        name = "finnhub"
        max_window_days = 30

        def __init__(self, api_key: str) -> None:
            seen["constructed"].append("news")
            assert api_key == "drill-test"

        def lookback_floor(self, now):
            del now
            return None

        def fetch(self, ticker, start, end):
            del start, end
            seen["calls"].append(("news", ticker))
            return FetchResult(ok=True, items=[])

    class Sec:
        name = "sec"
        max_window_days = 90

        def __init__(self, user_agent: str, *, ciks: dict[str, int]) -> None:
            del user_agent
            seen["constructed"].append("sec_index")
            seen["ciks"] = dict(ciks)

        def lookback_floor(self, now):
            del now
            return None

        def fetch(self, ticker, start, end):
            del start, end
            seen["calls"].append(("sec_index", ticker))
            return FetchResult(ok=True, items=[])

    return News, Sec


def _bind(monkeypatch, module, seen, blob: MemoryBlob | None = None):
    news, sec = _adapters(seen)
    monkeypatch.setattr(module, "FinnhubEventSource", news)
    monkeypatch.setattr(module, "EdgarRecentIndex", sec)
    monkeypatch.setenv("FINNHUB_API_KEY", "drill-test")
    monkeypatch.setenv("EDGAR_USER_AGENT", "Events Drill drill@example.com")
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    if blob is not None:
        def open_durable(_flags, *, drill=False):
            del drill
            return BlobDurable(blob), blob

        monkeypatch.setattr(module, "open_durable", open_durable)


def test_a_missing_or_empty_list_fails_before_any_fetch(tmp_path, monkeypatch, capsys):
    module = _load("refresh_events_missing", ROOT / "scripts" / "refresh_events.py")
    seen = {"calls": [], "constructed": [], "ciks": None}
    _bind(monkeypatch, module, seen)
    missing = module.main(
        ["--dataset", "all", "--universe", str(tmp_path / "missing.csv"), "--root", str(tmp_path / "store")]
    )
    assert missing == 2
    assert "config_error=universe_missing" in capsys.readouterr().out
    assert seen["constructed"] == []
    empty = tmp_path / "empty.csv"
    empty.write_text("ticker,name,cik\n", encoding="utf-8")
    blank = module.main(["--dataset", "all", "--universe", str(empty), "--root", str(tmp_path / "store")])
    assert blank == 2
    assert "config_error=universe_empty" in capsys.readouterr().out
    assert seen["calls"] == []


def test_sec_targets_without_a_cik_fail_before_fetch(tmp_path, monkeypatch, capsys):
    module = _load("refresh_events_cik", ROOT / "scripts" / "refresh_events.py")
    seen = {"calls": [], "constructed": [], "ciks": None}
    _bind(monkeypatch, module, seen)
    universe = tmp_path / "universe.csv"
    universe.write_text("ticker,name,cik\nAAPL,Apple Inc.,\n", encoding="utf-8")
    code = module.main(
        ["--dataset", "all", "--universe", str(universe), "--tickers", "AAPL", "--root", str(tmp_path / "store")]
    )
    assert code == 2
    assert "config_error=missing_cik tickers=AAPL" in capsys.readouterr().out
    assert seen["constructed"] == []


def test_prepared_list_calls_news_and_sec_for_the_same_companies(tmp_path, monkeypatch, capsys):
    prepare = _load("prepare_events_universe", ROOT / "scripts" / "prepare_events_universe.py")
    refresh = _load("refresh_events_ready", ROOT / "scripts" / "refresh_events.py")
    universe = tmp_path / "universe.csv"
    assert prepare.main(["--tickers", "AAPL", "JPM", "NVDA", "--out", str(universe)]) == 0
    seen = {"calls": [], "constructed": [], "ciks": None}
    blob = MemoryBlob()
    _bind(monkeypatch, refresh, seen, blob)
    code = refresh.main(
        [
            "--dataset",
            "all",
            "--universe",
            str(universe),
            "--tickers",
            "AAPL",
            "JPM",
            "NVDA",
            "--root",
            str(tmp_path / "first"),
            "--now",
            NOW.isoformat(),
        ]
    )
    assert code == 0
    assert "config_error" not in capsys.readouterr().out
    assert seen["ciks"] == {"AAPL": 320193, "JPM": 19617, "NVDA": 1045810}
    assert {ticker for kind, ticker in seen["calls"] if kind == "news"} == {"AAPL", "JPM", "NVDA"}
    assert {ticker for kind, ticker in seen["calls"] if kind == "sec_index"} == {"AAPL", "JPM", "NVDA"}
    saved, _etag = pull_checkpoint(blob)
    assert saved["expected_tickers"] == ["AAPL", "JPM", "NVDA"]
    seen["calls"].clear()
    later = refresh.main(
        [
            "--dataset",
            "all",
            "--universe",
            str(universe),
            "--tickers",
            "AAPL",
            "JPM",
            "NVDA",
            "--root",
            str(tmp_path / "second"),
            "--now",
            (NOW + timedelta(minutes=1)).isoformat(),
        ]
    )
    skipped = capsys.readouterr().out
    assert later == 0
    assert seen["calls"] == []
    assert "config_error" not in skipped
    assert skipped.count("reason=not_due") == 6
    other = MemoryBlob()

    def open_other(_flags, *, drill=False):
        del drill
        return BlobDurable(other), other

    monkeypatch.setattr(refresh, "open_durable", open_other)
    seen["calls"].clear()
    only = refresh.main(
        [
            "--dataset",
            "all",
            "--universe",
            str(universe),
            "--tickers",
            "JPM",
            "--root",
            str(tmp_path / "jpm"),
            "--now",
            NOW.isoformat(),
        ]
    )
    assert only == 0
    capsys.readouterr()
    assert seen["ciks"] == {"JPM": 19617}
    assert {ticker for _dataset, ticker in seen["calls"]} == {"JPM"}
    assert {dataset for dataset, _ticker in seen["calls"]} == {"news", "sec_index"}


def test_drill_health_does_not_treat_the_other_seventeen_as_missing():
    checkpoint = {
        "expected_tickers": ["AAPL", "JPM", "NVDA"],
        "datasets": {
            "news": {"states": {ticker: {"key": ticker, "last_successful_check_at": NOW.isoformat(), "status": "current"} for ticker in ("AAPL", "JPM", "NVDA")}},
            "sec_index": {"states": {ticker: {"key": ticker, "last_successful_check_at": NOW.isoformat(), "status": "current"} for ticker in ("AAPL", "JPM", "NVDA")}},
        },
    }
    report = judge_checkpoint(
        checkpoint,
        now=NOW + timedelta(minutes=10),
        expected=set(checkpoint["expected_tickers"]),
    )
    keys = {(source["dataset"], source["key"]) for source in report["sources"]}
    assert ("news", "WMT") not in keys
    assert ("sec_index", "MSFT") not in keys
    assert report["ok"] is True
    script = ROOT / "ops" / "vercel" / "events" / "index.js"
    program = (
        "const handler = require(process.argv[1]);\n"
        "const checkpoint = JSON.parse(process.argv[2]);\n"
        "const health = handler.healthFromCheckpoint(checkpoint, Date.parse(process.argv[3]));\n"
        "const keys = health.sources.map((source) => source.dataset + ':' + source.key);\n"
        "if (keys.includes('news:WMT') || keys.includes('sec_index:MSFT')) process.exit(2);\n"
        "if (!health.ok) process.exit(3);\n"
        "if (health.sources.length !== 6) process.exit(4);\n"
    )
    result = subprocess.run(
        [
            "node",
            "-e",
            program,
            str(script),
            json.dumps(checkpoint),
            (NOW + timedelta(minutes=10)).isoformat(),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        env=os.environ.copy(),
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_drill_does_not_use_a_production_blob_token(tmp_path, monkeypatch, capsys):
    module = _load("refresh_events_drill_token", ROOT / "scripts" / "refresh_events.py")
    seen = {"calls": [], "constructed": [], "ciks": None, "transport": []}
    _bind(monkeypatch, module, seen)

    class StorageClient:
        def __init__(self, token: str) -> None:
            seen["transport"].append(token)

    monkeypatch.setattr(module, "HttpBlobTransport", StorageClient)
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "production-token")
    monkeypatch.delenv("EVENTS_DRILL_BLOB_READ_WRITE_TOKEN", raising=False)
    universe = tmp_path / "universe.csv"
    universe.write_text(
        "ticker,name,cik\nAAPL,Apple Inc.,320193\nJPM,JPMorgan Chase & Co.,19617\nNVDA,NVIDIA Corp,1045810\n",
        encoding="utf-8",
    )
    code = module.main(
        [
            "--drill",
            "--dataset",
            "all",
            "--universe",
            str(universe),
            "--tickers",
            "AAPL",
            "JPM",
            "NVDA",
            "--root",
            str(tmp_path / "store"),
            "--require-blob",
        ]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "config_error=drill_blob_missing" in captured.out
    assert "production-token" not in captured.out
    assert seen["transport"] == []
    assert seen["constructed"] == []
    assert seen["calls"] == []


def test_drill_workflow_prepares_three_names_on_a_separate_blob_prefix(monkeypatch):
    monkeypatch.setenv("EVENTS_BLOB_PREFIX", "lens-events-drill")
    assert commit_path() == "lens-events-drill/commit.json"
    refresh = (ROOT / ".github/workflows/events-refresh.yml").read_text()
    monitor = (ROOT / ".github/workflows/events-monitor.yml").read_text()
    assert "schedule:" not in refresh
    assert "schedule:" not in monitor
    assert "deploy_vercel" not in refresh
    assert "prepare_events_universe.py" in refresh
    assert "build_demo_universe.py" not in refresh
    assert "data/build/universe.csv" not in refresh
    assert "AAPL JPM NVDA" in refresh
    assert "lens-events-drill" in refresh
    assert "EVENTS_DRILL_BLOB_READ_WRITE_TOKEN" in refresh
    assert "inputs.drill && secrets.EVENTS_DRILL_BLOB_READ_WRITE_TOKEN" not in refresh
    assert "|| secrets.BLOB_READ_WRITE_TOKEN" not in refresh
    drill_step, live_step = refresh.split("Refresh the live blob", 1)
    assert "secrets.BLOB_READ_WRITE_TOKEN" not in drill_step
    assert "secrets.EVENTS_DRILL_BLOB_READ_WRITE_TOKEN" in drill_step
    assert "if: inputs.drill" in drill_step
    assert "secrets.BLOB_READ_WRITE_TOKEN" in live_step
    assert "secrets.EVENTS_DRILL_BLOB_READ_WRITE_TOKEN" not in live_step
    assert "EVENTS_DRILL_BLOB_READ_WRITE_TOKEN" in monitor
    assert "--supported AAPL JPM NVDA" in monitor
