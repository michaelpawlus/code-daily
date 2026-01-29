"""
FastAPI web application for code-daily.

Provides REST API endpoints for streak and stats data.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from src.config import GITHUB_TOKEN, GITHUB_USERNAME, validate_config
from src.github_client import GitHubClient, GitHubClientError
from src.streak_calculator import calculate_streak
from src.stats_calculator import calculate_stats
from src.history_calculator import calculate_history
from src.storage import CommitStorage, get_commit_events_with_history
from src.achievements import check_achievements, get_all_achievements_status

app = FastAPI(
    title="code-daily",
    description="A gamified coding habit tracker",
    version="0.1.0",
)

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

DEFAULT_DAILY_GOAL = 1
DAILY_GOAL_KEY = "daily_commit_goal"


class GoalUpdate(BaseModel):
    """Request model for updating the daily goal."""

    goal: int = Field(..., ge=1, le=100, description="Daily commit goal (1-100)")


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


def _fetch_stats_data():
    """
    Fetch and calculate stats data.

    Returns:
        dict with username, streak, stats, and commit_dates

    Raises:
        HTTPException: on configuration or GitHub API errors
    """
    # Validate configuration
    try:
        validate_config()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"Configuration error: {e}")

    # Create client and storage
    client = GitHubClient(GITHUB_TOKEN, GITHUB_USERNAME)
    storage = CommitStorage()

    try:
        # Fetch from API, save to storage, and get all commits
        commit_events = get_commit_events_with_history(client, storage)
    except GitHubClientError as e:
        raise HTTPException(status_code=502, detail=str(e))

    # Calculate streak and stats
    streak_info = calculate_streak(commit_events)
    stats = calculate_stats(commit_events)

    # Get daily goal
    goal_str = storage.get_setting(DAILY_GOAL_KEY, str(DEFAULT_DAILY_GOAL))
    daily_goal = int(goal_str) if goal_str else DEFAULT_DAILY_GOAL

    # Process achievements
    unlocked_records = storage.get_unlocked_achievements()
    unlocked_ids = {r["id"] for r in unlocked_records}

    # Check for newly unlocked achievements
    newly_unlocked = check_achievements(
        current_streak=streak_info["current_streak"],
        longest_streak=streak_info["longest_streak"],
        total_commits=stats["total_commits"],
        unlocked_ids=unlocked_ids,
    )

    # Save newly unlocked achievements
    for achievement in newly_unlocked:
        if achievement.category == "streak":
            value = streak_info["longest_streak"]
        else:
            value = stats["total_commits"]
        # Only save if value actually meets threshold (defensive check)
        if value >= achievement.threshold:
            storage.save_achievement(achievement.id, value)

    # Refresh unlocked records if there were new achievements
    if newly_unlocked:
        unlocked_records = storage.get_unlocked_achievements()

    # Get all achievements with status
    achievements = get_all_achievements_status(unlocked_records)

    return {
        "username": GITHUB_USERNAME,
        "streak": {
            "current": streak_info["current_streak"],
            "longest": streak_info["longest_streak"],
            "active": streak_info["streak_active"],
            "last_commit_date": streak_info["last_commit_date"],
        },
        "stats": {
            "today": stats["commits_today"],
            "this_week": stats["commits_this_week"],
            "this_month": stats["commits_this_month"],
            "last_7_days": stats["commits_last_7_days"],
            "last_30_days": stats["commits_last_30_days"],
            "total": stats["total_commits"],
        },
        "goal": {
            "daily": daily_goal,
            "today_progress": stats["commits_today"],
            "met": stats["commits_today"] >= daily_goal,
        },
        "commit_dates": streak_info["commit_dates"],
        "commit_events": commit_events,
        "achievements": achievements,
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """Render the dashboard page."""
    data = _fetch_stats_data()
    # Add history data for heatmap
    data["history"] = calculate_history(data.get("commit_events", []))
    return templates.TemplateResponse(request, "index.html", data)


@app.get("/api/stats")
def get_stats():
    """
    Get current streak and commit statistics.

    Returns:
        JSON with streak info and commit stats
    """
    return _fetch_stats_data()


@app.get("/api/history")
def get_history():
    """
    Get commit history for heatmap display.

    Returns:
        JSON with daily commit counts and intensity levels for 84 days
    """
    # Validate configuration
    try:
        validate_config()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"Configuration error: {e}")

    # Create client and storage
    client = GitHubClient(GITHUB_TOKEN, GITHUB_USERNAME)
    storage = CommitStorage()

    try:
        commit_events = get_commit_events_with_history(client, storage)
    except GitHubClientError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return calculate_history(commit_events)


@app.get("/api/goal")
def get_goal():
    """
    Get current daily commit goal.

    Returns:
        JSON with the current daily goal
    """
    storage = CommitStorage()
    goal_str = storage.get_setting(DAILY_GOAL_KEY, str(DEFAULT_DAILY_GOAL))
    daily_goal = int(goal_str) if goal_str else DEFAULT_DAILY_GOAL
    return {"goal": daily_goal}


@app.post("/api/goal")
def set_goal(update: GoalUpdate):
    """
    Set daily commit goal.

    Args:
        update: GoalUpdate with goal value (1-100)

    Returns:
        JSON with the updated goal
    """
    storage = CommitStorage()
    storage.set_setting(DAILY_GOAL_KEY, str(update.goal))
    return {"goal": update.goal}


@app.get("/api/achievements")
def get_achievements():
    """
    Get all achievements with unlock status.

    Returns:
        JSON with achievements list and summary
    """
    data = _fetch_stats_data()
    achievements = data["achievements"]
    unlocked_count = sum(1 for a in achievements if a["unlocked"])

    return {
        "achievements": achievements,
        "summary": {
            "total": len(achievements),
            "unlocked": unlocked_count,
        },
    }
