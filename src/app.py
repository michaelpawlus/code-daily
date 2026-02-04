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
from src.quest_manager import QuestManager
from src.ideas import read_ideas, add_idea, sync_ideas_to_db
from src.todo_scanner import scan_directory

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


class QuestCreate(BaseModel):
    """Request model for creating a quest."""

    title: str = Field(..., min_length=1, max_length=500, description="Quest title")
    description: str | None = Field(None, max_length=2000, description="Optional description")


class QuestSkip(BaseModel):
    """Request model for skipping a quest."""

    action: str = Field("archive", description="Skip action: 'archive' or 'skip'")
    save_as_idea: bool = Field(False, description="Save quest as idea before skipping")


class IdeaCreate(BaseModel):
    """Request model for creating an idea."""

    content: str = Field(..., min_length=1, max_length=1000, description="Idea content")


class BatchEnhanceRequest(BaseModel):
    """Request model for batch quest enhancement."""

    limit: int = Field(5, ge=1, le=20, description="Number of quests to enhance (1-20)")


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

    # Add quest data
    storage = CommitStorage()
    quest_manager = QuestManager(storage)
    data["quests"] = {
        "pending": quest_manager.get_prioritized_quests(status="pending", limit=5),
        "active": quest_manager.get_active_quests(),
        "summary": quest_manager.get_quest_summary(),
    }

    # Add ideas data
    data["ideas"] = storage.get_ideas(status="active")

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


# Quest API endpoints
@app.get("/api/quests")
def get_quests():
    """
    Get quests with summary.

    Returns:
        JSON with pending quests, active quests, and summary
    """
    storage = CommitStorage()
    quest_manager = QuestManager(storage)

    return {
        "pending": quest_manager.get_prioritized_quests(status="pending", limit=5),
        "active": quest_manager.get_active_quests(),
        "summary": quest_manager.get_quest_summary(),
    }


@app.post("/api/quests")
def create_quest(quest: QuestCreate):
    """
    Create a new manual quest.

    Args:
        quest: QuestCreate with title and optional description

    Returns:
        JSON with the created quest
    """
    storage = CommitStorage()
    quest_manager = QuestManager(storage)

    created = quest_manager.add_manual_quest(
        title=quest.title,
        description=quest.description,
    )

    return {"quest": created}


@app.post("/api/quests/{quest_id}/accept")
def accept_quest(quest_id: int):
    """
    Accept a quest (mark as active).

    Args:
        quest_id: The quest ID

    Returns:
        JSON with the updated quest
    """
    storage = CommitStorage()
    quest_manager = QuestManager(storage)

    quest = quest_manager.accept_quest(quest_id)
    if not quest:
        raise HTTPException(status_code=404, detail="Quest not found")

    return {"quest": quest}


@app.post("/api/quests/{quest_id}/complete")
def complete_quest(quest_id: int):
    """
    Complete a quest.

    Args:
        quest_id: The quest ID

    Returns:
        JSON with the updated quest
    """
    storage = CommitStorage()
    quest_manager = QuestManager(storage)

    quest = quest_manager.complete_quest(quest_id)
    if not quest:
        raise HTTPException(status_code=404, detail="Quest not found")

    return {"quest": quest}


@app.post("/api/quests/{quest_id}/skip")
def skip_quest(quest_id: int, skip_data: QuestSkip | None = None):
    """
    Skip a quest with optional save-as-idea.

    Args:
        quest_id: The quest ID
        skip_data: Optional skip configuration

    Returns:
        JSON with skip result
    """
    storage = CommitStorage()
    quest_manager = QuestManager(storage)

    if skip_data is None:
        skip_data = QuestSkip()

    result = quest_manager.skip_quest(
        quest_id=quest_id,
        action=skip_data.action,
        save_as_idea=skip_data.save_as_idea,
    )

    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Quest not found"))

    return result


# Ideas API endpoints
@app.get("/api/ideas")
def get_ideas():
    """
    Get all active ideas.

    Returns:
        JSON with ideas list
    """
    storage = CommitStorage()
    ideas = storage.get_ideas(status="active")

    return {"ideas": ideas}


@app.post("/api/ideas")
def create_idea(idea: IdeaCreate):
    """
    Create a new idea (adds to both database and IDEAS.md).

    Args:
        idea: IdeaCreate with content

    Returns:
        JSON with the created idea
    """
    storage = CommitStorage()

    # Add to database
    idea_id = storage.create_idea(idea.content)

    # Add to IDEAS.md file
    add_idea(idea.content)

    created = storage.get_idea(idea_id)
    return {"idea": created}


@app.post("/api/ideas/{idea_id}/promote")
def promote_idea(idea_id: int):
    """
    Promote an idea to a quest.

    Args:
        idea_id: The idea ID

    Returns:
        JSON with the created quest
    """
    storage = CommitStorage()
    quest_manager = QuestManager(storage)

    quest = quest_manager.promote_idea_to_quest(idea_id)
    if not quest:
        raise HTTPException(status_code=404, detail="Idea not found")

    return {"quest": quest}


