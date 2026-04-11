"""
Tests for streak insights analysis.
"""

import pytest
from src.streak_insights import (
    compute_time_distribution,
    compute_day_distribution,
    compute_repo_breakdown,
    compute_streak_patterns,
    compute_streak_risk,
    compute_insights,
)


# ---- compute_time_distribution ----


def test_time_distribution_buckets():
    """Events at known hours land in correct buckets."""
    events = [
        {"type": "PushEvent", "created_at": "2026-01-10T08:00:00+00:00"},  # morning UTC
        {"type": "PushEvent", "created_at": "2026-01-10T09:30:00+00:00"},  # morning UTC
        {"type": "PushEvent", "created_at": "2026-01-10T14:00:00+00:00"},  # afternoon UTC
        {"type": "PushEvent", "created_at": "2026-01-10T19:00:00+00:00"},  # evening UTC
        {"type": "PushEvent", "created_at": "2026-01-10T23:30:00+00:00"},  # night UTC
        {"type": "PushEvent", "created_at": "2026-01-10T03:00:00+00:00"},  # night UTC
    ]
    result = compute_time_distribution(events)

    # Exact bucket depends on local timezone, but totals should be 6
    total = result["morning"] + result["afternoon"] + result["evening"] + result["night"]
    assert total == 6
    assert result["peak"] in ("morning", "afternoon", "evening", "night")


def test_time_distribution_filters_non_push():
    """Non-PushEvent events are ignored."""
    events = [
        {"type": "WatchEvent", "created_at": "2026-01-10T10:00:00+00:00"},
        {"type": "PushEvent", "created_at": "2026-01-10T10:00:00+00:00"},
    ]
    result = compute_time_distribution(events)
    total = result["morning"] + result["afternoon"] + result["evening"] + result["night"]
    assert total == 1


def test_time_distribution_empty():
    """Empty events list returns zeroes."""
    result = compute_time_distribution([])
    assert result["morning"] == 0
    assert result["afternoon"] == 0
    assert result["evening"] == 0
    assert result["night"] == 0
    assert result["peak"] == "morning"


# ---- compute_day_distribution ----


def test_day_distribution():
    """Commit dates produce correct weekday counts."""
    # 2026-01-05 = Monday, 2026-01-06 = Tuesday, ..., 2026-01-11 = Sunday
    dates = [
        "2026-01-05",  # Mon
        "2026-01-06",  # Tue
        "2026-01-07",  # Wed
        "2026-01-05",  # Mon again (duplicate date, still counted)
        "2026-01-12",  # Mon
        "2026-01-10",  # Sat
    ]
    result = compute_day_distribution(dates)

    assert result["monday"] == 3
    assert result["tuesday"] == 1
    assert result["wednesday"] == 1
    assert result["saturday"] == 1
    assert result["thursday"] == 0
    assert result["friday"] == 0
    assert result["sunday"] == 0
    assert result["strongest"] == "monday"
    assert result["weakest"] in ("thursday", "friday", "sunday")  # all are 0
    assert result["weekday_pct"] == 83.3  # 5/6


def test_day_distribution_empty():
    """Empty dates list returns zeroes."""
    result = compute_day_distribution([])
    assert result["monday"] == 0
    assert result["weekday_pct"] == 0.0


# ---- compute_repo_breakdown ----


def test_repo_breakdown_active_dormant(monkeypatch):
    """Repos classified correctly by recency."""
    from datetime import date
    from unittest.mock import patch

    # Fix "today" so assertions are stable
    fixed_today = date(2026, 4, 10)
    monkeypatch.setattr(
        "src.streak_insights.datetime",
        type("MockDT", (), {
            "now": staticmethod(lambda: type("D", (), {"date": lambda self: fixed_today})()),
            "strptime": staticmethod(lambda s, f: __import__("datetime").datetime.strptime(s, f)),
        })(),
    )
    # Instead of monkeypatching datetime, let's just use real data relative to "now"
    # and accept the result categories
    from datetime import datetime, timedelta
    today = datetime.now().date()

    events = [
        # Active: committed within last 7 days
        {"date": (today - timedelta(days=1)).strftime("%Y-%m-%d"),
         "repo": "user/active-repo", "commits": [], "commit_count": 5},
        {"date": (today - timedelta(days=3)).strftime("%Y-%m-%d"),
         "repo": "user/active-repo", "commits": [], "commit_count": 3},
        # Dormant: last commit > 14 days ago
        {"date": (today - timedelta(days=20)).strftime("%Y-%m-%d"),
         "repo": "user/dormant-repo", "commits": [], "commit_count": 2},
        # Recent: between 7 and 14 days ago
        {"date": (today - timedelta(days=10)).strftime("%Y-%m-%d"),
         "repo": "user/recent-repo", "commits": [], "commit_count": 1},
    ]
    monkeypatch.undo()  # undo the failed monkeypatch

    result = compute_repo_breakdown(events, days=90)

    repos_by_name = {r["repo"]: r for r in result["top"]}
    assert repos_by_name["user/active-repo"]["status"] == "active"
    assert repos_by_name["user/active-repo"]["commits"] == 8
    assert repos_by_name["user/dormant-repo"]["status"] == "dormant"
    assert repos_by_name["user/recent-repo"]["status"] == "recent"
    assert result["active_count"] == 1
    assert result["dormant_count"] == 1


