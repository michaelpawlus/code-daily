"""
Scan community subreddits for recurring problems and tool requests.

Picks random technically-oriented subreddits (outside of the AI subs used
by news_fetchers) and collects posts that signal pain points.  The raw data
is structured for Claude Code to synthesize in-session.
"""

import os
import random
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone

import requests

_TIMEOUT = 15

# Curated pool of fairly active, tech-oriented subreddits.
# Excludes the AI subs already used by news_fetchers ("artificial",
# "MachineLearning", "LocalLLaMA").
_COMMUNITY_SUBREDDITS = [
    # Dev / Engineering
    "sysadmin", "webdev", "datascience", "dataengineering",
    "devops", "selfhosted", "homelab", "learnprogramming",
    # Specific ecosystems
    "node", "django", "flask", "FastAPI", "golang", "rust",
    # Product / workflow
    "SideProject", "opensource", "commandline", "linux",
    # Data / analytics
    "analytics", "BusinessIntelligence",
]

# Words/phrases that signal a pain point or tool request.
_PROBLEM_KEYWORDS = [
    "how do i", "how can i", "is there a tool", "any tool",
    "struggling with", "frustrated", "workaround", "help with",
    "any alternatives", "alternative to", "looking for",
    "wish there was", "does anyone know", "best way to",
    "pain point", "annoying", "broken", "can't figure out",
]


@dataclass
class RedditPost:
    title: str
    url: str
    selftext: str
    score: int
    comment_count: int
    subreddit: str
    created_utc: str
    flair: str


def scan_subreddit_problems(
    subreddits: list[str] | None = None,
    count: int = 3,
    limit: int = 50,
    sort: str = "hot",
) -> dict:
    """Scan community subreddits for pain points and tool requests.

    Args:
        subreddits: Explicit subreddits to scan (overrides random pick).
        count: How many random subreddits to pick if not specified.
        limit: Max posts to fetch per subreddit.
        sort: Reddit sort order (hot, new, top).

    Returns:
        Dict with subreddits_scanned, problem_posts, all_posts, collected_at.
    """
    subs = subreddits or random.sample(
        _COMMUNITY_SUBREDDITS, min(count, len(_COMMUNITY_SUBREDDITS))
    )

    all_posts: list[dict] = []
    problem_posts: list[dict] = []
    errors: list[str] = []

    for i, sub in enumerate(subs):
        if i > 0:
            time.sleep(1.0)  # conservative rate limit
        posts, error = _fetch_subreddit_posts(sub, limit=limit, sort=sort)
        if error:
            errors.append(error)
        for post in posts:
            post_dict = asdict(post)
            all_posts.append(post_dict)
            if _is_problem_signal(post):
                post_dict["problem_signal"] = True
                problem_posts.append(post_dict)

    return {
        "subreddits_scanned": subs,
        "problem_posts": problem_posts,
        "problem_count": len(problem_posts),
        "all_posts": all_posts,
        "total_count": len(all_posts),
        "errors": errors,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


def _fetch_subreddit_posts(
    subreddit: str, limit: int = 50, sort: str = "hot"
) -> tuple[list[RedditPost], str]:
    """Fetch posts from a single subreddit via public JSON API.

    Returns (posts, error_message). Error is empty string on success.
    """
    headers = {"User-Agent": "code-daily/0.1 community-scanner"}
    try:
        url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
        params = {"limit": limit}
        if sort == "top":
            params["t"] = "day"

        resp = requests.get(url, params=params, headers=headers, timeout=_TIMEOUT)
        if resp.status_code == 429:
            return [], f"r/{subreddit}: rate limited (429)"
        resp.raise_for_status()
        data = resp.json()

        posts = []
        for child in data.get("data", {}).get("children", []):
            d = child.get("data", {})
            selftext = d.get("selftext", "") or ""
            posts.append(RedditPost(
                title=d.get("title", ""),
                url=f"https://reddit.com{d.get('permalink', '')}",
                selftext=selftext[:500],
                score=d.get("score", 0),
                comment_count=d.get("num_comments", 0),
                subreddit=f"r/{subreddit}",
                created_utc=datetime.fromtimestamp(
                    d.get("created_utc", 0), tz=timezone.utc
                ).isoformat(),
                flair=d.get("link_flair_text", "") or "",
            ))
        return posts, ""

    except Exception as e:
        return [], f"r/{subreddit}: {e}"


def _is_problem_signal(post: RedditPost) -> bool:
    """Heuristic: does this post indicate a pain point?"""
    title_lower = post.title.lower()
    text_lower = post.selftext.lower()
    flair_lower = post.flair.lower()

    # Keyword match in title or body
    for kw in _PROBLEM_KEYWORDS:
        if kw in title_lower or kw in text_lower:
            return True

    # Flair signals
    if any(f in flair_lower for f in ("question", "help", "support", "discussion")):
        return True

    # High comment:score ratio suggests many people chiming in with the same issue
    if post.score > 0 and post.comment_count > 0:
        ratio = post.comment_count / post.score
        if ratio > 2.0 and post.comment_count >= 10:
            return True

    return False


def write_reddit_scan_to_vault(vault_path: str, scan: dict, synthesis: dict) -> str:
    """Write synthesized Reddit problem analysis to the Obsidian vault.

    Args:
        vault_path: Path to the Obsidian vault root.
        scan: Raw scan data from scan_subreddit_problems().
        synthesis: Agent-synthesized analysis with structure:
            {
                "subreddit": str,
                "problem_summary": str,
                "evidence_posts": [{"title", "url", "comment_count"}],
                "project_idea": {
                    "title": str,
                    "description": str,
                    "why_build_it": str,
                    "target_users": str,
                    "skills_demonstrated": [str],
                }
            }

    Returns:
        Relative vault path of the written file.
    """
    today = date.today().isoformat()
    subs = ", ".join(scan.get("subreddits_scanned", []))

    lines = [
        "---",
        f"date: {today}",
        "tags: [project-idea, reddit-scan, community-problems]",
        f"subreddits: [{subs}]",
        "---",
        "",
        f"# Reddit Community Problem Scan -- {today}",
        "",
        f"**Subreddits scanned:** {subs}",
        f"**Problem posts found:** {scan.get('problem_count', 0)} / {scan.get('total_count', 0)}",
        "",
        "## Problem Summary",
        synthesis.get("problem_summary", ""),
        "",
        "## Evidence",
        "",
    ]

    for post in synthesis.get("evidence_posts", []):
        title = post.get("title", "")
        url = post.get("url", "")
        comments = post.get("comment_count", 0)
        lines.append(f"- [{title}]({url}) ({comments} comments)")

    lines.append("")

    idea = synthesis.get("project_idea", {})
    lines.extend([
        "## Project Idea",
        "",
        f"### {idea.get('title', 'Untitled')}",
        "",
        idea.get("description", ""),
        "",
        f"**Why build it:** {idea.get('why_build_it', '')}",
        f"**Target users:** {idea.get('target_users', '')}",
        f"**Skills demonstrated:** {', '.join(idea.get('skills_demonstrated', []))}",
        "",
    ])

    rel_path = f"project-ideas/reddit-scan-{today}.md"
    full_path = os.path.join(vault_path, rel_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    with open(full_path, "w") as f:
        f.write("\n".join(lines))

    return rel_path
