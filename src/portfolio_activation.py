"""Portfolio activation health: roll up `portfolio_snapshots` for the dashboard.

Reads from the rows that `portfolio sweep` persists and produces the
"moved 5 repos from C to A in 30 days" feed plus a current grade distribution,
top movers, and a stale-projects list.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.storage import CommitStorage

_GRADE_ORDER = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
_STALE_DAYS = 30
_TOP_MOVERS = 3


def _grade_dist(rows: list[dict]) -> dict[str, int]:
    dist = {g: 0 for g in ("A", "B", "C", "D", "F")}
    for r in rows:
        g = r.get("grade") or "F"
        dist[g] = dist.get(g, 0) + 1
    return dist


def _direction(prev_grade: str, curr_grade: str) -> str:
    a = _GRADE_ORDER.get(prev_grade, 0)
    b = _GRADE_ORDER.get(curr_grade, 0)
    if b > a:
        return "up"
    if b < a:
        return "down"
    return "flat"


def compute_activation_health(
    storage: CommitStorage,
    days: int = 30,
    now: datetime | None = None,
) -> dict:
    """Build a dashboard-ready activation snapshot.

    `now` is injectable for tests. The baseline is the most recent snapshot per
    project strictly older than `now - days`, so on a daily sweep cadence the
    baseline is one day older than the requested window — close enough for the
    "in N days" headline.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff_iso = (now - timedelta(days=days)).isoformat(timespec="seconds")

    current_by_path = storage.get_latest_per_project()
    if not current_by_path:
        return {
            "available": False,
            "since_days": days,
            "as_of": None,
            "baseline_as_of": None,
            "project_count": 0,
            "grade_distribution": {g: 0 for g in ("A", "B", "C", "D", "F")},
            "movements": {"up": 0, "down": 0, "flat": 0, "new": 0},
            "headline": None,
            "top_movers_up": [],
            "top_movers_down": [],
            "stale": {"count": 0, "examples": []},
        }

    baseline_by_path = storage.get_latest_per_project(before=cutoff_iso)
    current_rows = list(current_by_path.values())

    movements = {"up": 0, "down": 0, "flat": 0, "new": 0}
    movers: list[dict] = []
    upward_buckets: dict[tuple[str, str], int] = {}

    for path, curr in current_by_path.items():
        prev = baseline_by_path.get(path)
        if prev is None:
            movements["new"] += 1
            continue
        direction = _direction(prev["grade"], curr["grade"])
        movements[direction] += 1
        score_delta = int(curr["score"]) - int(prev["score"])
        if direction != "flat" or score_delta != 0:
            movers.append(
                {
                    "name": curr["project_name"],
                    "path": path,
                    "grade_from": prev["grade"],
                    "grade_to": curr["grade"],
                    "score_from": int(prev["score"]),
                    "score_to": int(curr["score"]),
                    "score_delta": score_delta,
                    "direction": direction,
                }
            )
        if direction == "up" and prev["grade"] != curr["grade"]:
            key = (prev["grade"], curr["grade"])
            upward_buckets[key] = upward_buckets.get(key, 0) + 1

    headline = None
    if upward_buckets:
        # Tie-break: bucket count, then highest destination grade.
        (gfrom, gto), n = max(
            upward_buckets.items(),
            key=lambda kv: (kv[1], _GRADE_ORDER.get(kv[0][1], 0)),
        )
        plural = "s" if n != 1 else ""
        headline = f"Moved {n} repo{plural} from {gfrom} to {gto} in {days} days"

    top_movers_up = sorted(
        (m for m in movers if m["score_delta"] > 0),
        key=lambda m: m["score_delta"],
        reverse=True,
    )[:_TOP_MOVERS]
    top_movers_down = sorted(
        (m for m in movers if m["score_delta"] < 0),
        key=lambda m: m["score_delta"],
    )[:_TOP_MOVERS]

    stale_rows = [
        r for r in current_rows
        if r.get("days_since_last_commit") is not None
        and r["days_since_last_commit"] >= _STALE_DAYS
    ]
    stale_rows.sort(key=lambda r: r["days_since_last_commit"], reverse=True)
    stale_examples = [
        {
            "name": r["project_name"],
            "days_since_last_commit": r["days_since_last_commit"],
            "grade": r["grade"],
        }
        for r in stale_rows[:_TOP_MOVERS]
    ]

    latest_capture = max(r["captured_at"] for r in current_rows)

    return {
        "available": True,
        "since_days": days,
        "as_of": latest_capture,
        "baseline_as_of": cutoff_iso,
        "project_count": len(current_by_path),
        "grade_distribution": _grade_dist(current_rows),
        "movements": movements,
        "headline": headline,
        "top_movers_up": top_movers_up,
        "top_movers_down": top_movers_down,
        "stale": {"count": len(stale_rows), "examples": stale_examples},
    }


def render_activation_health(health: dict) -> None:
    """Print the activation panel to stdout in the dashboard's existing style."""
    print()
    print("Portfolio Activation Health")
    print("-" * 50)

    if not health["available"]:
        print("No portfolio snapshots yet.")
        print("Run `code-daily portfolio sweep` to populate.")
        return

    days = health["since_days"]
    print(f"As of: {health['as_of']}  |  Looking back {days} days")

    dist = health["grade_distribution"]
    dist_str = "  ".join(f"{g}:{dist[g]}" for g in ("A", "B", "C", "D", "F"))
    print(f"Grades ({health['project_count']} projects):  {dist_str}")

    m = health["movements"]
    print(
        f"Since baseline:  up:{m['up']}  down:{m['down']}  "
        f"flat:{m['flat']}  new:{m['new']}"
    )

    if health.get("headline"):
        print()
        print(f"  {health['headline']}")

    if health["top_movers_up"]:
        print()
        print("Top movers up:")
        for mv in health["top_movers_up"]:
            print(
                f"  ↑ {mv['name']}: {mv['grade_from']}→{mv['grade_to']} "
                f"(score {mv['score_from']}→{mv['score_to']}, "
                f"+{mv['score_delta']})"
            )

    if health["top_movers_down"]:
        print()
        print("Top movers down:")
        for mv in health["top_movers_down"]:
            print(
                f"  ↓ {mv['name']}: {mv['grade_from']}→{mv['grade_to']} "
                f"(score {mv['score_from']}→{mv['score_to']}, "
                f"{mv['score_delta']:+d})"
            )

    stale = health["stale"]
    if stale["count"]:
        print()
        proj_word = "project" if stale["count"] == 1 else "projects"
        print(
            f"Stale ({stale['count']} {proj_word}, "
            f"no commits in {_STALE_DAYS}+ days):"
        )
        for s in stale["examples"]:
            print(
                f"  - {s['name']}: {s['days_since_last_commit']}d "
                f"(grade {s['grade']})"
            )

    print()
