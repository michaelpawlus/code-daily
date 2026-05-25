"""Shared helpers for quest discovery sources.

Each `run_*` function executes one discovery source and returns a dict with:
    {"status": "ok" | "skipped" | "error",
     "added": int,
     "skipped": int,
     "error": str (only when status == "error"),
     ...source-specific extras (repos_searched, scanned, total_gaps, from_cache)}

`"skipped"` means the source is unavailable (missing config, missing binary),
not a hard failure — the fan-out should continue and summarize.
"""

from __future__ import annotations

import json as json_mod
import shutil
import subprocess
from pathlib import Path


def run_sync_issues() -> dict:
    """Sync GitHub issues assigned to the user."""
    from src.config import GITHUB_TOKEN, GITHUB_USERNAME, validate_config
    from src.github_client import GitHubClient, GitHubClientError
    from src.quest_manager import QuestManager
    from src.storage import CommitStorage

    try:
        validate_config()
    except ValueError as e:
        return {"status": "skipped", "added": 0, "skipped": 0, "error": str(e)}

    client = GitHubClient(GITHUB_TOKEN, GITHUB_USERNAME)
    storage = CommitStorage()
    qm = QuestManager(storage)

    try:
        issues = client.get_assigned_issues(state="open", per_page=50)
    except GitHubClientError as e:
        return {"status": "error", "added": 0, "skipped": 0, "error": str(e)}

    result = qm.sync_github_issues(issues)
    return {"status": "ok", **result}


def run_scan_todos() -> dict:
    """Scan this project for TODO/FIXME comments."""
    from src.quest_manager import QuestManager
    from src.storage import CommitStorage
    from src.todo_scanner import scan_directory

    project_root = Path(__file__).parent.parent
    todos = scan_directory(project_root)

    storage = CommitStorage()
    qm = QuestManager(storage)
    result = qm.sync_todo_comments(todos)
    return {"status": "ok", **result}


def run_scan_skillvault() -> dict:
    """Scan skillvault for incomplete-work markers across all projects."""
    from src.quest_manager import QuestManager
    from src.skillvault_scanner import scan_skillvault
    from src.storage import CommitStorage

    findings = scan_skillvault()

    storage = CommitStorage()
    qm = QuestManager(storage)
    result = qm.sync_skillvault_findings(findings)
    result["scanned"] = len(findings)

    # `scan_skillvault()` returns [] silently when the binary or index is missing;
    # treat "no findings at all" as a soft skip so the fan-out can surface it.
    status = "skipped" if not findings else "ok"
    return {"status": status, **result}


def run_scan_launchpad(max_grade: str = "D") -> dict:
    """Scan launchpad scores for low-grade shippable projects and queue polish quests.

    Calls ``launchpad.run_sweep(persist=False)`` so this scan never writes a
    snapshot — ``launchpad sweep`` remains the single writer of snapshot rows.
    One quest per low-grade project (not per missing signal) to avoid flooding
    the queue; the description enumerates the missing signals.
    """
    from src.launchpad import _GRADE_ORDER, LaunchpadError, run_sweep
    from src.quest_manager import QuestManager
    from src.storage import CommitStorage

    threshold = _GRADE_ORDER.get(max_grade.upper())
    if threshold is None:
        return {"status": "error", "added": 0, "skipped": 0,
                "error": f"invalid max_grade {max_grade!r}; expected one of A-F"}

    try:
        sweep = run_sweep(persist=False)
    except LaunchpadError as e:
        return {"status": "error", "added": 0, "skipped": 0, "error": str(e)}

    low_grade = [
        p for p in sweep["projects"]
        if _GRADE_ORDER.get(p["grade"], 0) <= threshold
    ]

    storage = CommitStorage()
    qm = QuestManager(storage)
    result = qm.sync_launchpad_low_grades(low_grade)
    return {"status": "ok", "scanned": len(low_grade), "max_grade": max_grade.upper(), **result}


