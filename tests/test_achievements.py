"""Tests for the achievements module."""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.achievements import (
    Achievement,
    ACHIEVEMENTS,
    STREAK_ACHIEVEMENTS,
    COMMIT_ACHIEVEMENTS,
    check_achievements,
    get_all_achievements_status,
)
from src.storage import CommitStorage
from src.app import app


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
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


class TestAchievementDefinitions:
    """Tests for achievement definitions."""

    def test_all_achievements_have_unique_ids(self):
        """All achievement IDs should be unique."""
        ids = [a.id for a in ACHIEVEMENTS]
        assert len(ids) == len(set(ids))

    def test_total_achievement_count(self):
        """Should have exactly 10 achievements."""
        assert len(ACHIEVEMENTS) == 10

    def test_streak_achievement_count(self):
        """Should have 5 streak achievements."""
        assert len(STREAK_ACHIEVEMENTS) == 5

    def test_commit_achievement_count(self):
        """Should have 5 commit achievements."""
        assert len(COMMIT_ACHIEVEMENTS) == 5

    def test_all_achievements_have_required_fields(self):
        """All achievements should have all required fields."""
        for achievement in ACHIEVEMENTS:
            assert isinstance(achievement.id, str)
            assert isinstance(achievement.name, str)
            assert isinstance(achievement.emoji, str)
            assert isinstance(achievement.description, str)
            assert achievement.category in ("streak", "commits")
            assert isinstance(achievement.threshold, int)
            assert achievement.threshold > 0

    def test_streak_achievements_have_correct_category(self):
        """Streak achievements should have 'streak' category."""
        for achievement in STREAK_ACHIEVEMENTS:
            assert achievement.category == "streak"

    def test_commit_achievements_have_correct_category(self):
        """Commit achievements should have 'commits' category."""
        for achievement in COMMIT_ACHIEVEMENTS:
            assert achievement.category == "commits"

    def test_streak_thresholds(self):
        """Streak achievement thresholds should be correct."""
        expected = {"streak_3": 3, "streak_7": 7, "streak_14": 14, "streak_30": 30, "streak_100": 100}
        for achievement in STREAK_ACHIEVEMENTS:
            assert achievement.threshold == expected[achievement.id]

    def test_commit_thresholds(self):
        """Commit achievement thresholds should be correct."""
        expected = {"first_commit": 1, "commits_10": 10, "commits_50": 50, "commits_100": 100, "commits_500": 500}
        for achievement in COMMIT_ACHIEVEMENTS:
            assert achievement.threshold == expected[achievement.id]


