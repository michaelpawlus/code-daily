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
app.add_typer(issues_app, name="issues")
app.add_typer(vault_app, name="vault")
app.add_typer(notify_app, name="notify")


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
# suggest command
# ---------------------------------------------------------------------------


@app.command()
def suggest(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Suggest the best thing to work on next, combining all sources."""
    from src.gh_issues import get_assigned_issues, prioritize_issues
    from src.obsidian_scanner import scan_vault

    candidates: list[dict] = []

    # GitHub issues
    try:
        issues = get_assigned_issues(limit=20)
        ranked = prioritize_issues(issues)
        for r in ranked:
            iss = r["issue"]
            score = r["score"]
            # Bugs get extra weight
            candidates.append({
                "source": "github",
                "title": f"#{iss.number} {iss.title}",
                "url": iss.url,
                "score": score,
                "reason": _issue_reason(iss, score),
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
                candidates.append({
                    "source": "obsidian",
                    "title": item.content,
                    "url": item.source_file,
                    "score": score,
                    "reason": _obsidian_reason(item, score),
                })
        except Exception:
            pass

    # Cross-source variety bonus
    sources_present = {c["source"] for c in candidates}
    if len(sources_present) > 1:
        for c in candidates:
            c["score"] += 3

    candidates.sort(key=lambda c: c["score"], reverse=True)
    top = candidates[:5]

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
def cron():
    """Print crontab entries for the escalating notification schedule."""
    from src.main import _run_setup_cron

    _run_setup_cron()


# ---------------------------------------------------------------------------
# Typer entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