def run_sync_beacon_gaps(limit: int = 10) -> dict:
    """Sync skill gaps from the beacon CLI."""
    from src.storage import CommitStorage

    beacon_bin = shutil.which("beacon")
    if not beacon_bin:
        fallback = Path("/home/michaelpawlus/projects/beacon/.venv/bin/beacon")
        if fallback.exists():
            beacon_bin = str(fallback)

    if not beacon_bin:
        return {"status": "skipped", "added": 0, "skipped": 0, "error": "beacon CLI not found"}

    try:
        proc = subprocess.run(
            [beacon_bin, "gaps", "export", "--limit", str(limit), "--json"],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return {"status": "error", "added": 0, "skipped": 0, "error": f"beacon invocation failed: {e}"}

    if proc.returncode != 0:
        return {"status": "error", "added": 0, "skipped": 0,
                "error": "beacon gaps export returned non-zero (run 'beacon gaps analyze' first)"}

    try:
        gaps = json_mod.loads(proc.stdout)
    except json_mod.JSONDecodeError:
        return {"status": "error", "added": 0, "skipped": 0, "error": "invalid JSON from beacon"}

    storage = CommitStorage()
    added = 0
    skipped = 0
    for gap in gaps:
        source_ref = gap.get("source_ref", "")
        if storage.quest_exists_by_source_ref("beacon_gap", source_ref):
            skipped += 1
            continue
        storage.create_quest(
            title=gap["title"],
            source="beacon_gap",
            source_ref=source_ref,
            description=gap.get("description"),
        )
        added += 1

    return {"status": "ok", "added": added, "skipped": skipped, "total_gaps": len(gaps)}


def run_discover() -> dict:
    """Discover external good-first-issue candidates from starred repos."""
    from src.config import GITHUB_TOKEN, GITHUB_USERNAME, validate_config
    from src.github_client import GitHubClient, GitHubClientError
    from src.quest_manager import QuestManager
    from src.storage import CommitStorage

    try:
        validate_config()
    except ValueError as e:
        return {"status": "skipped", "added": 0, "skipped": 0, "error": str(e)}

    storage = CommitStorage()
    qm = QuestManager(storage)

    cache_key = "external_issues"
    cached_data = storage.get_cache(cache_key)

    if cached_data:
        issues = json_mod.loads(cached_data)
        result = qm.sync_external_issues(issues)
        return {"status": "ok", **result, "from_cache": True}

    client = GitHubClient(GITHUB_TOKEN, GITHUB_USERNAME)
    try:
        starred_repos = client.get_starred_repos(per_page=30)
        repo_names = [r.get("full_name") for r in starred_repos if r.get("full_name")]
        if not repo_names:
            return {"status": "ok", "added": 0, "skipped": 0,
                    "from_cache": False, "repos_searched": 0, "issues_found": 0}
        issues = client.search_good_first_issues(repo_names, per_page=20)
        storage.set_cache(cache_key, json_mod.dumps(issues), hours=24)
        sync_result = qm.sync_external_issues(issues)
        return {
            "status": "ok",
            **sync_result,
            "from_cache": False,
            "repos_searched": len(repo_names),
            "issues_found": len(issues),
        }
    except GitHubClientError as e:
        return {"status": "error", "added": 0, "skipped": 0, "error": str(e)}


# Ordered list used by `quests discover-all`. Local-only sources first, then
# network-bound. Each entry: (display_name, callable).
DISCOVERY_SOURCES = [
    ("scan-todos", run_scan_todos),
    ("scan-skillvault", run_scan_skillvault),
    ("scan-launchpad", run_scan_launchpad),
    ("sync-beacon-gaps", run_sync_beacon_gaps),
    ("sync-issues", run_sync_issues),
    ("discover", run_discover),
]


def run_all() -> dict:
    """Run every discovery source in order, aggregating results.

    Per-source exceptions are caught and reported as status="error" so one
    failing source does not abort the batch.
    """
    sources = []
    total_added = 0
    total_skipped = 0
    total_errors = 0

    for name, fn in DISCOVERY_SOURCES:
        try:
            result = fn()
        except Exception as e:  # noqa: BLE001 — we want to contain arbitrary failures
            result = {"status": "error", "added": 0, "skipped": 0, "error": f"{type(e).__name__}: {e}"}

        total_added += result.get("added", 0)
        total_skipped += result.get("skipped", 0)
        if result.get("status") == "error":
            total_errors += 1
        sources.append({"name": name, **result})

    return {
        "total_added": total_added,
        "total_skipped": total_skipped,
        "total_errors": total_errors,
        "sources": sources,
    }
