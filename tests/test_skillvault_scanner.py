"""Tests for the skillvault scanner."""

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.quest_manager import QuestManager
from src.skillvault_scanner import (
    DEFAULT_MARKERS,
    SkillvaultFinding,
    _resolve_skillvault_bin,
    _run_skillvault_search,
    scan_skillvault,
)
from src.storage import CommitStorage


# ---------------------------------------------------------------------------
# SkillvaultFinding
# ---------------------------------------------------------------------------


def test_source_ref_is_stable_for_same_content():
    f1 = SkillvaultFinding(
        project="code-daily",
        file_type="claude-md",
        file_path="/path/to/CLAUDE.md",
        marker="TODO",
        snippet="wire skillvault into quests discover",
    )
    f2 = SkillvaultFinding(
        project="code-daily",
        file_type="claude-md",
        file_path="/path/to/CLAUDE.md",
        marker="TODO",
        snippet="wire skillvault into quests discover",
    )
    assert f1.source_ref == f2.source_ref
    assert f1.source_ref.startswith("skillvault:/path/to/CLAUDE.md:TODO:")


def test_source_ref_differs_for_different_snippets():
    base = {
        "project": "code-daily",
        "file_type": "claude-md",
        "file_path": "/path/CLAUDE.md",
        "marker": "TODO",
    }
    a = SkillvaultFinding(**base, snippet="snippet A")
    b = SkillvaultFinding(**base, snippet="snippet B")
    assert a.source_ref != b.source_ref


def test_quest_title_truncates_long_snippets():
    long_snippet = "x" * 500
    finding = SkillvaultFinding(
        project="p",
        file_type="claude-md",
        file_path="/p",
        marker="TODO",
        snippet=long_snippet,
    )
    assert len(finding.quest_title) <= 200
    assert finding.quest_title.startswith("[skillvault/p] TODO:")


# ---------------------------------------------------------------------------
# _run_skillvault_search — subprocess handling
# ---------------------------------------------------------------------------


def _mock_completed(stdout: str, returncode: int = 0):
    return subprocess.CompletedProcess(
        args=["skillvault"], returncode=returncode, stdout=stdout, stderr=""
    )


def test_run_search_parses_json_results():
    payload = {
        "query": "TODO",
        "total_matches": 1,
        "results": [
            {
                "file_id": 4,
                "project": "code-daily",
                "file_type": "claude-md",
                "file_path": "/home/x/code-daily/CLAUDE.md",
                "snippet": "...TODO: wire skillvault...",
                "rank": -2.3,
                "last_scanned": "2026-04-10 01:19:50",
            }
        ],
    }
    with patch("src.skillvault_scanner.subprocess.run", return_value=_mock_completed(json.dumps(payload))):
        results = _run_skillvault_search("skillvault", "TODO", 10)
    assert len(results) == 1
    assert results[0]["project"] == "code-daily"


def test_run_search_returns_empty_on_file_not_found():
    with patch("src.skillvault_scanner.subprocess.run", side_effect=FileNotFoundError):
        assert _run_skillvault_search("skillvault", "TODO", 10) == []


def test_run_search_returns_empty_on_timeout():
    with patch(
        "src.skillvault_scanner.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="skillvault", timeout=30),
    ):
        assert _run_skillvault_search("skillvault", "TODO", 10) == []


def test_run_search_returns_empty_on_nonzero_exit():
    with patch(
        "src.skillvault_scanner.subprocess.run",
        return_value=_mock_completed("", returncode=1),
    ):
        assert _run_skillvault_search("skillvault", "TODO", 10) == []


def test_run_search_returns_empty_on_malformed_json():
    with patch(
        "src.skillvault_scanner.subprocess.run",
        return_value=_mock_completed("not json at all"),
    ):
        assert _run_skillvault_search("skillvault", "TODO", 10) == []


