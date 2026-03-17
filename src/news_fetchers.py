"""
Fetch AI news from multiple sources (Hacker News, Reddit, arXiv).

Each fetcher catches exceptions internally and returns a FetchResult
with success=False on failure, so one source failing never kills the digest.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import requests

_TIMEOUT = 15


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    score: int = 0
    comment_count: int = 0
    published_at: str = ""
    subreddit: str = ""
    summary: str = ""


@dataclass
class FetchResult:
    source: str
    items: list[NewsItem] = field(default_factory=list)
    success: bool = True
    error: str = ""


def fetch_hackernews(hours_back: int = 24, min_points: int = 10, limit: int = 25) -> FetchResult:
    """Fetch recent AI stories from Hacker News via Algolia API."""
    try:
        cutoff = int(datetime.now(timezone.utc).timestamp()) - (hours_back * 3600)
        params = {
            "query": "AI",
            "tags": "story",
            "numericFilters": f"created_at_i>{cutoff},points>{min_points}",
            "hitsPerPage": limit,
        }
        resp = requests.get(
            "https://hn.algolia.com/api/v1/search_by_date",
            params=params,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        items = []
        for hit in data.get("hits", []):
            items.append(NewsItem(
                title=hit.get("title", ""),
                url=hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}",
                source="hackernews",
                score=hit.get("points", 0),
                comment_count=hit.get("num_comments", 0),
                published_at=hit.get("created_at", ""),
            ))

        items.sort(key=lambda x: x.score, reverse=True)
        return FetchResult(source="hackernews", items=items)

    except Exception as e:
        return FetchResult(source="hackernews", success=False, error=str(e))


_DEFAULT_SUBREDDITS = ["artificial", "MachineLearning", "LocalLLaMA"]


def fetch_reddit(
    subreddits: Optional[list[str]] = None,
    limit: int = 25,
) -> FetchResult:
    """Fetch top daily posts from AI subreddits."""
    subs = subreddits or _DEFAULT_SUBREDDITS
    headers = {"User-Agent": "code-daily/0.1 AI-news-digest"}
    all_items: list[NewsItem] = []
    errors: list[str] = []

    for i, sub in enumerate(subs):
        if i > 0:
            time.sleep(0.5)
        try:
            resp = requests.get(
                f"https://www.reddit.com/r/{sub}/top.json",
                params={"t": "day", "limit": limit},
                headers=headers,
                timeout=_TIMEOUT,
            )
            if resp.status_code == 429:
                errors.append(f"r/{sub}: rate limited (429)")
                continue
            resp.raise_for_status()
            data = resp.json()

            for post in data.get("data", {}).get("children", []):
                d = post.get("data", {})
                all_items.append(NewsItem(
                    title=d.get("title", ""),
                    url=f"https://reddit.com{d.get('permalink', '')}",
                    source="reddit",
                    score=d.get("score", 0),
                    comment_count=d.get("num_comments", 0),
                    published_at=datetime.fromtimestamp(
                        d.get("created_utc", 0), tz=timezone.utc
                    ).isoformat(),
                    subreddit=f"r/{sub}",
                ))
        except Exception as e:
            errors.append(f"r/{sub}: {e}")

    all_items.sort(key=lambda x: x.score, reverse=True)

    if not all_items and errors:
        return FetchResult(source="reddit", success=False, error="; ".join(errors))

    result = FetchResult(source="reddit", items=all_items)
    if errors:
        result.error = "; ".join(errors)
    return result


def fetch_arxiv(max_results: int = 20) -> FetchResult:
    """Fetch recent AI/ML papers from arXiv Atom API."""
    try:
        import xml.etree.ElementTree as ET

        params = {
            "search_query": "cat:cs.AI+OR+cat:cs.LG",
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": max_results,
        }
        resp = requests.get(
            "https://export.arxiv.org/api/query",
            params=params,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(resp.text)

        items = []
        for entry in root.findall("atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            title = title_el.text.strip().replace("\n", " ") if title_el is not None and title_el.text else ""

            link_el = entry.find("atom:id", ns)
            url = link_el.text.strip() if link_el is not None and link_el.text else ""

            summary_el = entry.find("atom:summary", ns)
            summary = ""
            if summary_el is not None and summary_el.text:
                summary = summary_el.text.strip().replace("\n", " ")[:300]

            published_el = entry.find("atom:published", ns)
            published = published_el.text.strip() if published_el is not None and published_el.text else ""

            items.append(NewsItem(
                title=title,
                url=url,
                source="arxiv",
                published_at=published,
                summary=summary,
            ))

        return FetchResult(source="arxiv", items=items)

    except Exception as e:
        return FetchResult(source="arxiv", success=False, error=str(e))
