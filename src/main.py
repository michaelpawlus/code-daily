"""
code-daily: A gamified coding habit tracker

Entry point for the application.
"""

from src.config import GITHUB_TOKEN, GITHUB_USERNAME, validate_config
from src.github_client import GitHubClient, GitHubClientError
from src.streak_calculator import calculate_streak
from src.stats_calculator import calculate_stats
from src.storage import CommitStorage, get_commit_events_with_history
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

    # Create client and storage
    client = GitHubClient(GITHUB_TOKEN, GITHUB_USERNAME)
    storage = CommitStorage()

    try:
        print(f"\nFetching recent activity for {GITHUB_USERNAME}...\n")

        # Fetch from API, save to storage, and get all commits
        commit_events = get_commit_events_with_history(client, storage)

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
