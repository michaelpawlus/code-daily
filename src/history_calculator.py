"""
History calculator for commit activity heatmap.

Calculates daily commit counts and intensity levels for a GitHub-style
contribution heatmap.
"""

from datetime import date, timedelta
from typing import Optional


def calculate_history(
    commit_events: list,
    days: int = 84,
    today: Optional[date] = None,
) -> dict:
    """
    Calculate commit history for heatmap display.

    Args:
        commit_events: List of commit event dicts with 'date' and 'commit_count' keys
        days: Number of days to include (default 84 = 12 weeks)
        today: Override for today's date (for testing)

    Returns:
        Dictionary with:
            - days: List of {date, count, level} for each day
            - period: Start/end dates and total days
            - max_count: Maximum commits in a single day
    """
    if today is None:
        today = date.today()

    # Build a mapping of date string -> commit count
    commits_by_date: dict[str, int] = {}
    for event in commit_events:
        event_date = event.get("date", "")
        count = event.get("commit_count", 0)
        if event_date:
            commits_by_date[event_date] = commits_by_date.get(event_date, 0) + count

    # Calculate the start date (days-1 days ago to include today)
    start_date = today - timedelta(days=days - 1)

    # Build the list of days
    day_list = []
    max_count = 0

    for i in range(days):
        current_date = start_date + timedelta(days=i)
        date_str = current_date.isoformat()
        count = commits_by_date.get(date_str, 0)
        max_count = max(max_count, count)
        level = _calculate_level(count)

        day_list.append({
            "date": date_str,
            "count": count,
            "level": level,
        })

    return {
        "days": day_list,
        "period": {
            "start": start_date.isoformat(),
            "end": today.isoformat(),
            "total_days": days,
        },
        "max_count": max_count,
    }


def _calculate_level(count: int) -> int:
    """
    Calculate intensity level for heatmap coloring.

    Args:
        count: Number of commits for the day

    Returns:
        Level from 0-4:
            0: No commits
            1: 1 commit
            2: 2-3 commits
            3: 4-5 commits
            4: 6+ commits
    """
    if count == 0:
        return 0
    elif count == 1:
        return 1
    elif count <= 3:
        return 2
    elif count <= 5:
        return 3
    else:
        return 4
