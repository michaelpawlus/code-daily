"""Tests for gh_issues module."""

import json
from unittest.mock import patch, MagicMock

import pytest

from src.gh_issues import (
    GhIssue,
    check_gh_auth,
    get_assigned_issues,
    search_issues,
    prioritize_issues,
    _parse_issue,
)


# ---------------------------------------------------------------------------
# check_gh_auth
# ---------------------------------------------------------------------------


class TestCheckGhAuth:
    @patch("src.gh_issues.subprocess.run")
    def test_authenticated(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Logged in", stderr="")
        result = check_gh_auth()
        assert result["authenticated"] is True
        assert "Logged in" in result["message"]

    @patch("src.gh_issues.subprocess.run")
    def test_not_authenticated(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Not logged in")
        result = check_gh_auth()
        assert result["authenticated"] is False

    @patch("src.gh_issues.subprocess.run", side_effect=FileNotFoundError)
    def test_gh_not_installed(self, mock_run):
        result = check_gh_auth()
        assert result["authenticated"] is False
        assert "not found" in result["message"]

    @patch("src.gh_issues.subprocess.run", side_effect=__import__("subprocess").TimeoutExpired("gh", 10))
    def test_timeout(self, mock_run):
        result = check_gh_auth()
        assert result["authenticated"] is False
        assert "timed out" in result["message"]


# ---------------------------------------------------------------------------
# get_assigned_issues
# ---------------------------------------------------------------------------


SAMPLE_GH_OUTPUT = json.dumps([
    {
        "number": 42,
        "title": "Fix login bug",
        "url": "https://github.com/user/repo/issues/42",
        "repository": {"nameWithOwner": "user/repo"},
        "labels": [{"name": "bug"}, {"name": "p1"}],
        "createdAt": "2025-01-01T00:00:00Z",
        "updatedAt": "2025-01-10T00:00:00Z",
        "comments": [{"body": "comment1"}, {"body": "comment2"}],
    },
    {
        "number": 99,
        "title": "Add dark mode",
        "url": "https://github.com/user/repo/issues/99",
        "repository": {"nameWithOwner": "user/repo"},
        "labels": [{"name": "enhancement"}],
        "createdAt": "2025-02-01T00:00:00Z",
        "updatedAt": "2025-02-05T00:00:00Z",
        "comments": [],
    },
])


class TestGetAssignedIssues:
    @patch("src.gh_issues.subprocess.run")
    def test_returns_issues(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=SAMPLE_GH_OUTPUT)
        issues = get_assigned_issues()
        assert len(issues) == 2
        assert issues[0].number == 42
        assert issues[0].title == "Fix login bug"
        assert issues[0].repository == "user/repo"
        assert "bug" in issues[0].labels
        assert issues[0].comments == 2

    @patch("src.gh_issues.subprocess.run")
    def test_with_label_filter(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="[]")
        get_assigned_issues(labels="bug")
        cmd = mock_run.call_args[0][0]
        assert "--label=bug" in cmd

    @patch("src.gh_issues.subprocess.run")
    def test_with_repo_filter(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="[]")
        get_assigned_issues(repo="user/repo")
        cmd = mock_run.call_args[0][0]
        assert "-R" in cmd
        assert "user/repo" in cmd

    @patch("src.gh_issues.subprocess.run")
    def test_gh_failure_returns_empty(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        issues = get_assigned_issues()
        assert issues == []

    @patch("src.gh_issues.subprocess.run", side_effect=FileNotFoundError)
    def test_gh_not_found_returns_empty(self, mock_run):
        issues = get_assigned_issues()
        assert issues == []

    @patch("src.gh_issues.subprocess.run")
    def test_invalid_json_returns_empty(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="not json")
        issues = get_assigned_issues()
        assert issues == []


# ---------------------------------------------------------------------------
# search_issues
# ---------------------------------------------------------------------------


class TestSearchIssues:
    @patch("src.gh_issues.subprocess.run")
    def test_search(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=SAMPLE_GH_OUTPUT)
        issues = search_issues("login bug")
        assert len(issues) == 2
        cmd = mock_run.call_args[0][0]
        assert "login bug" in cmd


# ---------------------------------------------------------------------------
# _parse_issue
# ---------------------------------------------------------------------------


class TestParseIssue:
    def test_parses_dict_labels(self):
        issue = _parse_issue({
            "number": 1,
            "title": "test",
            "url": "http://example.com",
            "repository": {"nameWithOwner": "org/repo"},
            "labels": [{"name": "bug"}],
            "createdAt": "2025-01-01T00:00:00Z",
            "updatedAt": "2025-01-01T00:00:00Z",
            "comments": [],
        })
        assert issue.labels == ["bug"]
        assert issue.repository == "org/repo"

    def test_handles_string_labels(self):
        issue = _parse_issue({
            "number": 1,
            "title": "test",
            "url": "",
            "repository": "org/repo",
            "labels": ["bug"],
            "comments": 5,
        })
        assert issue.labels == ["bug"]
        assert issue.comments == 5

    def test_handles_missing_fields(self):
        issue = _parse_issue({})
        assert issue.number == 0
        assert issue.title == ""
        assert issue.labels == []


# ---------------------------------------------------------------------------
# prioritize_issues
# ---------------------------------------------------------------------------


class TestPrioritizeIssues:
    def test_bugs_rank_higher(self):
        bug = GhIssue(number=1, title="Bug", url="", repository="r", labels=["bug"])
        feat = GhIssue(number=2, title="Feature", url="", repository="r", labels=["enhancement"])
        ranked = prioritize_issues([feat, bug])
        assert ranked[0]["issue"].number == 1
        assert ranked[0]["score"] > ranked[1]["score"]

    def test_old_issues_get_bonus(self):
        old = GhIssue(
            number=1, title="Old", url="", repository="r",
            labels=[], created_at="2020-01-01T00:00:00Z",
        )
        new = GhIssue(
            number=2, title="New", url="", repository="r",
            labels=[], created_at="2099-01-01T00:00:00Z",
        )
        ranked = prioritize_issues([new, old])
        assert ranked[0]["issue"].number == 1

    def test_comments_add_score(self):
        active = GhIssue(number=1, title="Active", url="", repository="r", labels=[], comments=5)
        quiet = GhIssue(number=2, title="Quiet", url="", repository="r", labels=[], comments=0)
        ranked = prioritize_issues([quiet, active])
        assert ranked[0]["issue"].number == 1

    def test_empty_list(self):
        assert prioritize_issues([]) == []
