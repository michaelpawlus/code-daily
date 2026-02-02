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

    def get_starred_repos(self, per_page: int = 30) -> list[dict]:
        """
        Fetch repos starred by the authenticated user.

        Args:
            per_page: Number of repos to fetch (max 100)

        Returns:
            List of repository dictionaries from the GitHub API

        Raises:
            GitHubClientError: If the API request fails
        """
        url = f"{self.BASE_URL}/user/starred"
        params = {"per_page": min(per_page, 100), "sort": "updated"}

        response = self.session.get(url, params=params)

        if response.status_code == 401:
            raise GitHubClientError(
                "Authentication failed. Check your GITHUB_TOKEN is valid."
            )
        elif response.status_code == 403:
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

    def search_good_first_issues(
        self, repos: list[str], labels: list[str] | None = None, per_page: int = 20
    ) -> list[dict]:
        """
        Search for good first issues in specified repos.

        Uses GitHub's search API to find open issues with beginner-friendly labels.

        Args:
            repos: List of repo full names (e.g., ["owner/repo", "org/project"])
            labels: Labels to search for. Defaults to ["good first issue", "help wanted"]
            per_page: Maximum number of issues to return (max 100)

        Returns:
            List of issue dictionaries from the GitHub search API

        Raises:
            GitHubClientError: If the API request fails
        """
        if not repos:
            return []

        if labels is None:
            labels = ["good first issue", "help wanted"]

        # Build the search query
        # Format: repo:owner/name repo:owner2/name2 label:"good first issue" state:open
        repo_parts = " ".join(f"repo:{repo}" for repo in repos[:10])  # Limit to 10 repos
        label_parts = " ".join(f'label:"{label}"' for label in labels)
        query = f"{repo_parts} {label_parts} state:open is:issue"

        url = f"{self.BASE_URL}/search/issues"
        params = {
            "q": query,
            "sort": "updated",
            "order": "desc",
            "per_page": min(per_page, 100),
        }

        response = self.session.get(url, params=params)

        if response.status_code == 401:
            raise GitHubClientError(
                "Authentication failed. Check your GITHUB_TOKEN is valid."
            )
        elif response.status_code == 403:
            remaining = response.headers.get("X-RateLimit-Remaining", "unknown")
            raise GitHubClientError(
                f"API rate limit exceeded or access forbidden. "
                f"Remaining requests: {remaining}"
            )
        elif response.status_code == 422:
            raise GitHubClientError(
                f"Invalid search query: {response.text}"
            )
        elif not response.ok:
            raise GitHubClientError(
                f"GitHub API error: {response.status_code} - {response.text}"
            )

        data = response.json()
        return data.get("items", [])

    def get_assigned_issues(self, state: str = "open", per_page: int = 30) -> list[dict]:
        """
        Fetch issues assigned to the authenticated user.

        Args:
            state: Issue state filter ('open', 'closed', 'all')
            per_page: Number of issues to fetch (max 100)

        Returns:
            List of issue dictionaries from the GitHub API

        Raises:
            GitHubClientError: If the API request fails
        """
        url = f"{self.BASE_URL}/issues"
        params = {
            "filter": "assigned",
            "state": state,
            "per_page": min(per_page, 100),
            "sort": "updated",
            "direction": "desc",
        }

        response = self.session.get(url, params=params)

        if response.status_code == 401:
            raise GitHubClientError(
                "Authentication failed. Check your GITHUB_TOKEN is valid."
            )
        elif response.status_code == 403:
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
