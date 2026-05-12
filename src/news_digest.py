"""
Orchestrator for AI news digest: collects from multiple sources,
deduplicates, and writes a formatted digest to the Obsidian vault.

Vault writes are routed through ``oj capture`` (see ``src/oj_client.py``)
so ``obsidian_journal`` remains the household writer-of-record. The
``_build_*`` helpers are pure functions that return the body markdown +
frontmatter metadata and are independently unit-testable.
"""

import os
from dataclasses import asdict
from datetime import date

from src import oj_client
from src.news_fetchers import (
    FetchResult,
    fetch_arxiv,
    fetch_hackernews,
    fetch_reddit,
)

_DIGEST_FOLDER = "ai-news"

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


def _build_raw_digest(digest: dict) -> dict:
    """Build the raw (pre-synthesis) digest artifact: body + oj metadata.

    Returns a dict with keys ``title``, ``body``, ``folder``, ``date``,
    ``tags``, ``extra`` — ready to hand to ``oj_client.capture(**artifact)``
    (after popping any keys it doesn't accept).
    """
    digest_date = digest["date"]
    source_names = sorted(digest["sources"].keys())
    items = digest["items"]

    by_source: dict[str, list[dict]] = {}
    for item in items:
        by_source.setdefault(item["source"], []).append(item)

    lines = [
        f"# AI News Digest — {digest_date}",
        "",
    ]

    if "hackernews" in by_source:
        lines.append("## Hacker News")
        lines.append("| Score | Title |")
        lines.append("|-------|-------|")
        for item in by_source["hackernews"]:
            title_link = f"[{_escape_pipe(item['title'])}]({item['url']})"
            lines.append(f"| {item['score']} | {title_link} |")
        lines.append("")

    if "reddit" in by_source:
        lines.append("## Reddit")
        lines.append("| Score | Subreddit | Title |")
        lines.append("|-------|-----------|-------|")
        for item in by_source["reddit"]:
            title_link = f"[{_escape_pipe(item['title'])}]({item['url']})"
            lines.append(f"| {item['score']} | {item.get('subreddit', '')} | {title_link} |")
        lines.append("")

    if "arxiv" in by_source:
        lines.append("## arXiv")
        lines.append("| Title | Summary |")
        lines.append("|-------|---------|")
        for item in by_source["arxiv"]:
            title_link = f"[{_escape_pipe(item['title'])}]({item['url']})"
            summary = _escape_pipe(item.get("summary", ""))
            lines.append(f"| {title_link} | {summary} |")
        lines.append("")

    return {
        "title": digest_date,
        "body": "\n".join(lines),
        "folder": _DIGEST_FOLDER,
        "date": digest_date,
        "tags": ["ai-news", "digest", "daily"],
        "extra": {
            "sources": ", ".join(source_names),
            "total_items": str(digest["total_count"]),
        },
    }


def write_digest_to_vault(vault_path: str, digest: dict) -> str:
    """Write raw markdown digest to the Obsidian vault via ``oj capture``."""
    artifact = _build_raw_digest(digest)
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


