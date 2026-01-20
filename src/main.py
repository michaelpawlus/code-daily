"""
code-daily: A gamified coding habit tracker

Entry point for the application.
"""

from src.config import GITHUB_TOKEN, GITHUB_USERNAME, validate_config
from src.github_client import GitHubClient, GitHubClientError
from src.commit_parser import parse_commit_events
from src.streak_calculator import calculate_streak


def _display_streak(streak_info: dict) -> None:
    """Display streak information to the console."""
    current = streak_info["current_streak"]
    last_date = streak_info["last_commit_date"]
    active = streak_info["streak_active"]

    # Choose emoji based on streak status
    if current == 0:
        status = "No active streak"
    elif active:
        status = f"Current Streak: {current} day{'s' if current != 1 else ''}"
    else:
        status = f"Current Streak: {current} day{'s' if current != 1 else ''} (commit today to continue!)"

    print(f"🔥 {status}")
    if last_date:
        print(f"   Last commit: {last_date}")
    print()


def format_commit_event(commit_event: dict) -> str:
    """Format a parsed commit event for display."""
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


def main():
    print("code-daily - Track your coding streaks!")
    print("-" * 50)

    # Validate configuration
    try:
        validate_config()
    except ValueError as e:
        print(f"\nConfiguration Error:\n{e}")
        return 1

    # Create client and fetch events
    client = GitHubClient(GITHUB_TOKEN, GITHUB_USERNAME)

    try:
        print(f"\nFetching recent activity for {GITHUB_USERNAME}...\n")
        events = client.get_user_events(per_page=30)

        if not events:
            print("No recent events found.")
            return 0

        # Parse commit events
        commit_events = parse_commit_events(events)

        if not commit_events:
            print("No commit events found in recent activity.")
            return 0

        # Calculate and display streak
        streak_info = calculate_streak(commit_events)
        _display_streak(streak_info)

        print(f"Found {len(commit_events)} commit events:\n")
        print("  DATE        COMMITS    REPOSITORY                     MESSAGE")
        print("  " + "-" * 80)

        for commit_event in commit_events:
            print(format_commit_event(commit_event))

        print()

    except GitHubClientError as e:
        print(f"\nError: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
