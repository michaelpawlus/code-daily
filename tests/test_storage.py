"""Tests for the commit storage module."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.storage import CommitStorage, get_commit_events_with_history


@pytest.fixture
def temp_db():
    """Create a temporary database file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def storage(temp_db):
    """Create a CommitStorage instance with a temporary database."""
    return CommitStorage(temp_db)


@pytest.fixture
def sample_commit_events():
    """Sample commit events in parse_commit_events format."""
    return [
        {
            "date": "2025-01-25",
            "repo": "user/repo-a",
            "commits": [
                {"sha": "abc1234", "message": "Fix bug"},
                {"sha": "def5678", "message": "Add feature"},
            ],
            "commit_count": 2,
        },
        {
            "date": "2025-01-24",
            "repo": "user/repo-b",
            "commits": [
                {"sha": "ghi9012", "message": "Update docs"},
            ],
            "commit_count": 1,
        },
    ]


class TestDatabaseInitialization:
    """Tests for database initialization."""

    def test_creates_db_file(self, temp_db):
        """Database file is created on initialization."""
        # Remove file first
        if temp_db.exists():
            temp_db.unlink()

        CommitStorage(temp_db)
        assert temp_db.exists()

    def test_creates_parent_directories(self):
        """Parent directories are created if they don't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "subdir" / "nested" / "commits.db"
            CommitStorage(db_path)
            assert db_path.exists()

    def test_initialization_is_idempotent(self, temp_db):
        """Multiple initializations don't cause errors."""
        CommitStorage(temp_db)
        CommitStorage(temp_db)
        storage = CommitStorage(temp_db)
        # Should work without errors
        assert storage.get_all_commits() == []

    def test_default_path_uses_home_directory(self):
        """Default path uses ~/.code-daily/commits.db."""
        with patch.dict(os.environ, {}, clear=True):
            # Clear CODE_DAILY_DB_PATH if set
            os.environ.pop("CODE_DAILY_DB_PATH", None)
            from src.storage import _get_default_db_path

            path = _get_default_db_path()
            assert path == Path.home() / ".code-daily" / "commits.db"

    def test_env_var_overrides_default_path(self):
        """CODE_DAILY_DB_PATH environment variable overrides default."""
        with patch.dict(os.environ, {"CODE_DAILY_DB_PATH": "/custom/path.db"}):
            from src.storage import _get_default_db_path

            path = _get_default_db_path()
            assert path == Path("/custom/path.db")


class TestSaveCommits:
    """Tests for save_commits method."""

    def test_save_single_commit(self, storage):
        """Can save a single commit event."""
        events = [
            {
                "date": "2025-01-25",
                "repo": "user/repo",
                "commits": [{"sha": "abc1234", "message": "Test commit"}],
                "commit_count": 1,
            }
        ]
        count = storage.save_commits(events)
        assert count == 1

    def test_save_multiple_commits(self, storage, sample_commit_events):
        """Can save multiple commit events."""
        count = storage.save_commits(sample_commit_events)
        assert count == 3  # 2 + 1 commits

    def test_deduplication(self, storage, sample_commit_events):
        """Duplicate commits are not inserted twice."""
        storage.save_commits(sample_commit_events)
        count = storage.save_commits(sample_commit_events)
        assert count == 0  # No new commits

        # Total should still be 3
        all_commits = storage.get_all_commits()
        total = sum(e["commit_count"] for e in all_commits)
        assert total == 3

    def test_returns_insert_count(self, storage, sample_commit_events):
        """Returns the number of new commits inserted."""
        count1 = storage.save_commits(sample_commit_events)
        assert count1 == 3

        # Add one new commit
        new_events = [
            {
                "date": "2025-01-26",
                "repo": "user/repo-c",
                "commits": [{"sha": "xyz9999", "message": "New commit"}],
                "commit_count": 1,
            }
        ]
        count2 = storage.save_commits(new_events)
        assert count2 == 1

    def test_skips_commits_with_missing_fields(self, storage):
        """Commits with missing required fields are skipped."""
        events = [
            {
                "date": "2025-01-25",
                "repo": "user/repo",
                "commits": [
                    {"sha": "abc1234", "message": "Valid"},
                    {"sha": "", "message": "Missing sha"},  # Should skip
                    {"sha": "def5678", "message": "Also valid"},
                ],
                "commit_count": 3,
            }
        ]
        count = storage.save_commits(events)
        assert count == 2

    def test_handles_empty_events(self, storage):
        """Handles empty commit events list."""
        count = storage.save_commits([])
        assert count == 0


