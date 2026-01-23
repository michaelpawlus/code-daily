"""
Tests for the FastAPI web application.
"""

from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from src.app import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


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
    @patch("src.app.GitHubClient")
    def test_stats_with_no_events(self, mock_github_client, mock_validate, client):
        """Stats endpoint should handle empty events gracefully."""
        mock_client_instance = MagicMock()
        mock_github_client.return_value = mock_client_instance
        mock_client_instance.get_user_events.return_value = []

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
        from src.github_client import GitHubClientError

        mock_client_instance = MagicMock()
        mock_github_client.return_value = mock_client_instance
        mock_client_instance.get_user_events.side_effect = GitHubClientError(
            "API rate limit exceeded"
        )

        response = client.get("/api/stats")

        assert response.status_code == 502
        assert "rate limit" in response.json()["detail"]

    @patch("src.app.validate_config")
    @patch("src.app.GitHubClient")
    def test_stats_calculates_streak_correctly(
        self, mock_github_client, mock_validate, client
    ):
        """Stats endpoint should correctly calculate streak from events."""
        mock_client_instance = MagicMock()
        mock_github_client.return_value = mock_client_instance

        # Create events for 3 consecutive days
        mock_client_instance.get_user_events.return_value = [
            {
                "type": "PushEvent",
                "created_at": "2026-01-22T10:00:00Z",
                "repo": {"name": "user/repo"},
                "payload": {"commits": [{"sha": "a", "message": "m"}]},
            },
            {
                "type": "PushEvent",
                "created_at": "2026-01-21T10:00:00Z",
                "repo": {"name": "user/repo"},
                "payload": {"commits": [{"sha": "b", "message": "m"}]},
            },
            {
                "type": "PushEvent",
                "created_at": "2026-01-20T10:00:00Z",
                "repo": {"name": "user/repo"},
                "payload": {"commits": [{"sha": "c", "message": "m"}]},
            },
        ]

        response = client.get("/api/stats")
        data = response.json()

        # Should have a 3-day streak
        assert data["streak"]["current"] == 3
        assert data["stats"]["total"] == 3
        assert len(data["commit_dates"]) == 3
