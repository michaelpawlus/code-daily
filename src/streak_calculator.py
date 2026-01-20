"""
Calculate coding streaks from commit events.
"""

from datetime import datetime, timedelta


def calculate_streak(commit_events: list[dict], today: str | None = None) -> dict:
    """
    Calculate streak information from parsed commit events.

    Args:
        commit_events: List of parsed commit events from parse_commit_events()
            Each event has: date, repo, commits, commit_count
        today: Override today's date for testing (YYYY-MM-DD format).
            Defaults to current date.

    Returns:
        Dictionary with streak statistics:
        - current_streak: Consecutive days including today (or yesterday)
        - longest_streak: Longest streak found in the data
        - streak_active: Whether streak is active (committed today)
        - last_commit_date: Most recent commit date (or None)
        - commit_dates: List of unique dates with commits (sorted descending)
    """
    # Handle empty input
    if not commit_events:
        return {
            "current_streak": 0,
            "longest_streak": 0,
            "streak_active": False,
            "last_commit_date": None,
            "commit_dates": [],
        }

    # Get today's date
    if today is None:
        today = datetime.now().strftime("%Y-%m-%d")

    # Extract unique dates from commit events
    commit_dates = sorted(
        set(event["date"] for event in commit_events if event.get("date")),
        reverse=True,  # Most recent first
    )

    # Filter out invalid dates
    commit_dates = [d for d in commit_dates if d != "unknown"]

    if not commit_dates:
        return {
            "current_streak": 0,
            "longest_streak": 0,
            "streak_active": False,
            "last_commit_date": None,
            "commit_dates": [],
        }

    last_commit_date = commit_dates[0]

    # Check if streak is active (committed today)
    streak_active = last_commit_date == today

    # Calculate current streak
    current_streak = _calculate_current_streak(commit_dates, today)

    # Calculate longest streak
    longest_streak = _calculate_longest_streak(commit_dates)

    # Longest streak should be at least as long as current streak
    longest_streak = max(longest_streak, current_streak)

    return {
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "streak_active": streak_active,
        "last_commit_date": last_commit_date,
        "commit_dates": commit_dates,
    }


def _calculate_current_streak(commit_dates: list[str], today: str) -> int:
    """
    Calculate the current streak from commit dates.

    The streak starts from today or yesterday (grace period) and counts
    consecutive days backwards.

    Args:
        commit_dates: Sorted list of commit dates (descending)
        today: Today's date in YYYY-MM-DD format

    Returns:
        Current streak count
    """
    if not commit_dates:
        return 0

    today_date = datetime.strptime(today, "%Y-%m-%d").date()
    yesterday = today_date - timedelta(days=1)

    most_recent = datetime.strptime(commit_dates[0], "%Y-%m-%d").date()

    # Streak must start from today or yesterday
    if most_recent != today_date and most_recent != yesterday:
        return 0

    # Count consecutive days starting from the most recent commit
    streak = 1
    current_date = most_recent

    for i in range(1, len(commit_dates)):
        commit_date = datetime.strptime(commit_dates[i], "%Y-%m-%d").date()
        expected_date = current_date - timedelta(days=1)

        if commit_date == expected_date:
            streak += 1
            current_date = commit_date
        elif commit_date < expected_date:
            # Gap found, streak ends
            break
        # If commit_date == current_date, skip duplicate (shouldn't happen with unique dates)

    return streak


def _calculate_longest_streak(commit_dates: list[str]) -> int:
    """
    Calculate the longest streak in the commit date history.

    Args:
        commit_dates: Sorted list of commit dates (descending)

    Returns:
        Longest streak count
    """
    if not commit_dates:
        return 0

    if len(commit_dates) == 1:
        return 1

    longest = 1
    current_streak = 1

    for i in range(1, len(commit_dates)):
        current_date = datetime.strptime(commit_dates[i - 1], "%Y-%m-%d").date()
        prev_date = datetime.strptime(commit_dates[i], "%Y-%m-%d").date()

        # Check if consecutive (remember: dates are in descending order)
        if current_date - prev_date == timedelta(days=1):
            current_streak += 1
            longest = max(longest, current_streak)
        else:
            current_streak = 1

    return longest
