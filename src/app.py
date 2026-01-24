"""
FastAPI web application for code-daily.

Provides REST API endpoints for streak and stats data.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.config import GITHUB_TOKEN, GITHUB_USERNAME, validate_config
from src.github_client import GitHubClient, GitHubClientError
from src.commit_parser import parse_commit_events
from src.streak_calculator import calculate_streak
from src.stats_calculator import calculate_stats

app = FastAPI(
    title="code-daily",
    description="A gamified coding habit tracker",
    version="0.1.0",
)

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


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

    # Create client and fetch events
    client = GitHubClient(GITHUB_TOKEN, GITHUB_USERNAME)

    try:
        events = client.get_user_events(per_page=100)
    except GitHubClientError as e:
        raise HTTPException(status_code=502, detail=str(e))

    # Parse commit events
    commit_events = parse_commit_events(events)

    # Calculate streak and stats
    streak_info = calculate_streak(commit_events)
    stats = calculate_stats(commit_events)

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
        "commit_dates": streak_info["commit_dates"],
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """Render the dashboard page."""
    data = _fetch_stats_data()
    return templates.TemplateResponse(request, "index.html", data)


@app.get("/api/stats")
def get_stats():
    """
    Get current streak and commit statistics.

    Returns:
        JSON with streak info and commit stats
    """
    return _fetch_stats_data()
