"""Tests for the ideas module."""

import tempfile
from pathlib import Path

import pytest

from src.storage import CommitStorage
from src.ideas import (
    read_ideas,
    add_idea,
    mark_idea_completed,
    sync_ideas_to_db,
    sync_db_to_ideas,
)


@pytest.fixture
def temp_ideas_file():
    """Create a temporary IDEAS.md file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("# Ideas\n\nCoding ideas and tasks to work on.\n\n")
        ideas_path = Path(f.name)
    yield ideas_path
    if ideas_path.exists():
        ideas_path.unlink()


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def storage(temp_db):
    """Create a CommitStorage instance."""
    return CommitStorage(temp_db)


class TestReadIdeas:
    """Tests for read_ideas function."""

    def test_read_empty_file(self, temp_ideas_file):
        """Returns empty list for file with no ideas."""
        ideas = read_ideas(temp_ideas_file)
        assert ideas == []

    def test_read_single_idea(self, temp_ideas_file):
        """Can read a single idea."""
        temp_ideas_file.write_text(
            "# Ideas\n\n- [ ] Build feature X (2025-01-25)\n"
        )

        ideas = read_ideas(temp_ideas_file)

        assert len(ideas) == 1
        assert ideas[0]["content"] == "Build feature X"
        assert ideas[0]["completed"] is False
        assert ideas[0]["date"] == "2025-01-25"

    def test_read_multiple_ideas(self, temp_ideas_file):
        """Can read multiple ideas."""
        temp_ideas_file.write_text(
            "# Ideas\n\n"
            "- [ ] First idea (2025-01-25)\n"
            "- [x] Second idea (2025-01-24)\n"
            "- [ ] Third idea (2025-01-23)\n"
        )

        ideas = read_ideas(temp_ideas_file)

        assert len(ideas) == 3
        assert ideas[0]["content"] == "First idea"
        assert ideas[0]["completed"] is False
        assert ideas[1]["content"] == "Second idea"
        assert ideas[1]["completed"] is True
        assert ideas[2]["content"] == "Third idea"

    def test_read_idea_without_date(self, temp_ideas_file):
        """Can read idea without date."""
        temp_ideas_file.write_text("# Ideas\n\n- [ ] No date idea\n")

        ideas = read_ideas(temp_ideas_file)

        assert len(ideas) == 1
        assert ideas[0]["content"] == "No date idea"
        assert ideas[0]["date"] is None

    def test_read_completed_idea(self, temp_ideas_file):
        """Can read completed ideas with [x]."""
        temp_ideas_file.write_text("# Ideas\n\n- [x] Done task (2025-01-25)\n")

        ideas = read_ideas(temp_ideas_file)

        assert len(ideas) == 1
        assert ideas[0]["completed"] is True

    def test_read_completed_idea_uppercase(self, temp_ideas_file):
        """Handles uppercase X for completed."""
        temp_ideas_file.write_text("# Ideas\n\n- [X] Done task (2025-01-25)\n")

        ideas = read_ideas(temp_ideas_file)

        assert len(ideas) == 1
        assert ideas[0]["completed"] is True

    def test_read_nonexistent_file(self):
        """Returns empty list for non-existent file."""
        fake_path = Path("/nonexistent/IDEAS.md")
        ideas = read_ideas(fake_path)
        assert ideas == []


class TestAddIdea:
    """Tests for add_idea function."""

    def test_add_idea_to_existing_file(self, temp_ideas_file):
        """Can add idea to existing file."""
        add_idea("New feature idea", temp_ideas_file)

        content = temp_ideas_file.read_text()
        assert "- [ ] New feature idea" in content
        assert "(" in content  # Should have date

    def test_add_idea_creates_file(self):
        """Creates file if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ideas_path = Path(tmpdir) / "IDEAS.md"
            assert not ideas_path.exists()

            add_idea("First idea", ideas_path)

            assert ideas_path.exists()
            content = ideas_path.read_text()
            assert "# Ideas" in content
            assert "- [ ] First idea" in content

    def test_add_multiple_ideas(self, temp_ideas_file):
        """Can add multiple ideas."""
        add_idea("Idea 1", temp_ideas_file)
        add_idea("Idea 2", temp_ideas_file)
        add_idea("Idea 3", temp_ideas_file)

        ideas = read_ideas(temp_ideas_file)
        assert len(ideas) == 3


