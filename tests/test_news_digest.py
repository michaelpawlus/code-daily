"""Tests for news_digest orchestrator and vault writer."""

import os
from unittest.mock import patch

import pytest

from src.news_digest import collect_news, write_digest_to_vault, write_synthesized_digest_to_vault
from src.news_fetchers import FetchResult, NewsItem


# ---------------------------------------------------------------------------
# collect_news
# ---------------------------------------------------------------------------

def _mock_hn(**kwargs):
    return FetchResult(source="hackernews", items=[
        NewsItem(title="HN Story", url="https://example.com/hn", source="hackernews", score=50),
    ])


def _mock_reddit(**kwargs):
    return FetchResult(source="reddit", items=[
        NewsItem(title="Reddit Post", url="https://reddit.com/r/ai/1", source="reddit", score=30, subreddit="r/artificial"),
        # Duplicate URL to test dedup
        NewsItem(title="HN Story (crosspost)", url="https://example.com/hn", source="reddit", score=10),
    ])


def _mock_arxiv(**kwargs):
    return FetchResult(source="arxiv", items=[
        NewsItem(title="Paper", url="https://arxiv.org/abs/1", source="arxiv", summary="Abstract text here"),
    ])


def _mock_fail(**kwargs):
    return FetchResult(source="hackernews", success=False, error="API down")


@patch.dict("src.news_digest._FETCHERS", {"hackernews": _mock_hn, "reddit": _mock_reddit, "arxiv": _mock_arxiv})
def test_collect_news_all_sources():
    digest = collect_news()
    assert digest["total_count"] == 3  # 1 HN + 2 Reddit - 1 dedup = 3
    assert digest["sources"]["hackernews"]["success"] is True
    assert digest["sources"]["reddit"]["count"] == 2
    # Items sorted by score descending
    assert digest["items"][0]["score"] >= digest["items"][1]["score"]


@patch.dict("src.news_digest._FETCHERS", {"hackernews": _mock_hn})
def test_collect_news_single_source():
    digest = collect_news(sources=["hackernews"])
    assert "hackernews" in digest["sources"]
    assert "reddit" not in digest["sources"]
    assert digest["total_count"] == 1


@patch.dict("src.news_digest._FETCHERS", {"hackernews": _mock_fail})
def test_collect_news_source_failure():
    digest = collect_news(sources=["hackernews"])
    assert digest["sources"]["hackernews"]["success"] is False
    assert digest["total_count"] == 0


def test_collect_news_unknown_source():
    digest = collect_news(sources=["unknown_source"])
    assert digest["sources"]["unknown_source"]["success"] is False
    assert "Unknown" in digest["sources"]["unknown_source"]["error"]


# ---------------------------------------------------------------------------
# write_digest_to_vault
# ---------------------------------------------------------------------------


def test_write_digest_to_vault(tmp_path):
    digest = {
        "date": "2026-03-16",
        "sources": {"hackernews": {"count": 1, "success": True, "error": ""}},
        "items": [
            {
                "title": "Test Story",
                "url": "https://example.com",
                "source": "hackernews",
                "score": 42,
                "comment_count": 5,
                "published_at": "2026-03-16T00:00:00Z",
                "subreddit": "",
                "summary": "",
            }
        ],
        "total_count": 1,
        "vault_file": "",
    }

    rel_path = write_digest_to_vault(str(tmp_path), digest)
    assert rel_path == "ai-news/2026-03-16.md"

    full_path = tmp_path / "ai-news" / "2026-03-16.md"
    assert full_path.exists()

    content = full_path.read_text()
    assert "date: 2026-03-16" in content
    assert "tags: [ai-news, digest, daily]" in content
    assert "## Hacker News" in content
    assert "[Test Story](https://example.com)" in content
    assert "| 42 |" in content


def test_write_digest_pipe_escape(tmp_path):
    digest = {
        "date": "2026-03-16",
        "sources": {"arxiv": {"count": 1, "success": True, "error": ""}},
        "items": [
            {
                "title": "A | B comparison",
                "url": "https://arxiv.org/1",
                "source": "arxiv",
                "score": 0,
                "comment_count": 0,
                "published_at": "",
                "subreddit": "",
                "summary": "X | Y results",
            }
        ],
        "total_count": 1,
        "vault_file": "",
    }

    write_digest_to_vault(str(tmp_path), digest)
    content = (tmp_path / "ai-news" / "2026-03-16.md").read_text()
    assert "A \\| B comparison" in content
    assert "X \\| Y results" in content


# ---------------------------------------------------------------------------
# write_synthesized_digest_to_vault
# ---------------------------------------------------------------------------


def test_write_synthesized_digest_to_vault(tmp_path):
    digest = {
        "date": "2026-03-17",
        "sources": {
            "hackernews": {"count": 2, "success": True, "error": ""},
            "arxiv": {"count": 1, "success": True, "error": ""},
        },
        "total_count": 3,
    }

    synthesis = {
        "overview": "Today was dominated by GPT-5 and new tooling.",
        "sections": [
            {
                "name": "Industry & Labs",
                "slug": "industry-labs",
                "summary": "Big releases from labs.",
                "items": [
                    {
                        "title": "GPT-5 Released",
                        "url": "https://example.com/1",
                        "source": "hackernews",
                        "score": 100,
                        "commentary": "Major release.",
                    }
                ],
            },
            {
                "name": "Challenge Your Thinking",
                "slug": "challenge-your-thinking",
                "summary": "Consider another angle.",
                "items": [
                    {
                        "title": "AI Skeptic View",
                        "url": "https://example.com/2",
                        "source": "reddit",
                        "score": 30,
                        "commentary": "Worth considering.",
                    }
                ],
            },
        ],
    }

    rel_path = write_synthesized_digest_to_vault(str(tmp_path), digest, synthesis)
    assert rel_path == "ai-news/2026-03-17.md"

    full_path = tmp_path / "ai-news" / "2026-03-17.md"
    assert full_path.exists()

    content = full_path.read_text()
    assert "date: 2026-03-17" in content
    assert "tags: [ai-news, digest, daily, synthesized]" in content
    assert "## Overview" in content
    assert "Today was dominated by GPT-5" in content
    assert "## Industry & Labs" in content
    assert "[GPT-5 Released](https://example.com/1)" in content
    assert "100pts" in content
    assert "Major release." in content
    assert "## Challenge Your Thinking" in content
    assert "[AI Skeptic View](https://example.com/2)" in content
