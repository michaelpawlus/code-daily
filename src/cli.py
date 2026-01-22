"""
CLI display functions for code-daily.
"""

from datetime import datetime, timedelta


def get_milestone_message(streak_days: int) -> str | None:
    """
    Get milestone message for a given streak length.

    Args:
        streak_days: Current streak in days

    Returns:
        Milestone message string or None if no milestone
    """
    milestones = {
        7: "One week strong!",
        14: "Two weeks of consistency!",
        30: "One month champion!",
        60: "Two months unstoppable!",
        100: "100 days - legendary!",
    }
    return milestones.get(streak_days)


def display_streak(streak_info: dict) -> None:
    """
    Display streak information to the console with milestone messages.

    Args:
        streak_info: Dictionary from calculate_streak() containing:
            - current_streak: int
            - streak_active: bool
            - last_commit_date: str or None
    """
    current = streak_info["current_streak"]
    last_date = streak_info["last_commit_date"]
    active = streak_info["streak_active"]

    # Build status message
    if current == 0:
        status = "No active streak"
    else:
        day_word = "day" if current == 1 else "days"
        status = f"Current Streak: {current} {day_word}"

        # Add milestone message if applicable
        milestone = get_milestone_message(current)
        if milestone:
            status = f"{status} - {milestone}"
        elif not active:
            status = f"{status} (commit today to continue!)"

    print(f"🔥 {status}")
    if last_date:
        print(f"   Last commit: {last_date}")
    print()


def display_calendar(
    commit_dates: list[str], days: int = 14, today: str | None = None
) -> None:
    """
    Display a text-based activity calendar showing recent commit activity.

    Args:
        commit_dates: List of dates with commits (YYYY-MM-DD format)
        days: Number of days to display (default 14)
        today: Override today's date for testing (YYYY-MM-DD format)
    """
    if today is None:
        today_date = datetime.now().date()
    else:
        today_date = datetime.strptime(today, "%Y-%m-%d").date()

    # Convert commit dates to set for O(1) lookup
    commit_set = set(commit_dates)

    # Build list of dates to display (oldest to newest)
    dates_to_show = []
    for i in range(days - 1, -1, -1):
        date = today_date - timedelta(days=i)
        dates_to_show.append(date)

    # Day abbreviations
    day_abbrevs = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    # Group dates by week (starting on Monday)
    # Find the Monday of the first week
    first_date = dates_to_show[0]
    first_monday = first_date - timedelta(days=first_date.weekday())

    # Create grid structure
    weeks = []
    current_week = [None] * 7  # Initialize with None for empty slots

    for date in dates_to_show:
        weekday = date.weekday()  # 0=Monday, 6=Sunday
        has_commit = date.strftime("%Y-%m-%d") in commit_set

        # Check if we need to start a new week
        week_num = (date - first_monday).days // 7
        if week_num >= len(weeks):
            if any(cell is not None for cell in current_week):
                weeks.append(current_week)
            current_week = [None] * 7

        current_week[weekday] = "[*]" if has_commit else "[ ]"

    # Don't forget the last week
    if any(cell is not None for cell in current_week):
        weeks.append(current_week)

    # Print header
    print("Recent Activity:")
    header = "  " + " ".join(day_abbrevs)
    print(header)

    # Print each week
    for week in weeks:
        row = "  "
        for cell in week:
            if cell is None:
                row += "    "  # 4 spaces to match "[*] " width
            else:
                row += cell + " "
        print(row.rstrip())

    print()


def display_stats(stats: dict) -> None:
    """
    Display commit statistics to the console.

    Args:
        stats: Dictionary from calculate_stats() containing:
            - commits_today: int
            - commits_this_week: int
            - commits_this_month: int
    """
    today = stats["commits_today"]
    week = stats["commits_this_week"]
    month = stats["commits_this_month"]

    today_label = "commit" if today == 1 else "commits"
    week_label = "commit" if week == 1 else "commits"
    month_label = "commit" if month == 1 else "commits"

    print("📊 Commit Stats:")
    print(f"   Today:      {today} {today_label}")
    print(f"   This week:  {week} {week_label}")
    print(f"   This month: {month} {month_label}")
    print()


def format_commit_event(commit_event: dict) -> str:
    """
    Format a parsed commit event for display.

    Args:
        commit_event: Dictionary containing:
            - date: str
            - repo: str
            - commit_count: int
            - commits: list of commit dicts (optional)

    Returns:
        Formatted string for display
    """
    date = commit_event["date"]
    repo = commit_event["repo"]
    commit_count = commit_event["commit_count"]

    # Get first commit message if available
    commits = commit_event.get("commits", [])
    first_message = commits[0]["message"] if commits else "No commit message"

    # Truncate long messages
    if len(first_message) > 50:
        first_message = first_message[:47] + "..."

    plural = "commit" if commit_count == 1 else "commits"
    return f"  {date}  {commit_count} {plural:<10} {repo:<30} {first_message}"
