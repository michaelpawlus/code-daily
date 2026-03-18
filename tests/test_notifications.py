"""
Tests for the notification system.
"""

import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.notifications import (
    MESSAGES,
    NTFY_PRIORITY_MAP,
    ZERO_STREAK_MESSAGES,
    NotificationManager,
    NtfyChannel,
    build_message,
)
from src.storage import CommitStorage


@pytest.fixture
def tmp_storage(tmp_path):
    """Create a temporary CommitStorage for testing."""
    db_path = tmp_path / "test.db"
    return CommitStorage(db_path=db_path)


class TestBuildMessage:
    """Tests for the build_message function."""

    def test_active_streak_returns_empty(self):
        msg = build_message(level=1, current_streak=5, streak_active=True)
        assert msg == ""

    def test_zero_streak_returns_zero_message(self):
        for level in range(1, 5):
            msg = build_message(level=level, current_streak=0, streak_active=False)
            assert msg == ZERO_STREAK_MESSAGES[level]

    def test_includes_streak_count(self):
        for level in range(1, 5):
            msg = build_message(level=level, current_streak=7, streak_active=False)
            assert "7" in msg

    def test_level_1_is_gentle(self):
        msg = build_message(level=1, current_streak=5, streak_active=False)
        assert msg  # non-empty
        # Level 1 should not contain emergency language
        assert "EMERGENCY" not in msg
        assert "LAST CALL" not in msg

    def test_level_4_is_urgent(self):
        # Test all 3 variants of level 4 for urgency
        for option in MESSAGES[4]:
            formatted = option.format(streak=10)
            assert any(
                word in formatted
                for word in ["LAST CALL", "EMERGENCY", "hours to live"]
            )

    def test_deterministic_variety(self):
        """Message selection is based on day_of_year, so same day = same message."""
        msg1 = build_message(level=2, current_streak=3, streak_active=False)
        msg2 = build_message(level=2, current_streak=3, streak_active=False)
        assert msg1 == msg2

    def test_all_levels_produce_messages(self):
        for level in range(1, 5):
            msg = build_message(level=level, current_streak=10, streak_active=False)
            assert isinstance(msg, str)
            assert len(msg) > 0


class TestNtfyChannel:
    """Tests for the NtfyChannel class."""

    def test_not_configured_without_topic(self):
        ch = NtfyChannel(topic=None, server="https://ntfy.sh")
        assert not ch.is_configured

    def test_not_configured_with_empty_topic(self):
        ch = NtfyChannel(topic="", server="https://ntfy.sh")
        assert not ch.is_configured

    def test_not_configured_with_whitespace_topic(self):
        ch = NtfyChannel(topic="   ", server="https://ntfy.sh")
        assert not ch.is_configured

    def test_configured_with_topic(self):
        ch = NtfyChannel(topic="my-topic", server="https://ntfy.sh")
        assert ch.is_configured

    def test_name_is_ntfy(self):
        ch = NtfyChannel(topic="t", server="https://ntfy.sh")
        assert ch.name == "ntfy"

    def test_send_not_configured_returns_false(self):
        ch = NtfyChannel(topic=None, server="https://ntfy.sh")
        assert ch.send("msg", "title", 1) is False

    @patch("src.notifications.requests.post")
    def test_send_success(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)

        ch = NtfyChannel(topic="test-topic", server="https://ntfy.sh")
        result = ch.send("Hello", "Test Title", 2)

        assert result is True
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args.args[0] == "https://ntfy.sh"
        payload = call_args.kwargs["json"]
        assert payload["topic"] == "test-topic"
        assert payload["title"] == "Test Title"
        assert payload["message"] == "Hello"
        assert payload["priority"] == int(NTFY_PRIORITY_MAP[2])

    @patch("src.notifications.requests.post")
    def test_send_failure_status(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500)

        ch = NtfyChannel(topic="test-topic", server="https://ntfy.sh")
        result = ch.send("Hello", "Title", 1)

        assert result is False

    @patch("src.notifications.requests.post")
    def test_send_network_error(self, mock_post):
        import requests

        mock_post.side_effect = requests.ConnectionError("fail")

        ch = NtfyChannel(topic="test-topic", server="https://ntfy.sh")
        result = ch.send("Hello", "Title", 1)

        assert result is False

    @patch("src.notifications.requests.post")
    def test_priority_mapping(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)

        ch = NtfyChannel(topic="t", server="https://ntfy.sh")

        for level, expected_priority in NTFY_PRIORITY_MAP.items():
            ch.send("msg", "title", level)
            payload = mock_post.call_args.kwargs["json"]
            assert payload["priority"] == int(expected_priority)

    @patch("src.notifications.requests.post")
    def test_high_level_gets_fire_tags(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)

        ch = NtfyChannel(topic="t", server="https://ntfy.sh")

        ch.send("msg", "title", 3)
        assert "fire" in mock_post.call_args.kwargs["json"]["tags"]

        ch.send("msg", "title", 1)
        assert "fire" not in mock_post.call_args.kwargs["json"]["tags"]

    def test_server_trailing_slash_stripped(self):
        ch = NtfyChannel(topic="t", server="https://ntfy.sh/")
        assert ch._server == "https://ntfy.sh"


