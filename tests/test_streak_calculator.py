"""
Tests for streak calculation.
"""

import pytest
from src.streak_calculator import calculate_streak


def test_basic_streak_three_consecutive_days():
    """Test basic streak calculation with 3 consecutive days."""
    commit_events = [
        {"date": "2026-01-20", "repo": "user/repo1", "commits": [], "commit_count": 1},
        {"date": "2026-01-19", "repo": "user/repo2", "commits": [], "commit_count": 2},
        {"date": "2026-01-18", "repo": "user/repo1", "commits": [], "commit_count": 1},
    ]

    result = calculate_streak(commit_events, today="2026-01-20")

    assert result["current_streak"] == 3
    assert result["longest_streak"] == 3
    assert result["streak_active"] is True
    assert result["last_commit_date"] == "2026-01-20"


def test_streak_with_gap_breaks_streak():
    """Test that a gap in dates breaks the streak."""
    commit_events = [
        {"date": "2026-01-20", "repo": "user/repo1", "commits": [], "commit_count": 1},
        {"date": "2026-01-19", "repo": "user/repo2", "commits": [], "commit_count": 1},
        # Gap: 2026-01-18 missing
        {"date": "2026-01-17", "repo": "user/repo1", "commits": [], "commit_count": 1},
        {"date": "2026-01-16", "repo": "user/repo1", "commits": [], "commit_count": 1},
    ]

    result = calculate_streak(commit_events, today="2026-01-20")

    assert result["current_streak"] == 2
    assert result["longest_streak"] == 2  # Both segments are 2 days
    assert result["streak_active"] is True


def test_no_commits_returns_zero_streak():
    """Test with no commits returns zero streak."""
    commit_events = []

    result = calculate_streak(commit_events, today="2026-01-20")

    assert result["current_streak"] == 0
    assert result["longest_streak"] == 0
    assert result["streak_active"] is False
    assert result["last_commit_date"] is None
    assert result["commit_dates"] == []


def test_single_day_commit():
    """Test a single day commit results in streak of 1."""
    commit_events = [
        {"date": "2026-01-20", "repo": "user/repo1", "commits": [], "commit_count": 1},
    ]

    result = calculate_streak(commit_events, today="2026-01-20")

    assert result["current_streak"] == 1
    assert result["longest_streak"] == 1
    assert result["streak_active"] is True


def test_streak_from_yesterday_needs_commit_today():
    """Test streak starting from yesterday (grace period)."""
    commit_events = [
        {"date": "2026-01-19", "repo": "user/repo1", "commits": [], "commit_count": 1},
        {"date": "2026-01-18", "repo": "user/repo2", "commits": [], "commit_count": 1},
        {"date": "2026-01-17", "repo": "user/repo1", "commits": [], "commit_count": 1},
    ]

    result = calculate_streak(commit_events, today="2026-01-20")

    assert result["current_streak"] == 3
    assert result["longest_streak"] == 3
    assert result["streak_active"] is False  # No commit today
    assert result["last_commit_date"] == "2026-01-19"


def test_multiple_commits_same_day_counts_as_one():
    """Test that multiple commits on the same day count as 1 day."""
    commit_events = [
        {"date": "2026-01-20", "repo": "user/repo1", "commits": [], "commit_count": 1},
        {"date": "2026-01-20", "repo": "user/repo2", "commits": [], "commit_count": 3},
        {"date": "2026-01-20", "repo": "user/repo3", "commits": [], "commit_count": 1},
        {"date": "2026-01-19", "repo": "user/repo1", "commits": [], "commit_count": 2},
    ]

    result = calculate_streak(commit_events, today="2026-01-20")

    assert result["current_streak"] == 2
    assert result["longest_streak"] == 2
    # Should only have 2 unique dates
    assert len(result["commit_dates"]) == 2


def test_streak_broken_if_last_commit_more_than_yesterday():
    """Test that streak is 0 if last commit was before yesterday."""
    commit_events = [
        {"date": "2026-01-17", "repo": "user/repo1", "commits": [], "commit_count": 1},
        {"date": "2026-01-16", "repo": "user/repo2", "commits": [], "commit_count": 1},
        {"date": "2026-01-15", "repo": "user/repo1", "commits": [], "commit_count": 1},
    ]

    result = calculate_streak(commit_events, today="2026-01-20")

    assert result["current_streak"] == 0
    assert result["longest_streak"] == 3
    assert result["streak_active"] is False


def test_longest_streak_longer_than_current():
    """Test when longest streak is longer than current streak."""
    commit_events = [
        # Current streak: 2 days
        {"date": "2026-01-20", "repo": "user/repo1", "commits": [], "commit_count": 1},
        {"date": "2026-01-19", "repo": "user/repo1", "commits": [], "commit_count": 1},
        # Gap
        {"date": "2026-01-15", "repo": "user/repo1", "commits": [], "commit_count": 1},
        {"date": "2026-01-14", "repo": "user/repo1", "commits": [], "commit_count": 1},
        {"date": "2026-01-13", "repo": "user/repo1", "commits": [], "commit_count": 1},
        {"date": "2026-01-12", "repo": "user/repo1", "commits": [], "commit_count": 1},
        {"date": "2026-01-11", "repo": "user/repo1", "commits": [], "commit_count": 1},
    ]

    result = calculate_streak(commit_events, today="2026-01-20")

    assert result["current_streak"] == 2
    assert result["longest_streak"] == 5


def test_commit_dates_sorted_descending():
    """Test that commit_dates are sorted in descending order."""
    commit_events = [
        {"date": "2026-01-18", "repo": "user/repo1", "commits": [], "commit_count": 1},
        {"date": "2026-01-20", "repo": "user/repo2", "commits": [], "commit_count": 1},
        {"date": "2026-01-19", "repo": "user/repo1", "commits": [], "commit_count": 1},
    ]

    result = calculate_streak(commit_events, today="2026-01-20")

    assert result["commit_dates"] == ["2026-01-20", "2026-01-19", "2026-01-18"]


def test_handles_unknown_dates():
    """Test that unknown dates are filtered out."""
    commit_events = [
        {"date": "2026-01-20", "repo": "user/repo1", "commits": [], "commit_count": 1},
        {"date": "unknown", "repo": "user/repo2", "commits": [], "commit_count": 1},
        {"date": "2026-01-19", "repo": "user/repo1", "commits": [], "commit_count": 1},
    ]

    result = calculate_streak(commit_events, today="2026-01-20")

    assert "unknown" not in result["commit_dates"]
    assert result["current_streak"] == 2


def test_all_unknown_dates():
    """Test when all dates are unknown."""
    commit_events = [
        {"date": "unknown", "repo": "user/repo1", "commits": [], "commit_count": 1},
        {"date": "unknown", "repo": "user/repo2", "commits": [], "commit_count": 1},
    ]

    result = calculate_streak(commit_events, today="2026-01-20")

    assert result["current_streak"] == 0
    assert result["longest_streak"] == 0
    assert result["last_commit_date"] is None


def test_events_with_missing_date_field():
    """Test events with missing date field are handled."""
    commit_events = [
        {"date": "2026-01-20", "repo": "user/repo1", "commits": [], "commit_count": 1},
        {"repo": "user/repo2", "commits": [], "commit_count": 1},  # Missing date
        {"date": "2026-01-19", "repo": "user/repo1", "commits": [], "commit_count": 1},
    ]

    result = calculate_streak(commit_events, today="2026-01-20")

    assert result["current_streak"] == 2
    assert len(result["commit_dates"]) == 2
