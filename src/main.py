"""
code-daily: A gamified coding habit tracker

Entry point for the application.
"""

from src.config import GITHUB_TOKEN, GITHUB_USERNAME, validate_config
from src.github_client import GitHubClient, GitHubClientError


def format_event(event: dict) -> str:
    """Format a GitHub event for display."""
    event_type = event.get("type", "Unknown")
    repo = event.get("repo", {}).get("name", "unknown")
    created_at = event.get("created_at", "")[:10]  # Just the date part

    # Make event types more readable
    type_display = event_type.replace("Event", "")

    return f"  {created_at}  {type_display:<20} {repo}"


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
        events = client.get_user_events(per_page=10)

        if not events:
            print("No recent events found.")
            return 0

        print(f"Found {len(events)} recent events:\n")
        print("  DATE        TYPE                 REPOSITORY")
        print("  " + "-" * 46)

        for event in events:
            print(format_event(event))

        print()

    except GitHubClientError as e:
        print(f"\nError: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
