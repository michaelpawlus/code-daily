"""Launchpad: score "shareability" of every shipped Python tool under ~/projects.

The goal of this module is to close the build-vs-activate gap: many of the
user's CLI tools (typer-duo, alida-sdk, taskpilot, dab-forge, ...) exist as
working code but are not yet packaged for other humans or agents to actually
adopt. Launchpad scores each shippable project against a local-only signal
set — README depth, LICENSE, CHANGELOG, tests, CI, recent commits, console
scripts — and persists a snapshot so we can show "moved typer-duo from D to
B in 30 days" over time.

A "shippable" project is any directory under the scan root with a
``pyproject.toml`` declaring at least one entry in ``[project.scripts]``.
This filter is what separates a published CLI from a research notebook.
"""

from __future__ import annotations

import re
import subprocess
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.storage import CommitStorage

DEFAULT_ROOT = str(Path.home() / "projects")

_GRADE_ORDER = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}

# Per-signal point allocation; total = 100.
SIGNAL_WEIGHTS = {
    "has_readme": 10,
    "readme_substantial": 5,       # >= 800 bytes
    "readme_has_install": 5,
    "readme_has_usage": 10,
    "has_license": 10,
    "has_changelog": 10,
    "has_tests": 15,
    "has_ci": 15,
    "has_recent_commit": 10,       # <= 30 days
    "has_cli_entry": 10,           # console scripts in pyproject
}


class LaunchpadError(RuntimeError):
    """Raised when a sweep cannot complete."""


# ---------------------------------------------------------------------------
# discovery
# ---------------------------------------------------------------------------


def _read_pyproject(path: Path) -> Optional[dict]:
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return None


def _scripts_from_pyproject(data: dict) -> list[str]:
    """Return the list of console-script keys declared in a pyproject."""
    project = data.get("project") or {}
    scripts = project.get("scripts") or {}
    if isinstance(scripts, dict):
        return list(scripts.keys())
    return []


def discover_shippables(root: str | Path) -> list[dict]:
    """Find every project under ``root`` that declares ``[project.scripts]``.

    Returns one dict per shippable with name, path, and the declared scripts.
    Hidden directories (leading-dot) and ``.venv`` trees are skipped.
    """
    root_path = Path(root)
    if not root_path.exists():
        raise LaunchpadError(f"root does not exist: {root}")

    shippables: list[dict] = []
    for child in sorted(root_path.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        pyproject = child / "pyproject.toml"
        if not pyproject.exists():
            continue
        data = _read_pyproject(pyproject)
        if data is None:
            continue
        scripts = _scripts_from_pyproject(data)
        if not scripts:
            continue
        project_name = (data.get("project") or {}).get("name") or child.name
        version = (data.get("project") or {}).get("version")
        shippables.append(
            {
                "name": project_name,
                "path": str(child.resolve()),
                "version": version,
                "scripts": scripts,
            }
        )
    return shippables


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------


_INSTALL_RE = re.compile(r"^#+\s*install", re.IGNORECASE | re.MULTILINE)
_USAGE_RE = re.compile(
    r"^#+\s*(usage|example|examples|quickstart|getting started)",
    re.IGNORECASE | re.MULTILINE,
)


def _readme_signals(project_path: Path) -> dict:
    """Return (has_readme, readme_bytes, has_install_section, has_usage_section)."""
    for name in ("README.md", "README.rst", "README.txt", "README"):
        readme = project_path / name
        if readme.exists() and readme.is_file():
            try:
                text = readme.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            return {
                "has_readme": True,
                "readme_bytes": len(text.encode("utf-8")),
                "readme_has_install": bool(_INSTALL_RE.search(text)),
                "readme_has_usage": bool(_USAGE_RE.search(text)),
            }
    return {
        "has_readme": False,
        "readme_bytes": 0,
        "readme_has_install": False,
        "readme_has_usage": False,
    }


def _has_license(project_path: Path) -> bool:
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "COPYING.md"):
        if (project_path / name).exists():
            return True
    return False


def _has_changelog(project_path: Path) -> bool:
    for name in ("CHANGELOG.md", "CHANGELOG.rst", "CHANGELOG", "CHANGES.md", "CHANGES"):
        if (project_path / name).exists():
            return True
    return False


def _has_tests(project_path: Path) -> bool:
    tests_dir = project_path / "tests"
    if tests_dir.exists() and tests_dir.is_dir():
        if any(tests_dir.rglob("test_*.py")) or any(tests_dir.rglob("*_test.py")):
            return True
        if (tests_dir / "__init__.py").exists():
            return True
    src_tests = project_path / "src" / "tests"
    if src_tests.exists() and src_tests.is_dir():
        return True
    return False


def _has_ci(project_path: Path) -> bool:
    workflows = project_path / ".github" / "workflows"
    if workflows.exists() and workflows.is_dir():
        for f in workflows.iterdir():
            if f.suffix in (".yml", ".yaml"):
                return True
    return False


