"""
Tests for commit event parsing.
"""

import os
import time

import pytest
from src.commit_parser import parse_commit_events


def test_parse_push_event():
    """Test parsing a single PushEvent."""
    events = [
        {
            "type": "PushEvent",
            "created_at": "2026-01-19T12:00:00Z",
            "repo": {"name": "user/test-repo"},
            "payload": {
                "size": 2,
                "commits": [
                    {"sha": "abc1234567890", "message": "feat: add feature"},
                    {"sha": "def0987654321", "message": "fix: bug fix"},
                ],
            },
        }
    ]

    result = parse_commit_events(events)

    assert len(result) == 1
    assert result[0]["date"] == "2026-01-19"
    assert result[0]["repo"] == "user/test-repo"
    assert result[0]["commit_count"] == 2
    assert len(result[0]["commits"]) == 2
    assert result[0]["commits"][0]["sha"] == "abc1234"
    assert result[0]["commits"][0]["message"] == "feat: add feature"


def test_filter_non_push_events():
    """Test that non-PushEvent types are filtered out."""
    events = [
        {
            "type": "IssueCommentEvent",
            "created_at": "2026-01-19T12:00:00Z",
            "repo": {"name": "user/test-repo"},
        },
        {
            "type": "PushEvent",
            "created_at": "2026-01-19T13:00:00Z",
            "repo": {"name": "user/another-repo"},
            "payload": {
                "size": 1,
                "commits": [{"sha": "xyz1234567890", "message": "test: add tests"}],
            },
        },
        {
            "type": "WatchEvent",
            "created_at": "2026-01-19T14:00:00Z",
            "repo": {"name": "user/watched-repo"},
        },
    ]

    result = parse_commit_events(events)

    assert len(result) == 1
    assert result[0]["repo"] == "user/another-repo"
    assert result[0]["commits"][0]["message"] == "test: add tests"


def test_parse_empty_events_list():
    """Test parsing an empty events list."""
    events = []
    result = parse_commit_events(events)
    assert result == []


def test_parse_no_push_events():
    """Test when there are no PushEvents."""
    events = [
        {"type": "IssueCommentEvent", "created_at": "2026-01-19T12:00:00Z"},
        {"type": "WatchEvent", "created_at": "2026-01-19T13:00:00Z"},
    ]

    result = parse_commit_events(events)
    assert result == []


def test_parse_event_with_empty_commits():
    """Test parsing a PushEvent with empty commits array."""
    events = [
        {
            "type": "PushEvent",
            "created_at": "2026-01-19T12:00:00Z",
            "repo": {"name": "user/test-repo"},
            "payload": {"size": 0, "commits": []},
        }
    ]

    result = parse_commit_events(events)

    assert len(result) == 1
    assert result[0]["commit_count"] == 0
    assert result[0]["commits"] == []


def test_parse_commit_message_first_line_only():
    """Test that only the first line of commit messages is extracted."""
    events = [
        {
            "type": "PushEvent",
            "created_at": "2026-01-19T12:00:00Z",
            "repo": {"name": "user/test-repo"},
            "payload": {
                "size": 1,
                "commits": [
                    {
                        "sha": "abc1234567890",
                        "message": "feat: add feature\n\nThis is a detailed description\nof the feature.",
                    }
                ],
            },
        }
    ]

    result = parse_commit_events(events)

    assert result[0]["commits"][0]["message"] == "feat: add feature"


def test_parse_event_with_missing_fields():
    """Test parsing events with missing optional fields."""
    events = [
        {
            "type": "PushEvent",
            "created_at": "",
            "repo": {},
            "payload": {"commits": [{"sha": "", "message": ""}]},
        }
    ]

    result = parse_commit_events(events)

    assert len(result) == 1
    assert result[0]["date"] == "unknown"
    assert result[0]["repo"] == "unknown"
    assert result[0]["commits"][0]["sha"] == ""
    assert result[0]["commits"][0]["message"] == ""


def test_parse_multiple_push_events():
    """Test parsing multiple PushEvents."""
    events = [
        {
            "type": "PushEvent",
            "created_at": "2026-01-19T12:00:00Z",
            "repo": {"name": "user/repo1"},
            "payload": {
                "size": 1,
                "commits": [{"sha": "abc1234567890", "message": "commit 1"}],
            },
        },
        {
            "type": "PushEvent",
            "created_at": "2026-01-19T13:00:00Z",
            "repo": {"name": "user/repo2"},
            "payload": {
                "size": 2,
                "commits": [
                    {"sha": "def0987654321", "message": "commit 2"},
                    {"sha": "ghi1357924680", "message": "commit 3"},
                ],
            },
        },
    ]

    result = parse_commit_events(events)

    assert len(result) == 2
    assert result[0]["repo"] == "user/repo1"
    assert result[1]["repo"] == "user/repo2"
    assert result[1]["commit_count"] == 2


