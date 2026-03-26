"""Tests for reddit_scanner module -- mock all HTTP requests."""

from unittest.mock import MagicMock, patch

import pytest

from src.reddit_scanner import (
    RedditPost,
    _is_problem_signal,
    scan_subreddit_problems,
    write_reddit_scan_to_vault,
)


_REDDIT_RESPONSE = {
    "data": {
        "children": [
            {
                "data": {
                    "title": "How do I set up monitoring for my homelab?",
                    "permalink": "/r/homelab/comments/abc/how_do_i/",
                    "selftext": "I've been struggling with Prometheus and need help.",
                    "score": 45,
                    "num_comments": 32,
                    "created_utc": 1711382400,
                    "link_flair_text": "Question",
                }
            },
            {
                "data": {
                    "title": "My new server build",
                    "permalink": "/r/homelab/comments/def/my_new/",
                    "selftext": "Just finished building my rack.",
                    "score": 120,
                    "num_comments": 15,
                    "created_utc": 1711382400,
                    "link_flair_text": "Show Off",
                }
            },
            {
                "data": {
                    "title": "Is there a tool for tracking power usage?",
                    "permalink": "/r/homelab/comments/ghi/is_there/",
                    "selftext": "Looking for something to monitor watts per device.",
                    "score": 30,
                    "num_comments": 20,
                    "created_utc": 1711382400,
                    "link_flair_text": "",
                }
            },
        ]
    }
}


@patch("src.reddit_scanner.requests.get")
@patch("src.reddit_scanner.time.sleep")
def test_scan_subreddit_problems(mock_sleep, mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _REDDIT_RESPONSE
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    result = scan_subreddit_problems(subreddits=["homelab"], limit=10)

    assert result["subreddits_scanned"] == ["homelab"]
    assert result["total_count"] == 3
    # Two posts have problem signals: "How do I" + Question flair, "Is there a tool"
    assert result["problem_count"] >= 2
    assert len(result["errors"]) == 0


@patch("src.reddit_scanner.requests.get")
@patch("src.reddit_scanner.time.sleep")
def test_scan_handles_rate_limit(mock_sleep, mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_get.return_value = mock_resp

    result = scan_subreddit_problems(subreddits=["homelab"], limit=10)

    assert result["total_count"] == 0
    assert len(result["errors"]) == 1
    assert "429" in result["errors"][0]


def test_is_problem_signal_keyword():
    post = RedditPost(
        title="How do I configure Nginx?",
        url="", selftext="", score=10, comment_count=5,
        subreddit="r/webdev", created_utc="", flair="",
    )
    assert _is_problem_signal(post) is True


def test_is_problem_signal_flair():
    post = RedditPost(
        title="Something about servers",
        url="", selftext="", score=10, comment_count=5,
        subreddit="r/sysadmin", created_utc="", flair="Question",
    )
    assert _is_problem_signal(post) is True


def test_is_problem_signal_high_comment_ratio():
    post = RedditPost(
        title="Just deployed my app",
        url="", selftext="", score=5, comment_count=30,
        subreddit="r/webdev", created_utc="", flair="",
    )
    assert _is_problem_signal(post) is True


def test_is_problem_signal_false():
    post = RedditPost(
        title="My new project showcase",
        url="", selftext="Check out what I built", score=100, comment_count=5,
        subreddit="r/webdev", created_utc="", flair="Show Off",
    )
    assert _is_problem_signal(post) is False


def test_write_reddit_scan_to_vault(tmp_path):
    scan = {
        "subreddits_scanned": ["homelab"],
        "problem_count": 1,
        "total_count": 3,
    }
    synthesis = {
        "subreddit": "homelab",
        "problem_summary": "Users need better monitoring tools.",
        "evidence_posts": [
            {"title": "How do I monitor?", "url": "https://reddit.com/x", "comment_count": 32}
        ],
        "project_idea": {
            "title": "HomeLab Monitor",
            "description": "A unified monitoring dashboard.",
            "why_build_it": "Recurring pain point in r/homelab.",
            "target_users": "Homelab enthusiasts",
            "skills_demonstrated": ["full-stack", "monitoring"],
        },
    }

    rel_path = write_reddit_scan_to_vault(str(tmp_path), scan, synthesis)
    assert rel_path.startswith("project-ideas/reddit-scan-")
    assert (tmp_path / rel_path).exists()

    content = (tmp_path / rel_path).read_text()
    assert "HomeLab Monitor" in content
    assert "homelab" in content
