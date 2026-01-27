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
