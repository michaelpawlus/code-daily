"""Tests for quest_discovery helpers and the `discover-all` CLI command."""

from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from src import quest_discovery
from src.typer_cli import app


runner = CliRunner()


def _ok(**extras):
    base = {"status": "ok", "added": extras.pop("added", 0), "skipped": extras.pop("skipped", 0)}
    base.update(extras)
    return base


def _skip(error="unavailable"):
    return {"status": "skipped", "added": 0, "skipped": 0, "error": error}


def _err(error="boom"):
    return {"status": "error", "added": 0, "skipped": 0, "error": error}


class TestRunAll:
    """Unit tests for quest_discovery.run_all()."""

    def test_aggregates_totals_across_sources(self):
        fakes = {
            "scan-todos":       lambda: _ok(added=1, skipped=2),
            "scan-skillvault":  lambda: _ok(added=3, skipped=0, scanned=3),
            "sync-beacon-gaps": lambda: _ok(added=2, skipped=1, total_gaps=3),
            "sync-issues":      lambda: _ok(added=0, skipped=4),
            "discover":         lambda: _ok(added=1, skipped=0, from_cache=True),
        }
        sources = [(name, fn) for name, fn in fakes.items()]
        with patch.object(quest_discovery, "DISCOVERY_SOURCES", sources):
            result = quest_discovery.run_all()

        assert result["total_added"] == 7
        assert result["total_skipped"] == 7
        assert result["total_errors"] == 0
        assert [s["name"] for s in result["sources"]] == list(fakes.keys())
        assert result["sources"][1]["scanned"] == 3

    def test_skipped_source_counted_in_totals_but_not_errors(self):
        sources = [
            ("scan-todos", lambda: _ok(added=1)),
            ("sync-beacon-gaps", lambda: _skip("beacon CLI not found")),
        ]
        with patch.object(quest_discovery, "DISCOVERY_SOURCES", sources):
            result = quest_discovery.run_all()

        assert result["total_added"] == 1
        assert result["total_errors"] == 0
        assert result["sources"][1]["status"] == "skipped"
        assert "beacon" in result["sources"][1]["error"]

    def test_error_in_one_source_does_not_abort_batch(self):
        def exploder():
            raise RuntimeError("network is sad")

        sources = [
            ("scan-todos", lambda: _ok(added=2)),
            ("sync-issues", exploder),
            ("discover", lambda: _ok(added=1)),
        ]
        with patch.object(quest_discovery, "DISCOVERY_SOURCES", sources):
            result = quest_discovery.run_all()

        assert result["total_added"] == 3
        assert result["total_errors"] == 1
        assert result["sources"][1]["status"] == "error"
        assert "RuntimeError" in result["sources"][1]["error"]
        assert result["sources"][2]["status"] == "ok"


class TestRunScanLaunchpad:
    """Unit tests for quest_discovery.run_scan_launchpad()."""

    @staticmethod
    def _fake_project(name="proj", grade="D", score=45, path=None, missing=None):
        return {
            "name": name,
            "grade": grade,
            "score": score,
            "path": path or f"/tmp/{name}",
            "missing_signals": missing or ["has_license", "has_ci"],
        }

    def test_invalid_max_grade_returns_error_without_calling_sweep(self):
        with patch("src.launchpad.run_sweep") as mock_sweep:
            result = quest_discovery.run_scan_launchpad(max_grade="Z")

        assert result["status"] == "error"
        assert "invalid max_grade" in result["error"]
        mock_sweep.assert_not_called()

    def test_filters_by_threshold_and_does_not_persist(self):
        projects = [
            self._fake_project(name="alpha", grade="A", score=95),
            self._fake_project(name="charlie", grade="C", score=60),
            self._fake_project(name="delta", grade="D", score=45),
            self._fake_project(name="foxtrot", grade="F", score=10),
        ]
        with patch(
            "src.launchpad.run_sweep",
            return_value={"projects": projects},
        ) as mock_sweep, patch(
            "src.quest_manager.QuestManager.sync_launchpad_low_grades",
            return_value={"added": 2, "skipped": 0},
        ) as mock_sync, patch("src.storage.CommitStorage"):
            result = quest_discovery.run_scan_launchpad(max_grade="D")

        # run_sweep must be called with persist=False so launchpad sweep stays
        # the sole writer of snapshot rows.
        assert mock_sweep.call_args.kwargs["persist"] is False
        # Only the D and F projects should have been forwarded to the sync layer.
        forwarded = mock_sync.call_args.args[0]
        assert sorted(p["name"] for p in forwarded) == ["delta", "foxtrot"]
        assert result["status"] == "ok"
        assert result["scanned"] == 2
        assert result["added"] == 2
        assert result["max_grade"] == "D"

    def test_launchpad_error_returns_error_status(self):
        from src.launchpad import LaunchpadError

        with patch("src.launchpad.run_sweep", side_effect=LaunchpadError("root missing")):
            result = quest_discovery.run_scan_launchpad()

        assert result["status"] == "error"
        assert "root missing" in result["error"]


class TestDiscoverAllCli:
    """CLI tests for `code-daily quests discover-all`."""

    def test_json_output_shape(self):
        sources = [
            ("scan-todos", lambda: _ok(added=1, skipped=2)),
            ("discover", lambda: _ok(added=0, skipped=0, from_cache=True)),
        ]
        with patch.object(quest_discovery, "DISCOVERY_SOURCES", sources):
            result = runner.invoke(app, ["quests", "discover-all", "--json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["total_added"] == 1
        assert payload["total_skipped"] == 2
        assert payload["total_errors"] == 0
        assert len(payload["sources"]) == 2
        assert payload["sources"][0]["name"] == "scan-todos"

    def test_human_output_marks_skipped_and_errored(self):
        def exploder():
            raise ValueError("nope")

        sources = [
            ("scan-todos", lambda: _ok(added=1, skipped=0)),
            ("sync-beacon-gaps", lambda: _skip("beacon CLI not found")),
            ("sync-issues", exploder),
        ]
        with patch.object(quest_discovery, "DISCOVERY_SOURCES", sources):
            result = runner.invoke(app, ["quests", "discover-all"])

        assert result.exit_code == 0, result.output
        assert "[ok]" in result.stdout
        assert "[skip]" in result.stdout
        assert "[err]" in result.stdout
        assert "beacon CLI not found" in result.stdout
        assert "Total added:   1" in result.stdout
        assert "Errors:        1" in result.stdout
