---
date: 2026-04-10
status: Ready to build
complexity: evening
tags: [spec, streak, analytics, cli-tooling]
---

# Streak Insights

Add a `code-daily streak insights` command that analyzes commit patterns across
all repos and surfaces actionable insights about coding habits.

## Motivation

The existing streak system shows current/longest streak and a heatmap. But it
doesn't answer questions like: "What time of day do I code most?", "Which repos
am I neglecting?", "Am I about to break my streak based on past patterns?"

Connected to r/SideProject pain point: "What's the hardest part of keeping a
side project alive after the initial excitement?" This command helps you see
the patterns so you can stay consistent.

## CLI Interface

```
code-daily streak insights [--json] [--days INT]
```

- `--days`: Analysis window (default: 90)
- `--json`: Structured output for agent consumption

## Data Source

Uses the existing `CommitStorage` and `get_commit_events_with_history()` from
`src/storage.py`. The commit events already have:

- `date` (YYYY-MM-DD)
- `repo` (owner/name)
- `commits` (list with sha + message)
- `commit_count`

The GitHub API events also include `created_at` timestamps which have hour
information. To get time-of-day data, we need to use the raw events from
`GitHubClient.get_user_events()` — these have full ISO timestamps.

## Insights Computed

### 1. Time-of-Day Distribution
Bucket commits into 4 time blocks based on `created_at` local time:
- Morning (6am-12pm)
- Afternoon (12pm-5pm)
- Evening (5pm-10pm)
- Night (10pm-6am)

Output: count per block, peak block label

### 2. Day-of-Week Distribution
Count commit days (not commits) per weekday. Identify:
- Strongest day (most consistent)
- Weakest day (most likely to skip)
- Weekend vs weekday ratio

### 3. Repo Activity Breakdown
Top repos by commit count in the analysis window:
- repo name, commit count, last commit date
- Identify "dormant" repos (committed to in window but not in last 14 days)
- Identify "active" repos (committed to in last 7 days)

### 4. Streak Patterns
From the streak calculator's commit_dates:
- All streaks found (start, end, length)
- Average streak length
- Median streak length
- Streak killer: which day-of-week most often ends streaks

### 5. Streak Risk
Based on current state and patterns:
- Hours until streak breaks (midnight tonight if not committed, or midnight
  tomorrow if already committed today)
- Historical break rate: what % of days at this streak length did you break?
- Risk level: low/medium/high

## Output Structure

```python
{
    "period": {"start": "2026-01-10", "end": "2026-04-10", "days": 90},
    "time_of_day": {
        "morning": 12, "afternoon": 8, "evening": 45, "night": 18,
        "peak": "evening"
    },
    "day_of_week": {
        "monday": 11, "tuesday": 10, ...,
        "strongest": "wednesday",
        "weakest": "sunday",
        "weekday_pct": 72.5
    },
    "repos": {
        "top": [
            {"repo": "code-daily", "commits": 28, "last_commit": "2026-04-10", "status": "active"},
            ...
        ],
        "active_count": 5,
        "dormant_count": 3
    },
    "streak_patterns": {
        "all_streaks": [{"start": "...", "end": "...", "length": 7}, ...],
        "average_length": 4.2,
        "median_length": 3,
        "streak_killer_day": "sunday",
        "total_streaks": 12
    },
    "risk": {
        "hours_remaining": 6.5,
        "historical_break_rate": 0.15,
        "level": "low"
    }
}
```

## Human Output

```
=== Streak Insights (last 90 days) ===

⏰ Peak coding time: Evening (5pm-10pm) — 54% of commits
   Morning: ██░░ 14%  |  Afternoon: █░░░ 10%
   Evening: █████ 54% |  Night: ██░░ 22%

📅 Strongest day: Wednesday  |  Weakest: Sunday
   Mon ██░ Tue ██░ Wed ███ Thu ██░ Fri ██░ Sat █░░ Sun █░░
   Weekdays: 73% of commit days

📦 Active repos: 5  |  Dormant: 3
   code-daily        28 commits (last: today)
   advancement-codex 14 commits (last: today)
   workout-app        9 commits (last: 2d ago)
   ...

📊 Streak patterns: 12 streaks, avg 4.2 days, median 3
   Longest: 18 days  |  Streak killer: Sunday

🛡️ Streak risk: LOW
   6.5 hours until deadline  |  Historical break rate at day 8: 15%
```

## Source Module

**New file**: `src/streak_insights.py`

```python
def compute_time_distribution(events: list[dict]) -> dict:
    """Bucket raw GitHub events by local time-of-day."""

def compute_day_distribution(commit_dates: list[str]) -> dict:
    """Count commit days per weekday."""

def compute_repo_breakdown(commit_events: list[dict], days: int) -> dict:
    """Top repos by commit count with active/dormant status."""

def compute_streak_patterns(commit_dates: list[str]) -> dict:
    """Find all streaks, averages, and streak-killer day."""

def compute_streak_risk(streak_info: dict, commit_dates: list[str]) -> dict:
    """Assess current streak risk based on historical patterns."""

def compute_insights(
    events: list[dict],
    commit_events: list[dict],
    streak_info: dict,
    days: int = 90,
) -> dict:
    """Main entry point: compute all insights.

    Args:
        events: Raw GitHub API events (with created_at timestamps)
        commit_events: Parsed commit events (from commit_parser)
        streak_info: Current streak data (from streak_calculator)
        days: Analysis window

    Returns:
        Full insights dict
    """
```

## CLI Registration

In `typer_cli.py`, add to the existing `streak_app`:

```python
@streak_app.command("insights")
def streak_insights(
    json_output: bool = typer.Option(False, "--json"),
    days: int = typer.Option(90, help="Analysis window in days"),
):
```

This follows the same pattern as `streak show` — calls `GitHubClient`,
`get_commit_events_with_history()`, `calculate_streak()`, then passes
everything to `compute_insights()`.

## Tests

Test in `tests/test_streak_insights.py`:

- `test_time_distribution_buckets` — events at known hours land in correct buckets
- `test_day_distribution` — commit dates produce correct weekday counts
- `test_repo_breakdown_active_dormant` — repos classified correctly by recency
- `test_streak_patterns_finds_all` — known date sequences produce correct streaks
- `test_streak_patterns_killer_day` — identifies correct day-of-week
- `test_streak_risk_low` — committed today, long history → low
- `test_streak_risk_high` — not committed, late in day, short history → high
- `test_compute_insights_integration` — full pipeline with mock data
