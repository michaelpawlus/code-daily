"""
Tests for CLI display functions.
"""

import io
import sys
from contextlib import redirect_stdout

from src.cli import (
    display_calendar,
    display_streak,
    format_commit_event,
    get_milestone_message,
)


class TestGetMilestoneMessage:
    """Tests for milestone messages."""

    def test_7_day_milestone(self):
        assert get_milestone_message(7) == "One week strong!"

    def test_14_day_milestone(self):
        assert get_milestone_message(14) == "Two weeks of consistency!"

    def test_30_day_milestone(self):
        assert get_milestone_message(30) == "One month champion!"

    def test_60_day_milestone(self):
        assert get_milestone_message(60) == "Two months unstoppable!"

    def test_100_day_milestone(self):
        assert get_milestone_message(100) == "100 days - legendary!"

    def test_no_milestone(self):
        assert get_milestone_message(5) is None
        assert get_milestone_message(8) is None
        assert get_milestone_message(99) is None


class TestDisplayStreak:
    """Tests for streak display."""

    def test_no_active_streak(self):
        streak_info = {
            "current_streak": 0,
            "streak_active": False,
            "last_commit_date": None,
        }
        output = io.StringIO()
        with redirect_stdout(output):
            display_streak(streak_info)
        result = output.getvalue()
        assert "No active streak" in result

    def test_single_day_streak(self):
        streak_info = {
            "current_streak": 1,
            "streak_active": True,
            "last_commit_date": "2026-01-20",
        }
        output = io.StringIO()
        with redirect_stdout(output):
            display_streak(streak_info)
        result = output.getvalue()
        assert "1 day" in result
        assert "2026-01-20" in result

    def test_multi_day_streak(self):
        streak_info = {
            "current_streak": 5,
            "streak_active": True,
            "last_commit_date": "2026-01-20",
        }
        output = io.StringIO()
        with redirect_stdout(output):
            display_streak(streak_info)
        result = output.getvalue()
        assert "5 days" in result

    def test_streak_with_milestone_7_days(self):
        streak_info = {
            "current_streak": 7,
            "streak_active": True,
            "last_commit_date": "2026-01-20",
        }
        output = io.StringIO()
        with redirect_stdout(output):
            display_streak(streak_info)
        result = output.getvalue()
        assert "7 days" in result
        assert "One week strong!" in result

    def test_streak_with_milestone_30_days(self):
        streak_info = {
            "current_streak": 30,
            "streak_active": True,
            "last_commit_date": "2026-01-20",
        }
        output = io.StringIO()
        with redirect_stdout(output):
            display_streak(streak_info)
        result = output.getvalue()
        assert "30 days" in result
        assert "One month champion!" in result

    def test_inactive_streak_prompts_to_commit(self):
        streak_info = {
            "current_streak": 5,
            "streak_active": False,
            "last_commit_date": "2026-01-19",
        }
        output = io.StringIO()
        with redirect_stdout(output):
            display_streak(streak_info)
        result = output.getvalue()
        assert "commit today to continue" in result

    def test_milestone_takes_priority_over_inactive_warning(self):
        streak_info = {
            "current_streak": 7,
            "streak_active": False,
            "last_commit_date": "2026-01-19",
        }
        output = io.StringIO()
        with redirect_stdout(output):
            display_streak(streak_info)
        result = output.getvalue()
        assert "One week strong!" in result
        assert "commit today to continue" not in result


class TestDisplayCalendar:
    """Tests for activity calendar display."""

    def test_empty_commit_dates(self):
        output = io.StringIO()
        with redirect_stdout(output):
            display_calendar([], days=7, today="2026-01-20")
        result = output.getvalue()
        assert "Recent Activity:" in result
        assert "Mon" in result
        assert "[*]" not in result

    def test_single_commit_date(self):
        output = io.StringIO()
        with redirect_stdout(output):
            display_calendar(["2026-01-20"], days=7, today="2026-01-20")
        result = output.getvalue()
        assert "[*]" in result
        assert "[ ]" in result

    def test_multiple_commit_dates(self):
        commit_dates = ["2026-01-20", "2026-01-19", "2026-01-17"]
        output = io.StringIO()
        with redirect_stdout(output):
            display_calendar(commit_dates, days=7, today="2026-01-20")
        result = output.getvalue()
        # Should have 3 commit markers and some empty days
        assert result.count("[*]") == 3

    def test_calendar_shows_day_headers(self):
        output = io.StringIO()
        with redirect_stdout(output):
            display_calendar([], days=14, today="2026-01-20")
        result = output.getvalue()
        assert "Mon" in result
        assert "Tue" in result
        assert "Wed" in result
        assert "Thu" in result
        assert "Fri" in result
        assert "Sat" in result
        assert "Sun" in result

    def test_14_day_calendar(self):
        output = io.StringIO()
        with redirect_stdout(output):
            display_calendar([], days=14, today="2026-01-20")
        result = output.getvalue()
        # Count total day slots (14 days worth)
        assert result.count("[ ]") == 14


class TestFormatCommitEvent:
    """Tests for commit event formatting."""

    def test_format_single_commit(self):
        event = {
            "date": "2026-01-20",
            "repo": "user/repo",
            "commit_count": 1,
            "commits": [{"message": "Fix bug"}],
        }
        result = format_commit_event(event)
        assert "2026-01-20" in result
        assert "1 commit" in result
        assert "user/repo" in result
        assert "Fix bug" in result

    def test_format_multiple_commits(self):
        event = {
            "date": "2026-01-20",
            "repo": "user/repo",
            "commit_count": 5,
            "commits": [{"message": "First commit"}, {"message": "Second commit"}],
        }
        result = format_commit_event(event)
        assert "5 commits" in result
        assert "First commit" in result  # Only shows first message

    def test_format_truncates_long_message(self):
        long_message = "A" * 100
        event = {
            "date": "2026-01-20",
            "repo": "user/repo",
            "commit_count": 1,
            "commits": [{"message": long_message}],
        }
        result = format_commit_event(event)
        assert "..." in result
        assert len(result) < len(long_message) + 50

    def test_format_no_commits(self):
        event = {
            "date": "2026-01-20",
            "repo": "user/repo",
            "commit_count": 0,
            "commits": [],
        }
        result = format_commit_event(event)
        assert "No commit message" in result

    def test_format_missing_commits_key(self):
        event = {
            "date": "2026-01-20",
            "repo": "user/repo",
            "commit_count": 1,
        }
        result = format_commit_event(event)
        assert "No commit message" in result