class TestCheckAchievements:
    """Tests for check_achievements function."""

    def test_no_achievements_with_zero_stats(self):
        """No achievements should be unlocked with zero stats."""
        newly_unlocked = check_achievements(
            current_streak=0,
            longest_streak=0,
            total_commits=0,
            unlocked_ids=set(),
        )
        assert newly_unlocked == []

    def test_first_commit_achievement(self):
        """First commit achievement should unlock with 1 commit."""
        newly_unlocked = check_achievements(
            current_streak=0,
            longest_streak=0,
            total_commits=1,
            unlocked_ids=set(),
        )
        assert len(newly_unlocked) == 1
        assert newly_unlocked[0].id == "first_commit"

    def test_streak_3_achievement(self):
        """3-day streak achievement should unlock."""
        newly_unlocked = check_achievements(
            current_streak=3,
            longest_streak=3,
            total_commits=3,
            unlocked_ids={"first_commit"},
        )
        assert any(a.id == "streak_3" for a in newly_unlocked)

    def test_uses_longest_streak_not_current(self):
        """Streak achievements should use longest_streak, not current_streak."""
        # Current streak is 0, but longest was 7
        newly_unlocked = check_achievements(
            current_streak=0,
            longest_streak=7,
            total_commits=10,
            unlocked_ids=set(),
        )
        streak_ids = [a.id for a in newly_unlocked if a.category == "streak"]
        assert "streak_3" in streak_ids
        assert "streak_7" in streak_ids

    def test_multiple_achievements_at_once(self):
        """Multiple achievements can be unlocked at once."""
        newly_unlocked = check_achievements(
            current_streak=7,
            longest_streak=7,
            total_commits=10,
            unlocked_ids=set(),
        )
        # Should unlock: first_commit, commits_10, streak_3, streak_7
        assert len(newly_unlocked) >= 4
        ids = {a.id for a in newly_unlocked}
        assert "first_commit" in ids
        assert "commits_10" in ids
        assert "streak_3" in ids
        assert "streak_7" in ids

    def test_deduplication_with_unlocked_ids(self):
        """Already unlocked achievements should not be returned."""
        newly_unlocked = check_achievements(
            current_streak=10,
            longest_streak=10,
            total_commits=100,
            unlocked_ids={"first_commit", "commits_10", "streak_3"},
        )
        ids = {a.id for a in newly_unlocked}
        assert "first_commit" not in ids
        assert "commits_10" not in ids
        assert "streak_3" not in ids
        # But these should be unlocked
        assert "streak_7" in ids
        assert "commits_50" in ids
        assert "commits_100" in ids

    def test_all_achievements_unlockable(self):
        """All achievements should be unlockable with high enough stats."""
        newly_unlocked = check_achievements(
            current_streak=100,
            longest_streak=100,
            total_commits=500,
            unlocked_ids=set(),
        )
        assert len(newly_unlocked) == 10

    def test_partial_streak_achievements(self):
        """Only qualifying streak achievements should unlock."""
        newly_unlocked = check_achievements(
            current_streak=10,
            longest_streak=10,
            total_commits=0,
            unlocked_ids=set(),
        )
        streak_ids = [a.id for a in newly_unlocked if a.category == "streak"]
        assert "streak_3" in streak_ids
        assert "streak_7" in streak_ids
        assert "streak_14" not in streak_ids
        assert "streak_30" not in streak_ids
        assert "streak_100" not in streak_ids


class TestGetAllAchievementsStatus:
    """Tests for get_all_achievements_status function."""

    def test_returns_all_achievements(self):
        """Should return all 10 achievements."""
        result = get_all_achievements_status([])
        assert len(result) == 10

    def test_unlocked_achievement_status(self):
        """Unlocked achievements should have correct status."""
        unlocked_records = [
            {"id": "first_commit", "unlocked_at": "2026-01-15 10:00:00", "unlocked_value": 1},
        ]
        result = get_all_achievements_status(unlocked_records)
        first_commit = next(a for a in result if a["id"] == "first_commit")

        assert first_commit["unlocked"] is True
        assert first_commit["unlocked_at"] == "2026-01-15 10:00:00"
        assert first_commit["unlocked_value"] == 1

    def test_locked_achievement_status(self):
        """Locked achievements should have correct status."""
        result = get_all_achievements_status([])
        first_commit = next(a for a in result if a["id"] == "first_commit")

        assert first_commit["unlocked"] is False
        assert first_commit["unlocked_at"] is None
        assert first_commit["unlocked_value"] is None

    def test_mixed_unlock_status(self):
        """Should handle mix of locked and unlocked achievements."""
        unlocked_records = [
            {"id": "first_commit", "unlocked_at": "2026-01-15 10:00:00", "unlocked_value": 1},
            {"id": "streak_3", "unlocked_at": "2026-01-18 10:00:00", "unlocked_value": 3},
        ]
        result = get_all_achievements_status(unlocked_records)

        unlocked_count = sum(1 for a in result if a["unlocked"])
        assert unlocked_count == 2

    def test_includes_all_achievement_metadata(self):
        """Each achievement should include all metadata fields."""
        result = get_all_achievements_status([])
        for achievement in result:
            assert "id" in achievement
            assert "name" in achievement
            assert "emoji" in achievement
            assert "description" in achievement
            assert "category" in achievement
            assert "threshold" in achievement
            assert "unlocked" in achievement
            assert "unlocked_at" in achievement
            assert "unlocked_value" in achievement


