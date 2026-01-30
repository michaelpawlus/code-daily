"""
SQLite-based storage for commit history.

Provides persistent storage to track commits beyond GitHub API's limited event history.
"""

import os
import sqlite3
from pathlib import Path

from src.github_client import GitHubClient
from src.commit_parser import parse_commit_events


def _get_default_db_path() -> Path:
    """Get the default database path."""
    env_path = os.environ.get("CODE_DAILY_DB_PATH")
    if env_path:
        return Path(env_path)
    return Path.home() / ".code-daily" / "commits.db"


class CommitStorage:
    """SQLite-based storage for commit history."""

    def __init__(self, db_path: str | Path | None = None):
        """
        Initialize the commit storage.

        Args:
            db_path: Path to the SQLite database file.
                     Defaults to ~/.code-daily/commits.db
        """
        if db_path is None:
            db_path = _get_default_db_path()
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        """Create tables and indexes if they don't exist."""
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS commits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    repo TEXT NOT NULL,
                    sha TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(date, repo, sha)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_commits_date ON commits(date)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS achievements (
                    id TEXT PRIMARY KEY,
                    unlocked_at TEXT NOT NULL,
                    unlocked_value INTEGER
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS quests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    source_ref TEXT,
                    title TEXT NOT NULL,
                    description TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_quests_status ON quests(status)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ideas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def save_commits(self, commit_events: list[dict]) -> int:
        """
        Save commit events to the database.

        Uses INSERT OR IGNORE to skip duplicates.

        Args:
            commit_events: List of commit event dictionaries from parse_commit_events

        Returns:
            Number of new commits inserted
        """
        inserted = 0
        with sqlite3.connect(self.db_path) as conn:
            for event in commit_events:
                date = event.get("date", "")
                repo = event.get("repo", "")
                commits = event.get("commits", [])

                for commit in commits:
                    sha = commit.get("sha", "")
                    message = commit.get("message", "")

                    # Skip commits with missing required fields
                    if not (date and repo and sha):
                        continue

                    cursor = conn.execute(
                        """
                        INSERT OR IGNORE INTO commits (date, repo, sha, message)
                        VALUES (?, ?, ?, ?)
                        """,
                        (date, repo, sha, message),
                    )
                    inserted += cursor.rowcount

            conn.commit()
        return inserted

    def get_all_commits(self) -> list[dict]:
        """
        Retrieve all commits from the database.

        Returns:
            List of commit event dictionaries in the same format as parse_commit_events,
            sorted by date descending.
        """
        return self._get_commits_query()

    def get_commits_since(self, since_date: str) -> list[dict]:
        """
        Retrieve commits from the database since a given date.

        Args:
            since_date: Date in YYYY-MM-DD format (inclusive)

        Returns:
            List of commit event dictionaries.
        """
        return self._get_commits_query(since_date=since_date)

    def _get_commits_query(self, since_date: str | None = None) -> list[dict]:
        """
        Execute a query to get commits, optionally filtering by date.

        Groups commits by date and repo to match parse_commit_events format.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            if since_date:
                rows = conn.execute(
                    """
                    SELECT date, repo, sha, message
                    FROM commits
                    WHERE date >= ?
                    ORDER BY date DESC, repo, id
                    """,
                    (since_date,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT date, repo, sha, message
                    FROM commits
                    ORDER BY date DESC, repo, id
                    """,
                ).fetchall()

        # Group commits by (date, repo) to match parse_commit_events format
        events_dict: dict[tuple[str, str], list[dict]] = {}
        for row in rows:
            key = (row["date"], row["repo"])
            if key not in events_dict:
                events_dict[key] = []
            events_dict[key].append({
                "sha": row["sha"],
                "message": row["message"],
            })

        # Convert to list of commit events
        commit_events = []
        for (date, repo), commits in events_dict.items():
            commit_events.append({
                "date": date,
                "repo": repo,
                "commits": commits,
                "commit_count": len(commits),
            })

        # Sort by date descending
        commit_events.sort(key=lambda x: x["date"], reverse=True)
        return commit_events

    def get_commit_dates(self) -> list[str]:
        """
        Get all unique commit dates.

        Returns:
            List of dates in YYYY-MM-DD format, sorted descending.
        """
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT date FROM commits ORDER BY date DESC
                """
            ).fetchall()
        return [row[0] for row in rows]

    def clear(self) -> None:
        """Delete all commits from the database. Primarily for testing."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM commits")
            conn.commit()

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        """
        Get a setting value by key.

        Args:
            key: The setting key
            default: Default value if key doesn't exist

        Returns:
            The setting value or default
        """
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,),
            ).fetchone()
        return row[0] if row else default

    def set_setting(self, key: str, value: str) -> None:
        """
        Set a setting value (upserts).

        Args:
            key: The setting key
            value: The value to store
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value),
            )
            conn.commit()

    def get_unlocked_achievements(self) -> list[dict]:
        """
        Get all unlocked achievements.

        Returns:
            List of achievement records with id, unlocked_at, and unlocked_value
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, unlocked_at, unlocked_value FROM achievements"
            ).fetchall()
        return [dict(row) for row in rows]

    def save_achievement(self, achievement_id: str, unlocked_value: int | None = None) -> bool:
        """
        Save a newly unlocked achievement.

        Uses INSERT OR IGNORE for idempotency - won't update if already exists.

        Args:
            achievement_id: The achievement ID
            unlocked_value: The value at which the achievement was unlocked

        Returns:
            True if the achievement was newly saved, False if it already existed
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO achievements (id, unlocked_at, unlocked_value)
                VALUES (?, datetime('now'), ?)
                """,
                (achievement_id, unlocked_value),
            )
            conn.commit()
        return cursor.rowcount > 0

    def reset_achievements(self) -> None:
        """Delete all achievements. For debugging/reset purposes."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM achievements")
            conn.commit()

    # Quest methods
    def get_quests(self, status: str | None = None, limit: int | None = None) -> list[dict]:
        """
        Get quests, optionally filtered by status.

        Args:
            status: Filter by status ('pending', 'active', 'completed', 'skipped', 'archived')
            limit: Maximum number of quests to return

        Returns:
            List of quest dictionaries
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            query = "SELECT * FROM quests"
            params: list = []

            if status:
                query += " WHERE status = ?"
                params.append(status)

            query += " ORDER BY created_at DESC"

            if limit:
                query += " LIMIT ?"
                params.append(limit)

            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_quest(self, quest_id: int) -> dict | None:
        """
        Get a single quest by ID.

        Args:
            quest_id: The quest ID

        Returns:
            Quest dictionary or None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM quests WHERE id = ?",
                (quest_id,),
            ).fetchone()
        return dict(row) if row else None

    def create_quest(
        self,
        title: str,
        source: str = "manual",
        source_ref: str | None = None,
        description: str | None = None,
    ) -> int:
        """
        Create a new quest.

        Args:
            title: Quest title
            source: Source type ('manual', 'ideas_md', 'github_issue', 'todo_scan')
            source_ref: Reference to the source (issue number, file:line, etc.)
            description: Optional description

        Returns:
            ID of the created quest
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO quests (title, source, source_ref, description)
                VALUES (?, ?, ?, ?)
                """,
                (title, source, source_ref, description),
            )
            conn.commit()
            return cursor.lastrowid

    def update_quest_status(self, quest_id: int, status: str) -> bool:
        """
        Update a quest's status.

        Args:
            quest_id: The quest ID
            status: New status ('pending', 'active', 'completed', 'skipped', 'archived')

        Returns:
            True if quest was updated, False if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE quests
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, quest_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_quest(self, quest_id: int) -> bool:
        """
        Delete a quest.

        Args:
            quest_id: The quest ID

        Returns:
            True if quest was deleted, False if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM quests WHERE id = ?", (quest_id,))
            conn.commit()
            return cursor.rowcount > 0

    # Ideas methods
    def get_ideas(self, status: str | None = None) -> list[dict]:
        """
        Get ideas, optionally filtered by status.

        Args:
            status: Filter by status ('active', 'promoted', 'completed', 'archived')

        Returns:
            List of idea dictionaries
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if status:
                rows = conn.execute(
                    "SELECT * FROM ideas WHERE status = ? ORDER BY created_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM ideas ORDER BY created_at DESC"
                ).fetchall()
        return [dict(row) for row in rows]

    def get_idea(self, idea_id: int) -> dict | None:
        """
        Get a single idea by ID.

        Args:
            idea_id: The idea ID

        Returns:
            Idea dictionary or None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM ideas WHERE id = ?",
                (idea_id,),
            ).fetchone()
        return dict(row) if row else None

    def create_idea(self, content: str) -> int:
        """
        Create a new idea.

        Args:
            content: Idea content/description

        Returns:
            ID of the created idea
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO ideas (content) VALUES (?)",
                (content,),
            )
            conn.commit()
            return cursor.lastrowid

    def update_idea_status(self, idea_id: int, status: str) -> bool:
        """
        Update an idea's status.

        Args:
            idea_id: The idea ID
            status: New status ('active', 'promoted', 'completed', 'archived')

        Returns:
            True if idea was updated, False if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE ideas
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, idea_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_idea(self, idea_id: int) -> bool:
        """
        Delete an idea.

        Args:
            idea_id: The idea ID

        Returns:
            True if idea was deleted, False if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))
            conn.commit()
            return cursor.rowcount > 0


def get_commit_events_with_history(
    client: GitHubClient | None = None,
    storage: CommitStorage | None = None,
    fetch_new: bool = True,
) -> list[dict]:
    """
    Fetch commits from API, save to storage, and return all stored commits.

    Args:
        client: GitHub client for fetching new events. Required if fetch_new is True.
        storage: Commit storage instance. Creates default if not provided.
        fetch_new: Whether to fetch new commits from the API.

    Returns:
        List of all commit events from storage.
    """
    if storage is None:
        storage = CommitStorage()

    if fetch_new and client is not None:
        # Fetch new events from GitHub
        events = client.get_user_events(per_page=100)
        commit_events = parse_commit_events(events)
        storage.save_commits(commit_events)

    return storage.get_all_commits()