def _days_since_last_commit(project_path: Path) -> Optional[int]:
    """Return days since the most recent git commit, or None if not a git repo."""
    if not (project_path / ".git").exists():
        return None
    try:
        proc = subprocess.run(
            ["git", "-C", str(project_path), "log", "-1", "--format=%cI"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        commit_dt = datetime.fromisoformat(proc.stdout.strip())
    except ValueError:
        return None
    if commit_dt.tzinfo is None:
        commit_dt = commit_dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - commit_dt
    return max(delta.days, 0)


def score_signals(signals: dict) -> int:
    """Compute the 0-100 launchpad score from a signals dict."""
    score = 0
    for key, weight in SIGNAL_WEIGHTS.items():
        if signals.get(key):
            score += weight
    return min(score, 100)


def grade_for_score(score: int) -> str:
    """Map a 0-100 score to an A-F grade."""
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def score_project(shippable: dict) -> dict:
    """Collect all signals for one shippable and compute a graded score."""
    path = Path(shippable["path"])
    readme = _readme_signals(path)
    days_since = _days_since_last_commit(path)

    signals = {
        "has_readme": readme["has_readme"],
        "readme_substantial": readme["readme_bytes"] >= 800,
        "readme_has_install": readme["readme_has_install"],
        "readme_has_usage": readme["readme_has_usage"],
        "has_license": _has_license(path),
        "has_changelog": _has_changelog(path),
        "has_tests": _has_tests(path),
        "has_ci": _has_ci(path),
        "has_recent_commit": days_since is not None and days_since <= 30,
        "has_cli_entry": bool(shippable.get("scripts")),
    }
    score = score_signals(signals)
    grade = grade_for_score(score)

    missing = [k for k, v in signals.items() if not v]

    return {
        "name": shippable["name"],
        "path": shippable["path"],
        "version": shippable.get("version"),
        "scripts": shippable.get("scripts") or [],
        "score": score,
        "grade": grade,
        "signals": signals,
        "readme_bytes": readme["readme_bytes"],
        "days_since_last_commit": days_since,
        "missing_signals": missing,
    }


# ---------------------------------------------------------------------------
# sweep + diff
# ---------------------------------------------------------------------------


def grade_distribution(projects: list[dict]) -> dict[str, int]:
    dist = {g: 0 for g in ("A", "B", "C", "D", "F")}
    for p in projects:
        g = p.get("grade", "F")
        dist[g] = dist.get(g, 0) + 1
    return dist


def _grade_direction(prev: str, curr: str) -> str:
    a, b = _GRADE_ORDER.get(prev, 0), _GRADE_ORDER.get(curr, 0)
    if b > a:
        return "up"
    if b < a:
        return "down"
    return "flat"


def compute_changes(
    current: list[dict],
    prior_by_path: dict[str, dict],
) -> list[dict]:
    """Return one entry per project whose grade or score moved since prior snapshot."""
    changes: list[dict] = []
    for proj in current:
        path = proj["path"]
        prior = prior_by_path.get(path)
        if prior is None:
            changes.append(
                {
                    "name": proj["name"],
                    "path": path,
                    "grade_from": None,
                    "grade_to": proj["grade"],
                    "score_from": None,
                    "score_to": proj["score"],
                    "score_delta": None,
                    "direction": "new",
                    "days_since_previous": None,
                }
            )
            continue
        prev_grade = prior["grade"]
        prev_score = int(prior["score"])
        if prev_grade == proj["grade"] and prev_score == proj["score"]:
            continue
        try:
            prev_dt = datetime.fromisoformat(prior["captured_at"].replace("Z", "+00:00"))
            days = (datetime.now(timezone.utc) - prev_dt).days
        except (ValueError, AttributeError):
            days = None
        changes.append(
            {
                "name": proj["name"],
                "path": path,
                "grade_from": prev_grade,
                "grade_to": proj["grade"],
                "score_from": prev_score,
                "score_to": proj["score"],
                "score_delta": proj["score"] - prev_score,
                "direction": _grade_direction(prev_grade, proj["grade"]),
                "days_since_previous": days,
            }
        )
    return changes


def run_sweep(
    root: str = DEFAULT_ROOT,
    storage: CommitStorage | None = None,
    persist: bool = True,
) -> dict:
    """Discover every shippable under ``root``, score it, and persist a snapshot.

    Returns a summary dict suitable for ``--json`` output.
    """
    shippables = discover_shippables(root)
    projects = [score_project(s) for s in shippables]

    captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if storage is None:
        storage = CommitStorage()

    prior_by_path = storage.get_latest_launchpad_per_project()

    if persist:
        storage.save_launchpad_snapshot(captured_at, projects)

    changes = compute_changes(projects, prior_by_path)

    return {
        "captured_at": captured_at,
        "root": str(Path(root).resolve()),
        "persisted": persist,
        "project_count": len(projects),
        "grade_distribution": grade_distribution(projects),
        "changes": changes,
        "projects": projects,
    }
