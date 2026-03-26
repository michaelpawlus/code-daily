"""Tests for news_trends module."""

import os
from datetime import date, timedelta

import pytest

from src.news_trends import (
    _extract_topics,
    _parse_digest_titles,
    analyze_trends,
)


def _make_digest(tmp_path, file_date: str, items: list[tuple[str, str]]):
    """Create a minimal digest markdown file."""
    digest_dir = tmp_path / "ai-news"
    digest_dir.mkdir(exist_ok=True)

    lines = [
        "---",
        f"date: {file_date}",
        "tags: [ai-news, digest, daily]",
        "---",
        "",
        f"# AI News Digest -- {file_date}",
        "",
    ]
    for title, url in items:
        lines.append(f"- [{title}]({url})")
    lines.append("")

    filepath = digest_dir / f"{file_date}.md"
    filepath.write_text("\n".join(lines))
    return filepath


def test_parse_digest_titles(tmp_path):
    filepath = _make_digest(tmp_path, "2026-03-25", [
        ("TurboQuant paper released", "https://example.com/1"),
        ("Intel launches new GPU", "https://example.com/2"),
    ])
    titles = _parse_digest_titles(str(filepath))
    assert len(titles) == 2
    assert "TurboQuant paper released" in titles


def test_parse_digest_titles_skips_short(tmp_path):
    filepath = _make_digest(tmp_path, "2026-03-25", [
        ("Short", "https://example.com/1"),
        ("This is a longer title that should be included", "https://example.com/2"),
    ])
    titles = _parse_digest_titles(str(filepath))
    assert len(titles) == 1


def test_extract_topics():
    topics = _extract_topics("TurboQuant redefining AI efficiency with extreme compression")
    assert "turboquant" in topics
    assert "efficiency" in topics
    assert "compression" in topics


def test_extract_topics_filters_stopwords():
    topics = _extract_topics("The new model is very good and fast")
    assert "the" not in topics
    assert "is" not in topics
    assert "model" in topics


def test_analyze_trends_empty_vault(tmp_path):
    result = analyze_trends(str(tmp_path), days=30)
    assert result["digests_analyzed"] == 0
    assert result["trending"] == []


def test_analyze_trends_single_digest(tmp_path):
    today = date.today().isoformat()
    _make_digest(tmp_path, today, [
        ("TurboQuant paper is amazing", "https://example.com/1"),
        ("Intel launches cheap GPU", "https://example.com/2"),
    ])
    result = analyze_trends(str(tmp_path), days=30)
    assert result["digests_analyzed"] == 1
    assert result["trending"] == []  # Need 2+ days for trending


def test_analyze_trends_recurring_topic(tmp_path):
    today = date.today()
    yesterday = (today - timedelta(days=1)).isoformat()
    today_str = today.isoformat()

    _make_digest(tmp_path, yesterday, [
        ("TurboQuant paper changes everything", "https://example.com/1"),
        ("Intel releases new hardware", "https://example.com/2"),
    ])
    _make_digest(tmp_path, today_str, [
        ("TurboQuant implementation lands in MLX", "https://example.com/3"),
        ("DeepSeek announces new model", "https://example.com/4"),
    ])

    result = analyze_trends(str(tmp_path), days=30)
    assert result["digests_analyzed"] == 2

    # "turboquant" should be trending (appears both days)
    trending_topics = [t["topic"] for t in result["trending"]]
    assert "turboquant" in trending_topics

    turboquant = next(t for t in result["trending"] if t["topic"] == "turboquant")
    assert turboquant["day_count"] == 2


def test_analyze_trends_new_today(tmp_path):
    today = date.today()
    yesterday = (today - timedelta(days=1)).isoformat()
    today_str = today.isoformat()

    _make_digest(tmp_path, yesterday, [
        ("TurboQuant paper changes everything", "https://example.com/1"),
    ])
    _make_digest(tmp_path, today_str, [
        ("DeepSeek announces massive model", "https://example.com/2"),
    ])

    result = analyze_trends(str(tmp_path), days=30)
    assert "deepseek" in result["new_today"]


def test_analyze_trends_respects_days_cutoff(tmp_path):
    today = date.today()
    old_date = (today - timedelta(days=60)).isoformat()
    today_str = today.isoformat()

    _make_digest(tmp_path, old_date, [
        ("Ancient topic nobody cares about", "https://example.com/1"),
    ])
    _make_digest(tmp_path, today_str, [
        ("Fresh topic from today only", "https://example.com/2"),
    ])

    result = analyze_trends(str(tmp_path), days=30)
    assert result["digests_analyzed"] == 1  # Old one filtered out