def _build_synthesized_digest(digest: dict, synthesis: dict) -> dict:
    """Build the themed/synthesized digest artifact: body + oj metadata."""
    digest_date = digest["date"]
    source_names = sorted(digest["sources"].keys())

    lines = [
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

            meta_parts = []
            if source:
                meta_parts.append(source.capitalize())
            if score:
                meta_parts.append(f"{score}pts")
            meta_str = f" ({', '.join(meta_parts)})" if meta_parts else ""

            comment_str = f" — {commentary}" if commentary else ""
            lines.append(f"- [{title}]({url}){meta_str}{comment_str}")

        lines.append("")

    return {
        "title": digest_date,
        "body": "\n".join(lines),
        "folder": _DIGEST_FOLDER,
        "date": digest_date,
        "tags": ["ai-news", "digest", "daily", "synthesized"],
        "extra": {
            "sources": ", ".join(source_names),
            "total_items": str(digest["total_count"]),
        },
    }


def write_synthesized_digest_to_vault(vault_path: str, digest: dict, synthesis: dict) -> str:
    """Write themed synthesized digest to the Obsidian vault via ``oj capture``."""
    artifact = _build_synthesized_digest(digest, synthesis)
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


def read_digest_from_vault(vault_path: str, digest_date: str | None = None) -> dict | None:
    """Read and parse a synthesized digest from the Obsidian vault.

    Args:
        vault_path: Path to the Obsidian vault root.
        digest_date: ISO date string (e.g. "2026-03-29"). Defaults to today.

    Returns:
        Parsed digest dict with overview, sections, and metadata, or None if not found.
    """
    import re

    if digest_date is None:
        digest_date = date.today().isoformat()

    file_path = os.path.join(vault_path, "ai-news", f"{digest_date}.md")
    if not os.path.exists(file_path):
        return None

    with open(file_path) as f:
        content = f.read()

    # Parse frontmatter (handles both legacy flow-style `tags: [a, b]` and
    # the block-style YAML that `oj capture` emits)
    frontmatter: dict = {}
    body = content
    fm_match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    if fm_match:
        frontmatter = _parse_yaml_lite(fm_match.group(1))
        body = content[fm_match.end():]

    tags_value = frontmatter.get("tags", [])
    if isinstance(tags_value, list):
        is_synthesized = "synthesized" in tags_value
    else:
        is_synthesized = "synthesized" in str(tags_value)

    # Parse sections
    sections: list[dict] = []
    overview = ""

    # Split by ## headings
    section_splits = re.split(r"^## (.+)$", body, flags=re.MULTILINE)
    # section_splits: [preamble, heading1, body1, heading2, body2, ...]

    for i in range(1, len(section_splits), 2):
        heading = section_splits[i].strip()
        section_body = section_splits[i + 1].strip() if i + 1 < len(section_splits) else ""

        if heading == "Overview":
            overview = section_body
            continue

        # Parse items from bullet list
        items: list[dict] = []
        summary_lines: list[str] = []
        for line in section_body.splitlines():
            line = line.strip()
            if not line:
                continue
            # Match: - [title](url) (Source, Npts) — commentary
            item_match = re.match(
                r"^- \[(.+?)\]\((.+?)\)\s*(?:\(([^)]*)\))?\s*(?:—\s*(.+))?$",
                line,
            )
            if item_match:
                title, url, meta, commentary = item_match.groups()
                source = ""
                score = 0
                if meta:
                    meta_parts = [p.strip() for p in meta.split(",")]
                    for part in meta_parts:
                        if part.endswith("pts"):
                            try:
                                score = int(part.replace("pts", ""))
                            except ValueError:
                                pass
                        else:
                            source = part
                items.append({
                    "title": title,
                    "url": url,
                    "source": source,
                    "score": score,
                    "commentary": commentary or "",
                })
            elif not line.startswith("- ") and not line.startswith("|"):
                summary_lines.append(line)

        sections.append({
            "name": heading,
            "summary": " ".join(summary_lines),
            "items": items,
            "item_count": len(items),
        })

    # Check for podcast
    podcast_path = os.path.join(vault_path, "ai-news", "podcasts", f"{digest_date}.mp3")
    has_podcast = os.path.exists(podcast_path)

    return {
        "date": digest_date,
        "overview": overview,
        "sections": sections,
        "is_synthesized": is_synthesized,
        "has_podcast": has_podcast,
        "podcast_path": f"ai-news/podcasts/{digest_date}.mp3" if has_podcast else None,
        "total_items": sum(s["item_count"] for s in sections),
        "frontmatter": frontmatter,
    }


def _escape_pipe(text: str) -> str:
    """Escape pipe characters for markdown tables."""
    return text.replace("|", "\\|")


def _parse_yaml_lite(text: str) -> dict:
    """Tiny YAML subset parser for the frontmatter shapes oj + legacy code emit.

    Handles scalar values, single-quoted strings, flow-style lists
    (``tags: [a, b]``), and block-style lists (``tags:\\n- a\\n- b``). Anything
    else falls through as a raw string. Not a general-purpose YAML parser — just
    enough for vault frontmatter round-trips.
    """
    out: dict = {}
    current_list_key: str | None = None
    for raw in text.splitlines():
        if not raw.strip():
            current_list_key = None
            continue
        if raw.startswith("- ") and current_list_key:
            item = raw[2:].strip().strip("'\"")
            out[current_list_key].append(item)
            continue
        if ":" not in raw:
            current_list_key = None
            continue
        key, _, value = raw.partition(":")
        key = key.strip()
        value = value.strip()
        if not value:
            out[key] = []
            current_list_key = key
            continue
        current_list_key = None
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            out[key] = [p.strip() for p in inner.split(",") if p.strip()] if inner else []
        else:
            out[key] = value.strip("'\"")
    return out
