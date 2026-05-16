"""Tests for the launchpad module."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

from src import launchpad
from src.launchpad import (
    LaunchpadError,
    compute_changes,
    discover_shippables,
    grade_distribution,
    grade_for_score,
    run_sweep,
    score_project,
    score_signals,
)
from src.storage import CommitStorage


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


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


def _make_pyproject(path: Path, name: str, scripts: dict | None = None, version: str = "0.1.0"):
    scripts_block = ""
    if scripts:
        lines = "\n".join(f'{k} = "{v}"' for k, v in scripts.items())
        scripts_block = f'\n[project.scripts]\n{lines}\n'
    path.write_text(
        f'[project]\nname = "{name}"\nversion = "{version}"\n{scripts_block}',
        encoding="utf-8",
    )


def _make_project(
    root: Path,
    name: str,
    *,
    scripts: dict | None = None,
    readme: str | None = None,
    license_file: bool = False,
    changelog: bool = False,
    tests: bool = False,
    ci: bool = False,
    git_init: bool = False,
) -> Path:
    project = root / name
    project.mkdir(parents=True, exist_ok=True)
    _make_pyproject(project / "pyproject.toml", name, scripts=scripts)
    if readme is not None:
        (project / "README.md").write_text(readme, encoding="utf-8")
    if license_file:
        (project / "LICENSE").write_text("MIT", encoding="utf-8")
    if changelog:
        (project / "CHANGELOG.md").write_text("# 0.1.0\n", encoding="utf-8")
    if tests:
        (project / "tests").mkdir()
        (project / "tests" / "test_basic.py").write_text("def test_x():\n    pass\n")
    if ci:
        ci_dir = project / ".github" / "workflows"
        ci_dir.mkdir(parents=True)
        (ci_dir / "ci.yml").write_text("name: ci\non: [push]\n")
    if git_init:
        subprocess.run(["git", "init", "-q"], cwd=project, check=True)
        subprocess.run(
            ["git", "-c", "user.email=t@e", "-c", "user.name=t", "commit",
             "--allow-empty", "-m", "init", "-q"],
            cwd=project, check=True,
        )
    return project


# ---------------------------------------------------------------------------
# discovery
# ---------------------------------------------------------------------------


class TestDiscovery:
    def test_picks_up_projects_with_scripts(self, tmp_path):
        _make_project(tmp_path, "alpha", scripts={"alpha": "alpha:app"})
        _make_project(tmp_path, "beta", scripts={"beta": "beta:app"})
        ships = discover_shippables(tmp_path)
        names = {s["name"] for s in ships}
        assert names == {"alpha", "beta"}

    def test_skips_projects_without_scripts(self, tmp_path):
        _make_project(tmp_path, "alpha", scripts={"alpha": "alpha:app"})
        _make_project(tmp_path, "lib", scripts=None)  # library, no CLI
        ships = discover_shippables(tmp_path)
        assert [s["name"] for s in ships] == ["alpha"]

    def test_skips_hidden_and_missing_pyproject(self, tmp_path):
        _make_project(tmp_path, "alpha", scripts={"a": "a:app"})
        (tmp_path / ".cache").mkdir()
        _make_pyproject(tmp_path / ".cache" / "pyproject.toml", "hidden",
                        scripts={"h": "h:app"})
        (tmp_path / "no-pyproject").mkdir()
        ships = discover_shippables(tmp_path)
        assert [s["name"] for s in ships] == ["alpha"]

    def test_missing_root_raises(self, tmp_path):
        with pytest.raises(LaunchpadError):
            discover_shippables(tmp_path / "does-not-exist")

    def test_captures_scripts_and_version(self, tmp_path):
        _make_project(tmp_path, "alpha",
                      scripts={"alpha": "alpha:app", "alpha-admin": "alpha.admin:app"})
        ships = discover_shippables(tmp_path)
        assert ships[0]["version"] == "0.1.0"
        assert set(ships[0]["scripts"]) == {"alpha", "alpha-admin"}


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------


class TestScoring:
    def test_score_signals_sums_weights(self):
        # Everything passing should hit 100.
        all_on = {k: True for k in launchpad.SIGNAL_WEIGHTS}
        assert score_signals(all_on) == 100
        # Nothing passing -> 0.
        assert score_signals({}) == 0

    def test_grade_buckets(self):
        assert grade_for_score(100) == "A"
        assert grade_for_score(85) == "A"
        assert grade_for_score(84) == "B"
        assert grade_for_score(70) == "B"
        assert grade_for_score(55) == "C"
        assert grade_for_score(40) == "D"
        assert grade_for_score(39) == "F"
        assert grade_for_score(0) == "F"

    def test_readme_signals_detect_sections(self, tmp_path):
        readme = (
            "# alpha\n\n"
            "Quite a lot of description text here to make sure we exceed the "
            "substantial threshold. " * 20
            + "\n## Install\n\npip install alpha\n\n## Usage\n\nalpha --help\n"
        )
        proj = _make_project(tmp_path, "alpha",
                             scripts={"alpha": "alpha:app"},
                             readme=readme)
        ship = discover_shippables(tmp_path)[0]
        result = score_project(ship)
        assert result["signals"]["has_readme"]
        assert result["signals"]["readme_substantial"]
        assert result["signals"]["readme_has_install"]
        assert result["signals"]["readme_has_usage"]

    def test_missing_signals_listed(self, tmp_path):
        _make_project(tmp_path, "bare", scripts={"bare": "bare:app"})
        ship = discover_shippables(tmp_path)[0]
        result = score_project(ship)
        assert "has_readme" in result["missing_signals"]
        assert "has_license" in result["missing_signals"]
        assert "has_tests" in result["missing_signals"]
        # cli-entry always passes for a discovered shippable
        assert "has_cli_entry" not in result["missing_signals"]

    def test_full_house_project_scores_high(self, tmp_path):
        readme = (
            "# alpha\n\n" + ("Description. " * 100) +
            "\n## Install\n\npip install alpha\n## Usage\n\nalpha --help\n"
        )
        _make_project(tmp_path, "alpha",
                      scripts={"alpha": "alpha:app"},
                      readme=readme, license_file=True, changelog=True,
                      tests=True, ci=True, git_init=True)
        ship = discover_shippables(tmp_path)[0]
        result = score_project(ship)
        # has_recent_commit + all docs/tests/ci/license = 100
        assert result["score"] == 100
        assert result["grade"] == "A"

    def test_days_since_last_commit_none_when_not_a_repo(self, tmp_path):
        _make_project(tmp_path, "alpha", scripts={"alpha": "alpha:app"})
        ship = discover_shippables(tmp_path)[0]
        result = score_project(ship)
        assert result["days_since_last_commit"] is None
        assert not result["signals"]["has_recent_commit"]


# ---------------------------------------------------------------------------
# sweep + diff + storage
# ---------------------------------------------------------------------------


class TestSweep:
    def test_first_sweep_persists_and_marks_all_new(self, tmp_path, storage):
        _make_project(tmp_path, "alpha", scripts={"alpha": "alpha:app"})
        _make_project(tmp_path, "beta", scripts={"beta": "beta:app"},
                      readme="# beta\n## Install\nx\n## Usage\nx\n",
                      license_file=True)

        result = run_sweep(root=str(tmp_path), storage=storage)
        assert result["project_count"] == 2
        assert result["persisted"] is True
        assert all(c["direction"] == "new" for c in result["changes"])

        history = storage.get_launchpad_history()
        assert len(history) == 2

    def test_second_sweep_diffs_when_score_changes(self, tmp_path, storage):
        proj = _make_project(tmp_path, "alpha", scripts={"alpha": "alpha:app"})
        first = run_sweep(root=str(tmp_path), storage=storage)
        first_score = first["projects"][0]["score"]

        # Add LICENSE and CHANGELOG so the score moves up.
        (proj / "LICENSE").write_text("MIT")
        (proj / "CHANGELOG.md").write_text("# 0.1.0\n")

        second = run_sweep(root=str(tmp_path), storage=storage)
        second_score = second["projects"][0]["score"]
        assert second_score > first_score

        real_changes = [c for c in second["changes"] if c["direction"] != "new"]
        assert len(real_changes) == 1
        assert real_changes[0]["score_delta"] == second_score - first_score

    def test_dry_run_does_not_persist(self, tmp_path, storage):
        _make_project(tmp_path, "alpha", scripts={"alpha": "alpha:app"})
        result = run_sweep(root=str(tmp_path), storage=storage, persist=False)
        assert result["persisted"] is False
        assert storage.get_launchpad_history() == []


class TestGradeDistribution:
    def test_always_returns_all_grades(self):
        dist = grade_distribution([{"grade": "A"}, {"grade": "A"}, {"grade": "F"}])
        assert dist == {"A": 2, "B": 0, "C": 0, "D": 0, "F": 1}


class TestComputeChanges:
    def test_unchanged_projects_are_omitted(self):
        current = [{"name": "a", "path": "/p/a", "grade": "B", "score": 70}]
        prior = {"/p/a": {"grade": "B", "score": 70, "captured_at": "2026-01-01T00:00:00+00:00"}}
        assert compute_changes(current, prior) == []

    def test_grade_up_direction(self):
        current = [{"name": "a", "path": "/p/a", "grade": "A", "score": 90}]
        prior = {"/p/a": {"grade": "B", "score": 70, "captured_at": "2026-01-01T00:00:00+00:00"}}
        changes = compute_changes(current, prior)
        assert len(changes) == 1
        assert changes[0]["direction"] == "up"
        assert changes[0]["score_delta"] == 20