class TestMarkIdeaCompleted:
    """Tests for mark_idea_completed function."""

    def test_mark_completed(self, temp_ideas_file):
        """Can mark an idea as completed."""
        temp_ideas_file.write_text(
            "# Ideas\n\n- [ ] Complete me (2025-01-25)\n"
        )

        result = mark_idea_completed("Complete me", temp_ideas_file)

        assert result is True
        content = temp_ideas_file.read_text()
        assert "- [x] Complete me" in content

    def test_mark_completed_not_found(self, temp_ideas_file):
        """Returns False when idea not found."""
        temp_ideas_file.write_text("# Ideas\n\n- [ ] Other idea\n")

        result = mark_idea_completed("Nonexistent idea", temp_ideas_file)

        assert result is False

    def test_mark_completed_nonexistent_file(self):
        """Returns False for non-existent file."""
        fake_path = Path("/nonexistent/IDEAS.md")
        result = mark_idea_completed("Some idea", fake_path)
        assert result is False

    def test_mark_completed_preserves_other_ideas(self, temp_ideas_file):
        """Marking one idea doesn't affect others."""
        temp_ideas_file.write_text(
            "# Ideas\n\n"
            "- [ ] Keep open\n"
            "- [ ] Mark this done\n"
            "- [ ] Also keep open\n"
        )

        mark_idea_completed("Mark this done", temp_ideas_file)

        ideas = read_ideas(temp_ideas_file)
        assert ideas[0]["completed"] is False
        assert ideas[1]["completed"] is True
        assert ideas[2]["completed"] is False


class TestSyncIdeasToDb:
    """Tests for sync_ideas_to_db function."""

    def test_sync_adds_new_ideas(self, storage, temp_ideas_file):
        """Syncs new ideas from file to database."""
        temp_ideas_file.write_text(
            "# Ideas\n\n"
            "- [ ] Idea from file 1 (2025-01-25)\n"
            "- [ ] Idea from file 2 (2025-01-24)\n"
        )

        result = sync_ideas_to_db(storage, temp_ideas_file)

        assert result["added"] == 2
        assert result["total_in_file"] == 2

        db_ideas = storage.get_ideas()
        assert len(db_ideas) == 2

    def test_sync_updates_completed_status(self, storage, temp_ideas_file):
        """Syncs completed status from file to database."""
        # First sync with uncompleted idea
        temp_ideas_file.write_text("# Ideas\n\n- [ ] Test idea (2025-01-25)\n")
        sync_ideas_to_db(storage, temp_ideas_file)

        # Now mark as completed in file
        temp_ideas_file.write_text("# Ideas\n\n- [x] Test idea (2025-01-25)\n")
        result = sync_ideas_to_db(storage, temp_ideas_file)

        assert result["updated"] == 1

        db_ideas = storage.get_ideas()
        # The idea should now be completed, so it won't appear in active
        completed = storage.get_ideas(status="completed")
        assert len(completed) == 1

    def test_sync_handles_duplicates(self, storage, temp_ideas_file):
        """Doesn't add duplicate ideas."""
        temp_ideas_file.write_text("# Ideas\n\n- [ ] Same idea (2025-01-25)\n")

        sync_ideas_to_db(storage, temp_ideas_file)
        result = sync_ideas_to_db(storage, temp_ideas_file)

        assert result["added"] == 0
        db_ideas = storage.get_ideas()
        assert len(db_ideas) == 1


class TestSyncDbToIdeas:
    """Tests for sync_db_to_ideas function."""

    def test_sync_writes_ideas_to_file(self, storage, temp_ideas_file):
        """Writes database ideas to file."""
        storage.create_idea("DB idea 1")
        storage.create_idea("DB idea 2")

        result = sync_db_to_ideas(storage, temp_ideas_file)

        assert result["written"] == 2
        ideas = read_ideas(temp_ideas_file)
        assert len(ideas) == 2

    def test_sync_includes_completed_status(self, storage, temp_ideas_file):
        """Includes completed status in file."""
        i1 = storage.create_idea("Active idea")
        i2 = storage.create_idea("Completed idea")
        storage.update_idea_status(i2, "completed")

        sync_db_to_ideas(storage, temp_ideas_file)

        ideas = read_ideas(temp_ideas_file)
        active = [i for i in ideas if not i["completed"]]
        completed = [i for i in ideas if i["completed"]]

        assert len(active) == 1
        assert len(completed) == 1

    def test_sync_preserves_header(self, temp_ideas_file, storage):
        """Preserves existing file header."""
        temp_ideas_file.write_text(
            "# My Custom Header\n\n"
            "Custom description here.\n\n"
            "- [ ] Old idea\n"
        )

        storage.create_idea("New idea")
        sync_db_to_ideas(storage, temp_ideas_file)

        content = temp_ideas_file.read_text()
        assert "# My Custom Header" in content
        assert "Custom description" in content