def test_repo_breakdown_outside_window():
    """Events outside the analysis window are excluded."""
    from datetime import datetime, timedelta
    today = datetime.now().date()
    old_date = (today - timedelta(days=100)).strftime("%Y-%m-%d")

    events = [
        {"date": old_date, "repo": "user/old-repo", "commits": [], "commit_count": 1},
    ]
    result = compute_repo_breakdown(events, days=90)
    assert len(result["top"]) == 0


# ---- compute_streak_patterns ----


def test_streak_patterns_finds_all():
    """Known date sequences produce correct streaks."""
    # Two streaks: 3 days then 2 days
    dates = [
        "2026-01-05", "2026-01-06", "2026-01-07",  # streak of 3
        # gap on 2026-01-08
        "2026-01-09", "2026-01-10",  # streak of 2
    ]
    result = compute_streak_patterns(dates)

    assert result["total_streaks"] == 2
    assert result["all_streaks"][0]["length"] == 3
    assert result["all_streaks"][0]["start"] == "2026-01-05"
    assert result["all_streaks"][0]["end"] == "2026-01-07"
    assert result["all_streaks"][1]["length"] == 2
    assert result["average_length"] == 2.5
    assert result["median_length"] == 2


def test_streak_patterns_single_day():
    """A single commit date produces one streak of length 1."""
    result = compute_streak_patterns(["2026-01-10"])
    assert result["total_streaks"] == 1
    assert result["all_streaks"][0]["length"] == 1
    assert result["average_length"] == 1.0


def test_streak_patterns_killer_day():
    """Identifies correct day-of-week that kills streaks."""
    # Two streaks both ending on a Friday (break happens on Saturday)
    dates = [
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09",
        # 2026-01-09 = Friday, break on Saturday 2026-01-10
        "2026-01-12", "2026-01-13", "2026-01-14", "2026-01-15", "2026-01-16",
        # 2026-01-16 = Friday, break on Saturday 2026-01-17
    ]
    result = compute_streak_patterns(dates)
    assert result["streak_killer_day"] == "saturday"


def test_streak_patterns_empty():
    """Empty dates list returns zeroes."""
    result = compute_streak_patterns([])
    assert result["total_streaks"] == 0
    assert result["all_streaks"] == []
    assert result["streak_killer_day"] is None


# ---- compute_streak_risk ----


def test_streak_risk_low():
    """Committed today with long history produces low risk."""
    from datetime import datetime, timedelta
    today = datetime.now().date()
    # Build a long unbroken run so break rate at length 3 is low
    dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(30)]
    streak_info = {
        "current_streak": 3,
        "streak_active": True,
        "last_commit_date": today.strftime("%Y-%m-%d"),
        "commit_dates": dates,
    }
    result = compute_streak_risk(streak_info, dates)

    assert result["level"] == "low"
    assert result["hours_remaining"] > 0


def test_streak_risk_high():
    """Not committed today, late in day, short history produces high risk."""
    from unittest.mock import patch
    from datetime import datetime

    streak_info = {
        "current_streak": 2,
        "streak_active": False,
        "last_commit_date": "2026-04-09",
        "commit_dates": ["2026-04-09", "2026-04-08"],
    }

    # Mock "now" to be late at night (11pm)
    fake_now = datetime(2026, 4, 10, 23, 0, 0)
    with patch("src.streak_insights.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.strptime = datetime.strptime
        result = compute_streak_risk(streak_info, streak_info["commit_dates"])

    assert result["level"] == "high"
    assert result["hours_remaining"] < 2


def test_streak_risk_no_streak():
    """No current streak gives break rate of 1.0."""
    streak_info = {
        "current_streak": 0,
        "streak_active": False,
        "last_commit_date": None,
        "commit_dates": [],
    }
    result = compute_streak_risk(streak_info, [])
    assert result["historical_break_rate"] == 1.0


# ---- compute_insights (integration) ----


def test_compute_insights_integration():
    """Full pipeline with mock data produces all expected sections."""
    from datetime import datetime, timedelta

    today = datetime.now().date()

    raw_events = [
        {"type": "PushEvent", "created_at": f"{today}T10:00:00+00:00"},
        {"type": "PushEvent", "created_at": f"{today}T20:00:00+00:00"},
    ]

    commit_events = [
        {"date": (today - timedelta(days=i)).strftime("%Y-%m-%d"),
         "repo": "user/repo1", "commits": [], "commit_count": 1}
        for i in range(5)
    ]

    streak_info = {
        "current_streak": 5,
        "longest_streak": 5,
        "streak_active": True,
        "last_commit_date": today.strftime("%Y-%m-%d"),
        "commit_dates": [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(5)],
    }

    result = compute_insights(raw_events, commit_events, streak_info, days=30)

    assert "period" in result
    assert result["period"]["days"] == 30
    assert "time_of_day" in result
    assert "peak" in result["time_of_day"]
    assert "day_of_week" in result
    assert "strongest" in result["day_of_week"]
    assert "repos" in result
    assert "top" in result["repos"]
    assert "streak_patterns" in result
    assert "total_streaks" in result["streak_patterns"]
    assert "risk" in result
    assert result["risk"]["level"] in ("low", "medium", "high")
