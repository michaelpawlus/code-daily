"""
Obsidian vault scanner via direct file I/O.

Scans the Obsidian vault for actionable items: unchecked TODO tasks
from daily notes and project ideas from dedicated folders.
"""

import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

TODO_PATTERN = re.compile(r"^(\s*)- \[ \] (.+)$")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$")


@dataclass
class ObsidianItem:
    """An actionable item found in the Obsidian vault."""

    source_file: str
    content: str
    item_type: str  # "todo", "project_idea", "bullet"
    context: str  # heading or folder context
    date: str  # YYYY-MM-DD or empty


def scan_vault(
    vault_path: str,
    since: int = 7,
    folders: list[str] | None = None,
    search: str | None = None,
) -> list[ObsidianItem]:
    """Scan the vault for actionable items.

    Args:
        vault_path: Path to the Obsidian vault root.
        since: Number of days back to scan daily notes.
        folders: Specific folders to scan (default: all known).
        search: Filter items containing this text.

    Returns:
        List of ObsidianItem objects.
    """
    vault = Path(vault_path)
    if not vault.is_dir():
        return []

    items: list[ObsidianItem] = []

    target_folders = folders or ["daily notes", "project ideas", "personal project ideas"]
    lower_targets = [f.lower() for f in target_folders]

    if any("daily" in f for f in lower_targets):
        items.extend(scan_daily_notes(vault_path, since))

    if any("project" in f for f in lower_targets):
        items.extend(scan_project_ideas(vault_path))

    if search:
        search_lower = search.lower()
        items = [it for it in items if search_lower in it.content.lower() or search_lower in it.context.lower()]

    return items


def scan_project_ideas(vault_path: str) -> list[ObsidianItem]:
    """Scan Project Ideas folders for project idea notes.

    Uses filename as title and first paragraph as description.
    """
    vault = Path(vault_path)
    items: list[ObsidianItem] = []
    idea_folders = ["Project Ideas", "Personal Project Ideas"]

    for folder_name in idea_folders:
        folder = vault / folder_name
        if not folder.is_dir():
            continue

        for md_file in sorted(folder.glob("*.md")):
            title = md_file.stem
            description = _extract_first_paragraph(md_file)
            rel_path = str(md_file.relative_to(vault))

            items.append(
                ObsidianItem(
                    source_file=rel_path,
                    content=title + (f": {description}" if description else ""),
                    item_type="project_idea",
                    context=folder_name,
                    date="",
                )
            )

    return items


def scan_daily_notes(vault_path: str, since_days: int = 7) -> list[ObsidianItem]:
    """Scan Daily Notes folder for unchecked TODO items.

    Args:
        vault_path: Path to the vault root.
        since_days: Only scan notes from the last N days.

    Returns:
        List of ObsidianItem todo items with heading context.
    """
    vault = Path(vault_path)
    items: list[ObsidianItem] = []
    daily_folder = vault / "Daily Notes"

    if not daily_folder.is_dir():
        return items

    cutoff = datetime.now() - timedelta(days=since_days)

    for md_file in sorted(daily_folder.glob("*.md")):
        file_date = _parse_date_from_filename(md_file.stem)
        if file_date and file_date < cutoff:
            continue

        date_str = file_date.strftime("%Y-%m-%d") if file_date else ""
        rel_path = str(md_file.relative_to(vault))
        todos = scan_file_for_todos(md_file)

        for content, heading in todos:
            items.append(
                ObsidianItem(
                    source_file=rel_path,
                    content=content,
                    item_type="todo",
                    context=heading,
                    date=date_str,
                )
            )

    return items


def scan_file_for_todos(file_path: Path) -> list[tuple[str, str]]:
    """Extract unchecked TODO items from a markdown file.

    Returns:
        List of (content, current_heading) tuples.
    """
    try:
        text = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    results: list[tuple[str, str]] = []
    current_heading = ""

    for line in text.splitlines():
        heading_match = HEADING_PATTERN.match(line)
        if heading_match:
            current_heading = heading_match.group(2).strip()
            continue

        todo_match = TODO_PATTERN.match(line)
        if todo_match:
            content = todo_match.group(2).strip()
            results.append((content, current_heading))

    return results


def _extract_first_paragraph(file_path: Path) -> str:
    """Read first non-empty, non-heading paragraph from a markdown file."""
    try:
        text = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""

    lines: list[str] = []
    started = False

    for line in text.splitlines():
        stripped = line.strip()

        # Skip YAML frontmatter
        if stripped == "---" and not started and not lines:
            # Read until closing ---
            in_frontmatter = True
            continue

        # Skip headings
        if stripped.startswith("#"):
            if started:
                break
            continue

        if stripped:
            started = True
            lines.append(stripped)
        elif started:
            break

    return " ".join(lines)[:200]


def _parse_date_from_filename(stem: str) -> datetime | None:
    """Try to parse a date from a daily note filename."""
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%Y%m%d"):
        try:
            return datetime.strptime(stem, fmt)
        except ValueError:
            continue
    return None
