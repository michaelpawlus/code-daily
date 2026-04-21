"""Portfolio sweep: shell out to agent-ready + portfolio-audit, persist a snapshot.

The point of this module is to give code-daily a longitudinal view of
agent-readiness across every personal-use project. Each sweep:

1. Calls `agent-ready score --root <root> --json` for current grades.
2. Best-effort calls `portfolio-audit list --json` for activity context.
3. Merges the two on project path.
4. Persists one row per project into `portfolio_snapshots`.
5. Diffs against the previous snapshot per project so the caller can show
   "moved 5 repos from C to A in 30 days."
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.storage import CommitStorage

DEFAULT_ROOT = str(Path.home() / "projects")

_AGENT_READY_FALLBACK = Path.home() / "projects" / "agent-ready" / ".venv" / "bin" / "agent-ready"
_PORTFOLIO_AUDIT_FALLBACK = (
    Path.home() / "projects" / "portfolio-audit" / ".venv" / "bin" / "portfolio-audit"
)

_GRADE_ORDER = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}


class PortfolioSweepError(RuntimeError):
    """Raised when a sweep cannot complete (e.g. agent-ready missing)."""


def resolve_agent_ready_bin() -> Optional[str]:
    """Locate the agent-ready binary or return None."""
    override = os.environ.get("CODE_DAILY_AGENT_READY_BIN")
    if override:
        return override if Path(override).exists() else None
    on_path = shutil.which("agent-ready")
    if on_path:
        return on_path
    if _AGENT_READY_FALLBACK.exists():
        return str(_AGENT_READY_FALLBACK)
    return None


def resolve_portfolio_audit_bin() -> Optional[str]:
    """Locate the portfolio-audit binary or return None."""
    override = os.environ.get("CODE_DAILY_PORTFOLIO_AUDIT_BIN")
    if override:
        return override if Path(override).exists() else None
    on_path = shutil.which("portfolio-audit")
    if on_path:
        return on_path
    if _PORTFOLIO_AUDIT_FALLBACK.exists():
        return str(_PORTFOLIO_AUDIT_FALLBACK)
    return None


def _run_json(cmd: list[str]) -> dict | list:
    """Run a subprocess and parse stdout as JSON. Raises on non-zero exit."""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise PortfolioSweepError(
            f"{cmd[0]} exited {proc.returncode}: {proc.stderr.strip() or proc.stdout.strip()}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise PortfolioSweepError(
            f"{cmd[0]} did not return valid JSON: {e}\nstdout: {proc.stdout[:500]}"
        ) from e


def _normalize_path(p: str) -> str:
    """Normalize a path for cross-tool joining."""
    return str(Path(p).resolve())


def fetch_agent_ready(root: str, bin_path: str) -> dict:
    """Run agent-ready score and return its parsed payload."""
    payload = _run_json([bin_path, "score", "--root", root, "--json"])
    if not isinstance(payload, dict) or "projects" not in payload:
        raise PortfolioSweepError(
            "agent-ready returned unexpected payload (missing 'projects')"
        )
    return payload


def fetch_portfolio_audit(bin_path: str) -> list[dict]:
    """Run portfolio-audit list and return the parsed list, or [] on error."""
    payload = _run_json([bin_path, "list", "--json"])
    if isinstance(payload, list):
        return payload
    return []


def _derive_has_cli(activity: dict) -> Optional[bool]:
    """Return True if the project exposes at least one console script.

    portfolio-audit doesn't emit a `has_cli` field directly — it emits
    `project_scripts` (list of registered console scripts). An empty list
    means "has a pyproject but no CLI entry"; a missing activity row means
    "we don't know", so we return None in that case.
    """
    if not activity:
        return None
    scripts = activity.get("project_scripts")
    if scripts is None:
        return None
    return bool(scripts)


def merge_projects(
    agent_ready_payload: dict,
    portfolio_audit_rows: list[dict],
) -> list[dict]:
    """Merge agent-ready scoring with portfolio-audit activity by path.

    agent-ready is the source of truth for which projects are in the sweep.
    portfolio-audit data is decorative — missing rows are fine.
    """
    activity_by_path: dict[str, dict] = {}
    for row in portfolio_audit_rows:
        path = row.get("path")
        if not path:
            continue
        activity_by_path[_normalize_path(path)] = row

    merged: list[dict] = []
    for proj in agent_ready_payload.get("projects", []):
        path = proj.get("path")
        if not path:
            continue
        norm_path = _normalize_path(path)
        activity = activity_by_path.get(norm_path, {})
        merged.append(
            {
                "name": proj.get("name") or Path(norm_path).name,
                "path": norm_path,
                "grade": proj.get("grade", "F"),
                "score": int(proj.get("score", 0)),
                "categories": proj.get("categories") or {},
                "failing_checks": proj.get("failing_checks") or [],
                "days_since_last_commit": activity.get("days_since_last_commit"),
                "commits_30d": activity.get("commits_30d"),
                "has_cli": _derive_has_cli(activity),
                "raw": proj,
            }
        )
    return merged


def grade_distribution(projects: list[dict]) -> dict[str, int]:
    """Count projects per grade, always returning A-F keys."""
    dist = {g: 0 for g in ("A", "B", "C", "D", "F")}
    for p in projects:
        g = p.get("grade", "F")
        dist[g] = dist.get(g, 0) + 1
    return dist


def _grade_direction(prev: str, curr: str) -> str:
    """Return 'up', 'down', or 'flat' for a grade transition."""
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
    """Return one entry per project whose grade or score moved since prior snapshot.

    Projects with no prior snapshot are included with `grade_from = None` so the
    caller can distinguish "newly tracked" from "unchanged".
    """
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
        # Days since the prior snapshot — sweep timestamps are ISO8601 UTC.
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
    """Execute one portfolio sweep end-to-end.

    Args:
        root: Directory to scan (passed through to agent-ready --root).
        storage: Optional CommitStorage; one is created if not provided.
        persist: If False, skip writing to the database (dry-run).

    Returns:
        A summary dict suitable for `--json` output.
    """
    if not Path(root).exists():
        raise PortfolioSweepError(f"root does not exist: {root}")

    ar_bin = resolve_agent_ready_bin()
    if ar_bin is None:
        raise PortfolioSweepError(
            "agent-ready binary not found. Install it on PATH or set "
            "CODE_DAILY_AGENT_READY_BIN."
        )

    pa_bin = resolve_portfolio_audit_bin()
    activity_rows: list[dict] = []
    audit_warning: Optional[str] = None
    if pa_bin is None:
        audit_warning = (
            "portfolio-audit binary not found; activity fields will be null."
        )
    else:
        try:
            activity_rows = fetch_portfolio_audit(pa_bin)
        except PortfolioSweepError as e:
            audit_warning = f"portfolio-audit failed: {e}"

    agent_ready_payload = fetch_agent_ready(root, ar_bin)
    projects = merge_projects(agent_ready_payload, activity_rows)

    captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if storage is None:
        storage = CommitStorage()

    prior_by_path = storage.get_latest_per_project()

    if persist:
        storage.save_portfolio_snapshot(captured_at, projects)

    changes = compute_changes(projects, prior_by_path)

    return {
        "captured_at": captured_at,
        "root": _normalize_path(root),
        "persisted": persist,
        "project_count": len(projects),
        "grade_distribution": grade_distribution(projects),
        "changes": changes,
        "projects": projects,
        "warnings": [audit_warning] if audit_warning else [],
    }
