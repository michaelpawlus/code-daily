"""Tests for typer_cli module."""

import json
import os
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from src.typer_cli import app
from src.gh_issues import GhIssue

runner = CliRunner()


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------


class TestHelp:
    def test_main_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "code-daily" in result.output

    def test_issues_help(self):
        result = runner.invoke(app, ["issues", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output

    def test_vault_help(self):
        result = runner.invoke(app, ["vault", "--help"])
        assert result.exit_code == 0
        assert "scan" in result.output


# ---------------------------------------------------------------------------
# issues list
# ---------------------------------------------------------------------------


MOCK_ISSUES = [
    GhIssue(
        number=1, title="Fix bug", url="https://github.com/u/r/issues/1",
        repository="u/r", labels=["bug"], created_at="2025-01-01T00:00:00Z",
    ),
    GhIssue(
        number=2, title="Add feature", url="https://github.com/u/r/issues/2",
        repository="u/r", labels=["enhancement"],
    ),
]


class TestIssuesList:
    @patch("src.gh_issues.check_gh_auth", return_value={"authenticated": True, "message": ""})
    @patch("src.gh_issues.get_assigned_issues", return_value=MOCK_ISSUES)
    def test_human_output(self, mock_issues, mock_auth):
        result = runner.invoke(app, ["issues", "list"])
        assert result.exit_code == 0
        assert "Fix bug" in result.output
        assert "#1" in result.output

    @patch("src.gh_issues.check_gh_auth", return_value={"authenticated": True, "message": ""})
    @patch("src.gh_issues.get_assigned_issues", return_value=MOCK_ISSUES)
    def test_json_output(self, mock_issues, mock_auth):
        result = runner.invoke(app, ["issues", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["number"] == 1

    @patch("src.gh_issues.check_gh_auth", return_value={"authenticated": False, "message": "Not logged in"})
    def test_auth_failure(self, mock_auth):
        result = runner.invoke(app, ["issues", "list"])
        assert result.exit_code == 1

    @patch("src.gh_issues.check_gh_auth", return_value={"authenticated": True, "message": ""})
    @patch("src.gh_issues.get_assigned_issues", return_value=[])
    def test_no_issues(self, mock_issues, mock_auth):
        result = runner.invoke(app, ["issues", "list"])
        assert result.exit_code == 0
        assert "No issues" in result.output


# ---------------------------------------------------------------------------
# issues top
# ---------------------------------------------------------------------------


class TestIssuesTop:
    @patch("src.gh_issues.check_gh_auth", return_value={"authenticated": True, "message": ""})
    @patch("src.gh_issues.get_assigned_issues", return_value=MOCK_ISSUES)
    @patch("src.gh_issues.prioritize_issues")
    def test_json_output(self, mock_pri, mock_issues, mock_auth):
        mock_pri.return_value = [
            {"score": 8, "issue": MOCK_ISSUES[0]},
            {"score": 2, "issue": MOCK_ISSUES[1]},
        ]
        result = runner.invoke(app, ["issues", "top", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["score"] == 8


# ---------------------------------------------------------------------------
# vault scan
# ---------------------------------------------------------------------------


class TestVaultScan:
    def test_missing_vault_path(self, monkeypatch):
        monkeypatch.delenv("OBSIDIAN_VAULT_PATH", raising=False)
        result = runner.invoke(app, ["vault", "scan"])
        assert result.exit_code == 2

    @patch("src.obsidian_scanner.scan_vault")
    def test_scan_json(self, mock_scan, monkeypatch, tmp_path):
        monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
        from src.obsidian_scanner import ObsidianItem

        mock_scan.return_value = [
            ObsidianItem(
                source_file="Daily Notes/2025-03-15.md",
                content="Buy groceries",
                item_type="todo",
                context="Morning",
                date="2025-03-15",
            )
        ]
        result = runner.invoke(app, ["vault", "scan", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["content"] == "Buy groceries"


# ---------------------------------------------------------------------------
# vault ideas
# ---------------------------------------------------------------------------


class TestVaultIdeas:
    @patch("src.obsidian_scanner.scan_project_ideas")
    def test_ideas_json(self, mock_scan, monkeypatch, tmp_path):
        monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
        from src.obsidian_scanner import ObsidianItem

        mock_scan.return_value = [
            ObsidianItem(
                source_file="Project Ideas/CLI Dashboard.md",
                content="CLI Dashboard: A terminal tool",
                item_type="project_idea",
                context="Project Ideas",
                date="",
            )
        ]
        result = runner.invoke(app, ["vault", "ideas", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert "CLI Dashboard" in data[0]["content"]


# ---------------------------------------------------------------------------
# streak
# ---------------------------------------------------------------------------


MOCK_COMMIT_EVENTS = [
    {"date": "2026-03-18", "repo": "user/repo", "commits": [{"sha": "a1", "message": "test"}], "commit_count": 1},
    {"date": "2026-03-17", "repo": "user/repo", "commits": [{"sha": "a2", "message": "test"}], "commit_count": 1},
    {"date": "2026-03-16", "repo": "user/repo", "commits": [{"sha": "a3", "message": "test"}], "commit_count": 1},
]


class TestStreakShow:
    @patch("src.storage.get_commit_events_with_history", return_value=MOCK_COMMIT_EVENTS)
    @patch("src.storage.CommitStorage")
    @patch("src.github_client.GitHubClient")
    @patch("src.config.validate_config")
    def test_json_output(self, mock_config, mock_client, mock_storage, mock_commits):
        result = runner.invoke(app, ["streak", "show", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "current_streak" in data
        assert "longest_streak" in data
        assert "days_to_record" in data
        assert "is_record" in data

    @patch("src.storage.get_commit_events_with_history", return_value=MOCK_COMMIT_EVENTS)
    @patch("src.storage.CommitStorage")
    @patch("src.github_client.GitHubClient")
    @patch("src.config.validate_config")
    def test_human_output(self, mock_config, mock_client, mock_storage, mock_commits):
        result = runner.invoke(app, ["streak", "show"])
        assert result.exit_code == 0
        assert "streak" in result.output.lower()

    @patch("src.storage.get_commit_events_with_history", return_value=[])
    @patch("src.storage.CommitStorage")
    @patch("src.github_client.GitHubClient")
    @patch("src.config.validate_config")
    def test_no_commits(self, mock_config, mock_client, mock_storage, mock_commits):
        result = runner.invoke(app, ["streak", "show", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["current_streak"] == 0
        assert data["is_record"] is False

    @patch("src.config.validate_config", side_effect=ValueError("Missing GITHUB_TOKEN"))
    def test_config_error(self, mock_config):
        result = runner.invoke(app, ["streak", "show", "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert "error" in data


class TestStreakHistory:
    @patch("src.storage.CommitStorage")
    def test_empty_history(self, mock_storage_cls):
        instance = mock_storage_cls.return_value
        instance.get_notification_history.return_value = []
        result = runner.invoke(app, ["streak", "history"])
        assert result.exit_code == 0
        assert "No notifications" in result.output

    @patch("src.storage.CommitStorage")
    def test_json_output(self, mock_storage_cls):
        instance = mock_storage_cls.return_value
        instance.get_notification_history.return_value = [
            {"date": "2026-03-18", "level": 1, "channel": "ntfy", "message": "test msg"},
        ]
        result = runner.invoke(app, ["streak", "history", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["count"] == 1


# ---------------------------------------------------------------------------
# suggest
# ---------------------------------------------------------------------------


class TestSuggest:
    @patch("src.gh_issues.get_assigned_issues", return_value=MOCK_ISSUES)
    @patch("src.gh_issues.prioritize_issues")
    @patch("src.obsidian_scanner.scan_vault", return_value=[])
    def test_suggest_json(self, mock_vault, mock_pri, mock_issues, monkeypatch, tmp_path):
        monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
        mock_pri.return_value = [
            {"score": 5, "issue": MOCK_ISSUES[0]},
        ]
        result = runner.invoke(app, ["suggest", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) >= 1

    @patch("src.gh_issues.get_assigned_issues", side_effect=Exception("fail"))
    def test_suggest_handles_gh_failure(self, mock_issues, monkeypatch):
        monkeypatch.delenv("OBSIDIAN_VAULT_PATH", raising=False)
        result = runner.invoke(app, ["suggest", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------


class TestCheck:
    @patch("src.notifications.NotificationManager")
    @patch("src.storage.CommitStorage")
    def test_check_json(self, mock_storage, mock_nm):
        instance = mock_nm.return_value
        instance.check_and_notify.return_value = {"action": "skipped", "reason": "already_committed"}
        result = runner.invoke(app, ["check", "1", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["action"] == "skipped"


# ---------------------------------------------------------------------------
# notify
# ---------------------------------------------------------------------------


class TestNotify:
    @patch("src.main._run_notify_test", return_value=0)
    def test_notify_test(self, mock_fn):
        result = runner.invoke(app, ["notify", "test"])
        assert result.exit_code == 0

    @patch("src.main._run_notify_status", return_value=0)
    def test_notify_status(self, mock_fn):
        result = runner.invoke(app, ["notify", "status"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# cron
# ---------------------------------------------------------------------------


class TestCron:
    @patch("src.main._run_setup_cron", return_value=0)
    def test_cron_print(self, mock_fn):
        result = runner.invoke(app, ["cron"])
        assert result.exit_code == 0

    def test_cron_help_shows_install(self):
        result = runner.invoke(app, ["cron", "--help"])
        assert result.exit_code == 0
        assert "--install" in result.output
        assert "--uninstall" in result.output
