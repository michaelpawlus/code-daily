"""
Calculate weekly and monthly commit statistics.
"""

from datetime import datetime, timedelta


def calculate_stats(commit_events: list[dict], today: str | None = None) -> dict:
    """
    Calculate weekly and monthly commit statistics.

    Args:
        commit_events: List of parsed commit events from parse_commit_events()
            Each event has: date, repo, commits, commit_count
        today: Override today's date for testing (YYYY-MM-DD format).
            Defaults to current date.

    Returns:
        Dictionary with commit statistics:
        - commits_today: Commits made today
        - commits_this_week: Commits Mon-Sun of current week
        - commits_this_month: Commits in current calendar month
        - commits_last_7_days: Rolling 7-day commit count
        - commits_last_30_days: Rolling 30-day commit count
        - total_commits: Total commits from available data
    """
    if today is None:
        today_date = datetime.now().date()
    else:
        today_date = datetime.strptime(today, "%Y-%m-%d").date()

    # Initialize counters
    commits_today = 0
    commits_this_week = 0
    commits_this_month = 0
    commits_last_7_days = 0
    commits_last_30_days = 0
    total_commits = 0

    # Calculate date boundaries
    today_str = today_date.strftime("%Y-%m-%d")

    # Week boundaries (Monday to Sunday)
    week_start = today_date - timedelta(days=today_date.weekday())  # Monday
    week_end = week_start + timedelta(days=6)  # Sunday

    # Month boundaries
    month_start = today_date.replace(day=1)

    # Rolling period boundaries
    seven_days_ago = today_date - timedelta(days=6)  # Include today = 7 days
    thirty_days_ago = today_date - timedelta(days=29)  # Include today = 30 days

    for event in commit_events:
        date_str = event.get("date", "")
        if not date_str or date_str == "unknown":
            continue

        try:
            event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue

        commit_count = event.get("commit_count", 0)
        total_commits += commit_count

        # Today
        if date_str == today_str:
            commits_today += commit_count

        # This week (Mon-Sun)
        if week_start <= event_date <= week_end:
            commits_this_week += commit_count

        # This month
        if event_date >= month_start and event_date.month == today_date.month:
            commits_this_month += commit_count

        # Last 7 days (rolling)
        if seven_days_ago <= event_date <= today_date:
            commits_last_7_days += commit_count

        # Last 30 days (rolling)
        if thirty_days_ago <= event_date <= today_date:
            commits_last_30_days += commit_count

    return {
        "commits_today": commits_today,
        "commits_this_week": commits_this_week,
        "commits_this_month": commits_this_month,
        "commits_last_7_days": commits_last_7_days,
        "commits_last_30_days": commits_last_30_days,
        "total_commits": total_commits,
    }