def test_parse_event_sha_shortened():
    """Test that commit SHAs are shortened to 7 characters."""
    events = [
        {
            "type": "PushEvent",
            "created_at": "2026-01-19T12:00:00Z",
            "repo": {"name": "user/test-repo"},
            "payload": {
                "size": 1,
                "commits": [
                    {"sha": "abcdefghijklmnopqrstuvwxyz123456", "message": "test"}
                ],
            },
        }
    ]

    result = parse_commit_events(events)

    assert result[0]["commits"][0]["sha"] == "abcdefg"


@pytest.fixture
def set_timezone():
    """Fixture to temporarily set timezone for tests."""
    original_tz = os.environ.get("TZ")

    def _set_tz(tz_name):
        os.environ["TZ"] = tz_name
        time.tzset()

    yield _set_tz

    # Restore original timezone
    if original_tz is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = original_tz
    time.tzset()


class TestTimezoneConversion:
    """Tests for UTC to local timezone conversion."""

    def test_utc_timestamp_converted_to_local_date_est(self, set_timezone):
        """Test that UTC timestamps are converted to EST timezone before extracting date."""
        set_timezone("America/New_York")

        # A commit at 3 AM UTC on Jan 25 is actually late evening on Jan 24 in EST (UTC-5)
        events = [
            {
                "type": "PushEvent",
                "created_at": "2026-01-25T03:00:00Z",
                "repo": {"name": "user/test-repo"},
                "payload": {
                    "size": 1,
                    "commits": [{"sha": "abc1234567890", "message": "late commit"}],
                },
            }
        ]

        result = parse_commit_events(events)

        # 3 AM UTC = 10 PM EST previous day (Jan 24)
        assert result[0]["date"] == "2026-01-24"

    def test_utc_midday_same_date_in_est(self, set_timezone):
        """Test that midday UTC remains same date in EST."""
        set_timezone("America/New_York")

        events = [
            {
                "type": "PushEvent",
                "created_at": "2026-01-25T12:00:00Z",
                "repo": {"name": "user/test-repo"},
                "payload": {
                    "size": 1,
                    "commits": [{"sha": "abc1234567890", "message": "midday commit"}],
                },
            }
        ]

        result = parse_commit_events(events)

        # 12 PM UTC = 7 AM EST same day
        assert result[0]["date"] == "2026-01-25"

    def test_utc_late_night_next_day_in_positive_offset(self, set_timezone):
        """Test that late night UTC becomes next day in JST (UTC+9)."""
        set_timezone("Asia/Tokyo")

        events = [
            {
                "type": "PushEvent",
                "created_at": "2026-01-25T23:00:00Z",
                "repo": {"name": "user/test-repo"},
                "payload": {
                    "size": 1,
                    "commits": [{"sha": "abc1234567890", "message": "late commit"}],
                },
            }
        ]

        result = parse_commit_events(events)

        # 11 PM UTC = 8 AM JST next day (Jan 26)
        assert result[0]["date"] == "2026-01-26"

    def test_empty_created_at_returns_unknown(self):
        """Test that empty created_at still returns 'unknown'."""
        events = [
            {
                "type": "PushEvent",
                "created_at": "",
                "repo": {"name": "user/test-repo"},
                "payload": {"size": 1, "commits": []},
            }
        ]

        result = parse_commit_events(events)
        assert result[0]["date"] == "unknown"

    def test_utc_midnight_boundary(self, set_timezone):
        """Test commits right at UTC midnight are handled correctly."""
        set_timezone("America/New_York")

        events = [
            {
                "type": "PushEvent",
                "created_at": "2026-01-26T00:00:00Z",
                "repo": {"name": "user/test-repo"},
                "payload": {
                    "size": 1,
                    "commits": [{"sha": "abc1234567890", "message": "midnight commit"}],
                },
            }
        ]

        result = parse_commit_events(events)

        # Midnight UTC = 7 PM EST previous day (Jan 25)
        assert result[0]["date"] == "2026-01-25"
