"""Tests for the daily goal feature."""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.storage import CommitStorage
from src.app import app, DEFAULT_DAILY_GOAL, DAILY_GOAL_KEY


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


class TestSettingsStorage:
    """Tests for settings storage methods."""

    def test_get_setting_returns_default_when_not_set(self, storage):
        """get_setting returns default when key doesn't exist."""
        result = storage.get_setting("nonexistent", "default_value")
        assert result == "default_value"

    def test_get_setting_returns_none_without_default(self, storage):
        """get_setting returns None when key doesn't exist and no default."""
        result = storage.get_setting("nonexistent")
        assert result is None

    def test_set_and_get_setting(self, storage):
        """Can set and retrieve a setting value."""
        storage.set_setting("test_key", "test_value")
        result = storage.get_setting("test_key")
        assert result == "test_value"

    def test_set_setting_upsert(self, storage):
        """set_setting updates existing value (upsert behavior)."""
        storage.set_setting("test_key", "original")
        storage.set_setting("test_key", "updated")
        result = storage.get_setting("test_key")
        assert result == "updated"

    def test_multiple_settings(self, storage):
        """Can store and retrieve multiple settings."""
        storage.set_setting("key1", "value1")
        storage.set_setting("key2", "value2")
        storage.set_setting("key3", "value3")

        assert storage.get_setting("key1") == "value1"
        assert storage.get_setting("key2") == "value2"
        assert storage.get_setting("key3") == "value3"


class TestGoalEndpoints:
    """Tests for the goal API endpoints."""

    @patch("src.app.CommitStorage")
    def test_get_goal_returns_default(self, mock_storage_class, client):
        """GET /api/goal returns default when no goal is set."""
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.get_setting.return_value = None

        response = client.get("/api/goal")

        assert response.status_code == 200
        assert response.json() == {"goal": DEFAULT_DAILY_GOAL}

    @patch("src.app.CommitStorage")
    def test_get_goal_returns_stored_value(self, mock_storage_class, client):
        """GET /api/goal returns stored goal value."""
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.get_setting.return_value = "5"

        response = client.get("/api/goal")

        assert response.status_code == 200
        assert response.json() == {"goal": 5}

    @patch("src.app.CommitStorage")
    def test_set_goal_valid(self, mock_storage_class, client):
        """POST /api/goal sets a valid goal."""
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage

        response = client.post("/api/goal", json={"goal": 5})

        assert response.status_code == 200
        assert response.json() == {"goal": 5}
        mock_storage.set_setting.assert_called_once_with(DAILY_GOAL_KEY, "5")

    def test_set_goal_minimum(self, client):
        """POST /api/goal accepts minimum value of 1."""
        with patch("src.app.CommitStorage") as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage_class.return_value = mock_storage

            response = client.post("/api/goal", json={"goal": 1})

            assert response.status_code == 200
            assert response.json() == {"goal": 1}

    def test_set_goal_maximum(self, client):
        """POST /api/goal accepts maximum value of 100."""
        with patch("src.app.CommitStorage") as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage_class.return_value = mock_storage

            response = client.post("/api/goal", json={"goal": 100})

            assert response.status_code == 200
            assert response.json() == {"goal": 100}

    def test_set_goal_too_low(self, client):
        """POST /api/goal rejects goal below 1."""
        response = client.post("/api/goal", json={"goal": 0})
        assert response.status_code == 422

    def test_set_goal_too_high(self, client):
        """POST /api/goal rejects goal above 100."""
        response = client.post("/api/goal", json={"goal": 101})
        assert response.status_code == 422

    def test_set_goal_negative(self, client):
        """POST /api/goal rejects negative goal."""
        response = client.post("/api/goal", json={"goal": -5})
        assert response.status_code == 422


