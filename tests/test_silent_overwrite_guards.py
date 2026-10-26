"""Three ways to get a wrong result with no error, and the guards that stop them.

Every leakage guard in this project raises rather than logs, because a check
that can be ignored is a comment. These three failures were the same shape and
had no guard at all: each produces a plausible artefact and reports success.

  demo over a real build   a synthetic corpus replaces tens of thousands of
                           real filings; the pipeline then runs perfectly on it
  a stale bundle           the packager copies HTML rather than rendering it,
                           so a deploy after a renderer change ships the old
                           pages and still succeeds
  a mismatched project ID  `vercel deploy` publishes to the environment's
                           project, ignoring the bundle's own link

Two of the three happened while this file was being written, which is the
argument for it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from filing_triage import cli

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_vercel_output import staleness  # noqa: E402  (needs the path above)


class TestDemoWillNotOverwriteARealBuild:
    @pytest.fixture
    def build(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli, "BUILD", tmp_path)
        return tmp_path

    def _provenance(self, build: Path, source: str) -> None:
        (build / "provenance.json").write_text(json.dumps(
            {"source": source, "filings": 11_716, "issuers": 193,
             "written_at": "2026-08-27T04:20:30+00:00"}))

    def test_a_real_build_refuses_and_exits_nonzero(self, build, capsys):
        self._provenance(build, "edgar")
        assert cli._guard_real_build(force=False) == 1
        assert "real EDGAR build" in capsys.readouterr().err

    def test_the_refusal_names_the_way_out(self, build, capsys):
        """A guard that blocks without saying how to proceed gets worked around
        with a wilder command than the one it refused."""
        self._provenance(build, "edgar")
        cli._guard_real_build(force=False)
        message = capsys.readouterr().err
        assert "make ingest" in message
        assert "FORCE=1" in message

    def test_force_is_the_documented_override(self, build):
        self._provenance(build, "edgar")
        assert cli._guard_real_build(force=True) is None

    def test_a_synthetic_build_is_overwritten_freely(self, build):
        """The common case is rerunning the demo, and it must stay frictionless."""
        self._provenance(build, "synthetic")
        assert cli._guard_real_build(force=False) is None

    def test_an_empty_build_directory_is_not_an_obstacle(self, build):
        assert cli._guard_real_build(force=False) is None


class TestTheBundleRefusesStalePages:
    def _site(self, root: Path, *, page_age: float = 0.0) -> Path:
        source = root / "pages"
        source.mkdir()
        for name in ("index.html", "404.html", "aapl.html"):
            path = source / name
            path.write_text("<html></html>")
            if page_age:
                stamp = time.time() - page_age
                os.utime(path, (stamp, stamp))
        return source

    def _renderer(self, root: Path) -> Path:
        renderer = root / "renderer"
        renderer.mkdir()
        (renderer / "page.py").write_text("# renders the pages\n")
        return renderer

    def test_a_renderer_edited_after_the_pages_is_detected(self, tmp_path):
        source = self._site(tmp_path, page_age=3600)
        renderer = self._renderer(tmp_path)      # written now, an hour later
        stale = staleness(source, (renderer,))
        assert stale is not None
        assert stale[1].name == "page.py"

    def test_pages_rebuilt_after_the_renderer_are_current(self, tmp_path):
        renderer = self._renderer(tmp_path)
        time.sleep(0.01)
        source = self._site(tmp_path)            # written after the renderer
        assert staleness(source, (renderer,)) is None

    def test_a_missing_renderer_directory_is_not_staleness(self, tmp_path):
        source = self._site(tmp_path)
        assert staleness(source, (tmp_path / "absent",)) is None

    def test_an_empty_source_reports_nothing(self, tmp_path):
        """Emptiness is the packager's own error to raise, with a better message
        than this one could give."""
        empty = tmp_path / "pages"
        empty.mkdir()
        assert staleness(empty, (self._renderer(tmp_path),)) is None


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not installed")
class TestTheDeployRefusesAMismatchedProject:
    SCRIPT = ROOT / "scripts" / "deploy_vercel_frontend.sh"
    LINKED = "prj_thelinkedone"

    @pytest.fixture
    def bundle(self, tmp_path):
        """A bundle that looks deployable: a prebuilt output and a project link."""
        root = tmp_path / "bundle"
        (root / ".vercel" / "output").mkdir(parents=True)
        (root / ".vercel" / "output" / "config.json").write_text("{}")
        (root / ".vercel" / "project.json").write_text(json.dumps(
            {"projectId": self.LINKED, "orgId": "team_x",
             "projectName": "company-lens-josephjwang"}))
        return root

    def _run(self, bundle: Path, project_id: str, tmp_path: Path):
        """Runs the script with a stub `vercel` first on PATH, so a passing guard
        reaches a command that reports itself instead of publishing anything."""
        stub = tmp_path / "bin"
        stub.mkdir(exist_ok=True)
        (stub / "vercel").write_text("#!/bin/sh\necho DEPLOY-CALLED\n")
        (stub / "vercel").chmod(0o755)
        return subprocess.run(
            ["bash", str(self.SCRIPT)], capture_output=True, text=True,
            env={**os.environ, "PATH": f"{stub}:{os.environ['PATH']}",
                 "VERCEL_BUNDLE_ROOT": str(bundle),
                 "VERCEL_GLOBAL_CONFIG": str(tmp_path / "cli"),
                 "VERCEL_TOKEN": "t", "VERCEL_ORG_ID": "team_x",
                 "VERCEL_PROJECT_ID": project_id},
        )

    def test_a_mismatch_stops_before_vercel_is_called(self, bundle, tmp_path):
        done = self._run(bundle, "prj_somethingelse", tmp_path)
        assert done.returncode == 1
        assert "DEPLOY-CALLED" not in done.stdout
        assert "does not match" in done.stderr

    def test_the_refusal_shows_both_ids(self, bundle, tmp_path):
        done = self._run(bundle, "prj_somethingelse", tmp_path)
        assert "prj_somethingelse" in done.stderr
        assert self.LINKED in done.stderr

    def test_an_unreadable_link_refuses_rather_than_deploying_blind(
            self, bundle, tmp_path):
        """A guard that cannot verify the target and proceeds anyway is the
        failure it exists to prevent. This was the first version's behaviour:
        the field parse missed a whitespace variant and it deployed silently."""
        (bundle / ".vercel" / "project.json").write_text('{"orgId": "team_x"}')
        done = self._run(bundle, "prj_anything", tmp_path)
        assert done.returncode == 1
        assert "DEPLOY-CALLED" not in done.stdout
        assert "cannot be verified" in done.stderr

    def test_the_python_bundle_is_not_published_onto_the_next_project(self, bundle, tmp_path):
        lens_web = "prj_FZTMwbFl4fVES1HqAXn8LjvwnDpG"
        (bundle / ".vercel" / "project.json").write_text(json.dumps(
            {"projectId": lens_web, "orgId": "team_x", "projectName": "lens-web"}))
        done = self._run(bundle, lens_web, tmp_path)
        assert done.returncode == 1
        assert "DEPLOY-CALLED" not in done.stdout
        assert "lens-web" in done.stderr

    def test_a_matching_id_deploys_and_names_the_target(self, bundle, tmp_path):
        done = self._run(bundle, self.LINKED, tmp_path)
        assert done.returncode == 0
        assert "DEPLOY-CALLED" in done.stdout
        # Named on every run, not only on mismatch: the case this missed was two
        # projects that each looked right in isolation.
        assert "company-lens-josephjwang" in done.stdout
