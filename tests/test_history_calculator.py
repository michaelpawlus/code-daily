"""
Tests for the history calculator module.
"""

from datetime import date

import pytest

from src.history_calculator import calculate_history, _calculate_level


class TestCalculateLevel:
    """Tests for the _calculate_level function."""

    def test_level_0_for_no_commits(self):
        """Level 0 for no commits."""
        assert _calculate_level(0) == 0

    def test_level_1_for_one_commit(self):
        """Level 1 for exactly 1 commit."""
        assert _calculate_level(1) == 1

    def test_level_2_for_two_to_three_commits(self):
        """Level 2 for 2-3 commits."""
        assert _calculate_level(2) == 2
        assert _calculate_level(3) == 2

    def test_level_3_for_four_to_five_commits(self):
        """Level 3 for 4-5 commits."""
        assert _calculate_level(4) == 3
        assert _calculate_level(5) == 3

    def test_level_4_for_six_or_more_commits(self):
        """Level 4 for 6+ commits."""
        assert _calculate_level(6) == 4
        assert _calculate_level(10) == 4
        assert _calculate_level(100) == 4


class TestCalculateHistory:
    """Tests for the calculate_history function."""

    def test_empty_input_returns_days_with_zero_counts(self):
        """Empty commit_events should return days with count=0 and level=0."""
        today = date(2026, 1, 26)
        result = calculate_history([], days=7, today=today)

        assert len(result["days"]) == 7
        for day in result["days"]:
            assert day["count"] == 0
            assert day["level"] == 0

    def test_correct_number_of_days_returned(self):
        """Should return the requested number of days."""
        today = date(2026, 1, 26)

        result_7 = calculate_history([], days=7, today=today)
        assert len(result_7["days"]) == 7

        result_84 = calculate_history([], days=84, today=today)
        assert len(result_84["days"]) == 84

        result_30 = calculate_history([], days=30, today=today)
        assert len(result_30["days"]) == 30

    def test_accurate_per_day_commit_counting(self):
        """Should correctly count commits per day."""
        today = date(2026, 1, 26)
        commit_events = [
            {"date": "2026-01-26", "commit_count": 3},
            {"date": "2026-01-25", "commit_count": 1},
            {"date": "2026-01-24", "commit_count": 5},
        ]

        result = calculate_history(commit_events, days=7, today=today)

        # Find specific days
        day_map = {d["date"]: d for d in result["days"]}

        assert day_map["2026-01-26"]["count"] == 3
        assert day_map["2026-01-26"]["level"] == 2

        assert day_map["2026-01-25"]["count"] == 1
        assert day_map["2026-01-25"]["level"] == 1

        assert day_map["2026-01-24"]["count"] == 5
        assert day_map["2026-01-24"]["level"] == 3

    def test_multiple_events_same_day_are_summed(self):
        """Multiple commit events on the same day should be summed."""
        today = date(2026, 1, 26)
        commit_events = [
            {"date": "2026-01-26", "commit_count": 2},
            {"date": "2026-01-26", "commit_count": 3},
            {"date": "2026-01-26", "commit_count": 1},
        ]

        result = calculate_history(commit_events, days=7, today=today)
        day_map = {d["date"]: d for d in result["days"]}

        assert day_map["2026-01-26"]["count"] == 6
        assert day_map["2026-01-26"]["level"] == 4

    def test_proper_date_ordering(self):
        """Days should be ordered from oldest to newest for grid rendering."""
        today = date(2026, 1, 26)
        result = calculate_history([], days=7, today=today)

        dates = [d["date"] for d in result["days"]]

        # First day should be 6 days ago
        assert dates[0] == "2026-01-20"
        # Last day should be today
        assert dates[-1] == "2026-01-26"

        # Verify ordering
        for i in range(len(dates) - 1):
            assert dates[i] < dates[i + 1]

    def test_missing_days_have_zero_count(self):
        """Days not in commit_events should have count=0, level=0."""
        today = date(2026, 1, 26)
        # Only one commit event
        commit_events = [
            {"date": "2026-01-24", "commit_count": 2},
        ]

        result = calculate_history(commit_events, days=7, today=today)
        day_map = {d["date"]: d for d in result["days"]}

        # Day with commits
        assert day_map["2026-01-24"]["count"] == 2
        assert day_map["2026-01-24"]["level"] == 2

        # Days without commits
        assert day_map["2026-01-20"]["count"] == 0
        assert day_map["2026-01-20"]["level"] == 0
        assert day_map["2026-01-26"]["count"] == 0
        assert day_map["2026-01-26"]["level"] == 0

    def test_today_parameter_override(self):
        """Today parameter should control the end date."""
        custom_today = date(2026, 2, 15)
        result = calculate_history([], days=7, today=custom_today)

        dates = [d["date"] for d in result["days"]]

        assert dates[-1] == "2026-02-15"
        assert dates[0] == "2026-02-09"

    def test_period_metadata(self):
        """Should return correct period metadata."""
        today = date(2026, 1, 26)
        result = calculate_history([], days=84, today=today)

        assert result["period"]["end"] == "2026-01-26"
        assert result["period"]["start"] == "2025-11-04"
        assert result["period"]["total_days"] == 84

    def test_max_count_calculated_correctly(self):
        """Should return the maximum commit count across all days."""
        today = date(2026, 1, 26)
        commit_events = [
            {"date": "2026-01-26", "commit_count": 3},
            {"date": "2026-01-25", "commit_count": 8},
            {"date": "2026-01-24", "commit_count": 2},
        ]

        result = calculate_history(commit_events, days=7, today=today)

        assert result["max_count"] == 8

    def test_max_count_zero_for_empty_history(self):
        """max_count should be 0 when there are no commits."""
        today = date(2026, 1, 26)
        result = calculate_history([], days=7, today=today)

        assert result["max_count"] == 0

    def test_events_outside_range_ignored(self):
        """Commit events outside the date range should be ignored."""
        today = date(2026, 1, 26)
        commit_events = [
            {"date": "2026-01-26", "commit_count": 3},  # In range
            {"date": "2026-01-01", "commit_count": 10},  # Out of range (7 days)
        ]

        result = calculate_history(commit_events, days=7, today=today)
        day_map = {d["date"]: d for d in result["days"]}

        # Only 7 days should be present
        assert len(result["days"]) == 7
        assert "2026-01-01" not in day_map

        # max_count should only consider in-range days
        assert result["max_count"] == 3

    def test_handles_missing_date_key(self):
        """Should handle events missing the date key gracefully."""
        today = date(2026, 1, 26)
        commit_events = [
            {"date": "2026-01-26", "commit_count": 3},
            {"commit_count": 5},  # Missing date key
            {"date": "", "commit_count": 2},  # Empty date
        ]

        result = calculate_history(commit_events, days=7, today=today)
        day_map = {d["date"]: d for d in result["days"]}

        # Should only count the valid event
        assert day_map["2026-01-26"]["count"] == 3

    def test_default_days_is_84(self):
        """Default should be 84 days (12 weeks)."""
        today = date(2026, 1, 26)
        result = calculate_history([], today=today)

        assert len(result["days"]) == 84
        assert result["period"]["total_days"] == 84