@app.post("/api/ideas/sync")
def sync_ideas():
    """
    Sync ideas between IDEAS.md and database.

    Returns:
        JSON with sync statistics
    """
    storage = CommitStorage()
    result = sync_ideas_to_db(storage)

    return result


@app.post("/api/quests/sync-github-issues")
def sync_github_issues():
    """
    Sync GitHub issues assigned to the user as quests.

    Fetches open issues assigned to the authenticated user and creates
    quests for any that don't already exist in the database.

    Returns:
        JSON with added and skipped counts
    """
    try:
        validate_config()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"Configuration error: {e}")

    client = GitHubClient(GITHUB_TOKEN, GITHUB_USERNAME)
    storage = CommitStorage()
    quest_manager = QuestManager(storage)

    try:
        issues = client.get_assigned_issues(state="open", per_page=50)
    except GitHubClientError as e:
        raise HTTPException(status_code=502, detail=str(e))

    result = quest_manager.sync_github_issues(issues)
    return result


@app.post("/api/quests/scan-todos")
def scan_todos():
    """
    Scan the project for TODO/FIXME comments and create quests.

    Scans Python files in the project directory for TODO, FIXME, HACK, and XXX
    comments and creates quests for any that don't already exist.

    Returns:
        JSON with added and skipped counts
    """
    project_root = Path(__file__).parent.parent
    todos = scan_directory(project_root)

    storage = CommitStorage()
    quest_manager = QuestManager(storage)

    result = quest_manager.sync_todo_comments(todos)
    return result


@app.post("/api/quests/discover-external")
def discover_external_issues():
    """
    Discover external contribution opportunities from starred repos.

    Fetches repos starred by the user, searches for issues labeled
    'good first issue' or 'help wanted', and creates quests from them.
    Results are cached for 24 hours to avoid API rate limiting.

    Returns:
        JSON with added and skipped counts, plus cache status
    """
    import json

    try:
        validate_config()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"Configuration error: {e}")

    storage = CommitStorage()
    quest_manager = QuestManager(storage)

    cache_key = "external_issues"
    cached_data = storage.get_cache(cache_key)

    if cached_data:
        # Use cached issues
        issues = json.loads(cached_data)
        result = quest_manager.sync_external_issues(issues)
        result["from_cache"] = True
        return result

    # Fetch fresh data from GitHub
    client = GitHubClient(GITHUB_TOKEN, GITHUB_USERNAME)

    try:
        # Get starred repos
        starred_repos = client.get_starred_repos(per_page=30)
        repo_names = [repo.get("full_name") for repo in starred_repos if repo.get("full_name")]

        if not repo_names:
            return {"added": 0, "skipped": 0, "from_cache": False, "message": "No starred repos found"}

        # Search for good first issues in starred repos
        issues = client.search_good_first_issues(repo_names, per_page=20)

        # Cache the results for 24 hours
        storage.set_cache(cache_key, json.dumps(issues), hours=24)

        # Sync to quests
        result = quest_manager.sync_external_issues(issues)
        result["from_cache"] = False
        result["repos_searched"] = len(repo_names)
        result["issues_found"] = len(issues)
        return result

    except GitHubClientError as e:
        raise HTTPException(status_code=502, detail=str(e))


# AI Enhancement API endpoints
@app.get("/api/ai/status")
def get_ai_status():
    """
    Check if AI features are configured and available.

    Returns:
        JSON with enabled status and message
    """
    storage = CommitStorage()
    quest_manager = QuestManager(storage)

    return quest_manager.get_ai_status()


@app.post("/api/quests/{quest_id}/enhance")
def enhance_quest(quest_id: int):
    """
    Enhance a single quest with AI-generated description and difficulty.

    Args:
        quest_id: The quest ID to enhance

    Returns:
        JSON with enhanced quest data or error message
    """
    storage = CommitStorage()
    quest_manager = QuestManager(storage)

    result = quest_manager.enhance_quest(quest_id)

    if not result.get("success"):
        error = result.get("error", "Enhancement failed")
        if "not found" in error.lower():
            raise HTTPException(status_code=404, detail=error)
        if "not configured" in error.lower():
            raise HTTPException(status_code=503, detail=error)
        if "rate limit" in error.lower():
            raise HTTPException(status_code=429, detail=error)
        raise HTTPException(status_code=500, detail=error)

    return result


@app.post("/api/quests/enhance-batch")
def enhance_batch(request: BatchEnhanceRequest | None = None):
    """
    Batch enhance pending quests without AI descriptions.

    Args:
        request: Optional BatchEnhanceRequest with limit (default 5, max 20)

    Returns:
        JSON with enhancement results and any errors
    """
    storage = CommitStorage()
    quest_manager = QuestManager(storage)

    limit = request.limit if request else 5

    result = quest_manager.enhance_pending_quests(limit=limit)

    if not result.get("success") and "not configured" in result.get("error", "").lower():
        raise HTTPException(status_code=503, detail=result.get("error"))

    return result