# ---------------------------------------------------------------------------
# scan_skillvault — end-to-end with mocks
# ---------------------------------------------------------------------------


def test_scan_returns_empty_when_binary_missing():
    with patch("src.skillvault_scanner._resolve_skillvault_bin", return_value=None):
        assert scan_skillvault() == []


def test_scan_aggregates_results_across_markers_and_dedupes():
    # Same file/snippet appearing for multiple markers should collapse.
    duplicate_hit = {
        "file_id": 1,
        "project": "code-daily",
        "file_type": "claude-md",
        "file_path": "/a/CLAUDE.md",
        "snippet": "TODO: planned work",
    }
    unique_hit = {
        "file_id": 2,
        "project": "skillvault",
        "file_type": "claude-md",
        "file_path": "/b/CLAUDE.md",
        "snippet": "coming soon: auto-scan on cron",
    }

    def fake_run(binary, query, limit):
        # Return the duplicate for both TODO and "planned" searches (same marker
        # bucket — dedup is per source_ref which includes the marker), and the
        # unique hit only for "coming soon".
        if query == "TODO":
            return [duplicate_hit]
        if query == "planned":
            return [duplicate_hit]
        if query == "coming soon":
            return [unique_hit]
        return []

    with patch("src.skillvault_scanner._resolve_skillvault_bin", return_value="skillvault"), \
         patch("src.skillvault_scanner._run_skillvault_search", side_effect=fake_run):
        findings = scan_skillvault(markers=("TODO", "planned", "coming soon"))

    # Two markers + one unique = 3 findings (TODO and planned produce different
    # source_refs because the marker is part of the ref).
    assert len(findings) == 3
    markers_seen = {f.marker for f in findings}
    assert markers_seen == {"TODO", "planned", "coming soon"}


def test_scan_skips_results_missing_file_path_or_snippet():
    bad_hits = [
        {"project": "x", "file_type": "y", "file_path": "", "snippet": "text"},
        {"project": "x", "file_type": "y", "file_path": "/p", "snippet": ""},
    ]
    with patch("src.skillvault_scanner._resolve_skillvault_bin", return_value="sv"), \
         patch("src.skillvault_scanner._run_skillvault_search", return_value=bad_hits):
        assert scan_skillvault(markers=("TODO",)) == []


# ---------------------------------------------------------------------------
# QuestManager.sync_skillvault_findings
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
    return CommitStorage(db_path=str(temp_db))


def _finding(path: str, marker: str, snippet: str) -> SkillvaultFinding:
    return SkillvaultFinding(
        project="code-daily",
        file_type="claude-md",
        file_path=path,
        marker=marker,
        snippet=snippet,
    )


def test_sync_creates_quests_from_findings(storage):
    qm = QuestManager(storage)
    findings = [
        _finding("/a/CLAUDE.md", "TODO", "wire skillvault into discover"),
        _finding("/b/CLAUDE.md", "ready to build", "publish typer-duo to PyPI"),
    ]
    result = qm.sync_skillvault_findings(findings)
    assert result == {"added": 2, "skipped": 0}

    all_quests = storage.get_quests()
    assert len(all_quests) == 2
    sources = {q["source"] for q in all_quests}
    assert sources == {"skillvault"}


def test_sync_is_idempotent(storage):
    qm = QuestManager(storage)
    findings = [_finding("/a/CLAUDE.md", "TODO", "same content")]
    first = qm.sync_skillvault_findings(findings)
    second = qm.sync_skillvault_findings(findings)
    assert first == {"added": 1, "skipped": 0}
    assert second == {"added": 0, "skipped": 1}
    assert len(storage.get_quests()) == 1


def test_sync_truncates_long_descriptions(storage):
    qm = QuestManager(storage)
    long_snippet = "x" * 800
    qm.sync_skillvault_findings([_finding("/a", "TODO", long_snippet)])
    quest = storage.get_quests()[0]
    assert len(quest["description"]) <= 500
