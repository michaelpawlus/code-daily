"""
Typer-based CLI for code-daily.

Provides commands for GitHub issues, Obsidian vault scanning,
suggestion engine, dashboard, notifications, and cron setup.
Every output command supports --json for agent orchestration.
"""

import json
import os
import sys
from dataclasses import asdict
from typing import Optional

import typer

app = typer.Typer(help="code-daily: A gamified coding habit tracker")
issues_app = typer.Typer(help="GitHub issues commands")
vault_app = typer.Typer(help="Obsidian vault commands")
notify_app = typer.Typer(help="Notification commands")
news_app = typer.Typer(help="AI news commands")
streak_app = typer.Typer(help="Streak tracking commands")
ideas_app = typer.Typer(help="Project idea generation commands")
quests_app = typer.Typer(help="Quest management commands")
achievements_app = typer.Typer(help="Achievement tracking commands")
routines_app = typer.Typer(help="Claude Code Routines migration commands")
app.add_typer(issues_app, name="issues")
app.add_typer(vault_app, name="vault")
app.add_typer(notify_app, name="notify")
app.add_typer(news_app, name="news")
app.add_typer(streak_app, name="streak")
app.add_typer(ideas_app, name="ideas")
app.add_typer(quests_app, name="quests")
app.add_typer(achievements_app, name="achievements")
app.add_typer(routines_app, name="routines")


def _output(data, as_json: bool, human_fn=None):
    """Output data as JSON to stdout or human-readable to stderr+stdout."""
    if as_json:
        print(json.dumps(data, indent=2, default=str))
    elif human_fn:
        human_fn(data)
    else:
        print(json.dumps(data, indent=2, default=str))


# ---------------------------------------------------------------------------
# issues subcommands
# ---------------------------------------------------------------------------


@issues_app.command("list")
def issues_list(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    labels: Optional[str] = typer.Option(None, help="Comma-separated label filter"),
    repo: Optional[str] = typer.Option(None, help="Filter to repo (owner/name)"),
    limit: int = typer.Option(30, help="Max issues to fetch"),
):
    """List open GitHub issues assigned to you."""
    from src.gh_issues import check_gh_auth, get_assigned_issues

    auth = check_gh_auth()
    if not auth["authenticated"]:
        if json_output:
            print(json.dumps({"error": auth["message"], "code": 1}))
        else:
            print(auth["message"], file=sys.stderr)
        raise typer.Exit(1)

    issues = get_assigned_issues(limit=limit, labels=labels, repo=repo)
    data = [asdict(iss) for iss in issues]

    def _human(d):
        if not d:
            print("No issues assigned to you.")
            return
        print(f"Found {len(d)} assigned issues:\n")
        for item in d:
            labels_str = ", ".join(item.get("labels", []))
            label_suffix = f"  [{labels_str}]" if labels_str else ""
            print(f"  #{item['number']}  {item['title']}{label_suffix}")
            print(f"         {item['url']}")

    _output(data, json_output, _human)


