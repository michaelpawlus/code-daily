"""
Tests for stats calculation.
"""

import pytest
from src.stats_calculator import calculate_stats


def test_empty_input_returns_zeros():
    """Test that empty input returns all zeros."""
    result = calculate_stats([], today="2026-01-20")

    assert result["commits_today"] == 0
    assert result["commits_this_week"] == 0
    assert result["commits_this_month"] == 0
    assert result["commits_last_7_days"] == 0
    assert result["commits_last_30_days"] == 0
    assert result["total_commits"] == 0


def test_commits_today_counted_correctly():
    """Test that commits today are counted correctly."""
    commit_events = [
        {"date": "2026-01-20", "repo": "user/repo1", "commits": [], "commit_count": 3},
        {"date": "2026-01-20", "repo": "user/repo2", "commits": [], "commit_count": 2},
        {"date": "2026-01-19", "repo": "user/repo1", "commits": [], "commit_count": 5},
    ]

    result = calculate_stats(commit_events, today="2026-01-20")

    assert result["commits_today"] == 5  # 3 + 2
    assert result["total_commits"] == 10


def test_week_boundaries_monday_to_sunday():
    """Test that week boundaries are Mon-Sun (2026-01-20 is a Tuesday)."""
    # 2026-01-20 is Tuesday, so week is Mon 2026-01-19 to Sun 2026-01-25
    commit_events = [
        {"date": "2026-01-18", "repo": "user/repo1", "commits": [], "commit_count": 1},  # Sunday before
        {"date": "2026-01-19", "repo": "user/repo1", "commits": [], "commit_count": 2},  # Monday (start of week)
        {"date": "2026-01-20", "repo": "user/repo1", "commits": [], "commit_count": 3},  # Tuesday (today)
        {"date": "2026-01-25", "repo": "user/repo1", "commits": [], "commit_count": 4},  # Sunday (end of week)
        {"date": "2026-01-26", "repo": "user/repo1", "commits": [], "commit_count": 5},  # Monday next week
    ]

    result = calculate_stats(commit_events, today="2026-01-20")

    # Only 2026-01-19, 2026-01-20, 2026-01-25 are in the current week
    assert result["commits_this_week"] == 9  # 2 + 3 + 4


def test_month_boundaries():
    """Test that month boundaries are handled correctly."""
    commit_events = [
        {"date": "2026-01-01", "repo": "user/repo1", "commits": [], "commit_count": 1},  # Start of month
        {"date": "2026-01-15", "repo": "user/repo1", "commits": [], "commit_count": 2},  # Mid month
        {"date": "2026-01-20", "repo": "user/repo1", "commits": [], "commit_count": 3},  # Today
        {"date": "2025-12-31", "repo": "user/repo1", "commits": [], "commit_count": 10},  # Last month
    ]

    result = calculate_stats(commit_events, today="2026-01-20")

    assert result["commits_this_month"] == 6  # 1 + 2 + 3


def test_rolling_7_days():
    """Test rolling 7-day count includes today and 6 days prior."""
    commit_events = [
        {"date": "2026-01-20", "repo": "user/repo1", "commits": [], "commit_count": 1},  # Day 0 (today)
        {"date": "2026-01-19", "repo": "user/repo1", "commits": [], "commit_count": 1},  # Day 1
        {"date": "2026-01-18", "repo": "user/repo1", "commits": [], "commit_count": 1},  # Day 2
        {"date": "2026-01-17", "repo": "user/repo1", "commits": [], "commit_count": 1},  # Day 3
        {"date": "2026-01-16", "repo": "user/repo1", "commits": [], "commit_count": 1},  # Day 4
        {"date": "2026-01-15", "repo": "user/repo1", "commits": [], "commit_count": 1},  # Day 5
        {"date": "2026-01-14", "repo": "user/repo1", "commits": [], "commit_count": 1},  # Day 6 (7 days ago)
        {"date": "2026-01-13", "repo": "user/repo1", "commits": [], "commit_count": 5},  # Day 7 (excluded)
    ]

    result = calculate_stats(commit_events, today="2026-01-20")

    assert result["commits_last_7_days"] == 7  # 7 commits in last 7 days


