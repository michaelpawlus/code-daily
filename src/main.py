"""
code-daily: A gamified coding habit tracker

Entry point for the application.
"""

from src.config import GITHUB_TOKEN, GITHUB_USERNAME, validate_config
from src.github_client import GitHubClient, GitHubClientError
from src.commit_parser import parse_commit_events
from src.streak_calculator import calculate_streak
from src.stats_calculator import calculate_stats
from src.cli import display_streak, display_calendar, display_stats, format_commit_event


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
        display_streak(streak_info)

        # Calculate and display stats
        stats = calculate_stats(commit_events)
        display_stats(stats)

        # Display activity calendar
        display_calendar(streak_info["commit_dates"])

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
