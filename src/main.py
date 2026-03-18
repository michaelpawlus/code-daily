"""
code-daily: A gamified coding habit tracker

Entry point for the application.
"""

import argparse
import os
import sys

from src.config import GITHUB_TOKEN, GITHUB_USERNAME, validate_config
from src.github_client import GitHubClient, GitHubClientError
from src.streak_calculator import calculate_streak
from src.stats_calculator import calculate_stats
from src.storage import CommitStorage, get_commit_events_with_history
from src.cli import display_streak, display_calendar, display_stats, format_commit_event


def _run_dashboard():
    """Original dashboard behavior -- fetch and display streaks."""
    print("code-daily - Track your coding streaks!")
    print("-" * 50)

    try:
        validate_config()
    except ValueError as e:
        print(f"\nConfiguration Error:\n{e}")
        return 1

    client = GitHubClient(GITHUB_TOKEN, GITHUB_USERNAME)
    storage = CommitStorage()

    try:
        print(f"\nFetching recent activity for {GITHUB_USERNAME}...\n")

        commit_events = get_commit_events_with_history(client, storage)

        if not commit_events:
            print("No commit events found in recent activity.")
            return 0

        streak_info = calculate_streak(commit_events)
        display_streak(streak_info)

        stats = calculate_stats(commit_events)
        display_stats(stats)

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


def _run_check(level: int, dry_run: bool) -> int:
    """Check streak and send notification if needed."""
    from src.notifications import NotificationManager

    storage = CommitStorage()
    manager = NotificationManager(storage)

    result = manager.check_and_notify(level=level, dry_run=dry_run)
    action = result.get("action")

    if action == "skipped":
        reason = result.get("reason")
        if reason == "already_committed":
            print(f"Skipped: already committed today (streak: {result.get('streak')})")
        elif reason == "already_sent":
            print(f"Skipped: level {result.get('requested_level')} already sent (max sent: {result.get('max_level_sent')})")
        elif reason == "no_channels_configured":
            print("Skipped: no notification channels configured")
            print("Set NTFY_TOPIC in .env to enable notifications")
        return 0

    if action == "dry_run":
        print(f"[DRY RUN] Level {result.get('level')} notification:")
        print(f"  Title:   {result.get('title')}")
        print(f"  Message: {result.get('message')}")
        print(f"  Streak:  {result.get('streak')} (active: {result.get('streak_active')})")
        print(f"  Channels: {', '.join(result.get('channels', []))}")
        return 0

    if action == "sent":
        print(f"Sent level {result.get('level')} notification (streak: {result.get('streak')})")
        for ch in result.get("channels", []):
            status = "OK" if ch["success"] else "FAILED"
            print(f"  {ch['channel']}: {status}")
        return 0

    print(f"Unexpected result: {result}")
    return 1


def _run_notify_test() -> int:
    """Send test notification to verify channel setup."""
    from src.notifications import NotificationManager

    storage = CommitStorage()
    manager = NotificationManager(storage)

    result = manager.send_test()
    for ch in result.get("results", []):
        if ch.get("reason") == "not_configured":
            print(f"  {ch['channel']}: not configured")
        elif ch["success"]:
            print(f"  {ch['channel']}: OK")
        else:
            print(f"  {ch['channel']}: FAILED")

    return 0


def _run_notify_status() -> int:
    """Show notification channel status."""
    from src.notifications import NotificationManager

    storage = CommitStorage()
    manager = NotificationManager(storage)

    status = manager.get_status()
    if not status["any_configured"]:
        print("No notification channels configured.")
        print("Set NTFY_TOPIC in .env to enable push notifications.")
    else:
        print("Notification channels:")
        for ch in status["channels"]:
            state = "enabled" if ch["configured"] else "not configured"
            print(f"  {ch['name']}: {state}")

    return 0


def _run_setup_cron() -> int:
    """Print crontab entries for the escalating schedule."""
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    venv_python = os.path.join(project_dir, ".venv", "bin", "python")

    print("# code-daily notification schedule")
    print("# Add these to your crontab with: crontab -e")
    print()
    print(f"# Level 1: Morning gentle reminder (10 AM)")
    print(f"0 10 * * * cd {project_dir} && {venv_python} -m src.typer_cli check 1")
    print()
    print(f"# Level 2: Afternoon nudge (4 PM)")
    print(f"0 16 * * * cd {project_dir} && {venv_python} -m src.typer_cli check 2")
    print()
    print(f"# Level 3: Evening urgent (7 PM)")
    print(f"0 19 * * * cd {project_dir} && {venv_python} -m src.typer_cli check 3")
    print()
    print(f"# Level 4: Night critical (9 PM)")
    print(f"0 21 * * * cd {project_dir} && {venv_python} -m src.typer_cli check 4")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="code-daily: A gamified coding habit tracker",
    )
    parser.add_argument(
        "--check",
        type=int,
        choices=[1, 2, 3, 4],
        metavar="LEVEL",
        help="Check streak and send level 1-4 notification if needed",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview notification without sending (use with --check)",
    )
    parser.add_argument(
        "--notify-test",
        action="store_true",
        help="Send test notification to verify channel setup",
    )
    parser.add_argument(
        "--notify-status",
        action="store_true",
        help="Show which notification channels are configured",
    )
    parser.add_argument(
        "--setup-cron",
        action="store_true",
        help="Print crontab entries for escalating notification schedule",
    )

    args = parser.parse_args()

    # Dispatch to the appropriate command
    if args.check:
        return _run_check(args.check, args.dry_run)
    elif args.notify_test:
        return _run_notify_test()
    elif args.notify_status:
        return _run_notify_status()
    elif args.setup_cron:
        return _run_setup_cron()
    else:
        # Default: original dashboard behavior
        return _run_dashboard()


if __name__ == "__main__":
    from src.typer_cli import app as typer_app
    typer_app()
