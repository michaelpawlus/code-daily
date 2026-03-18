"""
Duolingo-style notification system for code-daily.

Sends escalating reminders throughout the day when you haven't committed yet.
Uses ntfy.sh as the notification channel (free push notifications).
"""

import os
from abc import ABC, abstractmethod
from datetime import datetime

import requests

from src.config import NTFY_TOPIC, NTFY_SERVER
from src.storage import CommitStorage, get_commit_events_with_history
from src.streak_calculator import calculate_streak


# Messages by level (1=gentle, 4=critical), each with 3 variants
MESSAGES = {
    1: [
        "Good morning! Your {streak}-day streak is waiting. One commit keeps it alive!",
        "Rise and code! You're on a {streak}-day streak. Don't let it slip!",
        "Hey! Your streak is at {streak} days. Time to write some code?",
    ],
    2: [
        "Afternoon check-in: still no commit today. Your {streak}-day streak needs you!",
        "Half the day is gone and no commits yet. Protect that {streak}-day streak!",
        "Your {streak}-day streak is getting nervous. Got a quick fix you can push?",
    ],
    3: [
        "Evening alert! Your {streak}-day streak is in danger. Commit something before bed!",
        "It's getting late and your {streak}-day streak hangs by a thread. Push something!",
        "Your {streak}-day streak is about to break. Even a small commit counts!",
    ],
    4: [
        "LAST CALL! Your {streak}-day streak dies at midnight. Commit NOW!",
        "EMERGENCY: {streak} days of work about to vanish. One commit saves it all!",
        "Your {streak}-day streak has hours to live. Don't let it end like this!",
    ],
}

ZERO_STREAK_MESSAGES = {
    1: "Good morning! No active streak yet. Today's a great day to start one!",
    2: "Afternoon nudge: start a new streak today with just one commit!",
    3: "Evening reminder: there's still time to start a streak today!",
    4: "Last chance today! One commit = day 1 of your new streak.",
}

# ntfy priority mapping (1=min, 5=max)
NTFY_PRIORITY_MAP = {1: "3", 2: "3", 3: "4", 4: "5"}


def build_message(level: int, current_streak: int, streak_active: bool) -> str:
    """
    Build a notification message for the given urgency level.

    Uses day_of_year % len(options) for deterministic variety (no randomness).

    Args:
        level: Urgency level (1-4)
        current_streak: Current streak count
        streak_active: Whether the user already committed today

    Returns:
        Formatted message string
    """
    if streak_active:
        return ""

    if current_streak == 0:
        return ZERO_STREAK_MESSAGES.get(level, ZERO_STREAK_MESSAGES[1])

    options = MESSAGES.get(level, MESSAGES[1])
    day_of_year = datetime.now().timetuple().tm_yday
    idx = day_of_year % len(options)
    return options[idx].format(streak=current_streak)


