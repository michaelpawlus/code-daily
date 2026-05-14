"""Tests for the codebase audit writer."""

from __future__ import annotations

from pathlib import Path

from src.codebase_audit import (
    ensure_project_stubs,
    extract_project_names,
    write_codebase_audit_to_vault,
)


# --- extract_project_names ---

def test_extract_project_names_basic():
    body = "- [[conductor]] add diff\n- [[agent-cron]] add logs"
    assert extract_project_names(body) == {"conductor", "agent-cron"}


def test_extract_project_names_with_display_text():
    body = "- [[direct-mail|the advancement app]] wrap behind CLI"
    assert extract_project_names(body) == {"direct-mail"}


def test_extract_project_names_dedup():
    body = "- [[conductor]] item one\n- [[conductor]] item two"
    assert extract_project_names(body) == {"conductor"}


def test_extract_project_names_ignores_non_wikilinks():
    body = "- [conductor](https://example.com) markdown link, not a wiki-link"
    assert extract_project_names(body) == set()


def test_extract_project_names_empty():
    assert extract_project_names("") == set()


# --- ensure_project_stubs ---

def test_ensure_project_stubs_creates_missing(tmp_path):
    new = ensure_project_stubs(str(tmp_path), {"conductor", "agent-cron"})

    assert sorted(new) == ["agent-cron", "conductor"]
    assert (tmp_path / "projects" / "conductor.md").is_file()
    assert (tmp_path / "projects" / "agent-cron.md").is_file()

    content = (tmp_path / "projects" / "conductor.md").read_text()
    assert "# conductor" in content
    assert "Project hub" in content


def test_ensure_project_stubs_is_idempotent(tmp_path):
    ensure_project_stubs(str(tmp_path), {"conductor"})
    # Second call should skip — file already exists.
    new = ensure_project_stubs(str(tmp_path), {"conductor"})
    assert new == []


def test_ensure_project_stubs_dedups_by_slug(tmp_path):
    # "Conductor" and "conductor" slug to the same filename — only one stub.
    new = ensure_project_stubs(str(tmp_path), ["Conductor", "conductor"])
    assert len(new) == 1
    assert (tmp_path / "projects" / "conductor.md").is_file()


def test_ensure_project_stubs_empty(tmp_path):
    assert ensure_project_stubs(str(tmp_path), set()) == []
    # Hub directory still gets created so future calls find it.
    assert (tmp_path / "projects").is_dir()


def test_ensure_project_stubs_skips_empty_slugs(tmp_path):
    new = ensure_project_stubs(str(tmp_path), ["", "  ", "!!!"])
    assert new == []


# --- write_codebase_audit_to_vault ---

def test_write_codebase_audit_round_trip(tmp_path):
    body = (
        "- [[conductor]] add `doctor diff` — **S** — adds the trajectory view.\n"
        "- [[agent-cron]] add `logs failures --since 7d` — **S** — closes the triage loop.\n"
    )

    result = write_codebase_audit_to_vault(
        str(tmp_path),
        body,
        audit_date="2026-05-14",
    )

    expected_rel = Path("Project Ideas") / "codebase-enhancements-2026-05-14.md"
    assert result["audit_path"] == str(expected_rel)
    assert result["audit_absolute_path"] == str(tmp_path / expected_rel)
    assert result["linked_projects"] == ["agent-cron", "conductor"]
    assert result["new_stubs"] == ["agent-cron", "conductor"]

    # Audit file exists at the expected location with a header.
    audit_file = tmp_path / expected_rel
    assert audit_file.is_file()
    audit_content = audit_file.read_text()
    assert "Codebase Enhancements" in audit_content
    assert "[[conductor]]" in audit_content
    assert "[[agent-cron]]" in audit_content

    # Hub stubs exist.
    assert (tmp_path / "projects" / "conductor.md").is_file()
    assert (tmp_path / "projects" / "agent-cron.md").is_file()


def test_write_codebase_audit_preserves_agent_heading(tmp_path):
    body = (
        "# My Audit Title\n"
        "\n"
        "- [[conductor]] item\n"
    )
    result = write_codebase_audit_to_vault(
        str(tmp_path), body, audit_date="2026-05-14"
    )
    audit_content = (tmp_path / result["audit_path"]).read_text()
    # Agent's heading kept; our auto-header was NOT prepended.
    assert "My Audit Title" in audit_content
    assert "Codebase Enhancements —" not in audit_content


def test_write_codebase_audit_existing_stubs_not_new(tmp_path):
    # Pre-create the conductor hub. Audit should detect it and not re-create.
    ensure_project_stubs(str(tmp_path), {"conductor"})

    body = "- [[conductor]] item one\n- [[agent-cron]] item two\n"
    result = write_codebase_audit_to_vault(
        str(tmp_path), body, audit_date="2026-05-14"
    )

    assert result["linked_projects"] == ["agent-cron", "conductor"]
    assert result["new_stubs"] == ["agent-cron"]


def test_write_codebase_audit_overwrites_same_day(tmp_path):
    body1 = "- [[conductor]] first run\n"
    write_codebase_audit_to_vault(str(tmp_path), body1, audit_date="2026-05-14")

    body2 = "- [[conductor]] second run, different content\n"
    write_codebase_audit_to_vault(str(tmp_path), body2, audit_date="2026-05-14")

    audit_file = tmp_path / "Project Ideas" / "codebase-enhancements-2026-05-14.md"
    content = audit_file.read_text()
    assert "second run" in content
    assert "first run" not in content

    # No collision-suffixed file should exist.
    assert not (tmp_path / "Project Ideas" / "codebase-enhancements-2026-05-14-2.md").exists()
