"""Tests for the portfolio sweep module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src import portfolio_sweep
from src.portfolio_sweep import (
    PortfolioSweepError,
    compute_changes,
    grade_distribution,
    merge_projects,
    run_sweep,
)
from src.storage import CommitStorage


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def storage(temp_db):
    return CommitStorage(temp_db)


@pytest.fixture
def sample_agent_ready_payload():
    return {
        "scanned_at": "2026-04-20T02:00:00+00:00",
        "projects": [
            {
                "path": "/home/u/projects/alpha",
                "name": "alpha",
                "score": 82,
                "grade": "B",
                "categories": {"machine_interface": {"score": 80, "weight": 30}},
                "failing_checks": [],
            },
            {
                "path": "/home/u/projects/beta",
                "name": "beta",
                "score": 45,
                "grade": "D",
                "categories": {"invocability": {"score": 40, "weight": 25}},
                "failing_checks": [{"id": "invocability.cli-entry-point"}],
            },
        ],
        "summary": {},
    }


@pytest.fixture
def sample_audit_rows():
    return [
        {
            "path": "/home/u/projects/alpha",
            "name": "alpha",
            "days_since_last_commit": 2,
            "commits_30d": 17,
            "project_scripts": ["alpha = 'alpha.cli:app'"],
        },
        # beta intentionally omitted so we test the null-activity path
    ]


class TestMerge:
    def test_merges_activity_onto_scoring(self, sample_agent_ready_payload, sample_audit_rows):
        merged = merge_projects(sample_agent_ready_payload, sample_audit_rows)
        assert len(merged) == 2

        alpha = next(p for p in merged if p["name"] == "alpha")
        assert alpha["grade"] == "B"
        assert alpha["score"] == 82
        assert alpha["days_since_last_commit"] == 2
        assert alpha["commits_30d"] == 17
        assert alpha["has_cli"] is True

    def test_missing_activity_leaves_fields_none(
        self, sample_agent_ready_payload, sample_audit_rows
    ):
        merged = merge_projects(sample_agent_ready_payload, sample_audit_rows)
        beta = next(p for p in merged if p["name"] == "beta")
        assert beta["days_since_last_commit"] is None
        assert beta["commits_30d"] is None
        assert beta["has_cli"] is None

    def test_has_cli_derived_from_project_scripts(self):
        payload = {"projects": [{"path": "/x", "name": "x", "score": 50, "grade": "C"}]}
        # empty project_scripts → False
        merged = merge_projects(payload, [{"path": "/x", "project_scripts": []}])
        assert merged[0]["has_cli"] is False
        # populated project_scripts → True
        merged = merge_projects(payload, [{"path": "/x", "project_scripts": ["x = m:a"]}])
        assert merged[0]["has_cli"] is True
        # project_scripts missing → None
        merged = merge_projects(payload, [{"path": "/x"}])
        assert merged[0]["has_cli"] is None

    def test_skips_projects_without_path(self):
        payload = {"projects": [{"name": "nopath", "score": 10, "grade": "F"}]}
        assert merge_projects(payload, []) == []


class TestGradeDistribution:
    def test_zero_fills_all_grades(self):
        dist = grade_distribution([{"grade": "A"}, {"grade": "A"}, {"grade": "F"}])
        assert dist == {"A": 2, "B": 0, "C": 0, "D": 0, "F": 1}


class TestStoragePersistence:
    def test_save_and_retrieve_latest(self, storage):
        projects = [
            {
                "name": "alpha",
                "path": "/tmp/alpha",
                "grade": "B",
                "score": 82,
                "categories": {},
                "raw": {},
            }
        ]
        storage.save_portfolio_snapshot("2026-04-20T00:00:00+00:00", projects)
        latest = storage.get_latest_per_project()
        assert "/tmp/alpha" in latest
        assert latest["/tmp/alpha"]["grade"] == "B"
        assert latest["/tmp/alpha"]["score"] == 82

    def test_latest_picks_newest_per_project(self, storage):
        p = {"name": "alpha", "path": "/tmp/alpha", "grade": "C", "score": 70, "categories": {}, "raw": {}}
        storage.save_portfolio_snapshot("2026-04-10T00:00:00+00:00", [p])
        p2 = {**p, "grade": "A", "score": 95}
        storage.save_portfolio_snapshot("2026-04-20T00:00:00+00:00", [p2])

        latest = storage.get_latest_per_project()
        assert latest["/tmp/alpha"]["grade"] == "A"

        # before filter excludes the newest
        prior = storage.get_latest_per_project(before="2026-04-15T00:00:00+00:00")
        assert prior["/tmp/alpha"]["grade"] == "C"

    def test_history_filters_by_project_and_since(self, storage):
        p_alpha = {"name": "alpha", "path": "/tmp/alpha", "grade": "A", "score": 90, "categories": {}, "raw": {}}
        p_beta = {"name": "beta", "path": "/tmp/beta", "grade": "F", "score": 10, "categories": {}, "raw": {}}
        storage.save_portfolio_snapshot("2026-04-01T00:00:00+00:00", [p_alpha, p_beta])
        storage.save_portfolio_snapshot("2026-04-20T00:00:00+00:00", [p_alpha, p_beta])

        alpha_only = storage.get_project_history(project_name="alpha")
        assert len(alpha_only) == 2
        assert all(r["project_name"] == "alpha" for r in alpha_only)

        recent = storage.get_project_history(since="2026-04-15T00:00:00+00:00")
        assert len(recent) == 2  # only the second sweep
        assert all(r["captured_at"].startswith("2026-04-20") for r in recent)


class TestComputeChanges:
    def test_new_project_has_null_from_fields(self):
        current = [{"name": "alpha", "path": "/tmp/alpha", "grade": "B", "score": 80}]
        changes = compute_changes(current, prior_by_path={})
        assert len(changes) == 1
        assert changes[0]["direction"] == "new"
        assert changes[0]["grade_from"] is None
        assert changes[0]["score_delta"] is None

    def test_unchanged_project_is_omitted(self):
        current = [{"name": "alpha", "path": "/tmp/alpha", "grade": "B", "score": 80}]
        prior = {
            "/tmp/alpha": {
                "grade": "B",
                "score": 80,
                "captured_at": "2026-04-01T00:00:00+00:00",
            }
        }
        assert compute_changes(current, prior) == []

    def test_grade_up_is_captured(self):
        current = [{"name": "alpha", "path": "/tmp/alpha", "grade": "A", "score": 95}]
        prior = {
            "/tmp/alpha": {
                "grade": "C",
                "score": 70,
                "captured_at": "2026-04-01T00:00:00+00:00",
            }
        }
        changes = compute_changes(current, prior)
        assert changes[0]["direction"] == "up"
        assert changes[0]["grade_from"] == "C"
        assert changes[0]["grade_to"] == "A"
        assert changes[0]["score_delta"] == 25

    def test_score_only_change_still_recorded(self):
        current = [{"name": "alpha", "path": "/tmp/alpha", "grade": "B", "score": 85}]
        prior = {
            "/tmp/alpha": {
                "grade": "B",
                "score": 80,
                "captured_at": "2026-04-01T00:00:00+00:00",
            }
        }
        changes = compute_changes(current, prior)
        assert len(changes) == 1
        assert changes[0]["direction"] == "flat"
        assert changes[0]["score_delta"] == 5


class TestRunSweep:
    def test_happy_path_persists_and_diffs(
        self, storage, sample_agent_ready_payload, sample_audit_rows, tmp_path
    ):
        with patch.object(
            portfolio_sweep, "resolve_agent_ready_bin", return_value="/fake/agent-ready"
        ), patch.object(
            portfolio_sweep,
            "resolve_portfolio_audit_bin",
            return_value="/fake/portfolio-audit",
        ), patch.object(
            portfolio_sweep, "fetch_agent_ready", return_value=sample_agent_ready_payload
        ), patch.object(
            portfolio_sweep, "fetch_portfolio_audit", return_value=sample_audit_rows
        ):
            result = run_sweep(root=str(tmp_path), storage=storage)

        assert result["project_count"] == 2
        assert result["persisted"] is True
        assert result["grade_distribution"]["B"] == 1
        assert result["grade_distribution"]["D"] == 1
        # First sweep: every project shows up as "new"
        assert all(c["direction"] == "new" for c in result["changes"])
        assert result["warnings"] == []

        # DB actually got the rows
        history = storage.get_project_history()
        assert len(history) == 2

    def test_second_sweep_surfaces_grade_changes(
        self, storage, sample_agent_ready_payload, sample_audit_rows, tmp_path
    ):
        with patch.object(
            portfolio_sweep, "resolve_agent_ready_bin", return_value="/fake/agent-ready"
        ), patch.object(
            portfolio_sweep,
            "resolve_portfolio_audit_bin",
            return_value="/fake/portfolio-audit",
        ), patch.object(
            portfolio_sweep, "fetch_agent_ready", return_value=sample_agent_ready_payload
        ), patch.object(
            portfolio_sweep, "fetch_portfolio_audit", return_value=sample_audit_rows
        ):
            run_sweep(root=str(tmp_path), storage=storage)

        bumped = json.loads(json.dumps(sample_agent_ready_payload))
        bumped["projects"][0]["grade"] = "A"
        bumped["projects"][0]["score"] = 95

        with patch.object(
            portfolio_sweep, "resolve_agent_ready_bin", return_value="/fake/agent-ready"
        ), patch.object(
            portfolio_sweep,
            "resolve_portfolio_audit_bin",
            return_value="/fake/portfolio-audit",
        ), patch.object(
            portfolio_sweep, "fetch_agent_ready", return_value=bumped
        ), patch.object(
            portfolio_sweep, "fetch_portfolio_audit", return_value=sample_audit_rows
        ):
            result = run_sweep(root=str(tmp_path), storage=storage)

        alpha_change = next(c for c in result["changes"] if c["name"] == "alpha")
        assert alpha_change["direction"] == "up"
        assert alpha_change["grade_from"] == "B"
        assert alpha_change["grade_to"] == "A"
        assert alpha_change["score_delta"] == 13

    def test_dry_run_does_not_persist(
        self, storage, sample_agent_ready_payload, sample_audit_rows, tmp_path
    ):
        with patch.object(
            portfolio_sweep, "resolve_agent_ready_bin", return_value="/fake/agent-ready"
        ), patch.object(
            portfolio_sweep,
            "resolve_portfolio_audit_bin",
            return_value="/fake/portfolio-audit",
        ), patch.object(
            portfolio_sweep, "fetch_agent_ready", return_value=sample_agent_ready_payload
        ), patch.object(
            portfolio_sweep, "fetch_portfolio_audit", return_value=sample_audit_rows
        ):
            result = run_sweep(root=str(tmp_path), storage=storage, persist=False)

        assert result["persisted"] is False
        assert storage.get_project_history() == []

    def test_missing_agent_ready_raises(self, storage, tmp_path):
        with patch.object(
            portfolio_sweep, "resolve_agent_ready_bin", return_value=None
        ):
            with pytest.raises(PortfolioSweepError, match="agent-ready"):
                run_sweep(root=str(tmp_path), storage=storage)

    def test_missing_portfolio_audit_produces_warning(
        self, storage, sample_agent_ready_payload, tmp_path
    ):
        with patch.object(
            portfolio_sweep, "resolve_agent_ready_bin", return_value="/fake/agent-ready"
        ), patch.object(
            portfolio_sweep, "resolve_portfolio_audit_bin", return_value=None
        ), patch.object(
            portfolio_sweep, "fetch_agent_ready", return_value=sample_agent_ready_payload
        ):
            result = run_sweep(root=str(tmp_path), storage=storage)

        assert result["warnings"]
        assert "portfolio-audit" in result["warnings"][0]
        # All activity fields should be null
        for p in result["projects"]:
            assert p["days_since_last_commit"] is None

    def test_nonexistent_root_raises(self, storage):
        with pytest.raises(PortfolioSweepError, match="root does not exist"):
            run_sweep(root="/definitely/not/a/real/path/xyz", storage=storage)
