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
app.add_typer(issues_app, name="issues")
app.add_typer(vault_app, name="vault")
app.add_typer(notify_app, name="notify")
app.add_typer(news_app, name="news")
app.add_typer(streak_app, name="streak")
app.add_typer(ideas_app, name="ideas")


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
):
    """Display streak dashboard (original default behavior)."""
    from src.main import _run_dashboard

    if json_output:
        from src.config import GITHUB_TOKEN, GITHUB_USERNAME, validate_config
        from src.github_client import GitHubClient
        from src.storage import CommitStorage, get_commit_events_with_history
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
            print(json.dumps({
                "streak": streak_info,
                "stats": stats,
                "commit_count": len(commit_events),
            }, default=str))
        except GitHubClientError as e:
            print(json.dumps({"error": str(e), "code": 1}))
            raise typer.Exit(1)
    else:
        result = _run_dashboard()
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
# Typer entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
