"""Tests for news_fetchers module — mock all HTTP requests."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.news_fetchers import (
    NewsItem,
    fetch_arxiv,
    fetch_hackernews,
    fetch_reddit,
)


# ---------------------------------------------------------------------------
# Hacker News
# ---------------------------------------------------------------------------

_HN_RESPONSE = {
    "hits": [
        {
            "objectID": "123",
            "title": "AI breakthrough",
            "url": "https://example.com/ai",
            "points": 42,
            "num_comments": 10,
            "created_at": "2026-03-16T00:00:00Z",
        },
        {
            "objectID": "124",
            "title": "LLM update",
            "url": None,
            "points": 20,
            "num_comments": 5,
            "created_at": "2026-03-16T01:00:00Z",
        },
    ]
}


@patch("src.news_fetchers.requests.get")
def test_fetch_hackernews_success(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _HN_RESPONSE
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    result = fetch_hackernews()
    assert result.success is True
    assert result.source == "hackernews"
    assert len(result.items) == 2
    assert result.items[0].score == 42
    # Item without URL falls back to HN link
    assert "news.ycombinator.com" in result.items[1].url


@patch("src.news_fetchers.requests.get", side_effect=Exception("timeout"))
def test_fetch_hackernews_failure(mock_get):
    result = fetch_hackernews()
    assert result.success is False
    assert "timeout" in result.error


# ---------------------------------------------------------------------------
# Reddit
# ---------------------------------------------------------------------------

_REDDIT_RESPONSE = {
    "data": {
        "children": [
            {
                "data": {
                    "title": "Cool ML paper",
                    "permalink": "/r/MachineLearning/comments/abc/cool",
                    "score": 89,
                    "num_comments": 15,
                    "created_utc": 1742083200,
                }
            }
        ]
    }
}


@patch("src.news_fetchers.time.sleep")
@patch("src.news_fetchers.requests.get")
def test_fetch_reddit_success(mock_get, mock_sleep):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _REDDIT_RESPONSE
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    result = fetch_reddit(subreddits=["MachineLearning"])
    assert result.success is True
    assert len(result.items) == 1
    assert result.items[0].subreddit == "r/MachineLearning"
    assert result.items[0].score == 89


@patch("src.news_fetchers.time.sleep")
@patch("src.news_fetchers.requests.get")
def test_fetch_reddit_429(mock_get, mock_sleep):
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.raise_for_status.side_effect = Exception("429")
    mock_get.return_value = mock_resp

    result = fetch_reddit(subreddits=["artificial"])
    assert result.success is False
    assert "rate limited" in result.error


@patch("src.news_fetchers.time.sleep")
@patch("src.news_fetchers.requests.get", side_effect=Exception("network error"))
def test_fetch_reddit_all_fail(mock_get, mock_sleep):
    result = fetch_reddit(subreddits=["artificial"])
    assert result.success is False
    assert "network error" in result.error


# ---------------------------------------------------------------------------
# arXiv
# ---------------------------------------------------------------------------

_ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Attention Is Still All You Need</title>
    <id>http://arxiv.org/abs/2603.12345</id>
    <summary>We show that transformers continue to dominate.</summary>
    <published>2026-03-15T00:00:00Z</published>
  </entry>
</feed>
"""


@patch("src.news_fetchers.requests.get")
def test_fetch_arxiv_success(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = _ARXIV_XML
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    result = fetch_arxiv()
    assert result.success is True
    assert len(result.items) == 1
    assert "Attention" in result.items[0].title
    assert result.items[0].source == "arxiv"
    assert result.items[0].summary.startswith("We show")


@patch("src.news_fetchers.requests.get", side_effect=Exception("xml error"))
def test_fetch_arxiv_failure(mock_get):
    result = fetch_arxiv()
    assert result.success is False
    assert "xml error" in result.error
