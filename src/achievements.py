"""
Achievement system for code-daily.

Provides gamified achievements based on streak length and total commit counts.
"""

from dataclasses import dataclass


@dataclass
class Achievement:
    """Represents an achievement that can be unlocked."""

    id: str
    name: str
    emoji: str
    description: str
    category: str  # "streak" or "commits"
    threshold: int  # The value needed to unlock


# Streak-based achievements
STREAK_ACHIEVEMENTS = [
    Achievement(
        id="streak_3",
        name="First Steps",
        emoji="🔥",
        description="Maintain a 3-day coding streak",
        category="streak",
        threshold=3,
    ),
    Achievement(
        id="streak_7",
        name="Week Warrior",
        emoji="🏆",
        description="Maintain a 7-day coding streak",
        category="streak",
        threshold=7,
    ),
    Achievement(
        id="streak_14",
        name="Fortnight Fighter",
        emoji="📅",
        description="Maintain a 14-day coding streak",
        category="streak",
        threshold=14,
    ),
    Achievement(
        id="streak_30",
        name="Monthly Master",
        emoji="⭐",
        description="Maintain a 30-day coding streak",
        category="streak",
        threshold=30,
    ),
    Achievement(
        id="streak_100",
        name="Century Coder",
        emoji="💯",
        description="Maintain a 100-day coding streak",
        category="streak",
        threshold=100,
    ),
]

# Commit count achievements
COMMIT_ACHIEVEMENTS = [
    Achievement(
        id="first_commit",
        name="Hello World",
        emoji="👋",
        description="Make your first commit",
        category="commits",
        threshold=1,
    ),
    Achievement(
        id="commits_10",
        name="Getting Started",
        emoji="🌱",
        description="Make 10 total commits",
        category="commits",
        threshold=10,
    ),
    Achievement(
        id="commits_50",
        name="Halfway Hero",
        emoji="🚀",
        description="Make 50 total commits",
        category="commits",
        threshold=50,
    ),
    Achievement(
        id="commits_100",
        name="Century Club",
        emoji="💯",
        description="Make 100 total commits",
        category="commits",
        threshold=100,
    ),
    Achievement(
        id="commits_500",
        name="Commit Champion",
        emoji="👑",
        description="Make 500 total commits",
        category="commits",
        threshold=500,
    ),
]

# Combined list of all achievements
ACHIEVEMENTS = STREAK_ACHIEVEMENTS + COMMIT_ACHIEVEMENTS


def check_achievements(
    current_streak: int,
    longest_streak: int,
    total_commits: int,
    unlocked_ids: set[str],
) -> list[Achievement]:
    """
    Check for newly unlocked achievements.

    Args:
        current_streak: Current active streak length
        longest_streak: Longest streak ever achieved
        total_commits: Total number of commits
        unlocked_ids: Set of already unlocked achievement IDs

    Returns:
        List of newly unlocked Achievement objects
    """
    newly_unlocked = []

    for achievement in ACHIEVEMENTS:
        # Skip already unlocked achievements
        if achievement.id in unlocked_ids:
            continue

        # Check if achievement criteria is met
        if achievement.category == "streak":
            # Use longest_streak for streak achievements (permanent unlock)
            if longest_streak >= achievement.threshold:
                newly_unlocked.append(achievement)
        elif achievement.category == "commits":
            if total_commits >= achievement.threshold:
                newly_unlocked.append(achievement)

    return newly_unlocked


def get_all_achievements_status(
    unlocked_achievements: list[dict],
) -> list[dict]:
    """
    Get all achievements with their unlock status.

    Args:
        unlocked_achievements: List of unlocked achievement records from storage
            Each record has: id, unlocked_at, unlocked_value

    Returns:
        List of all achievements with unlock status, sorted by category then threshold
    """
    # Create a lookup for unlocked achievements
    unlocked_lookup = {a["id"]: a for a in unlocked_achievements}

    result = []
    for achievement in ACHIEVEMENTS:
        unlocked_record = unlocked_lookup.get(achievement.id)
        result.append({
            "id": achievement.id,
            "name": achievement.name,
            "emoji": achievement.emoji,
            "description": achievement.description,
            "category": achievement.category,
            "threshold": achievement.threshold,
            "unlocked": unlocked_record is not None,
            "unlocked_at": unlocked_record["unlocked_at"] if unlocked_record else None,
            "unlocked_value": unlocked_record.get("unlocked_value") if unlocked_record else None,
        })

    return result