class TestRetrieveCommits:
    """Tests for get_all_commits and get_commits_since methods."""

    def test_get_all_commits_empty_db(self, storage):
        """Returns empty list for empty database."""
        result = storage.get_all_commits()
        assert result == []

    def test_get_all_commits_returns_correct_format(self, storage, sample_commit_events):
        """Returns commits in parse_commit_events format."""
        storage.save_commits(sample_commit_events)
        result = storage.get_all_commits()

        assert len(result) == 2
        for event in result:
            assert "date" in event
            assert "repo" in event
            assert "commits" in event
            assert "commit_count" in event
            assert isinstance(event["commits"], list)
            for commit in event["commits"]:
                assert "sha" in commit
                assert "message" in commit

    def test_get_all_commits_sorted_by_date_descending(self, storage):
        """Commits are sorted by date in descending order."""
        events = [
            {
                "date": "2025-01-20",
                "repo": "user/repo",
                "commits": [{"sha": "aaa", "message": "Old"}],
                "commit_count": 1,
            },
            {
                "date": "2025-01-25",
                "repo": "user/repo",
                "commits": [{"sha": "bbb", "message": "New"}],
                "commit_count": 1,
            },
            {
                "date": "2025-01-22",
                "repo": "user/repo",
                "commits": [{"sha": "ccc", "message": "Middle"}],
                "commit_count": 1,
            },
        ]
        storage.save_commits(events)
        result = storage.get_all_commits()

        dates = [e["date"] for e in result]
        assert dates == ["2025-01-25", "2025-01-22", "2025-01-20"]

    def test_get_commits_since(self, storage, sample_commit_events):
        """Filters commits by date."""
        storage.save_commits(sample_commit_events)
        result = storage.get_commits_since("2025-01-25")

        assert len(result) == 1
        assert result[0]["date"] == "2025-01-25"

    def test_get_commits_since_inclusive(self, storage, sample_commit_events):
        """Since date is inclusive."""
        storage.save_commits(sample_commit_events)
        result = storage.get_commits_since("2025-01-24")

        assert len(result) == 2

    def test_get_commit_dates(self, storage, sample_commit_events):
        """Returns unique commit dates."""
        storage.save_commits(sample_commit_events)
        dates = storage.get_commit_dates()

        assert dates == ["2025-01-25", "2025-01-24"]

    def test_get_commit_dates_sorted_descending(self, storage):
        """Commit dates are sorted descending."""
        events = [
            {
                "date": "2025-01-20",
                "repo": "user/repo",
                "commits": [{"sha": "aaa", "message": "Old"}],
                "commit_count": 1,
            },
            {
                "date": "2025-01-25",
                "repo": "user/repo",
                "commits": [{"sha": "bbb", "message": "New"}],
                "commit_count": 1,
            },
        ]
        storage.save_commits(events)
        dates = storage.get_commit_dates()

        assert dates == ["2025-01-25", "2025-01-20"]


class TestClear:
    """Tests for clear method."""

    def test_clear_removes_all_commits(self, storage, sample_commit_events):
        """Clear removes all commits from database."""
        storage.save_commits(sample_commit_events)
        assert len(storage.get_all_commits()) > 0

        storage.clear()
        assert storage.get_all_commits() == []

    def test_clear_on_empty_db(self, storage):
        """Clear works on empty database."""
        storage.clear()  # Should not raise
        assert storage.get_all_commits() == []


