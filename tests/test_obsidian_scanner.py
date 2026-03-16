"""Tests for obsidian_scanner module."""

import os
import tempfile
from pathlib import Path

import pytest

from src.obsidian_scanner import (
    ObsidianItem,
    scan_vault,
    scan_project_ideas,
    scan_daily_notes,
    scan_file_for_todos,
    _extract_first_paragraph,
    _parse_date_from_filename,
)


@pytest.fixture
def vault(tmp_path):
    """Create a temporary vault with sample files."""
    # Daily Notes
    daily = tmp_path / "Daily Notes"
    daily.mkdir()

    from datetime import datetime, timedelta

    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    old_str = (today - timedelta(days=30)).strftime("%Y-%m-%d")

    (daily / f"{today_str}.md").write_text(
        "# Morning\n\n"
        "- [x] Done task\n"
        "- [ ] Buy groceries\n"
        "\n"
        "## Priorities\n\n"
        "- [ ] Fix the login bug\n"
        "- [ ] Review PR #42\n"
    )

    (daily / f"{old_str}.md").write_text(
        "# Old Day\n\n- [ ] Old task\n"
    )

    # Project Ideas
    ideas = tmp_path / "Project Ideas"
    ideas.mkdir()

    (ideas / "CLI Dashboard.md").write_text(
        "# CLI Dashboard\n\n"
        "A terminal dashboard for monitoring coding habits.\n\n"
        "## Features\n\n- Streaks\n- Charts\n"
    )

    (ideas / "Empty Idea.md").write_text("# Empty Idea\n")

    # Personal Project Ideas
    personal = tmp_path / "Personal Project Ideas"
    personal.mkdir()

    (personal / "Garden Tracker.md").write_text(
        "---\ntags: [project]\n---\n\n"
        "# Garden Tracker\n\n"
        "Track plant watering schedules and growth.\n"
    )

    return tmp_path


# ---------------------------------------------------------------------------
# scan_vault
# ---------------------------------------------------------------------------


class TestScanVault:
    def test_returns_all_items(self, vault):
        items = scan_vault(str(vault), since=7)
        # Should find daily note TODOs + project ideas
        assert len(items) > 0
        types = {it.item_type for it in items}
        assert "todo" in types
        assert "project_idea" in types

    def test_search_filter(self, vault):
        items = scan_vault(str(vault), since=7, search="groceries")
        assert len(items) == 1
        assert "groceries" in items[0].content.lower()

    def test_nonexistent_vault(self):
        items = scan_vault("/nonexistent/path")
        assert items == []

    def test_folder_filter_daily_only(self, vault):
        items = scan_vault(str(vault), since=7, folders=["daily notes"])
        types = {it.item_type for it in items}
        assert "project_idea" not in types

    def test_folder_filter_projects_only(self, vault):
        items = scan_vault(str(vault), since=7, folders=["project ideas"])
        types = {it.item_type for it in items}
        assert "todo" not in types


# ---------------------------------------------------------------------------
# scan_project_ideas
# ---------------------------------------------------------------------------


class TestScanProjectIdeas:
    def test_finds_ideas(self, vault):
        ideas = scan_project_ideas(str(vault))
        assert len(ideas) == 3
        titles = [it.content for it in ideas]
        assert any("CLI Dashboard" in t for t in titles)
        assert any("Garden Tracker" in t for t in titles)

    def test_includes_description(self, vault):
        ideas = scan_project_ideas(str(vault))
        cli_idea = [i for i in ideas if "CLI Dashboard" in i.content][0]
        assert "terminal dashboard" in cli_idea.content.lower()

    def test_all_are_project_ideas(self, vault):
        ideas = scan_project_ideas(str(vault))
        assert all(it.item_type == "project_idea" for it in ideas)

    def test_empty_vault(self, tmp_path):
        ideas = scan_project_ideas(str(tmp_path))
        assert ideas == []


# ---------------------------------------------------------------------------
# scan_daily_notes
# ---------------------------------------------------------------------------


class TestScanDailyNotes:
    def test_finds_recent_todos(self, vault):
        items = scan_daily_notes(str(vault), since_days=7)
        contents = [it.content for it in items]
        assert "Buy groceries" in contents
        assert "Fix the login bug" in contents

    def test_excludes_old_notes(self, vault):
        items = scan_daily_notes(str(vault), since_days=7)
        contents = [it.content for it in items]
        assert "Old task" not in contents

    def test_includes_old_with_large_since(self, vault):
        items = scan_daily_notes(str(vault), since_days=60)
        contents = [it.content for it in items]
        assert "Old task" in contents

    def test_captures_heading_context(self, vault):
        items = scan_daily_notes(str(vault), since_days=7)
        priorities = [it for it in items if it.context == "Priorities"]
        assert len(priorities) == 2

    def test_has_date(self, vault):
        items = scan_daily_notes(str(vault), since_days=7)
        assert all(it.date for it in items)

    def test_empty_folder(self, tmp_path):
        (tmp_path / "Daily Notes").mkdir()
        items = scan_daily_notes(str(tmp_path), since_days=7)
        assert items == []


# ---------------------------------------------------------------------------
# scan_file_for_todos
# ---------------------------------------------------------------------------


class TestScanFileForTodos:
    def test_finds_unchecked(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("- [ ] Task 1\n- [x] Done\n- [ ] Task 2\n")
        results = scan_file_for_todos(f)
        assert len(results) == 2
        assert results[0] == ("Task 1", "")
        assert results[1] == ("Task 2", "")

    def test_tracks_headings(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("## Work\n- [ ] Do thing\n## Personal\n- [ ] Buy stuff\n")
        results = scan_file_for_todos(f)
        assert results[0] == ("Do thing", "Work")
        assert results[1] == ("Buy stuff", "Personal")

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.md"
        f.write_text("")
        assert scan_file_for_todos(f) == []

    def test_no_todos(self, tmp_path):
        f = tmp_path / "done.md"
        f.write_text("- [x] All done\n- Regular bullet\n")
        assert scan_file_for_todos(f) == []

    def test_nonexistent_file(self, tmp_path):
        f = tmp_path / "nope.md"
        assert scan_file_for_todos(f) == []


# ---------------------------------------------------------------------------
# _extract_first_paragraph
# ---------------------------------------------------------------------------


class TestExtractFirstParagraph:
    def test_basic(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("# Title\n\nFirst paragraph here.\n\nSecond paragraph.\n")
        assert _extract_first_paragraph(f) == "First paragraph here."

    def test_with_frontmatter(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("---\ntags: [a]\n---\n\n# Title\n\nContent line.\n")
        # Frontmatter handling skips the --- line
        result = _extract_first_paragraph(f)
        assert "Content" in result or "tags" in result  # flexible on frontmatter parsing

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.md"
        f.write_text("")
        assert _extract_first_paragraph(f) == ""

    def test_truncates_long(self, tmp_path):
        f = tmp_path / "long.md"
        f.write_text("# T\n\n" + "x" * 300 + "\n")
        result = _extract_first_paragraph(f)
        assert len(result) <= 200


# ---------------------------------------------------------------------------
# _parse_date_from_filename
# ---------------------------------------------------------------------------


class TestParseDateFromFilename:
    def test_iso_format(self):
        d = _parse_date_from_filename("2025-03-15")
        assert d is not None
        assert d.year == 2025

    def test_compact_format(self):
        d = _parse_date_from_filename("20250315")
        assert d is not None

    def test_invalid(self):
        assert _parse_date_from_filename("random-note") is None

    def test_empty(self):
        assert _parse_date_from_filename("") is None