@issues_app.command("top")
def issues_top(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show top prioritized GitHub issues."""
    from src.gh_issues import check_gh_auth, get_assigned_issues, prioritize_issues

    auth = check_gh_auth()
    if not auth["authenticated"]:
        if json_output:
            print(json.dumps({"error": auth["message"], "code": 1}))
        else:
            print(auth["message"], file=sys.stderr)
        raise typer.Exit(1)

    issues = get_assigned_issues()
    ranked = prioritize_issues(issues)[:10]
    data = [{"score": r["score"], **asdict(r["issue"])} for r in ranked]

    def _human(d):
        if not d:
            print("No issues to prioritize.")
            return
        print("Top prioritized issues:\n")
        for i, item in enumerate(d, 1):
            print(f"  {i}. [{item['score']}pts] #{item['number']}  {item['title']}")
            print(f"     {item['url']}")

    _output(data, json_output, _human)


# ---------------------------------------------------------------------------
# vault subcommands
# ---------------------------------------------------------------------------


def _get_vault_path() -> str:
    """Resolve the Obsidian vault path from env."""
    path = os.environ.get("OBSIDIAN_VAULT_PATH", "")
    if not path:
        print("OBSIDIAN_VAULT_PATH not set.", file=sys.stderr)
        raise typer.Exit(2)
    return path


@vault_app.command("scan")
def vault_scan(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    since: int = typer.Option(7, help="Days back to scan daily notes"),
    folders: Optional[str] = typer.Option(None, help="Comma-separated folder names"),
    search: Optional[str] = typer.Option(None, help="Filter items by text"),
):
    """Scan Obsidian vault for actionable items."""
    from src.obsidian_scanner import scan_vault

    vault_path = _get_vault_path()
    folder_list = [f.strip() for f in folders.split(",")] if folders else None
    items = scan_vault(vault_path, since=since, folders=folder_list, search=search)
    data = [asdict(it) for it in items]

    def _human(d):
        if not d:
            print("No actionable items found in vault.")
            return
        print(f"Found {len(d)} items:\n")
        for item in d:
            prefix = {"todo": "[ ]", "project_idea": "***", "bullet": " - "}
            marker = prefix.get(item["item_type"], " - ")
            ctx = f"  ({item['context']})" if item["context"] else ""
            date_str = f"  [{item['date']}]" if item["date"] else ""
            print(f"  {marker} {item['content']}{ctx}{date_str}")

    _output(data, json_output, _human)


@vault_app.command("ideas")
def vault_ideas(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List project ideas from Obsidian vault."""
    from src.obsidian_scanner import scan_project_ideas

    vault_path = _get_vault_path()
    items = scan_project_ideas(vault_path)
    data = [asdict(it) for it in items]

    def _human(d):
        if not d:
            print("No project ideas found in vault.")
            return
        print(f"Found {len(d)} project ideas:\n")
        for item in d:
            print(f"  *** {item['content']}")
            print(f"      {item['source_file']}")

    _output(data, json_output, _human)


# ---------------------------------------------------------------------------
# streak subcommands
# ---------------------------------------------------------------------------


@streak_app.command("show")
def streak_show(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show your current streak status with motivational context."""
    from src.config import GITHUB_TOKEN, GITHUB_USERNAME, validate_config
    from src.github_client import GitHubClient, GitHubClientError
    from src.storage import CommitStorage, get_commit_events_with_history
    from src.streak_calculator import calculate_streak

    try:
        validate_config()
    except ValueError as e:
        if json_output:
            print(json.dumps({"error": str(e), "code": 1}))
        else:
            print(str(e), file=sys.stderr)
        raise typer.Exit(1)

    client = GitHubClient(GITHUB_TOKEN, GITHUB_USERNAME)
    storage = CommitStorage()

    try:
        commit_events = get_commit_events_with_history(client, storage)
    except GitHubClientError as e:
        if json_output:
            print(json.dumps({"error": str(e), "code": 1}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        raise typer.Exit(1)

    streak_info = calculate_streak(commit_events) if commit_events else {
        "current_streak": 0, "longest_streak": 0,
        "streak_active": False, "last_commit_date": None, "commit_dates": [],
    }

    current = streak_info["current_streak"]
    longest = streak_info["longest_streak"]
    active = streak_info["streak_active"]
    days_to_record = max(0, longest - current + 1) if current < longest else 0
    is_record = current >= longest and current > 0

    data = {
        "current_streak": current,
        "longest_streak": longest,
        "streak_active": active,
        "last_commit_date": streak_info["last_commit_date"],
        "days_to_record": days_to_record,
        "is_record": is_record,
    }

    def _human(d):
        cur = d["current_streak"]
        lng = d["longest_streak"]
        act = d["streak_active"]

        # Streak flame display
        if cur == 0:
            print("  No active streak. Today is day 1 if you commit!")
        else:
            flame = "🔥" * min(cur, 10)
            print(f"  {flame} {cur}-day streak")

        print()

        # Active status
        if act:
            print("  ✅ You've committed today. Streak is safe!")
        else:
            print("  ⏳ No commit yet today. Your streak needs you!")

        print()

        # Record context
        if d["is_record"]:
            print(f"  🏆 You're at your all-time record! Keep going!")
        elif d["days_to_record"] > 0:
            print(f"  📊 Longest streak: {lng} days ({d['days_to_record']} more to beat it)")
        else:
            print(f"  📊 Longest streak: {lng} days")

        if d["last_commit_date"]:
            print(f"  📅 Last commit: {d['last_commit_date']}")

    _output(data, json_output, _human)


@streak_app.command("race")
def streak_race(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show a visual race toward your all-time streak record."""
    from datetime import datetime, timedelta

    from src.config import GITHUB_TOKEN, GITHUB_USERNAME, validate_config
    from src.github_client import GitHubClient, GitHubClientError
    from src.storage import CommitStorage, get_commit_events_with_history
    from src.streak_calculator import calculate_streak

    try:
        validate_config()
    except ValueError as e:
        if json_output:
            print(json.dumps({"error": str(e), "code": 1}))
        else:
            print(str(e), file=sys.stderr)
        raise typer.Exit(1)

    client = GitHubClient(GITHUB_TOKEN, GITHUB_USERNAME)
    storage = CommitStorage()

    try:
        commit_events = get_commit_events_with_history(client, storage)
    except GitHubClientError as e:
        if json_output:
            print(json.dumps({"error": str(e), "code": 1}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        raise typer.Exit(1)

    streak_info = calculate_streak(commit_events) if commit_events else {
        "current_streak": 0, "longest_streak": 0,
        "streak_active": False, "last_commit_date": None, "commit_dates": [],
    }

    current = streak_info["current_streak"]
    longest = streak_info["longest_streak"]
    active = streak_info["streak_active"]
    days_to_record = max(0, longest - current + 1) if current < longest else 0
    is_record = current >= longest and current > 0

    today = datetime.now().date()
    projected_record_date = (
        str(today + timedelta(days=days_to_record)) if days_to_record > 0 else None
    )

    # Progress as fraction of the record (cap at 1.0 once record is met/beaten)
    progress = current / longest if longest > 0 else 0.0
    progress = min(progress, 1.0)

    data = {
        "current_streak": current,
        "longest_streak": longest,
        "streak_active": active,
        "days_to_record": days_to_record,
        "is_record": is_record,
        "progress": round(progress, 3),
        "projected_record_date": projected_record_date,
    }

    def _human(d):
        cur = d["current_streak"]
        lng = d["longest_streak"]
        pct = d["progress"]
        dtr = d["days_to_record"]

        print("  === STREAK RACE ===\n")

        if cur == 0:
            print("  No active streak. Commit today to start the race!")
            print(f"  Record to beat: {lng} days")
            return

        # Progress bar: 30 chars wide
        bar_width = 30
        filled = int(pct * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        pct_display = int(pct * 100)

        print(f"  [{bar}] {pct_display}%")
        print(f"  Day {cur} of {lng}\n")

        if d["is_record"]:
            lead = cur - lng + 1 if cur > lng else 0
            if lead > 0:
                print(f"  🏆 NEW RECORD! You're {lead} day{'s' if lead != 1 else ''} past your old record!")
            else:
                print("  🏆 You've TIED your record! One more day to break it!")
        else:
            print(f"  {dtr} day{'s' if dtr != 1 else ''} to beat your record")
            if d["projected_record_date"]:
                print(f"  Record-break date: {d['projected_record_date']}")

        print()
        if d["streak_active"]:
            print("  ✅ Today's commit is in. See you tomorrow.")
        else:
            print("  ⏳ No commit yet today — don't break the chain!")

    _output(data, json_output, _human)


@streak_app.command("history")
def streak_history(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    days: int = typer.Option(30, help="Number of days to show"),
):
    """Show recent notification history and streak activity."""
    from src.storage import CommitStorage

    storage = CommitStorage()
    notifications = storage.get_notification_history(limit=days)

    data = {"notifications": notifications, "count": len(notifications)}

    def _human(d):
        if not d["notifications"]:
            print("No notifications sent yet.")
            print("Run 'code-daily cron --install' to set up daily reminders.")
            return
        print(f"Last {d['count']} notifications:\n")
        for n in d["notifications"]:
            level_icon = {1: "🌅", 2: "☀️", 3: "🌆", 4: "🚨"}.get(n["level"], "?")
            print(f"  {level_icon} [{n['date']}] L{n['level']} via {n['channel']}: {n['message'][:60]}...")

    _output(data, json_output, _human)


@streak_app.command("insights")
def streak_insights(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    days: int = typer.Option(90, help="Analysis window in days"),
):
    """Analyze commit patterns and surface actionable insights."""
    from src.config import GITHUB_TOKEN, GITHUB_USERNAME, validate_config
    from src.github_client import GitHubClient, GitHubClientError
    from src.storage import CommitStorage, get_commit_events_with_history
    from src.streak_calculator import calculate_streak
    from src.streak_insights import compute_insights

    try:
        validate_config()
    except ValueError as e:
        if json_output:
            print(json.dumps({"error": str(e), "code": 1}))
        else:
            print(str(e), file=sys.stderr)
        raise typer.Exit(1)

    client = GitHubClient(GITHUB_TOKEN, GITHUB_USERNAME)
    storage = CommitStorage()

    try:
        raw_events = client.get_user_events(per_page=100)
        commit_events = get_commit_events_with_history(client, storage)
    except GitHubClientError as e:
        if json_output:
            print(json.dumps({"error": str(e), "code": 1}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        raise typer.Exit(1)

    streak_info = calculate_streak(commit_events) if commit_events else {
        "current_streak": 0, "longest_streak": 0,
        "streak_active": False, "last_commit_date": None, "commit_dates": [],
    }

    data = compute_insights(raw_events, commit_events, streak_info, days=days)

    def _human(d):
        period = d["period"]
        print(f"=== Streak Insights (last {period['days']} days) ===\n")

        # Time of day
        tod = d["time_of_day"]
        total = tod["morning"] + tod["afternoon"] + tod["evening"] + tod["night"]
        if total > 0:
            def _bar(n):
                pct = n / total * 100
                blocks = round(pct / 20)
                return "\u2588" * blocks + "\u2591" * (5 - blocks)

            def _pct(n):
                return f"{n / total * 100:.0f}%"

            print(f"  \u23f0 Peak coding time: {tod['peak'].title()} — {_pct(tod[tod['peak']])} of commits")
            print(f"     Morning: {_bar(tod['morning'])} {_pct(tod['morning'])}  |  Afternoon: {_bar(tod['afternoon'])} {_pct(tod['afternoon'])}")
            print(f"     Evening: {_bar(tod['evening'])} {_pct(tod['evening'])}  |  Night: {_bar(tod['night'])} {_pct(tod['night'])}")
        else:
            print("  \u23f0 No time-of-day data (need raw API events)")
        print()

        # Day of week
        dow = d["day_of_week"]
        day_abbr = {"monday": "Mon", "tuesday": "Tue", "wednesday": "Wed",
                    "thursday": "Thu", "friday": "Fri", "saturday": "Sat", "sunday": "Sun"}
        day_names = list(day_abbr.keys())
        max_day = max((dow[dn] for dn in day_names), default=1) or 1
        bars = "   ".join(
            f"{day_abbr[dn]} {'█' * max(1, round(dow[dn] / max_day * 3))}"
            + "░" * (3 - max(1, round(dow[dn] / max_day * 3)))
            for dn in day_names
        )
        print(f"  📅 Strongest day: {dow['strongest'].title()}  |  Weakest: {dow['weakest'].title()}")
        print(f"     {bars}")
        print(f"     Weekdays: {dow['weekday_pct']}% of commit days")
        print()

        # Repos
        repos = d["repos"]
        print(f"  📦 Active repos: {repos['active_count']}  |  Dormant: {repos['dormant_count']}")
        for r in repos["top"][:5]:
            print(f"     {r['repo']:<30s} {r['commits']:>3d} commits (last: {r['last_commit']})")
        if len(repos["top"]) > 5:
            print(f"     ... and {len(repos['top']) - 5} more")
        print()

        # Streak patterns
        sp = d["streak_patterns"]
        if sp["total_streaks"] > 0:
            longest = max((s["length"] for s in sp["all_streaks"]), default=0)
            print(f"  📊 Streak patterns: {sp['total_streaks']} streaks, avg {sp['average_length']} days, median {sp['median_length']}")
            killer = sp['streak_killer_day'].title() if sp['streak_killer_day'] else 'N/A'
            print(f"     Longest: {longest} days  |  Streak killer: {killer}")
        else:
            print("  📊 No streak patterns found in this period")
        print()

        # Risk
        risk = d["risk"]
        level_icon = {"low": "🛡️", "medium": "⚠️", "high": "🚨"}.get(risk["level"], "?")
        print(f"  {level_icon} Streak risk: {risk['level'].upper()}")
        print(f"     {risk['hours_remaining']}h until deadline  |  Historical break rate at day {streak_info['current_streak']}: {risk['historical_break_rate']:.0%}")

    _output(data, json_output, _human)


# ---------------------------------------------------------------------------
# suggest command
# ---------------------------------------------------------------------------


@app.command()
def suggest(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Suggest the best thing to work on next, combining all sources."""
    import hashlib

    from src.gh_issues import get_assigned_issues, prioritize_issues
    from src.obsidian_scanner import scan_vault
    from src.storage import CommitStorage

    storage = CommitStorage()
    recent_domains = storage.get_recent_suggestion_domains(days=30)

    candidates: list[dict] = []

    # GitHub issues
    try:
        issues = get_assigned_issues(limit=20)
        ranked = prioritize_issues(issues)
        for r in ranked:
            iss = r["issue"]
            score = r["score"]
            candidates.append({
                "source": "github",
                "title": f"#{iss.number} {iss.title}",
                "url": iss.url,
                "score": score,
                "reason": _issue_reason(iss, score),
                "domain": iss.repo if hasattr(iss, "repo") else None,
            })
    except Exception:
        pass

    # Obsidian vault
    vault_path = os.environ.get("OBSIDIAN_VAULT_PATH", "")
    if vault_path:
        try:
            items = scan_vault(vault_path, since=3)
            for item in items:
                score = _score_obsidian_item(item)
                domain = item.context.lower() if item.context else None
                candidates.append({
                    "source": "obsidian",
                    "title": item.content,
                    "url": item.source_file,
                    "score": score,
                    "reason": _obsidian_reason(item, score),
                    "domain": domain,
                })
        except Exception:
            pass

    # Cross-source variety bonus
    sources_present = {c["source"] for c in candidates}
    if len(sources_present) > 1:
        for c in candidates:
            c["score"] += 3

    # Freshness: penalize recently-suggested ideas, reward domain diversity
    for c in candidates:
        content_hash = hashlib.sha256(
            c["title"].strip().lower().encode()
        ).hexdigest()[:16]
        c["_content_hash"] = content_hash

        freq = storage.get_suggestion_frequency(content_hash, days=14)
        if freq > 0:
            c["score"] -= 3 * freq

        domain = c.get("domain")
        if domain and domain not in recent_domains:
            c["score"] += 3

    candidates.sort(key=lambda c: c["score"], reverse=True)
    top = candidates[:5]

    # Log suggestions for future freshness tracking
    for c in top:
        try:
            storage.log_suggestion(c["source"], c["title"], c.get("domain"))
        except Exception:
            pass

    # Clean internal fields before output
    for c in top:
        c.pop("_content_hash", None)
        c.pop("domain", None)

    def _human(d):
        if not d:
            print("No suggestions available. Assign yourself some issues or add vault TODOs!")
            return
        print("Top suggestions:\n")
        for i, item in enumerate(d, 1):
            print(f"  {i}. [{item['score']}pts] {item['title']}")
            print(f"     Source: {item['source']}  |  {item['reason']}")
            if item.get("url"):
                print(f"     {item['url']}")
            print()

    _output(top, json_output, _human)


def _issue_reason(issue, score: int) -> str:
    lower_labels = {lb.lower() for lb in issue.labels}
    if {"bug", "critical", "urgent", "p0", "p1"} & lower_labels:
        return "Bug/urgent issue needs attention"
    if score >= 5:
        return "High priority based on age and activity"
    return "Open issue assigned to you"


def _score_obsidian_item(item) -> int:
    score = 0
    ctx_lower = item.context.lower() if item.context else ""
    if "priorities" in ctx_lower or "important" in ctx_lower:
        score += 4
    if item.item_type == "project_idea":
        score += 2
    if item.item_type == "todo":
        score += 2
    if item.date:
        from datetime import datetime, timedelta

        try:
            d = datetime.strptime(item.date, "%Y-%m-%d")
            if (datetime.now() - d).days <= 3:
                score += 2
        except ValueError:
            pass
    if item.content and len(item.content) > 20:
        score += 2
    return score


def _obsidian_reason(item, score: int) -> str:
    if "priorities" in (item.context or "").lower():
        return "Marked as a priority in your notes"
    if item.item_type == "project_idea":
        return "Project idea from vault"
    if item.date:
        return f"TODO from daily note ({item.date})"
    return "Actionable item from vault"


# ---------------------------------------------------------------------------
# dashboard command
# ---------------------------------------------------------------------------


@app.command()
def dashboard(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    since: int = typer.Option(
        30,
        "--since",
        help="Look back this many days for the portfolio activation panel.",
    ),
):
    """Display streak dashboard plus portfolio activation health panel."""
    from src.main import _run_dashboard
    from src.portfolio_activation import (
        compute_activation_health,
        render_activation_health,
    )
    from src.storage import CommitStorage

    if json_output:
        from src.config import GITHUB_TOKEN, GITHUB_USERNAME, validate_config
        from src.github_client import GitHubClient
        from src.storage import get_commit_events_with_history
        from src.streak_calculator import calculate_streak
        from src.stats_calculator import calculate_stats

        try:
            validate_config()
        except ValueError as e:
            print(json.dumps({"error": str(e), "code": 1}))
            raise typer.Exit(1)

        client = GitHubClient(GITHUB_TOKEN, GITHUB_USERNAME)
        storage = CommitStorage()
        from src.github_client import GitHubClientError

        try:
            commit_events = get_commit_events_with_history(client, storage)
            streak_info = calculate_streak(commit_events) if commit_events else {}
            stats = calculate_stats(commit_events) if commit_events else {}
            activation = compute_activation_health(storage, days=since)
            print(json.dumps({
                "streak": streak_info,
                "stats": stats,
                "commit_count": len(commit_events),
                "portfolio_activation": activation,
            }, default=str))
        except GitHubClientError as e:
            print(json.dumps({"error": str(e), "code": 1}))
            raise typer.Exit(1)
    else:
        result = _run_dashboard()
        # Always render the portfolio panel, even if streak fetch failed.
        storage = CommitStorage()
        activation = compute_activation_health(storage, days=since)
        render_activation_health(activation)
        if result:
            raise typer.Exit(result)


# ---------------------------------------------------------------------------
# check command
# ---------------------------------------------------------------------------


@app.command()
def check(
    level: int = typer.Argument(..., min=1, max=4, help="Notification level (1-4)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without sending"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Check streak and send notification if needed."""
    from src.main import _run_check
    from src.notifications import NotificationManager
    from src.storage import CommitStorage

    if json_output:
        storage = CommitStorage()
        manager = NotificationManager(storage)
        result = manager.check_and_notify(level=level, dry_run=dry_run)
        print(json.dumps(result, default=str))
    else:
        exit_code = _run_check(level, dry_run)
        if exit_code:
            raise typer.Exit(exit_code)


# ---------------------------------------------------------------------------
# notify subcommands
# ---------------------------------------------------------------------------


@notify_app.command("test")
def notify_test():
    """Send test notification to verify channel setup."""
    from src.main import _run_notify_test

    exit_code = _run_notify_test()
    if exit_code:
        raise typer.Exit(exit_code)


@notify_app.command("status")
def notify_status():
    """Show which notification channels are configured."""
    from src.main import _run_notify_status

    exit_code = _run_notify_status()
    if exit_code:
        raise typer.Exit(exit_code)


# ---------------------------------------------------------------------------
# cron command
# ---------------------------------------------------------------------------


@app.command()
def cron(
    install: bool = typer.Option(False, "--install", help="Install cron entries into crontab"),
    uninstall: bool = typer.Option(False, "--uninstall", help="Remove code-daily entries from crontab"),
):
    """Print or install crontab entries for the escalating notification schedule."""
    from src.main import _run_setup_cron, _get_cron_entries

    if install:
        _install_cron()
    elif uninstall:
        _uninstall_cron()
    else:
        _run_setup_cron()


def _install_cron():
    """Install code-daily cron entries into the user's crontab."""
    import subprocess
    from src.main import _get_cron_entries

    new_entries = _get_cron_entries()

    # Read existing crontab
    try:
        result = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True, check=False,
        )
        existing = result.stdout if result.returncode == 0 else ""
    except FileNotFoundError:
        print("Error: crontab not found on this system.", file=sys.stderr)
        raise typer.Exit(1)

    # Check if already installed
    if "code-daily" in existing:
        print("code-daily cron entries already exist. Use --uninstall first to replace them.")
        raise typer.Exit(0)

    # Append new entries
    updated = existing.rstrip("\n") + "\n\n" + new_entries + "\n"

    result = subprocess.run(
        ["crontab", "-"], input=updated, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        print(f"Failed to install crontab: {result.stderr}", file=sys.stderr)
        raise typer.Exit(1)

    print("Installed code-daily cron entries:")
    print()
    print(new_entries)
    print()
    print("Reminders will fire at 10 AM, 4 PM, 7 PM, and 9 PM daily.")
    print("Use 'code-daily cron --uninstall' to remove them.")


def _uninstall_cron():
    """Remove code-daily cron entries from the user's crontab."""
    import subprocess

    try:
        result = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            print("No crontab to modify.")
            raise typer.Exit(0)
        existing = result.stdout
    except FileNotFoundError:
        print("Error: crontab not found on this system.", file=sys.stderr)
        raise typer.Exit(1)

    if "code-daily" not in existing:
        print("No code-daily entries found in crontab.")
        raise typer.Exit(0)

    # Remove code-daily block (lines containing "code-daily")
    lines = existing.split("\n")
    filtered = [line for line in lines if "code-daily" not in line]
    # Clean up consecutive blank lines
    cleaned = "\n".join(filtered).strip() + "\n"

    result = subprocess.run(
        ["crontab", "-"], input=cleaned, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        print(f"Failed to update crontab: {result.stderr}", file=sys.stderr)
        raise typer.Exit(1)

    print("Removed code-daily cron entries.")


# ---------------------------------------------------------------------------
# routines subcommands (Claude Code Routines migration)
# ---------------------------------------------------------------------------


def _print_routines_plan_human(plan_dict: dict) -> None:
    summary = plan_dict["summary"]
    print(f"Scanned {summary['total']} cron entries:", file=sys.stderr)
    print(f"  ✅ ready:          {summary['ready']}", file=sys.stderr)
    print(f"  ⚠️  needs_refactor: {summary['needs_refactor']}", file=sys.stderr)
    print(f"  ❌ blocked:        {summary['blocked']}", file=sys.stderr)
    print(file=sys.stderr)
    for entry in plan_dict["entries"]:
        emoji = {"ready": "✅", "needs_refactor": "⚠️", "blocked": "❌"}[entry["status"]]
        cmd = f"code-daily {entry['code_daily_command']}" if entry["code_daily_command"] else "(unparsed)"
        print(f"{emoji} {entry['human_schedule']:<30} {cmd}")
        print(f"   → {entry['reason']}")
        if entry["routine_prompt"]:
            print(f"   {entry['routine_prompt']}")
        print()
    print(f"Docs: {plan_dict['routines_docs_url']}", file=sys.stderr)


@routines_app.command("plan")
def routines_plan(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Classify each code-daily cron entry by migratability to Claude Code Routines."""
    from src.main import _get_cron_entries
    from src.routines_migrator import build_plan

    plan = build_plan(_get_cron_entries())
    plan_dict = plan.to_dict()

    if json_output:
        print(json.dumps(plan_dict, indent=2, default=str))
    else:
        _print_routines_plan_human(plan_dict)


@routines_app.command("export")
def routines_export(
    output: Optional[str] = typer.Option(None, "--output", help="Output markdown path (defaults to vault project-ideas folder)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Write a Claude Code Routines migration guide to the Obsidian vault."""
    import datetime

    from src.main import _get_cron_entries
    from src.routines_migrator import build_plan, render_migration_guide_md

    plan = build_plan(_get_cron_entries())
    today = datetime.date.today().isoformat()
    markdown = render_migration_guide_md(plan, today)

    if output:
        target = output
    else:
        vault_path = _get_vault_path()
        target = os.path.join(vault_path, "project-ideas", f"routines-migration-{today}.md")

    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    with open(target, "w") as f:
        f.write(markdown)

    result = {"written": target, "summary": plan.summary}
    if json_output:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"Wrote migration guide to: {target}", file=sys.stderr)
        print(f"  ✅ ready:          {plan.summary['ready']}")
        print(f"  ⚠️  needs_refactor: {plan.summary['needs_refactor']}")
        print(f"  ❌ blocked:        {plan.summary['blocked']}")


# ---------------------------------------------------------------------------
# news subcommands
# ---------------------------------------------------------------------------


@news_app.command("digest")
def news_digest(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    sources: Optional[str] = typer.Option(None, help="Comma-separated sources (hackernews,reddit,arxiv)"),
    hours: int = typer.Option(24, help="Hours back to fetch"),
    limit: int = typer.Option(25, help="Max items per source"),
    no_write: bool = typer.Option(False, "--no-write", help="Skip writing to Obsidian vault"),
):
    """Fetch AI news digest from multiple sources."""
    from src.news_digest import collect_news, write_digest_to_vault

    source_list = [s.strip() for s in sources.split(",")] if sources else None
    digest = collect_news(sources=source_list, hours_back=hours, limit=limit)

    if not no_write:
        try:
            vault_path = _get_vault_path()
            rel_path = write_digest_to_vault(vault_path, digest)
            digest["vault_file"] = rel_path
        except SystemExit:
            raise
        except Exception as e:
            print(f"Vault write failed: {e}", file=sys.stderr)

    def _human(d):
        print(f"AI News Digest — {d['date']}\n")
        for src_name, meta in d["sources"].items():
            status = "OK" if meta["success"] else f"FAIL: {meta['error']}"
            print(f"  {src_name}: {meta['count']} items ({status})")
        print()

        for item in d["items"]:
            score_str = f"[{item['score']}]" if item["score"] else ""
            sub_str = f" {item['subreddit']}" if item.get("subreddit") else ""
            print(f"  {score_str} {item['title']}")
            print(f"    {item['source']}{sub_str}  {item['url']}")
            if item.get("summary"):
                print(f"    {item['summary'][:120]}...")
            print()

        if d.get("vault_file"):
            print(f"Written to vault: {d['vault_file']}")

    _output(digest, json_output, _human)


@news_app.command("trends")
def news_trends(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    days: int = typer.Option(30, help="Days back to analyze"),
):
    """Identify trending topics across news digests."""
    from src.news_trends import analyze_trends

    vault_path = _get_vault_path()
    data = analyze_trends(vault_path, days=days)

    def _human(d):
        if d["digests_analyzed"] == 0:
            print("No digest files found in vault. Run 'code-daily news digest' first.")
            return

        print(f"Analyzed {d['digests_analyzed']} digests ({d['date_range']['from']} to {d['date_range']['to']})\n")

        if d["trending"]:
            print("Trending topics (appearing on 2+ days):\n")
            for t in d["trending"][:15]:
                dates_str = ", ".join(t["dates"])
                print(f"  [{t['day_count']}d/{t['total_mentions']}x] {t['topic']}")
                print(f"    Dates: {dates_str}")
                if t["example_titles"]:
                    print(f"    e.g. {t['example_titles'][0][:70]}")
                print()
        else:
            print("No recurring topics found yet. Need 2+ digest days for trends.\n")

        if d["new_today"]:
            print(f"New today: {', '.join(d['new_today'][:10])}\n")

        if d["fading"]:
            print(f"Fading: {', '.join(d['fading'][:10])}")

    _output(data, json_output, _human)


@news_app.command("podcast")
def news_podcast(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    date_str: Optional[str] = typer.Option(None, "--date", help="Digest date (YYYY-MM-DD, default today)"),
    voice: str = typer.Option("en-US-AndrewMultilingualNeural", "--voice", help="edge-tts voice name"),
):
    """Generate a TTS podcast from the synthesized news digest."""
    from datetime import date

    from src.tts import (
        DEFAULT_VOICE,
        digest_to_script,
        read_synthesis_from_vault,
        write_podcast_to_vault,
    )

    vault_path = _get_vault_path()
    target_date = date_str or date.today().isoformat()

    try:
        synthesis = read_synthesis_from_vault(vault_path, target_date)
    except FileNotFoundError:
        print(f"No synthesized digest found for {target_date}.", file=sys.stderr)
        raise typer.Exit(1)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        raise typer.Exit(1)

    script = digest_to_script(synthesis, target_date)
    result = write_podcast_to_vault(vault_path, target_date, script, voice)
    result["script"] = script

    def _human(d):
        print(f"Podcast generated for {d['date']}\n")
        print(f"  Voice: {d['voice']}")
        print(f"  Script: {d['script_length']:,} characters")
        print(f"  File: {d['vault_file']}")
        print(f"\n  Play in Obsidian or any audio player.")

    _output(result, json_output, _human)


# ---------------------------------------------------------------------------
# diversity command
# ---------------------------------------------------------------------------


@app.command()
def diversity(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    days: int = typer.Option(14, help="Days back to analyze"),
):
    """Analyze how diverse your recent suggestions have been."""
    from src.diversity import compute_diversity_score
    from src.storage import CommitStorage

    storage = CommitStorage()
    data = compute_diversity_score(storage, days=days)

    def _human(d):
        score = d["score"]
        rating = d["rating"]
        total = d["total_suggestions"]

        if rating == "no data":
            print(d["warning"])
            return

        # Score display
        bar_len = int(score / 5)
        bar = "#" * bar_len + "-" * (20 - bar_len)
        print(f"  Diversity Score: {score}/100 [{bar}] ({rating})")
        print()

        # Breakdown
        print(f"  Suggestions analyzed: {total} (last {d['days_analyzed']} days)")
        print(f"  Unique domains: {d['unique_domains']} ({d['domain_spread']:.0%} spread)")
        print(f"  Sources: {', '.join(f'{k}={v}' for k, v in d['source_spread'].items())}")
        print()

        if d["most_repeated"]:
            print("  Most repeated:")
            for item in d["most_repeated"]:
                print(f"    [{item['count']}x] {item['title'][:70]}")
            print()

        if d["underrepresented_domains"]:
            print(f"  Underrepresented: {', '.join(d['underrepresented_domains'])}")
            print()

        if d["warning"]:
            print(f"  Warning: {d['warning']}")

    _output(data, json_output, _human)


# ---------------------------------------------------------------------------
# ideas subcommands
# ---------------------------------------------------------------------------


@ideas_app.command("from-news")
def ideas_from_news(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    hours: int = typer.Option(24, help="Hours back for news fetch"),
    limit: int = typer.Option(25, help="Max items per news source"),
):
    """Collect seed data for news-informed project ideas (agent synthesizes)."""
    from src.idea_generator import collect_idea_seeds

    seeds = collect_idea_seeds(hours_back=hours, limit=limit)

    def _human(d):
        print(f"Idea seeds collected at {d['collected_at']}\n")
        print(f"  Trending topics: {d['trending_count']}")
        print(f"  User interests: {len(d['user_interests'])}")
        print(f"  Recent domains: {len(d['recent_domains'])}")
        print()
        print("Top trending:")
        for item in d["trending_topics"][:5]:
            score = item.get("score", 0)
            print(f"  [{score}] {item.get('title', '')}")
        print()
        print("Run with --json for full data for agent synthesis.")

    _output(seeds, json_output, _human)


@ideas_app.command("from-reddit")
def ideas_from_reddit(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    subreddit: Optional[str] = typer.Option(None, help="Specific subreddit to scan"),
    count: int = typer.Option(3, help="Number of random subreddits to pick"),
    limit: int = typer.Option(50, help="Max posts per subreddit"),
):
    """Scan community subreddits for recurring problems (agent synthesizes)."""
    from src.reddit_scanner import scan_subreddit_problems

    subs = [subreddit] if subreddit else None
    scan = scan_subreddit_problems(subreddits=subs, count=count, limit=limit)

    def _human(d):
        print(f"Reddit scan at {d['collected_at']}\n")
        print(f"  Subreddits: {', '.join(d['subreddits_scanned'])}")
        print(f"  Total posts: {d['total_count']}")
        print(f"  Problem signals: {d['problem_count']}")
        if d["errors"]:
            print(f"  Errors: {'; '.join(d['errors'])}")
        print()
        if d["problem_posts"]:
            print("Top problem posts:")
            for post in d["problem_posts"][:5]:
                print(f"  [{post['score']}] r/{post['subreddit'].lstrip('r/')} - {post['title'][:80]}")
        print()
        print("Run with --json for full data for agent synthesis.")

    _output(scan, json_output, _human)


# ---------------------------------------------------------------------------
# quests subcommands
# ---------------------------------------------------------------------------


def _quest_not_found(quest_id: int, json_output: bool):
    """Handle quest-not-found with proper exit code and output."""
    if json_output:
        print(json.dumps({"error": "Quest not found", "code": 2}))
    else:
        print(f"Quest {quest_id} not found.", file=sys.stderr)
    raise typer.Exit(2)


@quests_app.command("list")
def quests_list(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    status: Optional[str] = typer.Option(None, help="Filter by status (pending, active, completed, skipped, archived)"),
    limit: int = typer.Option(10, help="Max quests to return"),
):
    """List quests, optionally filtered by status."""
    from src.quest_manager import QuestManager
    from src.storage import CommitStorage

    storage = CommitStorage()
    qm = QuestManager(storage)

    if status:
        quests = storage.get_quests(status=status, limit=limit)
        if json_output:
            print(json.dumps(quests, indent=2, default=str))
        else:
            if not quests:
                print(f"No {status} quests found.")
                return
            print(f"{status.capitalize()} quests ({len(quests)}):\n")
            for i, q in enumerate(quests, 1):
                score_str = f"[{q.get('priority_score', 0)}pts] " if q.get("priority_score") else ""
                source_str = f"  [{q.get('source', '')}]" if q.get("source") else ""
                print(f"  {i}. {score_str}#{q['id']}  {q['title']}{source_str}")
    else:
        pending = qm.get_prioritized_quests(limit=limit)
        active = qm.get_active_quests()
        summary = qm.get_quest_summary()

        data = {"pending": pending, "active": active, "summary": summary}

        def _human(d):
            print("Quest Board\n")
            if d["active"]:
                print(f"  Active ({len(d['active'])}):")
                for q in d["active"]:
                    source_str = f"  [{q.get('source', '')}]" if q.get("source") else ""
                    print(f"    #{q['id']}  {q['title']}{source_str}")
                print()

            if d["pending"]:
                print(f"  Pending (top {len(d['pending'])} by priority):")
                for i, q in enumerate(d["pending"], 1):
                    score = q.get("priority_score", 0)
                    source_str = f"  [{q.get('source', '')}]" if q.get("source") else ""
                    print(f"    {i}. [{score}pts] #{q['id']}  {q['title']}{source_str}")
                print()

            s = d["summary"]
            print(f"  Summary: {s['total']} total | {s['pending']} pending | {s['active']} active | {s['completed']} completed")

        _output(data, json_output, _human)


@quests_app.command("add")
def quests_add(
    title: str = typer.Argument(..., help="Quest title"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="Optional description"),
):
    """Create a new manual quest."""
    from src.quest_manager import QuestManager
    from src.storage import CommitStorage

    storage = CommitStorage()
    qm = QuestManager(storage)
    quest = qm.add_manual_quest(title, description)

    data = {"quest": quest}

    def _human(d):
        q = d["quest"]
        print("Quest created:")
        print(f"  #{q['id']}  {q['title']}")
        if q.get("description"):
            print(f"  Description: {q['description']}")
        print(f"  Status: {q['status']}")

    _output(data, json_output, _human)


@quests_app.command("accept")
def quests_accept(
    quest_id: int = typer.Argument(..., help="Quest ID to accept"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Accept a quest (mark as active)."""
    from src.quest_manager import QuestManager
    from src.storage import CommitStorage

    storage = CommitStorage()
    qm = QuestManager(storage)
    quest = qm.accept_quest(quest_id)

    if not quest:
        _quest_not_found(quest_id, json_output)

    data = {"quest": quest}

    def _human(d):
        q = d["quest"]
        print(f"Quest #{q['id']} accepted:")
        print(f"  {q['title']}")
        print(f"  Status: {q['status']}")

    _output(data, json_output, _human)


@quests_app.command("complete")
def quests_complete(
    quest_id: int = typer.Argument(..., help="Quest ID to complete"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Complete a quest."""
    from src.quest_manager import QuestManager
    from src.storage import CommitStorage

    storage = CommitStorage()
    qm = QuestManager(storage)
    quest = qm.complete_quest(quest_id)

    if not quest:
        _quest_not_found(quest_id, json_output)

    data = {"quest": quest}

    def _human(d):
        q = d["quest"]
        print(f"Quest #{q['id']} completed!")
        print(f"  {q['title']}")

    _output(data, json_output, _human)


@quests_app.command("skip")
def quests_skip(
    quest_id: int = typer.Argument(..., help="Quest ID to skip"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    save_idea: bool = typer.Option(False, "--save-idea", help="Save quest as idea before skipping"),
):
    """Skip a quest, optionally saving it as an idea."""
    from src.quest_manager import QuestManager
    from src.storage import CommitStorage

    storage = CommitStorage()
    qm = QuestManager(storage)
    result = qm.skip_quest(quest_id, action="archive", save_as_idea=save_idea)

    if not result.get("success"):
        _quest_not_found(quest_id, json_output)

    def _human(d):
        q = d["quest"]
        print(f"Quest #{q['id']} skipped (archived):")
        print(f"  {q['title']}")
        if d.get("idea"):
            print(f"  Saved as idea #{d['idea']['id']}")

    _output(result, json_output, _human)


@quests_app.command("summary")
def quests_summary(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show quest counts by status."""
    from src.quest_manager import QuestManager
    from src.storage import CommitStorage

    storage = CommitStorage()
    qm = QuestManager(storage)
    data = qm.get_quest_summary()

    def _human(d):
        print("Quest Summary:")
        print(f"  Total:     {d['total']}")
        print(f"  Pending:   {d['pending']}")
        print(f"  Active:    {d['active']}")
        print(f"  Completed: {d['completed']}")
        print(f"  Skipped:   {d['skipped']}")
        print(f"  Archived:  {d['archived']}")

    _output(data, json_output, _human)


@quests_app.command("sync-issues")
def quests_sync_issues(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Sync GitHub issues assigned to you as quests."""
    from src.quest_discovery import run_sync_issues

    result = run_sync_issues()

    if result["status"] in ("skipped", "error"):
        if json_output:
            print(json.dumps({"error": result.get("error", ""), "code": 1}))
        else:
            print(f"Error: {result.get('error', '')}", file=sys.stderr)
        raise typer.Exit(1)

    def _human(d):
        print("GitHub issue sync complete:")
        print(f"  Added: {d['added']} new quests")
        print(f"  Skipped: {d['skipped']} (already synced)")

    _output(result, json_output, _human)


@quests_app.command("scan-todos")
def quests_scan_todos(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Scan project for TODO/FIXME comments and create quests."""
    from src.quest_discovery import run_scan_todos

    result = run_scan_todos()

    def _human(d):
        if d["added"] == 0 and d["skipped"] == 0:
            print("TODO scan complete: No new TODOs found.")
        else:
            print("TODO scan complete:")
            print(f"  Added: {d['added']} new quests")
            print(f"  Skipped: {d['skipped']} (already synced)")

    _output(result, json_output, _human)


@quests_app.command("scan-skillvault")
def quests_scan_skillvault(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Scan skillvault for incomplete-work markers across all projects and create quests."""
    from src.quest_discovery import run_scan_skillvault

    result = run_scan_skillvault()

    def _human(d):
        if d["scanned"] == 0:
            print(
                "Skillvault scan complete: no findings "
                "(is skillvault installed and indexed?)"
            )
            return
        print("Skillvault scan complete:")
        print(f"  Scanned: {d['scanned']} findings")
        print(f"  Added: {d['added']} new quests")
        print(f"  Skipped: {d['skipped']} (already synced)")

    _output(result, json_output, _human)


@quests_app.command("sync-beacon-gaps")
def quests_sync_beacon_gaps(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    limit: int = typer.Option(10, "--limit", "-l", help="Max gaps to sync"),
):
    """Sync skill gaps from beacon into quests for focused practice."""
    from src.quest_discovery import run_sync_beacon_gaps

    result = run_sync_beacon_gaps(limit=limit)

    if result["status"] in ("skipped", "error"):
        err = result.get("error", "")
        payload = {"error": err, "code": 1, "added": 0, "skipped": 0}
        if "not found" in err:
            _output(payload, json_output,
                    lambda d: print("beacon CLI not found — install beacon or add it to PATH"))
        elif "non-zero" in err:
            _output(payload, json_output,
                    lambda d: print("beacon gaps export failed — run 'beacon gaps analyze' first"))
        elif "invalid JSON" in err:
            _output(payload, json_output,
                    lambda d: print("Invalid JSON from beacon gaps export"))
        else:
            _output(payload, json_output, lambda d: print(f"Beacon error: {err}"))
        return

    def _human(d):
        print("Beacon skill gap sync complete:")
        print(f"  Gaps found: {d['total_gaps']}")
        print(f"  Added: {d['added']} new quests")
        print(f"  Skipped: {d['skipped']} (already synced)")

    _output(result, json_output, _human)


@quests_app.command("discover")
def quests_discover(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Discover external contribution opportunities from starred repos."""
    from src.quest_discovery import run_discover

    result = run_discover()

    if result["status"] in ("skipped", "error"):
        if json_output:
            print(json.dumps({"error": result.get("error", ""), "code": 1}))
        else:
            print(f"Error: {result.get('error', '')}", file=sys.stderr)
        raise typer.Exit(1)

    def _human(d):
        cache_str = " (from cache)" if d.get("from_cache") else ""
        print(f"External issue discovery complete{cache_str}:")
        if d.get("repos_searched"):
            print(f"  Searched: {d['repos_searched']} starred repos")
        if d.get("issues_found"):
            print(f"  Found: {d['issues_found']} good-first-issue candidates")
        print(f"  Added: {d['added']} new quests")
        print(f"  Skipped: {d['skipped']} (already synced)")

    _output(result, json_output, _human)


@quests_app.command("discover-all")
def quests_discover_all(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Run every discovery source in one shot (scan-todos, scan-skillvault, beacon gaps, sync-issues, discover)."""
    from src.quest_discovery import run_all

    result = run_all()

    def _human(d):
        label = {"ok": "[ok]  ", "skipped": "[skip]", "error": "[err] "}
        print("Quest discovery (all sources):")
        for src in d["sources"]:
            tag = label.get(src["status"], "[?]   ")
            added = src.get("added", 0)
            skipped = src.get("skipped", 0)
            line = f"  {tag} {src['name']:<18} added={added:<3} skipped={skipped}"
            if src["status"] != "ok" and src.get("error"):
                line += f"  ({src['error']})"
            print(line)
        print()
        print(f"  Total added:   {d['total_added']}")
        print(f"  Total skipped: {d['total_skipped']}")
        if d["total_errors"]:
            print(f"  Errors:        {d['total_errors']}")

    _output(result, json_output, _human)


@quests_app.command("enhance")
def quests_enhance(
    quest_id: int = typer.Argument(..., help="Quest ID to enhance"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Enhance a quest with AI-generated description and difficulty."""
    from src.quest_manager import QuestManager
    from src.storage import CommitStorage

    storage = CommitStorage()
    qm = QuestManager(storage)
    result = qm.enhance_quest(quest_id)

    if not result.get("success"):
        error = result.get("error", "Unknown error")
        if "not found" in error.lower():
            _quest_not_found(quest_id, json_output)
        if json_output:
            print(json.dumps({"error": error, "code": 1}))
        else:
            print(f"Error: {error}", file=sys.stderr)
        raise typer.Exit(1)

    def _human(d):
        q = d["quest"]
        print(f"Quest #{q['id']} enhanced:")
        print(f"  {q['title']}")
        if q.get("ai_description"):
            print(f"  AI Description: {q['ai_description']}")
        if q.get("difficulty"):
            reasoning = f" - {q['difficulty_reasoning']}" if q.get("difficulty_reasoning") else ""
            print(f"  Difficulty: {q['difficulty']}/5{reasoning}")

    _output(result, json_output, _human)


@quests_app.command("enhance-batch")
def quests_enhance_batch(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    limit: int = typer.Option(5, help="Number of quests to enhance (max 20)"),
):
    """Batch enhance pending quests that lack AI descriptions."""
    from src.quest_manager import QuestManager
    from src.storage import CommitStorage

    storage = CommitStorage()
    qm = QuestManager(storage)
    result = qm.enhance_pending_quests(limit=limit)

    if not result.get("success"):
        error = result.get("error", "Unknown error")
        if json_output:
            print(json.dumps({"error": error, "code": 1}))
        else:
            print(f"Error: {error}", file=sys.stderr)
        raise typer.Exit(1)

    def _human(d):
        print("Batch enhancement complete:")
        print(f"  Enhanced: {d['enhanced']}/{d['total_requested']} quests")
        print(f"  Errors: {len(d['errors'])}")

    _output(result, json_output, _human)


@quests_app.command("ai-status")
def quests_ai_status(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Check if AI features are configured and available."""
    from src.quest_manager import QuestManager
    from src.storage import CommitStorage

    storage = CommitStorage()
    qm = QuestManager(storage)
    data = qm.get_ai_status()

    def _human(d):
        status = "Enabled" if d["enabled"] else "Disabled"
        print(f"AI Features: {status}")
        if not d["enabled"]:
            print(f"  {d['message']}")

    _output(data, json_output, _human)


# ---------------------------------------------------------------------------
# achievements subcommands
# ---------------------------------------------------------------------------


@achievements_app.command("list")
def achievements_list(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    category: Optional[str] = typer.Option(None, help="Filter by category (streak, commits)"),
):
    """Show all achievements with unlock status."""
    from src.achievements import get_all_achievements_status
    from src.storage import CommitStorage

    storage = CommitStorage()
    unlocked = storage.get_unlocked_achievements()
    all_achievements = get_all_achievements_status(unlocked)

    if category:
        all_achievements = [a for a in all_achievements if a["category"] == category]

    total = len(all_achievements)
    unlocked_count = sum(1 for a in all_achievements if a["unlocked"])

    data = {
        "achievements": all_achievements,
        "summary": {"total": total, "unlocked": unlocked_count},
    }

    def _human(d):
        s = d["summary"]
        print(f"Achievements ({s['unlocked']}/{s['total']} unlocked):\n")

        by_category = {}
        for a in d["achievements"]:
            by_category.setdefault(a["category"].capitalize(), []).append(a)

        for cat_name, items in by_category.items():
            print(f"  {cat_name}:")
            for a in items:
                if a["unlocked"]:
                    date_str = a["unlocked_at"][:10] if a["unlocked_at"] else ""
                    print(f"    [x] {a['name']} - {a['description']} (unlocked {date_str})")
                else:
                    print(f"    [ ] {a['name']} - {a['description']} (need {a['threshold']})")
            print()

    _output(data, json_output, _human)


# ---------------------------------------------------------------------------
# ideas list/add/promote/sync subcommands
# ---------------------------------------------------------------------------


@ideas_app.command("list")
def ideas_list(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    status: Optional[str] = typer.Option(None, help="Filter by status (active, completed, promoted)"),
):
    """List ideas from the database."""
    from src.storage import CommitStorage

    storage = CommitStorage()
    ideas = storage.get_ideas(status=status)

    data = {"ideas": ideas}

    def _human(d):
        items = d["ideas"]
        if not items:
            print("No ideas found.")
            return
        active_count = sum(1 for i in items if i.get("status") == "active")
        print(f"Ideas ({active_count} active):\n")
        for item in items:
            print(f"  #{item['id']}  {item['content']}")

    _output(data, json_output, _human)


@ideas_app.command("add")
def ideas_add(
    content: str = typer.Argument(..., help="Idea content"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Add a new idea to the database and IDEAS.md."""
    from src.ideas import add_idea
    from src.storage import CommitStorage

    storage = CommitStorage()
    idea_id = storage.create_idea(content)
    add_idea(content)
    idea = storage.get_idea(idea_id)

    data = {"idea": idea}

    def _human(d):
        i = d["idea"]
        print("Idea created:")
        print(f"  #{i['id']}  {i['content']}")

    _output(data, json_output, _human)


@ideas_app.command("promote")
def ideas_promote(
    idea_id: int = typer.Argument(..., help="Idea ID to promote to a quest"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Promote an idea to a quest."""
    from src.quest_manager import QuestManager
    from src.storage import CommitStorage

    storage = CommitStorage()
    qm = QuestManager(storage)
    quest = qm.promote_idea_to_quest(idea_id)

    if not quest:
        if json_output:
            print(json.dumps({"error": "Idea not found", "code": 2}))
        else:
            print(f"Idea {idea_id} not found.", file=sys.stderr)
        raise typer.Exit(2)

    data = {"quest": quest}

    def _human(d):
        q = d["quest"]
        print(f"Idea #{idea_id} promoted to quest #{q['id']}:")
        print(f"  {q['title']}")

    _output(data, json_output, _human)


@ideas_app.command("sync")
def ideas_sync(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Sync ideas between IDEAS.md and database."""
    from src.ideas import sync_ideas_to_db
    from src.storage import CommitStorage

    storage = CommitStorage()
    result = sync_ideas_to_db(storage)

    def _human(d):
        print("Ideas sync complete:")
        print(f"  Added: {d['added']} new ideas from IDEAS.md")
        print(f"  Updated: {d['updated']} status change")
        print(f"  File: {d['total_in_file']} ideas | Database: {d['total_in_db']} ideas")

    _output(result, json_output, _human)


# ---------------------------------------------------------------------------
# scaffold subcommands
# ---------------------------------------------------------------------------

scaffold_app = typer.Typer(help="Scaffolding commands")
app.add_typer(scaffold_app, name="scaffold")


@scaffold_app.command("justfile")
def scaffold_justfile_cmd(
    project_path: str = typer.Argument(".", help="Project directory to scaffold"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print instead of writing"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing justfile"),
):
    """Generate a tailored justfile for a project."""
    from src.justfile_scaffolder import scaffold_justfile

    try:
        result = scaffold_justfile(project_path, dry_run=dry_run, force=force)
    except FileExistsError as e:
        if json_output:
            print(json.dumps({"error": str(e), "code": 1}))
        else:
            print(str(e), file=sys.stderr)
        raise typer.Exit(1)

    def _human(d):
        if d["dry_run"]:
            print(d["content"])
        else:
            print(f"Justfile written to {d['justfile_path']}")
            print(f"  Project type: {d['project_type']}")
            print(f"  Recipes: {', '.join(d['recipes_generated'])}")

    _output(result, json_output, _human)


# ---------------------------------------------------------------------------
# portfolio subcommands
# ---------------------------------------------------------------------------

portfolio_app = typer.Typer(help="Portfolio sweep & grade history")
app.add_typer(portfolio_app, name="portfolio")


@portfolio_app.command("sweep")
def portfolio_sweep_cmd(
    root: str = typer.Option(
        None,
        "--root",
        help="Directory to scan. Defaults to ~/projects.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Compute and print without persisting"
    ),
):
    """Score every project and persist a grade snapshot."""
    from src.portfolio_sweep import DEFAULT_ROOT, PortfolioSweepError, run_sweep

    try:
        result = run_sweep(root=root or DEFAULT_ROOT, persist=not dry_run)
    except PortfolioSweepError as e:
        if json_output:
            print(json.dumps({"error": str(e), "code": 1}))
        else:
            print(f"error: {e}", file=sys.stderr)
        raise typer.Exit(1)

    def _human(d):
        for w in d.get("warnings", []):
            print(f"warning: {w}", file=sys.stderr)
        dist = d["grade_distribution"]
        dist_str = "  ".join(f"{g}:{dist[g]}" for g in ("A", "B", "C", "D", "F"))
        print(f"Swept {d['project_count']} projects at {d['captured_at']}")
        print(f"  root: {d['root']}")
        print(f"  grades: {dist_str}")
        if d["persisted"]:
            print(f"  persisted: yes")
        else:
            print(f"  persisted: no (dry-run)")

        real_changes = [c for c in d["changes"] if c["direction"] != "new"]
        if real_changes:
            print(f"\nChanges since last sweep ({len(real_changes)}):")
            for c in real_changes:
                arrow = "↑" if c["direction"] == "up" else ("↓" if c["direction"] == "down" else "→")
                delta = f"{c['score_delta']:+d}" if c["score_delta"] is not None else "?"
                days = (
                    f" ({c['days_since_previous']}d ago)"
                    if c["days_since_previous"] is not None
                    else ""
                )
                print(
                    f"  {arrow} {c['name']}: {c['grade_from']}→{c['grade_to']} "
                    f"(score {c['score_from']}→{c['score_to']}, {delta}){days}"
                )
        else:
            new_count = sum(1 for c in d["changes"] if c["direction"] == "new")
            if new_count == d["project_count"]:
                print("\nFirst sweep — no prior snapshots to diff against.")
            else:
                print("\nNo grade or score changes since last sweep.")

    _output(result, json_output, _human)


@portfolio_app.command("history")
def portfolio_history_cmd(
    project: Optional[str] = typer.Option(
        None, "--project", help="Filter to one project by name"
    ),
    days: int = typer.Option(
        30, "--days", help="Look back this many days"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show grade/score history from persisted sweeps."""
    from datetime import datetime, timedelta, timezone

    from src.storage import CommitStorage

    since_dt = datetime.now(timezone.utc) - timedelta(days=days)
    since = since_dt.isoformat(timespec="seconds")

    storage = CommitStorage()
    rows = storage.get_project_history(project_name=project, since=since)

    data = {
        "since": since,
        "days": days,
        "project_filter": project,
        "row_count": len(rows),
        "snapshots": [
            {
                "captured_at": r["captured_at"],
                "project_name": r["project_name"],
                "project_path": r["project_path"],
                "grade": r["grade"],
                "score": r["score"],
                "days_since_last_commit": r["days_since_last_commit"],
                "commits_30d": r["commits_30d"],
            }
            for r in rows
        ],
    }

    def _human(d):
        if not d["snapshots"]:
            scope = f"project={d['project_filter']} " if d["project_filter"] else ""
            print(f"No snapshots in the last {d['days']} days {scope}".rstrip())
            return
        scope = f" for {d['project_filter']}" if d["project_filter"] else ""
        print(f"{d['row_count']} snapshots in the last {d['days']} days{scope}:")
        for s in d["snapshots"]:
            print(
                f"  {s['captured_at']}  {s['project_name']:<28s}  "
                f"{s['grade']}  score={s['score']}"
            )

    _output(data, json_output, _human)


# ---------------------------------------------------------------------------
# launchpad subcommands
# ---------------------------------------------------------------------------

launchpad_app = typer.Typer(help="Shippable-tool launch readiness sweep")
app.add_typer(launchpad_app, name="launchpad")


def _launchpad_grade_summary(d: dict) -> str:
    dist = d["grade_distribution"]
    return "  ".join(f"{g}:{dist[g]}" for g in ("A", "B", "C", "D", "F"))


@launchpad_app.command("sweep")
def launchpad_sweep_cmd(
    root: str = typer.Option(
        None,
        "--root",
        help="Directory to scan. Defaults to ~/projects.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Compute and print without persisting"
    ),
):
    """Score every shippable project under root and persist a launch-readiness snapshot."""
    from src.launchpad import DEFAULT_ROOT, LaunchpadError, run_sweep

    try:
        result = run_sweep(root=root or DEFAULT_ROOT, persist=not dry_run)
    except LaunchpadError as e:
        if json_output:
            print(json.dumps({"error": str(e), "code": 1}))
        else:
            print(f"error: {e}", file=sys.stderr)
        raise typer.Exit(1)

    def _human(d):
        print(f"Swept {d['project_count']} shippables at {d['captured_at']}")
        print(f"  root: {d['root']}")
        print(f"  grades: {_launchpad_grade_summary(d)}")
        print(f"  persisted: {'yes' if d['persisted'] else 'no (dry-run)'}")

        real_changes = [c for c in d["changes"] if c["direction"] != "new"]
        if real_changes:
            print(f"\nChanges since last sweep ({len(real_changes)}):")
            for c in real_changes:
                arrow = "↑" if c["direction"] == "up" else ("↓" if c["direction"] == "down" else "→")
                delta = f"{c['score_delta']:+d}" if c["score_delta"] is not None else "?"
                days = (
                    f" ({c['days_since_previous']}d ago)"
                    if c["days_since_previous"] is not None
                    else ""
                )
                print(
                    f"  {arrow} {c['name']}: {c['grade_from']}→{c['grade_to']} "
                    f"(score {c['score_from']}→{c['score_to']}, {delta}){days}"
                )
        else:
            new_count = sum(1 for c in d["changes"] if c["direction"] == "new")
            if new_count == d["project_count"]:
                print("\nFirst sweep — no prior snapshots to diff against.")
            else:
                print("\nNo grade or score changes since last sweep.")

        print("\nProjects:")
        for p in sorted(d["projects"], key=lambda x: (-x["score"], x["name"])):
            missing = ", ".join(p["missing_signals"]) if p["missing_signals"] else "—"
            print(f"  {p['grade']}  {p['score']:>3}  {p['name']:<28s}  missing: {missing}")

    _output(result, json_output, _human)


@launchpad_app.command("history")
def launchpad_history_cmd(
    project: Optional[str] = typer.Option(
        None, "--project", help="Filter to one project by name"
    ),
    days: int = typer.Option(
        30, "--days", help="Look back this many days"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show launchpad grade/score history from persisted sweeps."""
    from datetime import datetime, timedelta, timezone

    from src.storage import CommitStorage

    since_dt = datetime.now(timezone.utc) - timedelta(days=days)
    since = since_dt.isoformat(timespec="seconds")

    storage = CommitStorage()
    rows = storage.get_launchpad_history(project_name=project, since=since)

    data = {
        "since": since,
        "days": days,
        "project_filter": project,
        "row_count": len(rows),
        "snapshots": [
            {
                "captured_at": r["captured_at"],
                "project_name": r["project_name"],
                "project_path": r["project_path"],
                "version": r["version"],
                "grade": r["grade"],
                "score": r["score"],
                "days_since_last_commit": r["days_since_last_commit"],
            }
            for r in rows
        ],
    }

    def _human(d):
        if not d["snapshots"]:
            scope = f"project={d['project_filter']} " if d["project_filter"] else ""
            print(f"No launchpad snapshots in the last {d['days']} days {scope}".rstrip())
            return
        scope = f" for {d['project_filter']}" if d["project_filter"] else ""
        print(f"{d['row_count']} snapshots in the last {d['days']} days{scope}:")
        for s in d["snapshots"]:
            print(
                f"  {s['captured_at']}  {s['project_name']:<28s}  "
                f"{s['grade']}  score={s['score']}"
            )

    _output(data, json_output, _human)


@launchpad_app.command("show")
def launchpad_show_cmd(
    name: str = typer.Argument(..., help="Project name to show details for"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show the most recent launchpad snapshot for one project, with full signal breakdown."""
    import json as _json

    from src.storage import CommitStorage

    storage = CommitStorage()
    latest = storage.get_latest_launchpad_per_project()
    matches = [r for r in latest.values() if r["project_name"] == name]
    if not matches:
        if json_output:
            print(_json.dumps({"error": f"no launchpad snapshot for {name!r}", "code": 2}))
        else:
            print(f"error: no launchpad snapshot for {name!r}", file=sys.stderr)
        raise typer.Exit(2)

    row = matches[0]
    raw = _json.loads(row["raw_json"]) if row.get("raw_json") else {}
    data = {
        "name": row["project_name"],
        "path": row["project_path"],
        "version": row["version"],
        "grade": row["grade"],
        "score": row["score"],
        "captured_at": row["captured_at"],
        "days_since_last_commit": row["days_since_last_commit"],
        "signals": _json.loads(row["signals_json"]) if row.get("signals_json") else {},
        "missing_signals": raw.get("missing_signals") or [],
        "scripts": raw.get("scripts") or [],
        "readme_bytes": raw.get("readme_bytes"),
    }

    def _human(d):
        print(f"{d['name']}  ({d['grade']}, score {d['score']})")
        print(f"  path: {d['path']}")
        if d["version"]:
            print(f"  version: {d['version']}")
        if d["scripts"]:
            print(f"  scripts: {', '.join(d['scripts'])}")
        if d["days_since_last_commit"] is not None:
            print(f"  days since last commit: {d['days_since_last_commit']}")
        if d["readme_bytes"] is not None:
            print(f"  README: {d['readme_bytes']} bytes")
        print(f"  signals (passing):")
        for key, value in d["signals"].items():
            print(f"    {'✓' if value else '✗'} {key}")

    _output(data, json_output, _human)


# ---------------------------------------------------------------------------
# Typer entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
