"""
GitHub issues via `gh` CLI subprocess.

Fetches assigned issues and search results using the GitHub CLI,
parses JSON output, and provides priority scoring.
"""

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class GhIssue:
    """A GitHub issue fetched via gh CLI."""

    number: int
    title: str
    url: str
    repository: str
    labels: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    comments: int = 0


def check_gh_auth() -> dict:
    """Check if gh CLI is authenticated.

    Returns:
        dict with 'authenticated' bool and 'message' str.
    """
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return {
            "authenticated": result.returncode == 0,
            "message": result.stdout.strip() or result.stderr.strip(),
        }
    except FileNotFoundError:
        return {
            "authenticated": False,
            "message": "gh CLI not found. Install from https://cli.github.com/",
        }
    except subprocess.TimeoutExpired:
        return {"authenticated": False, "message": "gh auth status timed out"}


def get_assigned_issues(
    limit: int = 30, labels: str | None = None, repo: str | None = None
) -> list[GhIssue]:
    """Fetch open issues assigned to the current user.

    Args:
        limit: Max issues to return.
        labels: Comma-separated label filter.
        repo: Filter to a specific repo (owner/name).

    Returns:
        List of GhIssue objects.
    """
    cmd = [
        "gh",
        "issue",
        "list",
        "--assignee=@me",
        "--state=open",
        "--json=number,title,url,repository,labels,createdAt,updatedAt,comments",
        f"--limit={limit}",
    ]
    if labels:
        cmd.append(f"--label={labels}")
    if repo:
        cmd.extend(["-R", repo])

    return _run_gh(cmd)


def search_issues(query: str, limit: int = 20) -> list[GhIssue]:
    """Search GitHub issues using gh search.

    Args:
        query: Search query string.
        limit: Max results.

    Returns:
        List of GhIssue objects.
    """
    cmd = [
        "gh",
        "search",
        "issues",
        query,
        "--assignee=@me",
        "--state=open",
        "--json=number,title,url,repository,labels,createdAt,updatedAt,comments",
        f"--limit={limit}",
    ]
    return _run_gh(cmd)


def _run_gh(cmd: list[str]) -> list[GhIssue]:
    """Run a gh command and parse the JSON output into GhIssue objects."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
    except FileNotFoundError:
        return []
    except subprocess.TimeoutExpired:
        return []

    if result.returncode != 0:
        return []

    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    return [_parse_issue(item) for item in raw]


def _parse_issue(item: dict) -> GhIssue:
    """Parse a single JSON object from gh output into a GhIssue."""
    repo = item.get("repository", {})
    repo_name = repo.get("nameWithOwner", "") if isinstance(repo, dict) else str(repo)

    labels_raw = item.get("labels", [])
    label_names = []
    for lb in labels_raw:
        if isinstance(lb, dict):
            label_names.append(lb.get("name", ""))
        else:
            label_names.append(str(lb))

    comments_raw = item.get("comments", [])
    comment_count = len(comments_raw) if isinstance(comments_raw, list) else int(comments_raw or 0)

    return GhIssue(
        number=item.get("number", 0),
        title=item.get("title", ""),
        url=item.get("url", ""),
        repository=repo_name,
        labels=label_names,
        created_at=item.get("createdAt", ""),
        updated_at=item.get("updatedAt", ""),
        comments=comment_count,
    )


def prioritize_issues(issues: list[GhIssue]) -> list[dict]:
    """Score and sort issues by priority.

    Scoring:
        - bug label: +5
        - feature/enhancement label: +2
        - Age > 7 days: +3
        - Has comments (activity): +1
        - High comment count (>3): +2

    Returns:
        List of dicts with 'issue' and 'score', sorted descending.
    """
    scored = []
    bug_labels = {"bug", "critical", "urgent", "p0", "p1"}
    feature_labels = {"feature", "enhancement", "feature-request"}

    for issue in issues:
        score = 0
        lower_labels = {lb.lower() for lb in issue.labels}

        if lower_labels & bug_labels:
            score += 5
        elif lower_labels & feature_labels:
            score += 2

        if issue.created_at:
            try:
                created = datetime.fromisoformat(issue.created_at.replace("Z", "+00:00"))
                age_days = (datetime.now(created.tzinfo) - created).days
                if age_days > 7:
                    score += 3
            except (ValueError, TypeError):
                pass

        if issue.comments > 0:
            score += 1
        if issue.comments > 3:
            score += 2

        scored.append({"issue": issue, "score": score})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored
