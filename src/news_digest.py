"""
Orchestrator for AI news digest: collects from multiple sources,
deduplicates, and writes a formatted digest to the Obsidian vault.
"""

import os
from dataclasses import asdict
from datetime import date

from src.news_fetchers import (
    FetchResult,
    fetch_arxiv,
    fetch_hackernews,
    fetch_reddit,
)

_FETCHERS = {
    "hackernews": fetch_hackernews,
    "reddit": fetch_reddit,
    "arxiv": fetch_arxiv,
}


def collect_news(
    sources: list[str] | None = None,
    hours_back: int = 24,
    limit: int = 25,
) -> dict:
    """Fetch news from selected sources, deduplicate, and return structured data."""
    active = sources or list(_FETCHERS.keys())
    results: dict[str, FetchResult] = {}

    for name in active:
        fetcher = _FETCHERS.get(name)
        if not fetcher:
            results[name] = FetchResult(source=name, success=False, error=f"Unknown source: {name}")
            continue
        if name == "hackernews":
            results[name] = fetcher(hours_back=hours_back, limit=limit)
        elif name == "reddit":
            results[name] = fetcher(limit=limit)
        elif name == "arxiv":
            results[name] = fetcher(max_results=limit)
        else:
            results[name] = fetcher()

    # Merge and deduplicate by URL
    seen_urls: set[str] = set()
    all_items = []
    for res in results.values():
        for item in res.items:
            if item.url not in seen_urls:
                seen_urls.add(item.url)
                all_items.append(item)

    all_items.sort(key=lambda x: x.score, reverse=True)

    source_meta = {}
    for name, res in results.items():
        source_meta[name] = {
            "count": len(res.items),
            "success": res.success,
            "error": res.error,
        }

    return {
        "date": date.today().isoformat(),
        "sources": source_meta,
        "items": [asdict(it) for it in all_items],
        "total_count": len(all_items),
        "vault_file": "",
    }


def write_digest_to_vault(vault_path: str, digest: dict) -> str:
    """Write markdown digest to the Obsidian vault. Returns relative file path."""
    digest_date = digest["date"]
    source_names = sorted(digest["sources"].keys())
    items = digest["items"]

    # Group items by source
    by_source: dict[str, list[dict]] = {}
    for item in items:
        by_source.setdefault(item["source"], []).append(item)

    lines = [
        "---",
        f"date: {digest_date}",
        f"tags: [ai-news, digest, daily]",
        f"sources: [{', '.join(source_names)}]",
        f"total_items: {digest['total_count']}",
        "---",
        "",
        f"# AI News Digest — {digest_date}",
        "",
    ]

    # Hacker News section
    if "hackernews" in by_source:
        lines.append("## Hacker News")
        lines.append("| Score | Title |")
        lines.append("|-------|-------|")
        for item in by_source["hackernews"]:
            title_link = f"[{_escape_pipe(item['title'])}]({item['url']})"
            lines.append(f"| {item['score']} | {title_link} |")
        lines.append("")

    # Reddit section
    if "reddit" in by_source:
        lines.append("## Reddit")
        lines.append("| Score | Subreddit | Title |")
        lines.append("|-------|-----------|-------|")
        for item in by_source["reddit"]:
            title_link = f"[{_escape_pipe(item['title'])}]({item['url']})"
            lines.append(f"| {item['score']} | {item.get('subreddit', '')} | {title_link} |")
        lines.append("")

    # arXiv section
    if "arxiv" in by_source:
        lines.append("## arXiv")
        lines.append("| Title | Summary |")
        lines.append("|-------|---------|")
        for item in by_source["arxiv"]:
            title_link = f"[{_escape_pipe(item['title'])}]({item['url']})"
            summary = _escape_pipe(item.get("summary", ""))
            lines.append(f"| {title_link} | {summary} |")
        lines.append("")

    rel_path = f"ai-news/{digest_date}.md"
    full_path = os.path.join(vault_path, rel_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    with open(full_path, "w") as f:
        f.write("\n".join(lines))

    return rel_path


def write_synthesized_digest_to_vault(vault_path: str, digest: dict, synthesis: dict) -> str:
    """Write themed synthesized digest to the Obsidian vault. Returns relative file path."""
    digest_date = digest["date"]
    source_names = sorted(digest["sources"].keys())

    lines = [
        "---",
        f"date: {digest_date}",
        "tags: [ai-news, digest, daily, synthesized]",
        f"sources: [{', '.join(source_names)}]",
        f"total_items: {digest['total_count']}",
        "---",
        "",
        f"# AI News Digest — {digest_date}",
        "",
        "## Overview",
        synthesis.get("overview", ""),
        "",
    ]

    for section in synthesis.get("sections", []):
        lines.append(f"## {section['name']}")
        if section.get("summary"):
            lines.append(section["summary"])
            lines.append("")

        for item in section.get("items", []):
            title = item.get("title", "")
            url = item.get("url", "")
            source = item.get("source", "")
            score = item.get("score", 0)
            commentary = item.get("commentary", "")

            # Build source/score tag
            meta_parts = []
            if source:
                meta_parts.append(source.capitalize())
            if score:
                meta_parts.append(f"{score}pts")
            meta_str = f" ({', '.join(meta_parts)})" if meta_parts else ""

            comment_str = f" — {commentary}" if commentary else ""
            lines.append(f"- [{title}]({url}){meta_str}{comment_str}")

        lines.append("")

    rel_path = f"ai-news/{digest_date}.md"
    full_path = os.path.join(vault_path, rel_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    with open(full_path, "w") as f:
        f.write("\n".join(lines))

    return rel_path


def _escape_pipe(text: str) -> str:
    """Escape pipe characters for markdown tables."""
    return text.replace("|", "\\|")
