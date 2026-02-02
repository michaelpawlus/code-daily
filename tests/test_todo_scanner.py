"""Tests for the TODO/FIXME scanner."""

import tempfile
from pathlib import Path

import pytest

from src.todo_scanner import TodoComment, scan_file, scan_directory
from src.storage import CommitStorage
from src.quest_manager import QuestManager


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_db():
    """Create a temporary database file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def storage(temp_db):
    """Create a CommitStorage instance with a temporary database."""
    return CommitStorage(temp_db)


@pytest.fixture
def quest_manager(storage):
    """Create a QuestManager instance."""
    return QuestManager(storage)


class TestTodoComment:
    """Tests for TodoComment dataclass."""

    def test_source_ref_property(self):
        """source_ref returns file:line format."""
        todo = TodoComment(
            file_path="src/app.py",
            line_number=42,
            comment_type="TODO",
            content="Fix this later",
        )
        assert todo.source_ref == "src/app.py:42"

    def test_source_ref_with_nested_path(self):
        """source_ref works with nested paths."""
        todo = TodoComment(
            file_path="src/utils/helpers.py",
            line_number=100,
            comment_type="FIXME",
            content="Broken",
        )
        assert todo.source_ref == "src/utils/helpers.py:100"


class TestScanFile:
    """Tests for scan_file function."""

    def test_scan_todo_comment(self, temp_dir):
        """Finds TODO comments."""
        file_path = temp_dir / "test.py"
        file_path.write_text("# TODO: Implement this function\ndef foo(): pass\n")

        todos = scan_file(file_path)

        assert len(todos) == 1
        assert todos[0].comment_type == "TODO"
        assert todos[0].content == "Implement this function"
        assert todos[0].line_number == 1

    def test_scan_fixme_comment(self, temp_dir):
        """Finds FIXME comments."""
        file_path = temp_dir / "test.py"
        file_path.write_text("def foo():\n    # FIXME: This is broken\n    pass\n")

        todos = scan_file(file_path)

        assert len(todos) == 1
        assert todos[0].comment_type == "FIXME"
        assert todos[0].content == "This is broken"
        assert todos[0].line_number == 2

    def test_scan_hack_comment(self, temp_dir):
        """Finds HACK comments."""
        file_path = temp_dir / "test.py"
        file_path.write_text("# HACK: Workaround for bug\nx = 1\n")

        todos = scan_file(file_path)

        assert len(todos) == 1
        assert todos[0].comment_type == "HACK"
        assert todos[0].content == "Workaround for bug"

    def test_scan_xxx_comment(self, temp_dir):
        """Finds XXX comments."""
        file_path = temp_dir / "test.py"
        file_path.write_text("# XXX: Needs review\nclass Foo: pass\n")

        todos = scan_file(file_path)

        assert len(todos) == 1
        assert todos[0].comment_type == "XXX"
        assert todos[0].content == "Needs review"

    def test_scan_multiple_comments(self, temp_dir):
        """Finds multiple TODO/FIXME comments."""
        file_path = temp_dir / "test.py"
        file_path.write_text(
            "# TODO: First task\n"
            "def foo():\n"
            "    # FIXME: Second task\n"
            "    pass\n"
            "# XXX: Third task\n"
        )

        todos = scan_file(file_path)

        assert len(todos) == 3
        assert todos[0].comment_type == "TODO"
        assert todos[0].line_number == 1
        assert todos[1].comment_type == "FIXME"
        assert todos[1].line_number == 3
        assert todos[2].comment_type == "XXX"
        assert todos[2].line_number == 5

    def test_scan_case_insensitive(self, temp_dir):
        """Comment types are case-insensitive but normalized to uppercase."""
        file_path = temp_dir / "test.py"
        file_path.write_text("# todo: lowercase\n# Todo: Mixed case\n# TODO: Upper\n")

        todos = scan_file(file_path)

        assert len(todos) == 3
        assert all(t.comment_type == "TODO" for t in todos)

    def test_scan_empty_file(self, temp_dir):
        """Returns empty list for empty file."""
        file_path = temp_dir / "test.py"
        file_path.write_text("")

        todos = scan_file(file_path)

        assert todos == []

    def test_scan_no_todos(self, temp_dir):
        """Returns empty list when no TODOs found."""
        file_path = temp_dir / "test.py"
        file_path.write_text("# Regular comment\ndef foo(): pass\n")

        todos = scan_file(file_path)

        assert todos == []

    def test_scan_file_not_found(self, temp_dir):
        """Returns empty list for non-existent file."""
        file_path = temp_dir / "nonexistent.py"

        todos = scan_file(file_path)

        assert todos == []

    def test_scan_requires_colon(self, temp_dir):
        """TODO without colon is not matched."""
        file_path = temp_dir / "test.py"
        file_path.write_text("# TODO without colon\n# TODO: with colon\n")

        todos = scan_file(file_path)

        assert len(todos) == 1
        assert todos[0].content == "with colon"


class TestScanDirectory:
    """Tests for scan_directory function."""

    def test_scan_single_file(self, temp_dir):
        """Scans a single Python file."""
        file_path = temp_dir / "app.py"
        file_path.write_text("# TODO: Test this\n")

        todos = scan_directory(temp_dir)

        assert len(todos) == 1
        assert todos[0].file_path == "app.py"
        assert todos[0].comment_type == "TODO"

    def test_scan_nested_files(self, temp_dir):
        """Scans files in nested directories."""
        src_dir = temp_dir / "src"
        src_dir.mkdir()
        (src_dir / "app.py").write_text("# TODO: In src\n")
        (src_dir / "utils.py").write_text("# FIXME: Also in src\n")

        todos = scan_directory(temp_dir)

        assert len(todos) == 2
        paths = [t.file_path for t in todos]
        assert "src/app.py" in paths
        assert "src/utils.py" in paths

    def test_scan_excludes_venv(self, temp_dir):
        """Excludes .venv directory."""
        venv_dir = temp_dir / ".venv"
        venv_dir.mkdir()
        (venv_dir / "lib.py").write_text("# TODO: Should be ignored\n")
        (temp_dir / "app.py").write_text("# TODO: Should be found\n")

        todos = scan_directory(temp_dir)

        assert len(todos) == 1
        assert todos[0].file_path == "app.py"

    def test_scan_excludes_pycache(self, temp_dir):
        """Excludes __pycache__ directory."""
        cache_dir = temp_dir / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "module.cpython-39.py").write_text("# TODO: Ignored\n")
        (temp_dir / "app.py").write_text("# TODO: Found\n")

        todos = scan_directory(temp_dir)

        assert len(todos) == 1
        assert todos[0].file_path == "app.py"

    def test_scan_excludes_git(self, temp_dir):
        """Excludes .git directory."""
        git_dir = temp_dir / ".git"
        git_dir.mkdir()
        (git_dir / "hooks.py").write_text("# TODO: Ignored\n")
        (temp_dir / "app.py").write_text("# TODO: Found\n")

        todos = scan_directory(temp_dir)

        assert len(todos) == 1

    def test_scan_excludes_nested_excluded_dir(self, temp_dir):
        """Excludes nested excluded directories."""
        nested = temp_dir / "src" / "__pycache__"
        nested.mkdir(parents=True)
        (nested / "cache.py").write_text("# TODO: Ignored\n")
        (temp_dir / "src" / "app.py").write_text("# TODO: Found\n")

        todos = scan_directory(temp_dir)

        assert len(todos) == 1
        assert todos[0].file_path == "src/app.py"

    def test_scan_only_python_files(self, temp_dir):
        """Only scans .py files."""
        (temp_dir / "app.py").write_text("# TODO: Python file\n")
        (temp_dir / "script.js").write_text("// TODO: JavaScript file\n")
        (temp_dir / "readme.md").write_text("TODO: Markdown file\n")

        todos = scan_directory(temp_dir)

        assert len(todos) == 1
        assert todos[0].file_path == "app.py"

    def test_scan_returns_relative_paths(self, temp_dir):
        """Returns relative paths from root."""
        nested = temp_dir / "src" / "utils"
        nested.mkdir(parents=True)
        (nested / "helpers.py").write_text("# TODO: Deep nested\n")

        todos = scan_directory(temp_dir)

        assert len(todos) == 1
        assert todos[0].file_path == "src/utils/helpers.py"

    def test_scan_empty_directory(self, temp_dir):
        """Returns empty list for empty directory."""
        todos = scan_directory(temp_dir)
        assert todos == []

    def test_scan_excludes_tests_directory(self, temp_dir):
        """Excludes tests/ directory."""
        tests_dir = temp_dir / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_app.py").write_text("# TODO: Should be ignored\n")
        (temp_dir / "app.py").write_text("# TODO: Should be found\n")

        todos = scan_directory(temp_dir)

        assert len(todos) == 1
        assert todos[0].file_path == "app.py"

    def test_scan_excludes_test_prefix_files(self, temp_dir):
        """Excludes test_*.py files in any directory."""
        src_dir = temp_dir / "src"
        src_dir.mkdir()
        (src_dir / "test_utils.py").write_text("# TODO: Should be ignored\n")
        (src_dir / "utils.py").write_text("# TODO: Should be found\n")

        todos = scan_directory(temp_dir)

        assert len(todos) == 1
        assert todos[0].file_path == "src/utils.py"

    def test_scan_excludes_test_suffix_files(self, temp_dir):
        """Excludes *_test.py files in any directory."""
        src_dir = temp_dir / "src"
        src_dir.mkdir()
        (src_dir / "utils_test.py").write_text("# TODO: Should be ignored\n")
        (src_dir / "utils.py").write_text("# TODO: Should be found\n")

        todos = scan_directory(temp_dir)

        assert len(todos) == 1
        assert todos[0].file_path == "src/utils.py"

    def test_scan_excludes_conftest(self, temp_dir):
        """Excludes conftest.py files."""
        (temp_dir / "conftest.py").write_text("# TODO: Should be ignored\n")
        (temp_dir / "app.py").write_text("# TODO: Should be found\n")

        todos = scan_directory(temp_dir)

        assert len(todos) == 1
        assert todos[0].file_path == "app.py"

    def test_scan_includes_non_test_files(self, temp_dir):
        """Non-test Python files are still scanned."""
        src_dir = temp_dir / "src"
        src_dir.mkdir()
        (src_dir / "app.py").write_text("# TODO: Main app\n")
        (src_dir / "utils.py").write_text("# TODO: Utilities\n")
        (src_dir / "models.py").write_text("# FIXME: Models\n")

        todos = scan_directory(temp_dir)

        assert len(todos) == 3
        paths = [t.file_path for t in todos]
        assert "src/app.py" in paths
        assert "src/utils.py" in paths
        assert "src/models.py" in paths


class TestSyncTodoComments:
    """Tests for QuestManager.sync_todo_comments method."""

    def test_sync_creates_quest(self, quest_manager, storage):
        """Syncing creates a quest from TODO comment."""
        todos = [
            TodoComment(
                file_path="src/app.py",
                line_number=42,
                comment_type="TODO",
                content="Implement feature X",
            )
        ]

        result = quest_manager.sync_todo_comments(todos)

        assert result["added"] == 1
        assert result["skipped"] == 0

        quests = storage.get_quests()
        assert len(quests) == 1
        assert quests[0]["title"] == "[TODO] Implement feature X"
        assert quests[0]["source"] == "todo_scan"
        assert quests[0]["source_ref"] == "src/app.py:42"

    def test_sync_skips_existing(self, quest_manager, storage):
        """Syncing skips already synced TODOs."""
        # Create existing quest
        storage.create_quest(
            title="[TODO] Already synced",
            source="todo_scan",
            source_ref="src/app.py:42",
        )

        todos = [
            TodoComment(
                file_path="src/app.py",
                line_number=42,
                comment_type="TODO",
                content="Already synced",
            )
        ]

        result = quest_manager.sync_todo_comments(todos)

        assert result["added"] == 0
        assert result["skipped"] == 1

        quests = storage.get_quests()
        assert len(quests) == 1

    def test_sync_multiple_todos(self, quest_manager, storage):
        """Syncing handles multiple TODOs."""
        todos = [
            TodoComment("src/app.py", 10, "TODO", "First task"),
            TodoComment("src/app.py", 20, "FIXME", "Second task"),
            TodoComment("src/utils.py", 5, "HACK", "Third task"),
        ]

        result = quest_manager.sync_todo_comments(todos)

        assert result["added"] == 3
        assert result["skipped"] == 0

        quests = storage.get_quests()
        assert len(quests) == 3

    def test_sync_preserves_comment_type_in_title(self, quest_manager, storage):
        """Title includes the comment type prefix."""
        todos = [
            TodoComment("a.py", 1, "TODO", "Task 1"),
            TodoComment("b.py", 1, "FIXME", "Task 2"),
            TodoComment("c.py", 1, "HACK", "Task 3"),
            TodoComment("d.py", 1, "XXX", "Task 4"),
        ]

        quest_manager.sync_todo_comments(todos)

        quests = storage.get_quests()
        titles = [q["title"] for q in quests]

        assert "[TODO] Task 1" in titles
        assert "[FIXME] Task 2" in titles
        assert "[HACK] Task 3" in titles
        assert "[XXX] Task 4" in titles

    def test_sync_truncates_long_content(self, quest_manager, storage):
        """Syncing truncates very long TODO content."""
        long_content = "x" * 250
        todos = [
            TodoComment("app.py", 1, "TODO", long_content)
        ]

        quest_manager.sync_todo_comments(todos)

        quests = storage.get_quests()
        assert len(quests[0]["title"]) == 200
        assert quests[0]["title"].endswith("...")

    def test_sync_deduplication_by_source_ref(self, quest_manager, storage):
        """Deduplication uses source_ref (file:line)."""
        # First sync
        todos1 = [
            TodoComment("app.py", 10, "TODO", "Original content")
        ]
        result1 = quest_manager.sync_todo_comments(todos1)
        assert result1["added"] == 1

        # Same file:line but different content - should be skipped
        todos2 = [
            TodoComment("app.py", 10, "TODO", "Updated content")
        ]
        result2 = quest_manager.sync_todo_comments(todos2)
        assert result2["added"] == 0
        assert result2["skipped"] == 1

        # Different line - should be added
        todos3 = [
            TodoComment("app.py", 11, "TODO", "New line")
        ]
        result3 = quest_manager.sync_todo_comments(todos3)
        assert result3["added"] == 1

    def test_sync_empty_list(self, quest_manager):
        """Syncing empty list returns zeros."""
        result = quest_manager.sync_todo_comments([])

        assert result["added"] == 0
        assert result["skipped"] == 0
