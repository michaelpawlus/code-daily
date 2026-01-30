"""
IDEAS.md integration for code-daily.

Provides utilities to read/write the IDEAS.md file and sync with the database.
"""

import re
from datetime import datetime
from pathlib import Path

from src.storage import CommitStorage


def _get_default_ideas_path() -> Path:
    """Get the default IDEAS.md path (project root)."""
    return Path(__file__).parent.parent / "IDEAS.md"


def read_ideas(ideas_path: Path | None = None) -> list[dict]:
    """
    Read ideas from IDEAS.md file.

    Parses markdown checkbox format:
    - [ ] Idea content (YYYY-MM-DD)
    - [x] Completed idea (YYYY-MM-DD)

    Args:
        ideas_path: Path to IDEAS.md. Uses default if not provided.

    Returns:
        List of idea dictionaries with content, completed, and date fields
    """
    if ideas_path is None:
        ideas_path = _get_default_ideas_path()

    if not ideas_path.exists():
        return []

    ideas = []
    content = ideas_path.read_text(encoding="utf-8")

    # Match markdown checkbox items: - [ ] or - [x] followed by content
    pattern = r"^-\s*\[([ xX])\]\s*(.+?)(?:\s*\((\d{4}-\d{2}-\d{2})\))?\s*$"

    for line in content.splitlines():
        match = re.match(pattern, line.strip())
        if match:
            checkbox, idea_content, date = match.groups()
            ideas.append({
                "content": idea_content.strip(),
                "completed": checkbox.lower() == "x",
                "date": date,
            })

    return ideas


def add_idea(content: str, ideas_path: Path | None = None) -> None:
    """
    Add a new idea to IDEAS.md file.

    Args:
        content: Idea content to add
        ideas_path: Path to IDEAS.md. Uses default if not provided.
    """
    if ideas_path is None:
        ideas_path = _get_default_ideas_path()

    today = datetime.now().strftime("%Y-%m-%d")
    new_line = f"- [ ] {content} ({today})\n"

    if ideas_path.exists():
        existing = ideas_path.read_text(encoding="utf-8")
        # Add new idea at the end, ensuring there's a newline before
        if existing and not existing.endswith("\n"):
            existing += "\n"
        ideas_path.write_text(existing + new_line, encoding="utf-8")
    else:
        # Create new file with header
        header = "# Ideas\n\nCoding ideas and tasks to work on.\n\n"
        ideas_path.write_text(header + new_line, encoding="utf-8")


def mark_idea_completed(content: str, ideas_path: Path | None = None) -> bool:
    """
    Mark an idea as completed in IDEAS.md.

    Args:
        content: Content of the idea to mark complete
        ideas_path: Path to IDEAS.md. Uses default if not provided.

    Returns:
        True if idea was found and marked, False otherwise
    """
    if ideas_path is None:
        ideas_path = _get_default_ideas_path()

    if not ideas_path.exists():
        return False

    file_content = ideas_path.read_text(encoding="utf-8")
    lines = file_content.splitlines()
    modified = False

    for i, line in enumerate(lines):
        # Check if this line contains our idea content
        if content in line and "- [ ]" in line:
            lines[i] = line.replace("- [ ]", "- [x]", 1)
            modified = True
            break

    if modified:
        ideas_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return modified


def sync_ideas_to_db(
    storage: CommitStorage | None = None,
    ideas_path: Path | None = None,
) -> dict:
    """
    Sync ideas from IDEAS.md to the database.

    Creates new ideas in the database for any ideas in the file
    that don't already exist. Marks completed ideas as 'completed' status.

    Args:
        storage: CommitStorage instance. Creates default if not provided.
        ideas_path: Path to IDEAS.md. Uses default if not provided.

    Returns:
        Dictionary with sync statistics (added, updated, total)
    """
    if storage is None:
        storage = CommitStorage()

    file_ideas = read_ideas(ideas_path)
    db_ideas = storage.get_ideas()

    # Create a set of existing idea contents for quick lookup
    existing_contents = {idea["content"] for idea in db_ideas}

    added = 0
    updated = 0

    for file_idea in file_ideas:
        content = file_idea["content"]

        if content not in existing_contents:
            # New idea - add to database
            idea_id = storage.create_idea(content)
            if file_idea["completed"]:
                storage.update_idea_status(idea_id, "completed")
            added += 1
        else:
            # Existing idea - check if status needs update
            for db_idea in db_ideas:
                if db_idea["content"] == content:
                    if file_idea["completed"] and db_idea["status"] != "completed":
                        storage.update_idea_status(db_idea["id"], "completed")
                        updated += 1
                    break

    return {
        "added": added,
        "updated": updated,
        "total_in_file": len(file_ideas),
        "total_in_db": len(db_ideas) + added,
    }


def sync_db_to_ideas(
    storage: CommitStorage | None = None,
    ideas_path: Path | None = None,
) -> dict:
    """
    Sync ideas from database to IDEAS.md file.

    Writes all active ideas from the database to the file.
    This is useful for ensuring the file reflects the database state.

    Args:
        storage: CommitStorage instance. Creates default if not provided.
        ideas_path: Path to IDEAS.md. Uses default if not provided.

    Returns:
        Dictionary with sync statistics
    """
    if storage is None:
        storage = CommitStorage()

    if ideas_path is None:
        ideas_path = _get_default_ideas_path()

    db_ideas = storage.get_ideas()

    # Read existing file to preserve header
    header = "# Ideas\n\nCoding ideas and tasks to work on.\n\n"
    if ideas_path.exists():
        content = ideas_path.read_text(encoding="utf-8")
        # Try to preserve existing header
        lines = content.splitlines()
        header_lines = []
        for line in lines:
            if line.startswith("- ["):
                break
            header_lines.append(line)
        if header_lines:
            header = "\n".join(header_lines) + "\n\n"

    # Generate idea lines
    idea_lines = []
    for idea in db_ideas:
        checkbox = "[x]" if idea["status"] == "completed" else "[ ]"
        date_str = idea.get("created_at", "")[:10] if idea.get("created_at") else ""
        date_part = f" ({date_str})" if date_str else ""
        idea_lines.append(f"- {checkbox} {idea['content']}{date_part}")

    # Write file
    file_content = header + "\n".join(idea_lines)
    if idea_lines:
        file_content += "\n"
    ideas_path.write_text(file_content, encoding="utf-8")

    return {
        "written": len(db_ideas),
    }
