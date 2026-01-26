"""
Tests for the FastAPI web application.
"""

from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from src.app import app
from src.github_client import GitHubClientError


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_events():
    """Sample GitHub events for testing."""
    return [
        {
            "type": "PushEvent",
            "created_at": "2026-01-22T10:00:00Z",
            "repo": {"name": "user/test-repo"},
            "payload": {
                "commits": [{"sha": "abc123", "message": "test commit"}]
            },
        }
    ]


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    def test_health_returns_ok(self, client):
        """Health endpoint should return status ok."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestStatsEndpoint:
    """Tests for the /api/stats endpoint."""

    @patch("src.app.validate_config")
    @patch("src.app.GitHubClient")
    def test_stats_returns_expected_structure(
        self, mock_github_client, mock_validate, client
    ):
        """Stats endpoint should return JSON with expected structure."""
        # Mock GitHub client
        mock_client_instance = MagicMock()
        mock_github_client.return_value = mock_client_instance
        mock_client_instance.get_user_events.return_value = [
            {
                "type": "PushEvent",
                "created_at": "2026-01-22T10:00:00Z",
                "repo": {"name": "user/test-repo"},
                "payload": {
                    "commits": [
                        {"sha": "abc123", "message": "test commit"}
                    ]
                },
            }
        ]

        response = client.get("/api/stats")

        assert response.status_code == 200
        data = response.json()

        # Check top-level keys
        assert "username" in data
        assert "streak" in data
        assert "stats" in data
        assert "commit_dates" in data

        # Check streak structure
        streak = data["streak"]
        assert "current" in streak
        assert "longest" in streak
        assert "active" in streak
        assert "last_commit_date" in streak

        # Check stats structure
        stats = data["stats"]
        assert "today" in stats
        assert "this_week" in stats
        assert "this_month" in stats
        assert "last_7_days" in stats
        assert "last_30_days" in stats
        assert "total" in stats

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    def test_stats_with_no_events(
        self, mock_github_client, mock_storage, mock_get_commits, mock_validate, client
    ):
        """Stats endpoint should handle empty events gracefully."""
        mock_get_commits.return_value = []

        response = client.get("/api/stats")

        assert response.status_code == 200
        data = response.json()

        assert data["streak"]["current"] == 0
        assert data["streak"]["longest"] == 0
        assert data["streak"]["active"] is False
        assert data["stats"]["total"] == 0

    @patch("src.app.validate_config")
    def test_stats_config_error(self, mock_validate, client):
        """Stats endpoint should return 500 on configuration error."""
        mock_validate.side_effect = ValueError("Missing GITHUB_TOKEN")

        response = client.get("/api/stats")

        assert response.status_code == 500
        assert "Configuration error" in response.json()["detail"]

    @patch("src.app.validate_config")
    @patch("src.app.GitHubClient")
    def test_stats_github_error(self, mock_github_client, mock_validate, client):
        """Stats endpoint should return 502 on GitHub API error."""
        mock_client_instance = MagicMock()
        mock_github_client.return_value = mock_client_instance
        mock_client_instance.get_user_events.side_effect = GitHubClientError(
            "API rate limit exceeded"
        )

        response = client.get("/api/stats")

        assert response.status_code == 502
        assert "rate limit" in response.json()["detail"]

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    @patch("src.app.calculate_streak")
    def test_stats_calculates_streak_correctly(
        self, mock_streak, mock_github_client, mock_storage, mock_get_commits, mock_validate, client
    ):
        """Stats endpoint should correctly calculate streak from events."""
        # Return 3 commit events from storage
        mock_get_commits.return_value = [
            {
                "date": "2026-01-24",
                "repo": "user/repo",
                "commits": [{"sha": "a", "message": "m"}],
                "commit_count": 1,
            },
            {
                "date": "2026-01-23",
                "repo": "user/repo",
                "commits": [{"sha": "b", "message": "m"}],
                "commit_count": 1,
            },
            {
                "date": "2026-01-22",
                "repo": "user/repo",
                "commits": [{"sha": "c", "message": "m"}],
                "commit_count": 1,
            },
        ]

        # Mock streak calculation for consistent test results
        mock_streak.return_value = {
            "current_streak": 3,
            "longest_streak": 3,
            "streak_active": True,
            "last_commit_date": "2026-01-24",
            "commit_dates": ["2026-01-24", "2026-01-23", "2026-01-22"],
        }

        response = client.get("/api/stats")
        data = response.json()

        # Should have a 3-day streak
        assert data["streak"]["current"] == 3
        assert data["stats"]["total"] == 3
        assert len(data["commit_dates"]) == 3


class TestIndexEndpoint:
    """Tests for the / (index) HTML endpoint."""

    @patch("src.app.validate_config")
    @patch("src.app.GitHubClient")
    @patch("src.app.GITHUB_USERNAME", "testuser")
    def test_index_returns_html(self, mock_github_client, mock_validate, client, mock_events):
        """Index endpoint should return HTML content."""
        mock_client_instance = MagicMock()
        mock_github_client.return_value = mock_client_instance
        mock_client_instance.get_user_events.return_value = mock_events

        response = client.get("/")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @patch("src.app.validate_config")
    @patch("src.app.GitHubClient")
    @patch("src.app.GITHUB_USERNAME", "testuser")
    def test_index_displays_streak(self, mock_github_client, mock_validate, client, mock_events):
        """Index page should display Current Streak text."""
        mock_client_instance = MagicMock()
        mock_github_client.return_value = mock_client_instance
        mock_client_instance.get_user_events.return_value = mock_events

        response = client.get("/")

        assert response.status_code == 200
        assert "Current Streak" in response.text

    @patch("src.app.validate_config")
    @patch("src.app.GitHubClient")
    @patch("src.app.GITHUB_USERNAME", "testuser")
    def test_index_displays_username(self, mock_github_client, mock_validate, client, mock_events):
        """Index page should display the username."""
        mock_client_instance = MagicMock()
        mock_github_client.return_value = mock_client_instance
        mock_client_instance.get_user_events.return_value = mock_events

        response = client.get("/")

        assert response.status_code == 200
        assert "@testuser" in response.text

    @patch("src.app.validate_config")
    def test_index_handles_config_error(self, mock_validate, client):
        """Index endpoint should return 500 on configuration error."""
        mock_validate.side_effect = ValueError("Missing GITHUB_TOKEN")

        response = client.get("/")

        assert response.status_code == 500

    @patch("src.app.validate_config")
    @patch("src.app.GitHubClient")
    def test_index_handles_github_error(self, mock_github_client, mock_validate, client):
        """Index endpoint should return 502 on GitHub API error."""
        mock_client_instance = MagicMock()
        mock_github_client.return_value = mock_client_instance
        mock_client_instance.get_user_events.side_effect = GitHubClientError(
            "API rate limit exceeded"
        )

        response = client.get("/")

        assert response.status_code == 502


class TestFireVisualization:
    """Tests for the streak fire visualization."""

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    @patch("src.app.GITHUB_USERNAME", "testuser")
    def test_no_fire_for_zero_streak(
        self, mock_github_client, mock_storage, mock_get_commits, mock_validate, client
    ):
        """Zero streak should show no fire icon (dormant smoke)."""
        mock_get_commits.return_value = []

        response = client.get("/")

        assert response.status_code == 200
        assert 'data-fire="none"' in response.text
        assert 'data-fire="single"' not in response.text

    @patch("src.app.validate_config")
    @patch("src.app.GitHubClient")
    @patch("src.app.GITHUB_USERNAME", "testuser")
    @patch("src.app.calculate_streak")
    def test_single_fire_for_streak_1_to_6(
        self, mock_streak, mock_github_client, mock_validate, client
    ):
        """Streak of 1-6 days should show single fire icon."""
        mock_client_instance = MagicMock()
        mock_github_client.return_value = mock_client_instance
        mock_client_instance.get_user_events.return_value = []

        # Mock streak calculation to return streak of 3
        mock_streak.return_value = {
            "current_streak": 3,
            "longest_streak": 3,
            "streak_active": True,
            "last_commit_date": "2026-01-24",
            "commit_dates": ["2026-01-24", "2026-01-23", "2026-01-22"],
        }

        response = client.get("/")

        assert response.status_code == 200
        assert 'data-fire="single"' in response.text
        assert 'data-fire="double"' not in response.text

    @patch("src.app.validate_config")
    @patch("src.app.GitHubClient")
    @patch("src.app.GITHUB_USERNAME", "testuser")
    @patch("src.app.calculate_streak")
    def test_double_fire_for_streak_7_to_13(
        self, mock_streak, mock_github_client, mock_validate, client
    ):
        """Streak of 7-13 days should show double fire icon."""
        mock_client_instance = MagicMock()
        mock_github_client.return_value = mock_client_instance
        mock_client_instance.get_user_events.return_value = []

        # Mock streak calculation to return streak of 10
        mock_streak.return_value = {
            "current_streak": 10,
            "longest_streak": 10,
            "streak_active": True,
            "last_commit_date": "2026-01-24",
            "commit_dates": [f"2026-01-{24-i:02d}" for i in range(10)],
        }

        response = client.get("/")

        assert response.status_code == 200
        assert 'data-fire="double"' in response.text
        assert 'data-badge="week"' in response.text

    @patch("src.app.validate_config")
    @patch("src.app.GitHubClient")
    @patch("src.app.GITHUB_USERNAME", "testuser")
    @patch("src.app.calculate_streak")
    def test_triple_fire_for_streak_14_to_29(
        self, mock_streak, mock_github_client, mock_validate, client
    ):
        """Streak of 14-29 days should show triple fire icon."""
        mock_client_instance = MagicMock()
        mock_github_client.return_value = mock_client_instance
        mock_client_instance.get_user_events.return_value = []

        # Mock streak calculation to return streak of 20
        mock_streak.return_value = {
            "current_streak": 20,
            "longest_streak": 20,
            "streak_active": True,
            "last_commit_date": "2026-01-24",
            "commit_dates": ["2026-01-24"],  # Simplified
        }

        response = client.get("/")

        assert response.status_code == 200
        assert 'data-fire="triple"' in response.text

    @patch("src.app.validate_config")
    @patch("src.app.GitHubClient")
    @patch("src.app.GITHUB_USERNAME", "testuser")
    @patch("src.app.calculate_streak")
    def test_multi_fire_for_streak_30_plus(
        self, mock_streak, mock_github_client, mock_validate, client
    ):
        """Streak of 30+ days should show multiple fire icons and on-fire badge."""
        mock_client_instance = MagicMock()
        mock_github_client.return_value = mock_client_instance
        mock_client_instance.get_user_events.return_value = []

        # Mock streak calculation to return streak of 35
        mock_streak.return_value = {
            "current_streak": 35,
            "longest_streak": 35,
            "streak_active": True,
            "last_commit_date": "2026-01-24",
            "commit_dates": ["2026-01-24"],  # Simplified
        }

        response = client.get("/")

        assert response.status_code == 200
        assert 'data-fire="multi"' in response.text
        assert 'data-badge="on-fire"' in response.text


class TestHistoryEndpoint:
    """Tests for the /api/history endpoint."""

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    def test_history_returns_expected_structure(
        self, mock_github_client, mock_storage, mock_get_commits, mock_validate, client
    ):
        """History endpoint should return JSON with expected structure."""
        mock_get_commits.return_value = [
            {
                "date": "2026-01-26",
                "repo": "user/repo",
                "commits": [{"sha": "abc", "message": "test"}],
                "commit_count": 2,
            }
        ]

        response = client.get("/api/history")

        assert response.status_code == 200
        data = response.json()

        # Check top-level keys
        assert "days" in data
        assert "period" in data
        assert "max_count" in data

        # Check days structure
        assert len(data["days"]) == 84  # Default 12 weeks
        day = data["days"][0]
        assert "date" in day
        assert "count" in day
        assert "level" in day

        # Check period structure
        assert "start" in data["period"]
        assert "end" in data["period"]
        assert "total_days" in data["period"]

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    def test_history_with_no_events(
        self, mock_github_client, mock_storage, mock_get_commits, mock_validate, client
    ):
        """History endpoint should handle empty events gracefully."""
        mock_get_commits.return_value = []

        response = client.get("/api/history")

        assert response.status_code == 200
        data = response.json()

        assert data["max_count"] == 0
        # All days should have level 0
        for day in data["days"]:
            assert day["count"] == 0
            assert day["level"] == 0


class TestHeatmapVisualization:
    """Tests for the heatmap visualization on the index page."""

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    @patch("src.app.GITHUB_USERNAME", "testuser")
    def test_index_contains_heatmap_container(
        self, mock_github_client, mock_storage, mock_get_commits, mock_validate, client
    ):
        """Index page should contain the heatmap section."""
        mock_get_commits.return_value = []

        response = client.get("/")

        assert response.status_code == 200
        assert "data-heatmap" in response.text
        assert "Activity History" in response.text

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    @patch("src.app.GITHUB_USERNAME", "testuser")
    def test_heatmap_cells_have_level_classes(
        self, mock_github_client, mock_storage, mock_get_commits, mock_validate, client
    ):
        """Heatmap cells should have level-N classes based on commit counts."""
        mock_get_commits.return_value = []

        response = client.get("/")

        assert response.status_code == 200
        # With no commits, all cells should have level-0
        assert "level-0" in response.text

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    @patch("src.app.GITHUB_USERNAME", "testuser")
    @patch("src.app.calculate_history")
    def test_heatmap_cells_have_data_attributes(
        self, mock_history, mock_github_client, mock_storage, mock_get_commits, mock_validate, client
    ):
        """Heatmap cells should have data-date and data-count attributes."""
        mock_get_commits.return_value = []
        mock_history.return_value = {
            "days": [
                {"date": "2026-01-26", "count": 3, "level": 2},
                {"date": "2026-01-25", "count": 0, "level": 0},
            ],
            "period": {"start": "2025-11-04", "end": "2026-01-26", "total_days": 84},
            "max_count": 3,
        }

        response = client.get("/")

        assert response.status_code == 200
        assert 'data-date="2026-01-26"' in response.text
        assert 'data-count="3"' in response.text
        assert "level-2" in response.text

    @patch("src.app.validate_config")
    @patch("src.app.get_commit_events_with_history")
    @patch("src.app.CommitStorage")
    @patch("src.app.GitHubClient")
    @patch("src.app.GITHUB_USERNAME", "testuser")
    def test_heatmap_legend_displayed(
        self, mock_github_client, mock_storage, mock_get_commits, mock_validate, client
    ):
        """Heatmap should display the legend with Less/More labels."""
        mock_get_commits.return_value = []

        response = client.get("/")

        assert response.status_code == 200
        assert "Less" in response.text
        assert "More" in response.text