def test_rolling_30_days():
    """Test rolling 30-day count includes today and 29 days prior."""
    commit_events = [
        {"date": "2026-01-20", "repo": "user/repo1", "commits": [], "commit_count": 1},  # Day 0
        {"date": "2026-01-10", "repo": "user/repo1", "commits": [], "commit_count": 2},  # Day 10
        {"date": "2025-12-22", "repo": "user/repo1", "commits": [], "commit_count": 3},  # Day 29 (30 days ago)
        {"date": "2025-12-21", "repo": "user/repo1", "commits": [], "commit_count": 10},  # Day 30 (excluded)
    ]

    result = calculate_stats(commit_events, today="2026-01-20")

    assert result["commits_last_30_days"] == 6  # 1 + 2 + 3


def test_unknown_dates_ignored():
    """Test that unknown dates are ignored."""
    commit_events = [
        {"date": "2026-01-20", "repo": "user/repo1", "commits": [], "commit_count": 5},
        {"date": "unknown", "repo": "user/repo2", "commits": [], "commit_count": 100},
        {"date": "", "repo": "user/repo3", "commits": [], "commit_count": 50},
    ]

    result = calculate_stats(commit_events, today="2026-01-20")

    assert result["commits_today"] == 5
    assert result["total_commits"] == 5  # Only valid date counted


def test_missing_date_field_ignored():
    """Test that events with missing date field are ignored."""
    commit_events = [
        {"date": "2026-01-20", "repo": "user/repo1", "commits": [], "commit_count": 5},
        {"repo": "user/repo2", "commits": [], "commit_count": 100},  # Missing date
    ]

    result = calculate_stats(commit_events, today="2026-01-20")

    assert result["total_commits"] == 5


def test_total_commits_from_all_data():
    """Test that total commits includes all valid data."""
    commit_events = [
        {"date": "2026-01-20", "repo": "user/repo1", "commits": [], "commit_count": 1},
        {"date": "2026-01-01", "repo": "user/repo1", "commits": [], "commit_count": 2},
        {"date": "2025-12-01", "repo": "user/repo1", "commits": [], "commit_count": 3},
        {"date": "2025-06-01", "repo": "user/repo1", "commits": [], "commit_count": 4},
    ]

    result = calculate_stats(commit_events, today="2026-01-20")

    assert result["total_commits"] == 10


def test_week_at_year_boundary():
    """Test week calculation at year boundary (2025-12-29 is Monday)."""
    # 2026-01-01 is Thursday, week starts 2025-12-29 (Monday)
    commit_events = [
        {"date": "2025-12-29", "repo": "user/repo1", "commits": [], "commit_count": 1},  # Monday
        {"date": "2025-12-30", "repo": "user/repo1", "commits": [], "commit_count": 1},  # Tuesday
        {"date": "2025-12-31", "repo": "user/repo1", "commits": [], "commit_count": 1},  # Wednesday
        {"date": "2026-01-01", "repo": "user/repo1", "commits": [], "commit_count": 1},  # Thursday (today)
        {"date": "2026-01-04", "repo": "user/repo1", "commits": [], "commit_count": 1},  # Sunday (end)
    ]

    result = calculate_stats(commit_events, today="2026-01-01")

    assert result["commits_this_week"] == 5


def test_invalid_date_format_ignored():
    """Test that invalid date formats are ignored gracefully."""
    commit_events = [
        {"date": "2026-01-20", "repo": "user/repo1", "commits": [], "commit_count": 5},
        {"date": "invalid-date", "repo": "user/repo2", "commits": [], "commit_count": 100},
        {"date": "01-20-2026", "repo": "user/repo3", "commits": [], "commit_count": 50},
    ]

    result = calculate_stats(commit_events, today="2026-01-20")

    assert result["commits_today"] == 5
    assert result["total_commits"] == 5