class TestGetCommitEventsWithHistory:
    """Tests for get_commit_events_with_history function."""

    def test_fetch_and_store(self, temp_db):
        """Fetches from API and stores commits."""
        mock_client = MagicMock()
        mock_client.get_user_events.return_value = [
            {
                "type": "PushEvent",
                "created_at": "2025-01-25T10:00:00Z",
                "repo": {"name": "user/repo"},
                "payload": {
                    "commits": [
                        {"sha": "abc1234567890", "message": "Test commit"},
                    ]
                },
            }
        ]

        storage = CommitStorage(temp_db)
        result = get_commit_events_with_history(mock_client, storage)

        mock_client.get_user_events.assert_called_once_with(per_page=100)
        assert len(result) == 1
        assert result[0]["date"] == "2025-01-25"

    def test_merge_old_and_new(self, temp_db):
        """Merges existing and new commits."""
        storage = CommitStorage(temp_db)

        # Pre-populate with old commits
        old_events = [
            {
                "date": "2025-01-20",
                "repo": "user/old-repo",
                "commits": [{"sha": "old1234", "message": "Old commit"}],
                "commit_count": 1,
            }
        ]
        storage.save_commits(old_events)

        # Mock client returns new commits
        mock_client = MagicMock()
        mock_client.get_user_events.return_value = [
            {
                "type": "PushEvent",
                "created_at": "2025-01-25T10:00:00Z",
                "repo": {"name": "user/new-repo"},
                "payload": {
                    "commits": [
                        {"sha": "new5678901234", "message": "New commit"},
                    ]
                },
            }
        ]

        result = get_commit_events_with_history(mock_client, storage)

        # Should have both old and new commits
        assert len(result) == 2
        dates = [e["date"] for e in result]
        assert "2025-01-20" in dates
        assert "2025-01-25" in dates

    def test_offline_mode(self, temp_db):
        """Works without API when fetch_new is False."""
        storage = CommitStorage(temp_db)

        # Pre-populate storage
        events = [
            {
                "date": "2025-01-25",
                "repo": "user/repo",
                "commits": [{"sha": "abc1234", "message": "Cached commit"}],
                "commit_count": 1,
            }
        ]
        storage.save_commits(events)

        # Call without client
        result = get_commit_events_with_history(client=None, storage=storage, fetch_new=False)

        assert len(result) == 1
        assert result[0]["commits"][0]["message"] == "Cached commit"

    def test_creates_default_storage(self):
        """Creates default storage if not provided."""
        mock_client = MagicMock()
        mock_client.get_user_events.return_value = []

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            with patch.dict(os.environ, {"CODE_DAILY_DB_PATH": str(db_path)}):
                result = get_commit_events_with_history(mock_client)

            assert db_path.exists()
            assert result == []


class TestEdgeCases:
    """Tests for edge cases."""

    def test_unknown_date_handling(self, storage):
        """Handles 'unknown' date values."""
        events = [
            {
                "date": "unknown",
                "repo": "user/repo",
                "commits": [{"sha": "abc1234", "message": "Unknown date"}],
                "commit_count": 1,
            }
        ]
        count = storage.save_commits(events)
        assert count == 1

        result = storage.get_all_commits()
        assert result[0]["date"] == "unknown"

    def test_empty_message(self, storage):
        """Handles empty commit messages."""
        events = [
            {
                "date": "2025-01-25",
                "repo": "user/repo",
                "commits": [{"sha": "abc1234", "message": ""}],
                "commit_count": 1,
            }
        ]
        count = storage.save_commits(events)
        assert count == 1

    def test_special_characters_in_message(self, storage):
        """Handles special characters in commit messages."""
        events = [
            {
                "date": "2025-01-25",
                "repo": "user/repo",
                "commits": [
                    {"sha": "abc1234", "message": "Fix bug with 'quotes' and \"double quotes\""}
                ],
                "commit_count": 1,
            }
        ]
        storage.save_commits(events)
        result = storage.get_all_commits()

        assert result[0]["commits"][0]["message"] == "Fix bug with 'quotes' and \"double quotes\""

    def test_unicode_in_message(self, storage):
        """Handles unicode characters in commit messages."""
        events = [
            {
                "date": "2025-01-25",
                "repo": "user/repo",
                "commits": [{"sha": "abc1234", "message": "Add emoji support \U0001f680"}],
                "commit_count": 1,
            }
        ]
        storage.save_commits(events)
        result = storage.get_all_commits()

        assert "\U0001f680" in result[0]["commits"][0]["message"]

    def test_custom_db_path(self):
        """Works with custom database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_path = Path(tmpdir) / "custom" / "my_commits.db"
            storage = CommitStorage(custom_path)

            events = [
                {
                    "date": "2025-01-25",
                    "repo": "user/repo",
                    "commits": [{"sha": "abc1234", "message": "Test"}],
                    "commit_count": 1,
                }
            ]
            storage.save_commits(events)

            assert custom_path.exists()
            assert len(storage.get_all_commits()) == 1