class TestNotificationManager:
    """Tests for the NotificationManager class."""

    def _make_manager(self, storage, channel_success=True, channel_configured=True):
        """Create a manager with a mock channel."""
        channel = MagicMock()
        channel.name = "mock"
        channel.is_configured = channel_configured
        channel.send.return_value = channel_success
        return NotificationManager(storage, channels=[channel]), channel

    def _add_commits(self, storage, dates):
        """Add commit events for the given dates."""
        events = []
        for date in dates:
            events.append({
                "date": date,
                "repo": "user/test-repo",
                "commits": [{"sha": f"abc{date}", "message": "test commit"}],
                "commit_count": 1,
            })
        storage.save_commits(events)

    def test_skip_if_already_committed(self, tmp_storage):
        self._add_commits(tmp_storage, ["2025-01-15"])
        manager, _ = self._make_manager(tmp_storage)

        result = manager.check_and_notify(level=1, today="2025-01-15")

        assert result["action"] == "skipped"
        assert result["reason"] == "already_committed"
        assert result["streak_active"] is True

    def test_skip_if_level_already_sent(self, tmp_storage):
        self._add_commits(tmp_storage, ["2025-01-14"])
        manager, _ = self._make_manager(tmp_storage)

        # Log a previous level 2 notification
        tmp_storage.log_notification(
            date="2025-01-15", level=2, channel="mock",
            message="test", streak_value=1, streak_active=False,
        )

        # Level 1 should be skipped (2 already sent)
        result = manager.check_and_notify(level=1, today="2025-01-15")
        assert result["action"] == "skipped"
        assert result["reason"] == "already_sent"

        # Level 2 should also be skipped
        result = manager.check_and_notify(level=2, today="2025-01-15")
        assert result["action"] == "skipped"
        assert result["reason"] == "already_sent"

    def test_send_higher_level_after_lower(self, tmp_storage):
        self._add_commits(tmp_storage, ["2025-01-14"])
        manager, channel = self._make_manager(tmp_storage)

        # Log a previous level 1 notification
        tmp_storage.log_notification(
            date="2025-01-15", level=1, channel="mock",
            message="test", streak_value=1, streak_active=False,
        )

        # Level 2 should still send
        result = manager.check_and_notify(level=2, today="2025-01-15")
        assert result["action"] == "sent"
        assert result["level"] == 2
        channel.send.assert_called_once()

    def test_send_notification_logs_to_db(self, tmp_storage):
        self._add_commits(tmp_storage, ["2025-01-14"])
        manager, _ = self._make_manager(tmp_storage)

        result = manager.check_and_notify(level=1, today="2025-01-15")

        assert result["action"] == "sent"

        # Check it was logged
        notifications = tmp_storage.get_notifications_for_date("2025-01-15")
        assert len(notifications) == 1
        assert notifications[0]["level"] == 1
        assert notifications[0]["channel"] == "mock"

    def test_dry_run_does_not_send(self, tmp_storage):
        self._add_commits(tmp_storage, ["2025-01-14"])
        manager, channel = self._make_manager(tmp_storage)

        result = manager.check_and_notify(level=1, today="2025-01-15", dry_run=True)

        assert result["action"] == "dry_run"
        assert result["message"]  # non-empty
        channel.send.assert_not_called()

        # Should not be logged
        notifications = tmp_storage.get_notifications_for_date("2025-01-15")
        assert len(notifications) == 0

    def test_no_channels_configured(self, tmp_storage):
        self._add_commits(tmp_storage, ["2025-01-14"])
        manager, _ = self._make_manager(tmp_storage, channel_configured=False)

        result = manager.check_and_notify(level=1, today="2025-01-15")

        assert result["action"] == "skipped"
        assert result["reason"] == "no_channels_configured"

    def test_send_with_no_commits(self, tmp_storage):
        """No commits at all -- should send (zero streak message)."""
        manager, channel = self._make_manager(tmp_storage)

        result = manager.check_and_notify(level=1, today="2025-01-15")

        assert result["action"] == "sent"
        assert result["streak"] == 0

    def test_send_test(self, tmp_storage):
        manager, channel = self._make_manager(tmp_storage)

        result = manager.send_test()

        assert len(result["results"]) == 1
        assert result["results"][0]["success"] is True
        channel.send.assert_called_once()

    def test_send_test_not_configured(self, tmp_storage):
        manager, _ = self._make_manager(tmp_storage, channel_configured=False)

        result = manager.send_test()

        assert result["results"][0]["reason"] == "not_configured"

    def test_get_status(self, tmp_storage):
        manager, _ = self._make_manager(tmp_storage)

        status = manager.get_status()

        assert status["any_configured"] is True
        assert len(status["channels"]) == 1
        assert status["channels"][0]["name"] == "mock"

    def test_get_status_none_configured(self, tmp_storage):
        manager, _ = self._make_manager(tmp_storage, channel_configured=False)

        status = manager.get_status()

        assert status["any_configured"] is False

    def test_get_today_notifications(self, tmp_storage):
        tmp_storage.log_notification(
            date="2025-01-15", level=1, channel="mock",
            message="test", streak_value=5, streak_active=False,
        )

        manager, _ = self._make_manager(tmp_storage)
        notifications = manager.get_today_notifications(today="2025-01-15")

        assert len(notifications) == 1
        assert notifications[0]["level"] == 1

    def test_failed_send_not_logged(self, tmp_storage):
        """If channel.send returns False, don't log it."""
        self._add_commits(tmp_storage, ["2025-01-14"])
        manager, _ = self._make_manager(tmp_storage, channel_success=False)

        result = manager.check_and_notify(level=1, today="2025-01-15")

        assert result["action"] == "sent"
        assert result["channels"][0]["success"] is False

        # Should NOT be logged since it failed
        notifications = tmp_storage.get_notifications_for_date("2025-01-15")
        assert len(notifications) == 0