class TestStorageAchievementMethods:
    """Tests for CommitStorage achievement methods."""

    def test_save_achievement_new(self, storage):
        """Can save a new achievement."""
        result = storage.save_achievement("first_commit", 1)
        assert result is True

    def test_save_achievement_idempotent(self, storage):
        """Saving the same achievement twice is idempotent."""
        storage.save_achievement("first_commit", 1)
        result = storage.save_achievement("first_commit", 1)
        assert result is False

        # Should still only have one record
        achievements = storage.get_unlocked_achievements()
        assert len(achievements) == 1

    def test_get_unlocked_achievements_empty(self, storage):
        """Returns empty list when no achievements unlocked."""
        result = storage.get_unlocked_achievements()
        assert result == []

    def test_get_unlocked_achievements_returns_records(self, storage):
        """Returns all unlocked achievement records."""
        storage.save_achievement("first_commit", 1)
        storage.save_achievement("streak_3", 3)

        result = storage.get_unlocked_achievements()
        assert len(result) == 2

        ids = {a["id"] for a in result}
        assert "first_commit" in ids
        assert "streak_3" in ids

    def test_unlocked_achievement_record_structure(self, storage):
        """Unlocked achievement records have correct structure."""
        storage.save_achievement("first_commit", 1)

        result = storage.get_unlocked_achievements()
        assert len(result) == 1

        record = result[0]
        assert record["id"] == "first_commit"
        assert "unlocked_at" in record
        assert record["unlocked_value"] == 1

    def test_save_achievement_without_value(self, storage):
        """Can save achievement without unlocked_value."""
        storage.save_achievement("test_achievement")

        result = storage.get_unlocked_achievements()
        assert len(result) == 1
        assert result[0]["unlocked_value"] is None


class TestAchievementsAPIEndpoint:
    """Tests for the /api/achievements endpoint."""

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    def test_achievements_endpoint_structure(
        self, mock_github_client, mock_storage_class, mock_get_commits, mock_validate, client
    ):
        """Achievements endpoint should return expected structure."""
        mock_get_commits.return_value = []

        # Mock storage instance
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.get_setting.return_value = "1"
        mock_storage.get_unlocked_achievements.return_value = []

        response = client.get("/api/achievements")

        assert response.status_code == 200
        data = response.json()

        assert "achievements" in data
        assert "summary" in data
        assert "total" in data["summary"]
        assert "unlocked" in data["summary"]

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    def test_achievements_endpoint_returns_all_achievements(
        self, mock_github_client, mock_storage_class, mock_get_commits, mock_validate, client
    ):
        """Achievements endpoint should return all 10 achievements."""
        mock_get_commits.return_value = []

        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.get_setting.return_value = "1"
        mock_storage.get_unlocked_achievements.return_value = []

        response = client.get("/api/achievements")

        assert response.status_code == 200
        data = response.json()

        assert data["summary"]["total"] == 10
        assert len(data["achievements"]) == 10

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    def test_achievements_endpoint_counts_unlocked(
        self, mock_github_client, mock_storage_class, mock_get_commits, mock_validate, client
    ):
        """Achievements endpoint should count unlocked achievements."""
        mock_get_commits.return_value = [
            {
                "date": "2026-01-26",
                "repo": "user/repo",
                "commits": [{"sha": "abc", "message": "test"}],
                "commit_count": 1,
            }
        ]

        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.get_setting.return_value = "1"
        mock_storage.get_unlocked_achievements.return_value = [
            {"id": "first_commit", "unlocked_at": "2026-01-26", "unlocked_value": 1},
        ]

        response = client.get("/api/achievements")

        assert response.status_code == 200
        data = response.json()

        assert data["summary"]["unlocked"] >= 1


