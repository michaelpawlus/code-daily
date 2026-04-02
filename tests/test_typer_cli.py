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


# ---------------------------------------------------------------------------
# quests help
# ---------------------------------------------------------------------------


class TestQuestsHelp:
    def test_quests_help(self):
        result = runner.invoke(app, ["quests", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "add" in result.output

    def test_achievements_help(self):
        result = runner.invoke(app, ["achievements", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output


# ---------------------------------------------------------------------------
# quests list
# ---------------------------------------------------------------------------


MOCK_QUESTS_PENDING = [
    {"id": 1, "title": "[u/r] Fix login bug", "source": "github_issue", "status": "pending", "priority_score": 12, "created_at": "2026-03-28T10:00:00"},
    {"id": 5, "title": "[TODO] Refactor storage", "source": "todo_scan", "status": "pending", "priority_score": 9, "created_at": "2026-03-29T10:00:00"},
]

MOCK_QUESTS_ACTIVE = [
    {"id": 3, "title": "Build CLI dashboard", "source": "manual", "status": "active", "created_at": "2026-03-30T14:00:00"},
]

MOCK_QUEST_SUMMARY = {"total": 15, "pending": 10, "active": 2, "completed": 3, "skipped": 0, "archived": 0}


class TestQuestsList:
    @patch("src.quest_manager.QuestManager.get_quest_summary", return_value=MOCK_QUEST_SUMMARY)
    @patch("src.quest_manager.QuestManager.get_active_quests", return_value=MOCK_QUESTS_ACTIVE)
    @patch("src.quest_manager.QuestManager.get_prioritized_quests", return_value=MOCK_QUESTS_PENDING)
    @patch("src.storage.CommitStorage")
    def test_json_output_default(self, mock_storage_cls, mock_pending, mock_active, mock_summary):
        result = runner.invoke(app, ["quests", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "pending" in data
        assert "active" in data
        assert "summary" in data

    @patch("src.storage.CommitStorage")
    def test_json_output_status_filter(self, mock_storage_cls):
        instance = mock_storage_cls.return_value
        instance.get_quests.return_value = [
            {"id": 1, "title": "Done quest", "status": "completed", "source": "manual", "created_at": "2026-03-28T10:00:00"},
        ]
        result = runner.invoke(app, ["quests", "list", "--json", "--status", "completed"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    @patch("src.quest_manager.QuestManager.get_quest_summary", return_value={"total": 0, "pending": 0, "active": 0, "completed": 0, "skipped": 0, "archived": 0})
    @patch("src.quest_manager.QuestManager.get_active_quests", return_value=[])
    @patch("src.quest_manager.QuestManager.get_prioritized_quests", return_value=[])
    @patch("src.storage.CommitStorage")
    def test_human_output_empty(self, mock_storage_cls, mock_pending, mock_active, mock_summary):
        result = runner.invoke(app, ["quests", "list"])
        assert result.exit_code == 0
        assert "Quest Board" in result.output or "0" in result.output

    @patch("src.quest_manager.QuestManager.get_quest_summary", return_value=MOCK_QUEST_SUMMARY)
    @patch("src.quest_manager.QuestManager.get_active_quests", return_value=MOCK_QUESTS_ACTIVE)
    @patch("src.quest_manager.QuestManager.get_prioritized_quests", return_value=MOCK_QUESTS_PENDING)
    @patch("src.storage.CommitStorage")
    def test_human_output(self, mock_storage_cls, mock_pending, mock_active, mock_summary):
        result = runner.invoke(app, ["quests", "list"])
        assert result.exit_code == 0
        assert "Quest Board" in result.output
        assert "Pending" in result.output


# ---------------------------------------------------------------------------
# quests add
# ---------------------------------------------------------------------------


MOCK_CREATED_QUEST = {"id": 16, "title": "Build a REST API", "source": "manual", "description": "For the new service", "status": "pending", "created_at": "2026-04-01T09:00:00"}


class TestQuestsAdd:
    @patch("src.quest_manager.QuestManager.add_manual_quest", return_value=MOCK_CREATED_QUEST)
    @patch("src.storage.CommitStorage")
    def test_add_quest_json(self, mock_storage_cls, mock_add):
        result = runner.invoke(app, ["quests", "add", "Build a REST API", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["quest"]["title"] == "Build a REST API"

    @patch("src.quest_manager.QuestManager.add_manual_quest", return_value=MOCK_CREATED_QUEST)
    @patch("src.storage.CommitStorage")
    def test_add_quest_with_description(self, mock_storage_cls, mock_add):
        result = runner.invoke(app, ["quests", "add", "Build a REST API", "-d", "For the new service", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["quest"]["description"] == "For the new service"

    @patch("src.quest_manager.QuestManager.add_manual_quest", return_value=MOCK_CREATED_QUEST)
    @patch("src.storage.CommitStorage")
    def test_add_quest_human(self, mock_storage_cls, mock_add):
        result = runner.invoke(app, ["quests", "add", "Build a REST API"])
        assert result.exit_code == 0
        assert "created" in result.output.lower()


# ---------------------------------------------------------------------------
# quest lifecycle (accept, complete, skip)
# ---------------------------------------------------------------------------


class TestQuestLifecycle:
    @patch("src.quest_manager.QuestManager.accept_quest", return_value={"id": 1, "title": "Fix bug", "status": "active"})
    @patch("src.storage.CommitStorage")
    def test_accept_quest(self, mock_storage_cls, mock_accept):
        result = runner.invoke(app, ["quests", "accept", "1", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["quest"]["status"] == "active"

    @patch("src.quest_manager.QuestManager.accept_quest", return_value=None)
    @patch("src.storage.CommitStorage")
    def test_accept_quest_not_found(self, mock_storage_cls, mock_accept):
        result = runner.invoke(app, ["quests", "accept", "999", "--json"])
        assert result.exit_code == 2

    @patch("src.quest_manager.QuestManager.complete_quest", return_value={"id": 1, "title": "Fix bug", "status": "completed"})
    @patch("src.storage.CommitStorage")
    def test_complete_quest(self, mock_storage_cls, mock_complete):
        result = runner.invoke(app, ["quests", "complete", "1", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["quest"]["status"] == "completed"

    @patch("src.quest_manager.QuestManager.complete_quest", return_value=None)
    @patch("src.storage.CommitStorage")
    def test_complete_quest_not_found(self, mock_storage_cls, mock_complete):
        result = runner.invoke(app, ["quests", "complete", "999", "--json"])
        assert result.exit_code == 2

    @patch("src.quest_manager.QuestManager.skip_quest", return_value={"success": True, "quest": {"id": 1, "title": "Fix bug", "status": "archived"}})
    @patch("src.storage.CommitStorage")
    def test_skip_quest(self, mock_storage_cls, mock_skip):
        result = runner.invoke(app, ["quests", "skip", "1", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True

    @patch("src.quest_manager.QuestManager.skip_quest", return_value={"success": True, "quest": {"id": 1, "title": "Fix bug", "status": "archived"}, "idea": {"id": 5, "content": "Fix bug", "status": "active"}})
    @patch("src.storage.CommitStorage")
    def test_skip_quest_save_idea(self, mock_storage_cls, mock_skip):
        result = runner.invoke(app, ["quests", "skip", "1", "--save-idea", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "idea" in data

    @patch("src.quest_manager.QuestManager.skip_quest", return_value={"success": False, "error": "Quest not found"})
    @patch("src.storage.CommitStorage")
    def test_skip_quest_not_found(self, mock_storage_cls, mock_skip):
        result = runner.invoke(app, ["quests", "skip", "999", "--json"])
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# quests summary
# ---------------------------------------------------------------------------


class TestQuestsSummary:
    @patch("src.quest_manager.QuestManager.get_quest_summary", return_value=MOCK_QUEST_SUMMARY)
    @patch("src.storage.CommitStorage")
    def test_summary_json(self, mock_storage_cls, mock_summary):
        result = runner.invoke(app, ["quests", "summary", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total"] == 15
        assert data["pending"] == 10

    @patch("src.quest_manager.QuestManager.get_quest_summary", return_value=MOCK_QUEST_SUMMARY)
    @patch("src.storage.CommitStorage")
    def test_summary_human(self, mock_storage_cls, mock_summary):
        result = runner.invoke(app, ["quests", "summary"])
        assert result.exit_code == 0
        assert "Quest Summary" in result.output


# ---------------------------------------------------------------------------
# quests sync
# ---------------------------------------------------------------------------


class TestQuestsSync:
    @patch("src.quest_manager.QuestManager.sync_github_issues", return_value={"added": 3, "skipped": 7})
    @patch("src.github_client.GitHubClient.get_assigned_issues", return_value=[])
    @patch("src.github_client.GitHubClient.__init__", return_value=None)
    @patch("src.config.validate_config")
    @patch("src.storage.CommitStorage")
    def test_sync_issues_json(self, mock_storage_cls, mock_config, mock_init, mock_issues, mock_sync):
        result = runner.invoke(app, ["quests", "sync-issues", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "added" in data
        assert "skipped" in data

    @patch("src.config.validate_config", side_effect=ValueError("Missing GITHUB_TOKEN"))
    def test_sync_issues_config_error(self, mock_config):
        result = runner.invoke(app, ["quests", "sync-issues", "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert "error" in data

    @patch("src.quest_manager.QuestManager.sync_todo_comments", return_value={"added": 2, "skipped": 5})
    @patch("src.todo_scanner.scan_directory", return_value=[])
    @patch("src.storage.CommitStorage")
    def test_scan_todos_json(self, mock_storage_cls, mock_scan, mock_sync):
        result = runner.invoke(app, ["quests", "scan-todos", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "added" in data
        assert "skipped" in data


# ---------------------------------------------------------------------------
# quests AI
# ---------------------------------------------------------------------------


class TestQuestsAI:
    @patch("src.quest_manager.QuestManager.get_ai_status", return_value={"enabled": True, "message": "AI features enabled"})
    @patch("src.storage.CommitStorage")
    def test_ai_status_json(self, mock_storage_cls, mock_ai):
        result = runner.invoke(app, ["quests", "ai-status", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "enabled" in data

    @patch("src.quest_manager.QuestManager.get_ai_status", return_value={"enabled": False, "message": "Set ANTHROPIC_API_KEY"})
    @patch("src.storage.CommitStorage")
    def test_ai_status_disabled(self, mock_storage_cls, mock_ai):
        result = runner.invoke(app, ["quests", "ai-status"])
        assert result.exit_code == 0
        assert "Disabled" in result.output

    @patch("src.quest_manager.QuestManager.enhance_quest", return_value={"success": False, "error": "Quest not found"})
    @patch("src.storage.CommitStorage")
    def test_enhance_quest_not_found(self, mock_storage_cls, mock_enhance):
        result = runner.invoke(app, ["quests", "enhance", "999", "--json"])
        assert result.exit_code == 2

    @patch("src.quest_manager.QuestManager.enhance_quest", return_value={"success": True, "quest": {"id": 1, "title": "Fix bug", "ai_description": "Fix the auth flow", "difficulty": 2, "difficulty_reasoning": "Moderate complexity"}})
    @patch("src.storage.CommitStorage")
    def test_enhance_quest_json(self, mock_storage_cls, mock_enhance):
        result = runner.invoke(app, ["quests", "enhance", "1", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True
        assert data["quest"]["ai_description"] == "Fix the auth flow"

    @patch("src.quest_manager.QuestManager.enhance_pending_quests", return_value={"success": True, "enhanced": 3, "total_requested": 3, "errors": [], "quests": []})
    @patch("src.storage.CommitStorage")
    def test_enhance_batch_json(self, mock_storage_cls, mock_enhance):
        result = runner.invoke(app, ["quests", "enhance-batch", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "enhanced" in data

    @patch("src.quest_manager.QuestManager.enhance_pending_quests", return_value={"success": False, "error": "AI features not configured. Set ANTHROPIC_API_KEY in .env", "enhanced": 0, "errors": []})
    @patch("src.storage.CommitStorage")
    def test_enhance_batch_no_ai(self, mock_storage_cls, mock_enhance):
        result = runner.invoke(app, ["quests", "enhance-batch", "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert "error" in data


# ---------------------------------------------------------------------------
# achievements list
# ---------------------------------------------------------------------------


MOCK_UNLOCKED = [
    {"id": "first_commit", "unlocked_at": "2026-01-15 10:00:00", "unlocked_value": 1},
]

MOCK_ALL_ACHIEVEMENTS = [
    {"id": "first_commit", "name": "Hello World", "emoji": "wave", "description": "Make your first commit", "category": "commits", "threshold": 1, "unlocked": True, "unlocked_at": "2026-01-15 10:00:00", "unlocked_value": 1},
    {"id": "commits_10", "name": "Getting Started", "emoji": "seedling", "description": "Make 10 total commits", "category": "commits", "threshold": 10, "unlocked": False, "unlocked_at": None, "unlocked_value": None},
    {"id": "streak_3", "name": "First Steps", "emoji": "fire", "description": "Maintain a 3-day coding streak", "category": "streak", "threshold": 3, "unlocked": False, "unlocked_at": None, "unlocked_value": None},
]


class TestAchievementsList:
    @patch("src.achievements.get_all_achievements_status", return_value=MOCK_ALL_ACHIEVEMENTS)
    @patch("src.storage.CommitStorage")
    def test_achievements_json(self, mock_storage_cls, mock_achv):
        instance = mock_storage_cls.return_value
        instance.get_unlocked_achievements.return_value = MOCK_UNLOCKED
        result = runner.invoke(app, ["achievements", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "achievements" in data
        assert "summary" in data
        assert data["summary"]["total"] == 3

    @patch("src.achievements.get_all_achievements_status", return_value=MOCK_ALL_ACHIEVEMENTS)
    @patch("src.storage.CommitStorage")
    def test_achievements_category_filter(self, mock_storage_cls, mock_achv):
        instance = mock_storage_cls.return_value
        instance.get_unlocked_achievements.return_value = MOCK_UNLOCKED
        result = runner.invoke(app, ["achievements", "list", "--json", "--category", "streak"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        for a in data["achievements"]:
            assert a["category"] == "streak"

    @patch("src.achievements.get_all_achievements_status", return_value=[a for a in MOCK_ALL_ACHIEVEMENTS if not a["unlocked"]])
    @patch("src.storage.CommitStorage")
    def test_achievements_no_unlocked(self, mock_storage_cls, mock_achv):
        instance = mock_storage_cls.return_value
        instance.get_unlocked_achievements.return_value = []
        result = runner.invoke(app, ["achievements", "list"])
        assert result.exit_code == 0
        assert "0" in result.output or "unlocked" in result.output.lower()


# ---------------------------------------------------------------------------
# ideas list
# ---------------------------------------------------------------------------


MOCK_IDEAS = [
    {"id": 1, "content": "Build a CLI dashboard", "status": "active", "created_at": "2026-03-28T10:00:00"},
    {"id": 2, "content": "Add notifications", "status": "active", "created_at": "2026-03-29T10:00:00"},
]


class TestIdeasList:
    @patch("src.storage.CommitStorage")
    def test_ideas_list_json(self, mock_storage_cls):
        instance = mock_storage_cls.return_value
        instance.get_ideas.return_value = MOCK_IDEAS
        result = runner.invoke(app, ["ideas", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "ideas" in data

    @patch("src.storage.CommitStorage")
    def test_ideas_list_empty(self, mock_storage_cls):
        instance = mock_storage_cls.return_value
        instance.get_ideas.return_value = []
        result = runner.invoke(app, ["ideas", "list"])
        assert result.exit_code == 0
        assert "No ideas" in result.output


# ---------------------------------------------------------------------------
# ideas add
# ---------------------------------------------------------------------------


class TestIdeasAdd:
    @patch("src.ideas.add_idea")
    @patch("src.storage.CommitStorage")
    def test_add_idea_json(self, mock_storage_cls, mock_add):
        instance = mock_storage_cls.return_value
        instance.create_idea.return_value = 4
        instance.get_idea.return_value = {"id": 4, "content": "Build a caching layer", "status": "active", "created_at": "2026-04-01T09:00:00"}
        result = runner.invoke(app, ["ideas", "add", "Build a caching layer", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "idea" in data
        assert data["idea"]["content"] == "Build a caching layer"

    @patch("src.ideas.add_idea")
    @patch("src.storage.CommitStorage")
    def test_add_idea_human(self, mock_storage_cls, mock_add):
        instance = mock_storage_cls.return_value
        instance.create_idea.return_value = 4
        instance.get_idea.return_value = {"id": 4, "content": "Build a caching layer", "status": "active"}
        result = runner.invoke(app, ["ideas", "add", "Build a caching layer"])
        assert result.exit_code == 0
        assert "created" in result.output.lower()


# ---------------------------------------------------------------------------
# ideas promote
# ---------------------------------------------------------------------------


class TestIdeasPromote:
    @patch("src.quest_manager.QuestManager.promote_idea_to_quest", return_value={"id": 17, "title": "Build a caching layer", "source": "ideas_md", "status": "pending"})
    @patch("src.storage.CommitStorage")
    def test_promote_idea_json(self, mock_storage_cls, mock_promote):
        result = runner.invoke(app, ["ideas", "promote", "1", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "quest" in data

    @patch("src.quest_manager.QuestManager.promote_idea_to_quest", return_value=None)
    @patch("src.storage.CommitStorage")
    def test_promote_idea_not_found(self, mock_storage_cls, mock_promote):
        result = runner.invoke(app, ["ideas", "promote", "999", "--json"])
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# ideas sync
# ---------------------------------------------------------------------------


class TestIdeasSync:
    @patch("src.ideas.sync_ideas_to_db", return_value={"added": 2, "updated": 0, "total_in_file": 5, "total_in_db": 7})
    @patch("src.storage.CommitStorage")
    def test_sync_ideas_json(self, mock_storage_cls, mock_sync):
        result = runner.invoke(app, ["ideas", "sync", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["added"] == 2
