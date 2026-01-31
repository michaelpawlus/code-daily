"""
Tests for the GitHub client and configuration.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from src.config import validate_config
from src.github_client import GitHubClient, GitHubClientError


class TestConfig:
    """Tests for configuration validation."""

    def test_validate_config_missing_token(self):
        """Should raise error when token is missing."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "", "GITHUB_USERNAME": "testuser"}):
            with patch("src.config.GITHUB_TOKEN", ""):
                with patch("src.config.GITHUB_USERNAME", "testuser"):
                    with pytest.raises(ValueError, match="GITHUB_TOKEN"):
                        validate_config()

    def test_validate_config_missing_username(self):
        """Should raise error when username is missing."""
        with patch("src.config.GITHUB_TOKEN", "valid_token"):
            with patch("src.config.GITHUB_USERNAME", ""):
                with pytest.raises(ValueError, match="GITHUB_USERNAME"):
                    validate_config()

    def test_validate_config_placeholder_values(self):
        """Should reject placeholder values from .env.example."""
        with patch("src.config.GITHUB_TOKEN", "your_token_here"):
            with patch("src.config.GITHUB_USERNAME", "your_username_here"):
                with pytest.raises(ValueError):
                    validate_config()


class TestGitHubClient:
    """Tests for the GitHub API client."""

    def test_client_initialization(self):
        """Client should store credentials and set up session."""
        client = GitHubClient("test_token", "test_user")

        assert client.token == "test_token"
        assert client.username == "test_user"
        assert "Authorization" in client.session.headers
        assert "Bearer test_token" in client.session.headers["Authorization"]

    def test_client_headers(self):
        """Client should set correct API headers."""
        client = GitHubClient("test_token", "test_user")

        assert client.session.headers["Accept"] == "application/vnd.github+json"
        assert "X-GitHub-Api-Version" in client.session.headers

    @patch("requests.Session.get")
    def test_get_user_events_success(self, mock_get):
        """Should return events on successful API call."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"type": "PushEvent", "repo": {"name": "user/repo"}}
        ]
        mock_get.return_value = mock_response

        client = GitHubClient("test_token", "test_user")
        events = client.get_user_events()

        assert len(events) == 1
        assert events[0]["type"] == "PushEvent"
        mock_get.assert_called_once()

    @patch("requests.Session.get")
    def test_get_user_events_auth_failure(self, mock_get):
        """Should raise error on 401 unauthorized."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        client = GitHubClient("bad_token", "test_user")

        with pytest.raises(GitHubClientError, match="Authentication failed"):
            client.get_user_events()

    @patch("requests.Session.get")
    def test_get_user_events_user_not_found(self, mock_get):
        """Should raise error on 404 user not found."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        client = GitHubClient("test_token", "nonexistent_user")

        with pytest.raises(GitHubClientError, match="not found"):
            client.get_user_events()

    @patch("requests.Session.get")
    def test_get_user_events_rate_limit(self, mock_get):
        """Should raise error on 403 rate limit."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 403
        mock_response.headers = {"X-RateLimit-Remaining": "0"}
        mock_get.return_value = mock_response

        client = GitHubClient("test_token", "test_user")

        with pytest.raises(GitHubClientError, match="rate limit"):
            client.get_user_events()

    @patch("requests.Session.get")
    def test_get_user_events_respects_per_page(self, mock_get):
        """Should pass per_page parameter to API."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        client = GitHubClient("test_token", "test_user")
        client.get_user_events(per_page=50)

        call_args = mock_get.call_args
        assert call_args[1]["params"]["per_page"] == 50

    @patch("requests.Session.get")
    def test_get_user_events_caps_per_page_at_100(self, mock_get):
        """Should cap per_page at 100 (GitHub's max)."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        client = GitHubClient("test_token", "test_user")
        client.get_user_events(per_page=200)

        call_args = mock_get.call_args
        assert call_args[1]["params"]["per_page"] == 100


class TestGitHubClientAssignedIssues:
    """Tests for fetching assigned issues."""

    @patch("requests.Session.get")
    def test_get_assigned_issues_success(self, mock_get):
        """Should return issues on successful API call."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": 1,
                "title": "Test Issue",
                "html_url": "https://github.com/user/repo/issues/1",
                "body": "Issue description",
            }
        ]
        mock_get.return_value = mock_response

        client = GitHubClient("test_token", "test_user")
        issues = client.get_assigned_issues()

        assert len(issues) == 1
        assert issues[0]["title"] == "Test Issue"
        mock_get.assert_called_once()

        # Verify correct endpoint and params
        call_args = mock_get.call_args
        assert "/issues" in call_args[0][0]
        assert call_args[1]["params"]["filter"] == "assigned"
        assert call_args[1]["params"]["state"] == "open"

    @patch("requests.Session.get")
    def test_get_assigned_issues_auth_failure(self, mock_get):
        """Should raise error on 401 unauthorized."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        client = GitHubClient("bad_token", "test_user")

        with pytest.raises(GitHubClientError, match="Authentication failed"):
            client.get_assigned_issues()

    @patch("requests.Session.get")
    def test_get_assigned_issues_rate_limit(self, mock_get):
        """Should raise error on 403 rate limit."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 403
        mock_response.headers = {"X-RateLimit-Remaining": "0"}
        mock_get.return_value = mock_response

        client = GitHubClient("test_token", "test_user")

        with pytest.raises(GitHubClientError, match="rate limit"):
            client.get_assigned_issues()

    @patch("requests.Session.get")
    def test_get_assigned_issues_respects_state(self, mock_get):
        """Should pass state parameter to API."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        client = GitHubClient("test_token", "test_user")
        client.get_assigned_issues(state="closed")

        call_args = mock_get.call_args
        assert call_args[1]["params"]["state"] == "closed"

    @patch("requests.Session.get")
    def test_get_assigned_issues_caps_per_page_at_100(self, mock_get):
        """Should cap per_page at 100 (GitHub's max)."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        client = GitHubClient("test_token", "test_user")
        client.get_assigned_issues(per_page=200)

        call_args = mock_get.call_args
        assert call_args[1]["params"]["per_page"] == 100
