"""
SQLite-based storage for commit history.

Provides persistent storage to track commits beyond GitHub API's limited event history.
Supports Turso (libsql) for serverless deployment with automatic SQLite fallback.
"""

import os
import sqlite3
from pathlib import Path

try:
    import libsql_experimental as libsql
    HAS_LIBSQL = True
except ImportError:
    HAS_LIBSQL = False

from src.github_client import GitHubClient
from src.commit_parser import parse_commit_events


def _get_default_db_path() -> Path:
    """Get the default database path."""
    env_path = os.environ.get("CODE_DAILY_DB_PATH")
    if env_path:
        return Path(env_path)
    # Use /tmp on Vercel (read-only filesystem except /tmp)
    if os.environ.get("TURSO_DATABASE_URL"):
        return Path("/tmp/code-daily-replica.db")
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

        self._turso_url = os.environ.get("TURSO_DATABASE_URL")
        self._turso_token = os.environ.get("TURSO_AUTH_TOKEN")
        self._use_turso = bool(self._turso_url and self._turso_token and HAS_LIBSQL)

        self._init_db()

    def _get_connection(self):
        """Get a database connection (Turso or local SQLite)."""
        if self._use_turso:
            conn = libsql.connect(
                str(self.db_path),
                sync_url=self._turso_url,
                auth_token=self._turso_token,
            )
            conn.sync()
            return conn
        return sqlite3.connect(self.db_path)

    def _commit_and_sync(self, conn) -> None:
        """Commit transaction and sync to Turso remote if applicable."""
        conn.commit()
        if self._use_turso and hasattr(conn, "sync"):
            conn.sync()

    @staticmethod
    def _fetchall_as_dicts(cursor) -> list[dict]:
        """Convert cursor fetchall results to list of dicts."""
        rows = cursor.fetchall()
        if not rows:
            return []
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    @staticmethod
    def _fetchone_as_dict(cursor) -> dict | None:
        """Convert cursor fetchone result to dict or None."""
        row = cursor.fetchone()
        if not row:
            return None
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))

    def _init_db(self) -> None:
        """Create tables and indexes if they don't exist."""
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = self._get_connection()
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
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                ai_description TEXT,
                difficulty INTEGER,
                difficulty_reasoning TEXT,
                enhanced_at TEXT
            )
        """)
        # Add columns if they don't exist (for existing databases)
        try:
            conn.execute("ALTER TABLE quests ADD COLUMN ai_description TEXT")
        except Exception:
            pass  # Column already exists
        try:
            conn.execute("ALTER TABLE quests ADD COLUMN difficulty INTEGER")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE quests ADD COLUMN difficulty_reasoning TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE quests ADD COLUMN enhanced_at TEXT")
        except Exception:
            pass
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_quests_status ON quests(status)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_quests_source_ref ON quests(source, source_ref)
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS external_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cache_key TEXT UNIQUE NOT NULL,
                data TEXT NOT NULL,
                fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_external_cache_key ON external_cache(cache_key)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notification_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                level INTEGER NOT NULL,
                channel TEXT NOT NULL,
                message TEXT NOT NULL,
                sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
                streak_value INTEGER,
                streak_active INTEGER
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_notification_log_date ON notification_log(date)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS suggestion_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                suggested_at TEXT DEFAULT CURRENT_TIMESTAMP,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                domain TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_suggestion_log_hash ON suggestion_log(content_hash)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_suggestion_log_date ON suggestion_log(suggested_at)
        """)
        self._commit_and_sync(conn)

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
        conn = self._get_connection()
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

        self._commit_and_sync(conn)
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
        conn = self._get_connection()

        if since_date:
            cursor = conn.execute(
                """
                SELECT date, repo, sha, message
                FROM commits
                WHERE date >= ?
                ORDER BY date DESC, repo, id
                """,
                (since_date,),
            )
        else:
            cursor = conn.execute(
                """
                SELECT date, repo, sha, message
                FROM commits
                ORDER BY date DESC, repo, id
                """,
            )

        rows = self._fetchall_as_dicts(cursor)

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
        conn = self._get_connection()
        rows = conn.execute(
            """
            SELECT DISTINCT date FROM commits ORDER BY date DESC
            """
        ).fetchall()
        return [row[0] for row in rows]

    def clear(self) -> None:
        """Delete all commits from the database. Primarily for testing."""
        conn = self._get_connection()
        conn.execute("DELETE FROM commits")
        self._commit_and_sync(conn)

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        """
        Get a setting value by key.

        Args:
            key: The setting key
            default: Default value if key doesn't exist

        Returns:
            The setting value or default
        """
        conn = self._get_connection()
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
        conn = self._get_connection()
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
        self._commit_and_sync(conn)

    def get_unlocked_achievements(self) -> list[dict]:
        """
        Get all unlocked achievements.

        Returns:
            List of achievement records with id, unlocked_at, and unlocked_value
        """
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT id, unlocked_at, unlocked_value FROM achievements"
        )
        return self._fetchall_as_dicts(cursor)

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
        conn = self._get_connection()
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO achievements (id, unlocked_at, unlocked_value)
            VALUES (?, datetime('now'), ?)
            """,
            (achievement_id, unlocked_value),
        )
        self._commit_and_sync(conn)
        return cursor.rowcount > 0

    def reset_achievements(self) -> None:
        """Delete all achievements. For debugging/reset purposes."""
        conn = self._get_connection()
        conn.execute("DELETE FROM achievements")
        self._commit_and_sync(conn)

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
        conn = self._get_connection()
        query = "SELECT * FROM quests"
        params: list = []

        if status:
            query += " WHERE status = ?"
            params.append(status)

        query += " ORDER BY created_at DESC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor = conn.execute(query, params)
        return self._fetchall_as_dicts(cursor)

    def get_quest(self, quest_id: int) -> dict | None:
        """
        Get a single quest by ID.

        Args:
            quest_id: The quest ID

        Returns:
            Quest dictionary or None if not found
        """
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM quests WHERE id = ?",
            (quest_id,),
        )
        return self._fetchone_as_dict(cursor)

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
        conn = self._get_connection()
        cursor = conn.execute(
            """
            INSERT INTO quests (title, source, source_ref, description)
            VALUES (?, ?, ?, ?)
            """,
            (title, source, source_ref, description),
        )
        self._commit_and_sync(conn)
        return cursor.lastrowid

    def quest_exists_by_source_ref(self, source: str, source_ref: str) -> bool:
        """
        Check if a quest with given source and source_ref exists.

        Used for deduplication when syncing external sources like GitHub issues.

        Args:
            source: Source type (e.g., 'github_issue')
            source_ref: Reference to the source (e.g., issue URL)

        Returns:
            True if quest exists, False otherwise
        """
        conn = self._get_connection()
        row = conn.execute(
            "SELECT 1 FROM quests WHERE source = ? AND source_ref = ? LIMIT 1",
            (source, source_ref),
        ).fetchone()
        return row is not None

    def update_quest_status(self, quest_id: int, status: str) -> bool:
        """
        Update a quest's status.

        Args:
            quest_id: The quest ID
            status: New status ('pending', 'active', 'completed', 'skipped', 'archived')

        Returns:
            True if quest was updated, False if not found
        """
        conn = self._get_connection()
        cursor = conn.execute(
            """
            UPDATE quests
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, quest_id),
        )
        self._commit_and_sync(conn)
        return cursor.rowcount > 0

    def delete_quest(self, quest_id: int) -> bool:
        """
        Delete a quest.

        Args:
            quest_id: The quest ID

        Returns:
            True if quest was deleted, False if not found
        """
        conn = self._get_connection()
        cursor = conn.execute("DELETE FROM quests WHERE id = ?", (quest_id,))
        self._commit_and_sync(conn)
        return cursor.rowcount > 0

    def update_quest_ai_fields(
        self,
        quest_id: int,
        ai_description: str | None = None,
        difficulty: int | None = None,
        difficulty_reasoning: str | None = None,
    ) -> bool:
        """
        Update a quest's AI-generated fields.

        Args:
            quest_id: The quest ID
            ai_description: AI-generated description
            difficulty: Difficulty rating (1-5)
            difficulty_reasoning: Explanation for difficulty rating

        Returns:
            True if quest was updated, False if not found
        """
        conn = self._get_connection()
        cursor = conn.execute(
            """
            UPDATE quests
            SET ai_description = ?,
                difficulty = ?,
                difficulty_reasoning = ?,
                enhanced_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (ai_description, difficulty, difficulty_reasoning, quest_id),
        )
        self._commit_and_sync(conn)
        return cursor.rowcount > 0

    def get_quests_without_ai(self, limit: int = 5) -> list[dict]:
        """
        Get pending quests that haven't been enhanced by AI.

        Args:
            limit: Maximum number of quests to return

        Returns:
            List of quest dictionaries without AI enhancement
        """
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT * FROM quests
            WHERE status = 'pending' AND enhanced_at IS NULL
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return self._fetchall_as_dicts(cursor)

    # Ideas methods
    def get_ideas(self, status: str | None = None) -> list[dict]:
        """
        Get ideas, optionally filtered by status.

        Args:
            status: Filter by status ('active', 'promoted', 'completed', 'archived')

        Returns:
            List of idea dictionaries
        """
        conn = self._get_connection()
        if status:
            cursor = conn.execute(
                "SELECT * FROM ideas WHERE status = ? ORDER BY created_at DESC",
                (status,),
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM ideas ORDER BY created_at DESC"
            )
        return self._fetchall_as_dicts(cursor)

    def get_idea(self, idea_id: int) -> dict | None:
        """
        Get a single idea by ID.

        Args:
            idea_id: The idea ID

        Returns:
            Idea dictionary or None if not found
        """
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM ideas WHERE id = ?",
            (idea_id,),
        )
        return self._fetchone_as_dict(cursor)

    def create_idea(self, content: str) -> int:
        """
        Create a new idea.

        Args:
            content: Idea content/description

        Returns:
            ID of the created idea
        """
        conn = self._get_connection()
        cursor = conn.execute(
            "INSERT INTO ideas (content) VALUES (?)",
            (content,),
        )
        self._commit_and_sync(conn)
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
        conn = self._get_connection()
        cursor = conn.execute(
            """
            UPDATE ideas
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, idea_id),
        )
        self._commit_and_sync(conn)
        return cursor.rowcount > 0

    def delete_idea(self, idea_id: int) -> bool:
        """
        Delete an idea.

        Args:
            idea_id: The idea ID

        Returns:
            True if idea was deleted, False if not found
        """
        conn = self._get_connection()
        cursor = conn.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))
        self._commit_and_sync(conn)
        return cursor.rowcount > 0

    # Notification log methods
    def log_notification(
        self,
        date: str,
        level: int,
        channel: str,
        message: str,
        streak_value: int,
        streak_active: bool,
    ) -> int:
        """
        Log a sent notification.

        Args:
            date: Date in YYYY-MM-DD format
            level: Urgency level (1-4)
            channel: Channel name (e.g. 'ntfy')
            message: The message that was sent
            streak_value: Current streak count
            streak_active: Whether streak was active when sent

        Returns:
            ID of the log entry
        """
        conn = self._get_connection()
        cursor = conn.execute(
            """
            INSERT INTO notification_log (date, level, channel, message, streak_value, streak_active)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (date, level, channel, message, streak_value, int(streak_active)),
        )
        self._commit_and_sync(conn)
        return cursor.lastrowid

    def get_notifications_for_date(self, date: str) -> list[dict]:
        """
        Get all notifications sent on a given date.

        Args:
            date: Date in YYYY-MM-DD format

        Returns:
            List of notification log dictionaries
        """
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM notification_log WHERE date = ? ORDER BY sent_at",
            (date,),
        )
        return self._fetchall_as_dicts(cursor)

    def get_max_level_sent_today(self, date: str) -> int | None:
        """
        Get the highest notification level sent on a given date.

        Used for deduplication -- don't re-send same or lower level.

        Args:
            date: Date in YYYY-MM-DD format

        Returns:
            Highest level sent, or None if no notifications sent today
        """
        conn = self._get_connection()
        row = conn.execute(
            "SELECT MAX(level) FROM notification_log WHERE date = ?",
            (date,),
        ).fetchone()
        return row[0] if row and row[0] is not None else None

    def get_notification_history(self, limit: int = 30) -> list[dict]:
        """
        Get recent notification history.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of notification log dictionaries, most recent first
        """
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM notification_log ORDER BY sent_at DESC, id DESC LIMIT ?",
            (limit,),
        )
        return self._fetchall_as_dicts(cursor)

    # Suggestion log methods
    def log_suggestion(self, source: str, title: str, domain: str | None = None) -> int:
        """Log that an idea was suggested. Returns log entry ID."""
        import hashlib

        content_hash = hashlib.sha256(title.strip().lower().encode()).hexdigest()[:16]
        conn = self._get_connection()
        cursor = conn.execute(
            """
            INSERT INTO suggestion_log (source, title, content_hash, domain)
            VALUES (?, ?, ?, ?)
            """,
            (source, title, content_hash, domain),
        )
        self._commit_and_sync(conn)
        return cursor.lastrowid

    def get_recent_suggestions(self, days: int = 14) -> list[dict]:
        """Get suggestions from the last N days."""
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT * FROM suggestion_log
            WHERE suggested_at >= datetime('now', '-' || ? || ' days')
            ORDER BY suggested_at DESC
            """,
            (days,),
        )
        return self._fetchall_as_dicts(cursor)

    def get_suggestion_frequency(self, content_hash: str, days: int = 14) -> int:
        """How many times has this exact idea been suggested in the last N days?"""
        conn = self._get_connection()
        row = conn.execute(
            """
            SELECT COUNT(*) FROM suggestion_log
            WHERE content_hash = ?
            AND suggested_at >= datetime('now', '-' || ? || ' days')
            """,
            (content_hash, days),
        ).fetchone()
        return row[0] if row else 0

    def get_recent_suggestion_domains(self, days: int = 30) -> list[str]:
        """Get domains that have been suggested recently, for diversity scoring."""
        conn = self._get_connection()
        rows = conn.execute(
            """
            SELECT DISTINCT domain FROM suggestion_log
            WHERE domain IS NOT NULL
            AND suggested_at >= datetime('now', '-' || ? || ' days')
            """,
            (days,),
        ).fetchall()
        return [row[0] for row in rows]

    # External cache methods
    def get_cache(self, cache_key: str) -> str | None:
        """
        Get cached data if not expired.

        Args:
            cache_key: The cache key to look up

        Returns:
            Cached JSON data as string, or None if not found/expired
        """
        conn = self._get_connection()
        row = conn.execute(
            """
            SELECT data FROM external_cache
            WHERE cache_key = ? AND expires_at > datetime('now')
            """,
            (cache_key,),
        ).fetchone()
        return row[0] if row else None

    def set_cache(self, cache_key: str, data: str, hours: int = 24) -> None:
        """
        Store data in cache with expiration.

        Args:
            cache_key: The cache key
            data: JSON string data to cache
            hours: Hours until expiration (default 24)
        """
        conn = self._get_connection()
        conn.execute(
            """
            INSERT INTO external_cache (cache_key, data, expires_at)
            VALUES (?, ?, datetime('now', '+' || ? || ' hours'))
            ON CONFLICT(cache_key) DO UPDATE SET
                data = excluded.data,
                fetched_at = CURRENT_TIMESTAMP,
                expires_at = excluded.expires_at
            """,
            (cache_key, data, hours),
        )
        self._commit_and_sync(conn)

    def clear_expired_cache(self) -> int:
        """
        Remove expired cache entries.

        Returns:
            Number of entries removed
        """
        conn = self._get_connection()
        cursor = conn.execute(
            "DELETE FROM external_cache WHERE expires_at <= datetime('now')"
        )
        self._commit_and_sync(conn)
        return cursor.rowcount


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