class NotificationChannel(ABC):
    """Abstract base class for notification channels."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Channel name identifier."""

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Whether this channel has required configuration."""

    @abstractmethod
    def send(self, message: str, title: str, level: int) -> bool:
        """
        Send a notification.

        Args:
            message: Message body
            title: Notification title
            level: Urgency level (1-4)

        Returns:
            True if sent successfully, False otherwise
        """


class NtfyChannel(NotificationChannel):
    """ntfy.sh push notification channel."""

    def __init__(self, topic: str | None = None, server: str | None = None):
        self._topic = topic or NTFY_TOPIC
        self._server = (server or NTFY_SERVER or "https://ntfy.sh").rstrip("/")

    @property
    def name(self) -> str:
        return "ntfy"

    @property
    def is_configured(self) -> bool:
        return bool(self._topic and self._topic.strip())

    def send(self, message: str, title: str, level: int) -> bool:
        if not self.is_configured:
            return False

        priority = int(NTFY_PRIORITY_MAP.get(level, "3"))
        tags = ["computer", "fire"] if level >= 3 else ["computer"]
        url = f"{self._server}"

        try:
            resp = requests.post(
                url,
                json={
                    "topic": self._topic,
                    "title": title,
                    "message": message,
                    "priority": priority,
                    "tags": tags,
                },
                timeout=10,
            )
            return resp.status_code == 200
        except requests.RequestException:
            return False


class NotificationManager:
    """Orchestrates notification checks and sending."""

    def __init__(self, storage: CommitStorage, channels: list[NotificationChannel] | None = None):
        self.storage = storage
        self.channels = channels if channels is not None else [NtfyChannel()]

    def check_and_notify(
        self,
        level: int,
        today: str | None = None,
        dry_run: bool = False,
    ) -> dict:
        """
        Check streak status and send notification if needed.

        This is the main cron entry point. It:
        1. Loads commits from storage (no API call)
        2. Calculates streak
        3. Skips if already committed today
        4. Skips if this level already sent today
        5. Builds message and sends via configured channels
        6. Logs to notification_log

        Args:
            level: Urgency level (1-4)
            today: Override today's date (YYYY-MM-DD) for testing
            dry_run: If True, build message but don't send

        Returns:
            Dict with action taken and details
        """
        if today is None:
            today = datetime.now().strftime("%Y-%m-%d")

        # Get commits from storage only (no API fetch)
        commit_events = get_commit_events_with_history(
            storage=self.storage, fetch_new=False
        )

        # Calculate streak
        streak_info = calculate_streak(commit_events, today=today)
        current_streak = streak_info["current_streak"]
        streak_active = streak_info["streak_active"]

        # Skip if already committed today
        if streak_active:
            return {
                "action": "skipped",
                "reason": "already_committed",
                "streak": current_streak,
                "streak_active": True,
            }

        # Check deduplication -- skip if this level already sent
        max_level = self.storage.get_max_level_sent_today(today)
        if max_level is not None and level <= max_level:
            return {
                "action": "skipped",
                "reason": "already_sent",
                "max_level_sent": max_level,
                "requested_level": level,
            }

        # Build message
        message = build_message(level, current_streak, streak_active)
        if current_streak > 0:
            title = f"code-daily: {current_streak}-day streak at risk!"
        else:
            title = "code-daily: start a streak today!"

        if dry_run:
            return {
                "action": "dry_run",
                "level": level,
                "message": message,
                "title": title,
                "streak": current_streak,
                "streak_active": streak_active,
                "channels": [ch.name for ch in self.channels if ch.is_configured],
            }

        # Send via all configured channels
        results = []
        for channel in self.channels:
            if not channel.is_configured:
                continue
            success = channel.send(message, title, level)
            results.append({"channel": channel.name, "success": success})

            if success:
                self.storage.log_notification(
                    date=today,
                    level=level,
                    channel=channel.name,
                    message=message,
                    streak_value=current_streak,
                    streak_active=streak_active,
                )

        if not results:
            return {
                "action": "skipped",
                "reason": "no_channels_configured",
            }

        return {
            "action": "sent",
            "level": level,
            "message": message,
            "streak": current_streak,
            "channels": results,
        }

    def send_test(self, channel_name: str | None = None) -> dict:
        """
        Send a test notification to verify channel setup.

        Args:
            channel_name: Specific channel to test, or None for all configured

        Returns:
            Dict with test results per channel
        """
        results = []
        for channel in self.channels:
            if channel_name and channel.name != channel_name:
                continue
            if not channel.is_configured:
                results.append({
                    "channel": channel.name,
                    "success": False,
                    "reason": "not_configured",
                })
                continue

            success = channel.send(
                message="This is a test notification from code-daily. If you see this, notifications are working!",
                title="code-daily test",
                level=1,
            )
            results.append({"channel": channel.name, "success": success})

        return {"results": results}

    def get_status(self) -> dict:
        """
        Get configuration status for all channels.

        Returns:
            Dict with channel statuses
        """
        channels = []
        for channel in self.channels:
            channels.append({
                "name": channel.name,
                "configured": channel.is_configured,
            })

        any_configured = any(ch["configured"] for ch in channels)
        return {
            "any_configured": any_configured,
            "channels": channels,
        }

    def get_today_notifications(self, today: str | None = None) -> list[dict]:
        """
        Get notifications sent today.

        Args:
            today: Override today's date for testing

        Returns:
            List of notification log entries
        """
        if today is None:
            today = datetime.now().strftime("%Y-%m-%d")
        return self.storage.get_notifications_for_date(today)
