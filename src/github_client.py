"""
GitHub API client for fetching user activity.
"""

import requests


class GitHubClientError(Exception):
    """Base exception for GitHub client errors."""

    pass


class GitHubClient:
    """Client for interacting with the GitHub API."""

    BASE_URL = "https://api.github.com"

    def __init__(self, token: str, username: str):
        """
        Initialize the GitHub client.

        Args:
            token: GitHub personal access token
            username: GitHub username to fetch events for
        """
        self.token = token
        self.username = username
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def get_user_events(self, per_page: int = 30) -> list[dict]:
        """
        Fetch recent events for the configured user.

        Args:
            per_page: Number of events to fetch (max 100)

        Returns:
            List of event dictionaries from the GitHub API

        Raises:
            GitHubClientError: If the API request fails
        """
        url = f"{self.BASE_URL}/users/{self.username}/events"
        params = {"per_page": min(per_page, 100)}

        response = self.session.get(url, params=params)

        if response.status_code == 401:
            raise GitHubClientError(
                "Authentication failed. Check your GITHUB_TOKEN is valid."
            )
        elif response.status_code == 404:
            raise GitHubClientError(f"User '{self.username}' not found on GitHub.")
        elif response.status_code == 403:
            # Check for rate limiting
            remaining = response.headers.get("X-RateLimit-Remaining", "unknown")
            raise GitHubClientError(
                f"API rate limit exceeded or access forbidden. "
                f"Remaining requests: {remaining}"
            )
        elif not response.ok:
            raise GitHubClientError(
                f"GitHub API error: {response.status_code} - {response.text}"
            )

        return response.json()