class TestStorageNotificationMethods:
    """Tests for notification-related storage methods."""

    def test_log_and_retrieve(self, tmp_storage):
        entry_id = tmp_storage.log_notification(
            date="2025-01-15", level=2, channel="ntfy",
            message="Test message", streak_value=5, streak_active=False,
        )

        assert entry_id is not None
        assert entry_id > 0

        entries = tmp_storage.get_notifications_for_date("2025-01-15")
        assert len(entries) == 1
        assert entries[0]["level"] == 2
        assert entries[0]["channel"] == "ntfy"
        assert entries[0]["message"] == "Test message"
        assert entries[0]["streak_value"] == 5
        assert entries[0]["streak_active"] == 0  # stored as int

    def test_get_max_level_no_entries(self, tmp_storage):
        result = tmp_storage.get_max_level_sent_today("2025-01-15")
        assert result is None

    def test_get_max_level_with_entries(self, tmp_storage):
        tmp_storage.log_notification(
            date="2025-01-15", level=1, channel="ntfy",
            message="msg1", streak_value=5, streak_active=False,
        )
        tmp_storage.log_notification(
            date="2025-01-15", level=3, channel="ntfy",
            message="msg3", streak_value=5, streak_active=False,
        )

        result = tmp_storage.get_max_level_sent_today("2025-01-15")
        assert result == 3

    def test_max_level_only_for_given_date(self, tmp_storage):
        tmp_storage.log_notification(
            date="2025-01-14", level=4, channel="ntfy",
            message="yesterday", streak_value=5, streak_active=False,
        )
        tmp_storage.log_notification(
            date="2025-01-15", level=1, channel="ntfy",
            message="today", streak_value=5, streak_active=False,
        )

        assert tmp_storage.get_max_level_sent_today("2025-01-15") == 1
        assert tmp_storage.get_max_level_sent_today("2025-01-14") == 4

    def test_notification_history(self, tmp_storage):
        for i in range(5):
            tmp_storage.log_notification(
                date=f"2025-01-{10 + i:02d}", level=i % 4 + 1,
                channel="ntfy", message=f"msg{i}",
                streak_value=i, streak_active=False,
            )

        history = tmp_storage.get_notification_history(limit=3)
        assert len(history) == 3
        # Most recent first
        assert history[0]["date"] == "2025-01-14"

    def test_notification_history_default_limit(self, tmp_storage):
        tmp_storage.log_notification(
            date="2025-01-15", level=1, channel="ntfy",
            message="msg", streak_value=0, streak_active=False,
        )

        history = tmp_storage.get_notification_history()
        assert len(history) == 1

    def test_empty_date_returns_empty(self, tmp_storage):
        entries = tmp_storage.get_notifications_for_date("2099-12-31")
        assert entries == []