class TestGoalInDashboard:
    """Tests for goal display in the dashboard."""

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    @patch("src.app.GITHUB_USERNAME", "testuser")
    def test_dashboard_shows_goal_section(
        self, mock_github_client, mock_storage_class, mock_get_commits, mock_validate, client
    ):
        """Dashboard page should display the goal section."""
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.get_setting.return_value = "3"
        mock_get_commits.return_value = []

        response = client.get("/")

        assert response.status_code == 200
        assert "data-goal" in response.text
        assert "Daily Goal" in response.text

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    @patch("src.app.GITHUB_USERNAME", "testuser")
    def test_dashboard_shows_goal_progress(
        self, mock_github_client, mock_storage_class, mock_get_commits, mock_validate, client
    ):
        """Dashboard shows progress towards daily goal."""
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.get_setting.return_value = "3"
        mock_get_commits.return_value = []

        response = client.get("/")

        assert response.status_code == 200
        assert "0 / 3 commits" in response.text

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    @patch("src.app.GITHUB_USERNAME", "testuser")
    @patch("src.app.calculate_stats")
    def test_dashboard_shows_goal_met(
        self, mock_stats, mock_github_client, mock_storage_class, mock_get_commits, mock_validate, client
    ):
        """Dashboard shows 'Goal met!' when commits >= goal."""
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.get_setting.return_value = "2"
        mock_get_commits.return_value = []
        mock_stats.return_value = {
            "commits_today": 3,
            "commits_this_week": 3,
            "commits_this_month": 3,
            "commits_last_7_days": 3,
            "commits_last_30_days": 3,
            "total_commits": 3,
        }

        response = client.get("/")

        assert response.status_code == 200
        assert "Goal met!" in response.text

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    @patch("src.app.GITHUB_USERNAME", "testuser")
    @patch("src.app.calculate_stats")
    def test_dashboard_shows_remaining_commits(
        self, mock_stats, mock_github_client, mock_storage_class, mock_get_commits, mock_validate, client
    ):
        """Dashboard shows how many commits needed to reach goal."""
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.get_setting.return_value = "5"
        mock_get_commits.return_value = []
        mock_stats.return_value = {
            "commits_today": 2,
            "commits_this_week": 2,
            "commits_this_month": 2,
            "commits_last_7_days": 2,
            "commits_last_30_days": 2,
            "total_commits": 2,
        }

        response = client.get("/")

        assert response.status_code == 200
        assert "3 more to reach your goal" in response.text

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    @patch("src.app.GITHUB_USERNAME", "testuser")
    def test_dashboard_has_edit_button(
        self, mock_github_client, mock_storage_class, mock_get_commits, mock_validate, client
    ):
        """Dashboard has an edit button for the goal."""
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.get_setting.return_value = "1"
        mock_get_commits.return_value = []

        response = client.get("/")

        assert response.status_code == 200
        assert "data-goal-edit-btn" in response.text

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    @patch("src.app.GITHUB_USERNAME", "testuser")
    def test_dashboard_has_edit_form(
        self, mock_github_client, mock_storage_class, mock_get_commits, mock_validate, client
    ):
        """Dashboard has a hidden edit form for the goal."""
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.get_setting.return_value = "1"
        mock_get_commits.return_value = []

        response = client.get("/")

        assert response.status_code == 200
        assert "data-goal-form" in response.text
        assert 'id="goal-input"' in response.text


class TestGoalInStatsAPI:
    """Tests for goal data in the stats API."""

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    def test_stats_includes_goal(
        self, mock_github_client, mock_storage_class, mock_get_commits, mock_validate, client
    ):
        """Stats API includes goal information."""
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.get_setting.return_value = "5"
        mock_get_commits.return_value = []

        response = client.get("/api/stats")

        assert response.status_code == 200
        data = response.json()
        assert "goal" in data
        assert data["goal"]["daily"] == 5
        assert "today_progress" in data["goal"]
        assert "met" in data["goal"]

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    @patch("src.app.calculate_stats")
    def test_stats_goal_met_true(
        self, mock_stats, mock_github_client, mock_storage_class, mock_get_commits, mock_validate, client
    ):
        """Stats API shows goal.met as true when commits >= goal."""
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.get_setting.return_value = "2"
        mock_get_commits.return_value = []
        mock_stats.return_value = {
            "commits_today": 3,
            "commits_this_week": 3,
            "commits_this_month": 3,
            "commits_last_7_days": 3,
            "commits_last_30_days": 3,
            "total_commits": 3,
        }

        response = client.get("/api/stats")

        data = response.json()
        assert data["goal"]["met"] is True
        assert data["goal"]["today_progress"] == 3

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    @patch("src.app.calculate_stats")
    def test_stats_goal_met_false(
        self, mock_stats, mock_github_client, mock_storage_class, mock_get_commits, mock_validate, client
    ):
        """Stats API shows goal.met as false when commits < goal."""
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.get_setting.return_value = "5"
        mock_get_commits.return_value = []
        mock_stats.return_value = {
            "commits_today": 2,
            "commits_this_week": 2,
            "commits_this_month": 2,
            "commits_last_7_days": 2,
            "commits_last_30_days": 2,
            "total_commits": 2,
        }

        response = client.get("/api/stats")

        data = response.json()
        assert data["goal"]["met"] is False
        assert data["goal"]["today_progress"] == 2
