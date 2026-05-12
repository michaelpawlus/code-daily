"""
Collect seed data for news-informed project idea generation.

Gathers trending topics from the news digest, user interests from the
Obsidian vault, and recent commit domains -- structured for Claude Code
to synthesize into project ideas in-session.
"""

import os
from datetime import date, datetime, timedelta, timezone

from src.news_digest import collect_news
from src.storage import CommitStorage


def collect_idea_seeds(
    digest: dict | None = None,
    hours_back: int = 24,
    limit: int = 25,
) -> dict:
    """Collect raw materials for project idea generation.

    Args:
        digest: Pre-fetched news digest. If None, fetches fresh.
        hours_back: Hours back for news fetch (if fetching fresh).
        limit: Max items per news source.

    Returns:
        Dict with trending_topics, user_interests, recent_domains,
        target_profile, collected_at.
    """
    if digest is None:
        digest = collect_news(hours_back=hours_back, limit=limit)

    # Extract top trending topics (top 15 items by score)
    items = digest.get("items", [])
    trending = items[:15]

    # Get user interests from vault
    user_interests = _get_user_interests()

    # Get recent commit domains for diversity
    storage = CommitStorage()
    recent_domains = get_recent_commit_domains(storage, days=30)

    return {
        "trending_topics": trending,
        "trending_count": len(trending),
        "user_interests": user_interests,
        "recent_domains": recent_domains,
        "target_profile": {
            "focus": "AI-native companies, agentic coding tools",
            "skills_to_show": [
                "CLI tooling", "data engineering", "ML infrastructure",
                "full-stack web", "API design", "agent workflows",
            ],
        },
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "digest_date": digest.get("date", date.today().isoformat()),
    }


def get_recent_commit_domains(storage: CommitStorage, days: int = 30) -> list[str]:
    """Extract repo/project names from recent commits for diversity scoring."""
    since = (date.today() - timedelta(days=days)).isoformat()
    commits = storage.get_commits_since(since)
    return list({c["repo"] for c in commits if c.get("repo")})


def _get_user_interests() -> list[dict]:
    """Load user interests from Obsidian vault project ideas."""
    vault_path = os.environ.get("OBSIDIAN_VAULT_PATH", "")
    if not vault_path:
        return []

    try:
        from src.obsidian_scanner import scan_project_ideas

        ideas = scan_project_ideas(vault_path)
        return [
            {"title": idea.content[:120], "source_file": idea.source_file}
            for idea in ideas[:10]
        ]
    except Exception:
        return []


_IDEAS_FOLDER = "project-ideas"


def _build_project_ideas(ideas: dict) -> dict:
    """Build the news-informed ideas artifact: body + oj metadata."""
    today = date.today().isoformat()
    generated_from = ideas.get("generated_from", today)

    lines = [
        f"# News-Informed Project Ideas -- {today}",
        "",
    ]

    for i, idea in enumerate(ideas.get("ideas", []), 1):
        lines.extend([
            f"## {i}. {idea.get('title', 'Untitled')}",
            "",
            idea.get("description", ""),
            "",
            f"**Why now:** {idea.get('why_now', '')}",
            f"**Skills demonstrated:** {', '.join(idea.get('skills_demonstrated', []))}",
            f"**Complexity:** {idea.get('complexity', 'unknown')}",
            f"**Trending source:** {idea.get('trending_source', '')}",
            "",
        ])

    return {
        "title": today,
        "body": "\n".join(lines),
        "folder": _IDEAS_FOLDER,
        "date": today,
        "tags": ["project-idea", "news-informed", "daily"],
        "extra": {"generated_from": generated_from},
    }


def write_project_ideas_to_vault(vault_path: str, ideas: dict) -> str:
    """Write synthesized project ideas to the Obsidian vault via ``oj capture``.

    Args:
        vault_path: Path to the Obsidian vault root.
        ideas: Synthesized ideas dict with structure:
            {
                "ideas": [
                    {
                        "title": str,
                        "description": str,
                        "why_now": str,
                        "skills_demonstrated": [str],
                        "trending_source": str,
                        "complexity": str,  # "weekend", "week", "multi-week"
                    }
                ],
                "generated_from": str,  # date of news digest used
            }

    Returns:
        Relative vault path of the written file.
    """
    from src import oj_client

    artifact = _build_project_ideas(ideas)
    return oj_client.capture(
        title=artifact["title"],
        body=artifact["body"],
        folder=artifact["folder"],
        date=artifact["date"],
        tags=artifact["tags"],
        extra=artifact["extra"],
        vault_path=vault_path,
        overwrite=True,
    )
