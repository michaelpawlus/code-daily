"""
Analyze commit patterns and surface actionable insights about coding habits.
"""

from collections import Counter
from datetime import datetime, timedelta
from statistics import median


def compute_time_distribution(events: list[dict]) -> dict:
    """Bucket raw GitHub events by local time-of-day.

    Args:
        events: Raw GitHub API events with created_at timestamps.

    Returns:
        Dict with morning/afternoon/evening/night counts and peak label.
    """
    buckets = {"morning": 0, "afternoon": 0, "evening": 0, "night": 0}

    for event in events:
        if event.get("type") != "PushEvent":
            continue
        created_at = event.get("created_at", "")
        if not created_at:
            continue
        utc_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        local_dt = utc_dt.astimezone()
        hour = local_dt.hour

        if 6 <= hour < 12:
            buckets["morning"] += 1
        elif 12 <= hour < 17:
            buckets["afternoon"] += 1
        elif 17 <= hour < 22:
            buckets["evening"] += 1
        else:
            buckets["night"] += 1

    peak = max(buckets, key=buckets.get) if any(buckets.values()) else "morning"
    return {**buckets, "peak": peak}


def compute_day_distribution(commit_dates: list[str]) -> dict:
    """Count commit days per weekday.

    Args:
        commit_dates: List of YYYY-MM-DD date strings.

    Returns:
        Dict with per-day counts, strongest/weakest day, and weekday percentage.
    """
    day_names = [
        "monday", "tuesday", "wednesday", "thursday",
        "friday", "saturday", "sunday",
    ]
    counts = Counter()

    for date_str in commit_dates:
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            counts[day_names[dt.weekday()]] += 1
        except ValueError:
            continue

    result = {name: counts.get(name, 0) for name in day_names}

    if any(result.values()):
        strongest = max(day_names, key=lambda d: result[d])
        weakest = min(day_names, key=lambda d: result[d])
        weekday_total = sum(result[d] for d in day_names[:5])
        total = sum(result.values())
        weekday_pct = round(weekday_total / total * 100, 1) if total else 0.0
    else:
        strongest = "monday"
        weakest = "monday"
        weekday_pct = 0.0

    result["strongest"] = strongest
    result["weakest"] = weakest
    result["weekday_pct"] = weekday_pct
    return result


def compute_repo_breakdown(commit_events: list[dict], days: int) -> dict:
    """Top repos by commit count with active/dormant status.

    Args:
        commit_events: Parsed commit events with date, repo, commit_count.
        days: Analysis window in days.

    Returns:
        Dict with top repos list, active_count, and dormant_count.
    """
    today = datetime.now().date()
    cutoff = today - timedelta(days=days)

    repo_stats: dict[str, dict] = {}
    for event in commit_events:
        date_str = event.get("date", "")
        if date_str == "unknown":
            continue
        try:
            event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if event_date < cutoff:
            continue

        repo = event.get("repo", "unknown")
        if repo not in repo_stats:
            repo_stats[repo] = {"commits": 0, "last_commit": date_str}
        repo_stats[repo]["commits"] += event.get("commit_count", 1)
        if date_str > repo_stats[repo]["last_commit"]:
            repo_stats[repo]["last_commit"] = date_str

    top = []
    active_count = 0
    dormant_count = 0
    active_cutoff = today - timedelta(days=7)
    dormant_cutoff = today - timedelta(days=14)

    for repo, stats in sorted(
        repo_stats.items(), key=lambda x: x[1]["commits"], reverse=True
    ):
        last = datetime.strptime(stats["last_commit"], "%Y-%m-%d").date()
        if last >= active_cutoff:
            status = "active"
            active_count += 1
        elif last < dormant_cutoff:
            status = "dormant"
            dormant_count += 1
        else:
            status = "recent"

        top.append({
            "repo": repo,
            "commits": stats["commits"],
            "last_commit": stats["last_commit"],
            "status": status,
        })

    return {"top": top, "active_count": active_count, "dormant_count": dormant_count}


def compute_streak_patterns(commit_dates: list[str]) -> dict:
    """Find all streaks, averages, and streak-killer day.

    Args:
        commit_dates: Sorted descending list of unique YYYY-MM-DD date strings.

    Returns:
        Dict with all_streaks, average_length, median_length,
        streak_killer_day, and total_streaks.
    """
    if not commit_dates:
        return {
            "all_streaks": [],
            "average_length": 0,
            "median_length": 0,
            "streak_killer_day": None,
            "total_streaks": 0,
        }

    # Sort ascending for easier streak detection
    sorted_dates = sorted(
        commit_dates,
        key=lambda d: datetime.strptime(d, "%Y-%m-%d"),
    )

    streaks = []
    streak_start = sorted_dates[0]
    streak_len = 1
    prev_date = datetime.strptime(sorted_dates[0], "%Y-%m-%d").date()

    for date_str in sorted_dates[1:]:
        current_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        if current_date - prev_date == timedelta(days=1):
            streak_len += 1
        else:
            streaks.append({
                "start": streak_start,
                "end": prev_date.strftime("%Y-%m-%d"),
                "length": streak_len,
            })
            streak_start = date_str
            streak_len = 1
        prev_date = current_date

    # Final streak
    streaks.append({
        "start": streak_start,
        "end": prev_date.strftime("%Y-%m-%d"),
        "length": streak_len,
    })

    lengths = [s["length"] for s in streaks]
    avg_length = round(sum(lengths) / len(lengths), 1) if lengths else 0
    med_length = int(median(lengths)) if lengths else 0

    # Streak killer: day-of-week that most often follows the end of a streak
    # (the day after the last day of a streak, where the user didn't commit)
    killer_counts: Counter = Counter()
    for s in streaks:
        end_date = datetime.strptime(s["end"], "%Y-%m-%d").date()
        break_day = end_date + timedelta(days=1)
        day_names = [
            "monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday",
        ]
        killer_counts[day_names[break_day.weekday()]] += 1

    streak_killer = killer_counts.most_common(1)[0][0] if killer_counts else None

    return {
        "all_streaks": streaks,
        "average_length": avg_length,
        "median_length": med_length,
        "streak_killer_day": streak_killer,
        "total_streaks": len(streaks),
    }


def compute_streak_risk(streak_info: dict, commit_dates: list[str]) -> dict:
    """Assess current streak risk based on historical patterns.

    Args:
        streak_info: Output from calculate_streak() with current_streak,
            streak_active, etc.
        commit_dates: All unique commit dates (sorted descending).

    Returns:
        Dict with hours_remaining, historical_break_rate, and level.
    """
    now = datetime.now()
    midnight = now.replace(hour=23, minute=59, second=59)
    hours_remaining = round((midnight - now).total_seconds() / 3600, 1)

    current = streak_info.get("current_streak", 0)
    active = streak_info.get("streak_active", False)

    if active:
        # Already committed today, streak is safe until tomorrow midnight
        tomorrow_midnight = midnight + timedelta(days=1)
        hours_remaining = round(
            (tomorrow_midnight - now).total_seconds() / 3600, 1
        )

    # Historical break rate: what fraction of streaks at this length broke?
    if current == 0:
        historical_break_rate = 1.0
    else:
        # Count how many streaks reached at least this length
        # and how many broke at exactly this length
        sorted_dates = sorted(
            commit_dates,
            key=lambda d: datetime.strptime(d, "%Y-%m-%d"),
        )
        if len(sorted_dates) < 2:
            historical_break_rate = 0.0
        else:
            # Build all historical streaks
            streak_lengths = []
            slen = 1
            prev = datetime.strptime(sorted_dates[0], "%Y-%m-%d").date()
            for ds in sorted_dates[1:]:
                cur = datetime.strptime(ds, "%Y-%m-%d").date()
                if cur - prev == timedelta(days=1):
                    slen += 1
                else:
                    streak_lengths.append(slen)
                    slen = 1
                prev = cur
            streak_lengths.append(slen)

            reached = sum(1 for sl in streak_lengths if sl >= current)
            broke_at = sum(1 for sl in streak_lengths if sl == current)
            historical_break_rate = round(
                broke_at / reached, 2
            ) if reached > 0 else 0.0

    # Risk level
    if active and historical_break_rate < 0.3:
        level = "low"
    elif not active and hours_remaining < 4:
        level = "high"
    elif not active:
        level = "medium"
    elif historical_break_rate >= 0.5:
        level = "medium"
    else:
        level = "low"

    return {
        "hours_remaining": hours_remaining,
        "historical_break_rate": historical_break_rate,
        "level": level,
    }


def compute_insights(
    events: list[dict],
    commit_events: list[dict],
    streak_info: dict,
    days: int = 90,
) -> dict:
    """Compute all streak insights.

    Args:
        events: Raw GitHub API events (with created_at timestamps).
        commit_events: Parsed commit events (from commit_parser).
        streak_info: Current streak data (from streak_calculator).
        days: Analysis window.

    Returns:
        Full insights dict with period, time_of_day, day_of_week,
        repos, streak_patterns, and risk sections.
    """
    today = datetime.now().date()
    start = today - timedelta(days=days)
    commit_dates = streak_info.get("commit_dates", [])

    # Filter commit_dates to the analysis window
    window_dates = [
        d for d in commit_dates
        if d >= start.strftime("%Y-%m-%d")
    ]

    return {
        "period": {
            "start": start.strftime("%Y-%m-%d"),
            "end": today.strftime("%Y-%m-%d"),
            "days": days,
        },
        "time_of_day": compute_time_distribution(events),
        "day_of_week": compute_day_distribution(window_dates),
        "repos": compute_repo_breakdown(commit_events, days),
        "streak_patterns": compute_streak_patterns(window_dates),
        "risk": compute_streak_risk(streak_info, commit_dates),
    }