class TestAchievementSaveValidation:
    """Tests for achievement save validation in app.py."""

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    def test_achievement_not_saved_when_value_below_threshold(
        self, mock_github_client, mock_storage_class, mock_get_commits, mock_validate, client
    ):
        """Achievements should not be saved if value is below threshold."""
        from src.achievements import check_achievements, ACHIEVEMENTS

        # Mock storage
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.get_setting.return_value = "1"
        mock_storage.get_unlocked_achievements.return_value = []

        # Create commit events that would give us a 3-day streak
        mock_get_commits.return_value = [
            {"date": "2026-01-26", "repo": "user/repo", "commits": [{"sha": "a"}], "commit_count": 1},
            {"date": "2026-01-27", "repo": "user/repo", "commits": [{"sha": "b"}], "commit_count": 1},
            {"date": "2026-01-28", "repo": "user/repo", "commits": [{"sha": "c"}], "commit_count": 1},
        ]

        # Make the request
        response = client.get("/api/stats")
        assert response.status_code == 200

        # Check that save_achievement was called
        save_calls = mock_storage.save_achievement.call_args_list

        # Verify that streak_14 and streak_30 were NOT saved (threshold not met)
        saved_ids = [call[0][0] for call in save_calls]
        assert "streak_14" not in saved_ids, "streak_14 should not be saved with 3-day streak"
        assert "streak_30" not in saved_ids, "streak_30 should not be saved with 3-day streak"

        # Verify that appropriate achievements WERE saved
        assert "streak_3" in saved_ids, "streak_3 should be saved with 3-day streak"
        assert "first_commit" in saved_ids, "first_commit should be saved"


class TestAchievementsDashboardDisplay:
    """Tests for achievements display on the dashboard."""

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    @patch("src.app.GITHUB_USERNAME", "testuser")
    def test_dashboard_contains_achievements_section(
        self, mock_github_client, mock_storage_class, mock_get_commits, mock_validate, client
    ):
        """Dashboard should contain the achievements section."""
        mock_get_commits.return_value = []

        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.get_setting.return_value = "1"
        mock_storage.get_unlocked_achievements.return_value = []

        response = client.get("/")

        assert response.status_code == 200
        assert "data-achievements" in response.text
        assert "Achievements" in response.text

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    @patch("src.app.GITHUB_USERNAME", "testuser")
    def test_dashboard_shows_achievement_progress(
        self, mock_github_client, mock_storage_class, mock_get_commits, mock_validate, client
    ):
        """Dashboard should show achievement unlock progress."""
        mock_get_commits.return_value = []

        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.get_setting.return_value = "1"
        mock_storage.get_unlocked_achievements.return_value = []

        response = client.get("/")

        assert response.status_code == 200
        assert "data-achievements-progress" in response.text
        assert "unlocked" in response.text

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    @patch("src.app.GITHUB_USERNAME", "testuser")
    def test_dashboard_shows_achievement_cards(
        self, mock_github_client, mock_storage_class, mock_get_commits, mock_validate, client
    ):
        """Dashboard should display achievement cards."""
        mock_get_commits.return_value = []

        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.get_setting.return_value = "1"
        mock_storage.get_unlocked_achievements.return_value = []

        response = client.get("/")

        assert response.status_code == 200
        assert "data-achievements-grid" in response.text
        assert "data-achievement-id" in response.text

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    @patch("src.app.GITHUB_USERNAME", "testuser")
    def test_unlocked_achievement_has_correct_styling(
        self, mock_github_client, mock_storage_class, mock_get_commits, mock_validate, client
    ):
        """Unlocked achievements should have unlocked styling."""
        mock_get_commits.return_value = [
            {
                "date": "2026-01-26",
                "repo": "user/repo",
                "commits": [{"sha": "abc", "message": "test"}],
                "commit_count": 1,
            }
        ]

        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.get_setting.return_value = "1"
        mock_storage.get_unlocked_achievements.return_value = [
            {"id": "first_commit", "unlocked_at": "2026-01-26 10:00:00", "unlocked_value": 1},
        ]

        response = client.get("/")

        assert response.status_code == 200
        assert 'data-unlocked="true"' in response.text

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    @patch("src.app.GITHUB_USERNAME", "testuser")
    def test_locked_achievement_has_correct_styling(
        self, mock_github_client, mock_storage_class, mock_get_commits, mock_validate, client
    ):
        """Locked achievements should have locked styling."""
        mock_get_commits.return_value = []

        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.get_setting.return_value = "1"
        mock_storage.get_unlocked_achievements.return_value = []

        response = client.get("/")

        assert response.status_code == 200
        assert 'data-unlocked="false"' in response.text
        assert "grayscale" in response.text
