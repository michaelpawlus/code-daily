"""
TODO/FIXME scanner for Python code.

Scans Python files for TODO, FIXME, HACK, and XXX comments and surfaces them
as quest suggestions.
"""

import re
from dataclasses import dataclass
from pathlib import Path

# Regex pattern to match TODO, FIXME, HACK, XXX comments
# Matches: # TODO: content, # FIXME: content, etc.
TODO_PATTERN = re.compile(r"#\s*(TODO|FIXME|HACK|XXX):\s*(.+)", re.IGNORECASE)

# Directories to exclude from scanning
EXCLUDED_DIRS = {".venv", "__pycache__", ".git", "node_modules", ".tox", ".pytest_cache", "tests"}

# Test file patterns to exclude (test-specific TODOs are usually not actionable production work)
TEST_FILE_PATTERNS = {"conftest.py"}


@dataclass
class TodoComment:
    """Represents a TODO/FIXME comment found in code."""

    file_path: str
    line_number: int
    comment_type: str  # TODO, FIXME, HACK, or XXX
    content: str

    @property
    def source_ref(self) -> str:
        """Return source reference in file:line format."""
        return f"{self.file_path}:{self.line_number}"


def scan_file(path: Path) -> list[TodoComment]:
    """
    Scan a single file for TODO/FIXME comments.

    Args:
        path: Path to the file to scan

    Returns:
        List of TodoComment objects found in the file
    """
    todos = []

    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return todos

    for line_number, line in enumerate(content.splitlines(), start=1):
        match = TODO_PATTERN.search(line)
        if match:
            comment_type = match.group(1).upper()
            comment_content = match.group(2).strip()

            todos.append(
                TodoComment(
                    file_path=str(path),
                    line_number=line_number,
                    comment_type=comment_type,
                    content=comment_content,
                )
            )

    return todos


def scan_directory(root: Path) -> list[TodoComment]:
    """
    Recursively scan a directory for TODO/FIXME comments in Python files.

    Args:
        root: Root directory to scan

    Returns:
        List of TodoComment objects found, with relative paths
    """
    todos = []
    root = root.resolve()

    for path in root.rglob("*.py"):
        # Check if any parent directory should be excluded
        rel_path = path.relative_to(root)
        if any(part in EXCLUDED_DIRS for part in rel_path.parts):
            continue

        # Check if file matches test patterns
        filename = path.name
        if filename.startswith("test_") or filename.endswith("_test.py") or filename in TEST_FILE_PATTERNS:
            continue

        # Scan the file and convert to relative paths
        file_todos = scan_file(path)
        for todo in file_todos:
            todo.file_path = str(rel_path)

        todos.extend(file_todos)

    return todos
