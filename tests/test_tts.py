"""Tests for TTS podcast generation."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tts import (
    DEFAULT_VOICE,
    digest_to_script,
    generate_podcast,
    read_synthesis_from_vault,
    write_podcast_to_vault,
)


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_SYNTHESIS = {
    "overview": "TurboQuant dominates today with 6x memory reduction for LLMs.",
    "sections": [
        {
            "name": "Industry & Labs",
            "slug": "industry-labs",
            "summary": "Major model releases.",
            "items": [
                {
                    "title": "GPT-5 Released",
                    "url": "https://example.com/1",
                    "source": "Hackernews",
                    "score": 100,
                    "commentary": "A landmark release.",
                },
                {
                    "title": "New Unsloth Studio",
                    "url": "https://reddit.com/r/LocalLLaMA/abc",
                    "source": "Reddit",
                    "score": 214,
                    "commentary": "Fine-tuning tooling update.",
                },
            ],
        },
        {
            "name": "Challenge Your Thinking",
            "slug": "challenge-your-thinking",
            "summary": "Contrarian takes.",
            "items": [
                {
                    "title": "AI Skeptic View",
                    "url": "https://example.com/2",
                    "source": "Hackernews",
                    "score": 30,
                    "commentary": "",
                },
            ],
        },
    ],
}

SAMPLE_SYNTHESIZED_MD = """---
date: 2026-03-27
tags: [ai-news, digest, daily, synthesized]
sources: [hackernews, reddit]
total_items: 3
---

# AI News Digest — 2026-03-27

## Overview
TurboQuant dominates today with 6x memory reduction for LLMs.

## Industry & Labs
Major model releases.

- [GPT-5 Released](https://example.com/1) (Hackernews, 100pts) — A landmark release.
- [New Unsloth Studio](https://reddit.com/r/LocalLLaMA/abc) (Reddit, 214pts) — Fine-tuning tooling update.

## Challenge Your Thinking
Contrarian takes.

- [AI Skeptic View](https://example.com/2) (Hackernews, 30pts)
"""


# ---------------------------------------------------------------------------
# read_synthesis_from_vault
# ---------------------------------------------------------------------------


def test_read_synthesis_from_vault(tmp_path):
    ai_news = tmp_path / "ai-news"
    ai_news.mkdir()
    (ai_news / "2026-03-27.md").write_text(SAMPLE_SYNTHESIZED_MD)

    result = read_synthesis_from_vault(str(tmp_path), "2026-03-27")

    assert "TurboQuant" in result["overview"]
    assert len(result["sections"]) == 2
    assert result["sections"][0]["name"] == "Industry & Labs"
    assert result["sections"][0]["summary"] == "Major model releases."
    assert len(result["sections"][0]["items"]) == 2
    assert result["sections"][0]["items"][0]["title"] == "GPT-5 Released"
    assert result["sections"][0]["items"][0]["score"] == 100
    assert result["sections"][0]["items"][0]["commentary"] == "A landmark release."
    assert result["sections"][1]["name"] == "Challenge Your Thinking"
    assert result["sections"][1]["items"][0]["commentary"] == ""


def test_read_synthesis_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_synthesis_from_vault(str(tmp_path), "2026-01-01")


def test_read_synthesis_not_synthesized(tmp_path):
    ai_news = tmp_path / "ai-news"
    ai_news.mkdir()
    raw_md = """---
date: 2026-03-27
tags: [ai-news, digest, daily]
sources: [hackernews]
total_items: 1
---

# AI News Digest — 2026-03-27

## Hacker News
| Score | Title |
|-------|-------|
| 50 | [Story](https://example.com) |
"""
    (ai_news / "2026-03-27.md").write_text(raw_md)

    with pytest.raises(ValueError, match="not a synthesized"):
        read_synthesis_from_vault(str(tmp_path), "2026-03-27")


# ---------------------------------------------------------------------------
# digest_to_script
# ---------------------------------------------------------------------------


def test_digest_to_script_basic():
    script = digest_to_script(SAMPLE_SYNTHESIS, "2026-03-27")

    assert "March 27, 2026" in script
    assert "TurboQuant" in script
    assert "Industry & Labs" in script
    assert "GPT-5 Released" in script
    assert "A landmark release" in script
    assert "Challenge Your Thinking" in script
    assert "AI Skeptic View" in script
    # URLs should not appear in the script
    assert "https://example.com" not in script
    assert "https://reddit.com" not in script
    # Score metadata should not appear
    assert "100pts" not in script
    assert "214pts" not in script


def test_digest_to_script_with_date():
    script = digest_to_script(SAMPLE_SYNTHESIS, "2026-01-15")
    assert "January 15, 2026" in script


def test_digest_to_script_empty_sections():
    synthesis = {"overview": "Quiet day.", "sections": []}
    script = digest_to_script(synthesis, "2026-03-27")

    assert "Quiet day." in script
    assert "wraps up" in script


def test_digest_to_script_no_commentary():
    script = digest_to_script(SAMPLE_SYNTHESIS, "2026-03-27")
    # AI Skeptic View has no commentary — should end with just a period
    assert "AI Skeptic View." in script


def test_digest_to_script_section_transitions():
    script = digest_to_script(SAMPLE_SYNTHESIS, "2026-03-27")
    assert "Starting with" in script
    assert "Finally," in script


# ---------------------------------------------------------------------------
# generate_podcast
# ---------------------------------------------------------------------------


@patch("src.tts.edge_tts", create=True)
def test_generate_podcast_calls_edge_tts(mock_edge_tts, tmp_path):
    output_path = str(tmp_path / "podcasts" / "test.mp3")

    mock_communicate = MagicMock()
    mock_communicate.save = AsyncMock()
    mock_edge_tts.Communicate.return_value = mock_communicate

    with patch("src.tts._generate_audio", new_callable=AsyncMock) as mock_gen:
        result = generate_podcast("Hello world", output_path)

    assert result == output_path
    assert os.path.isdir(str(tmp_path / "podcasts"))


@patch("src.tts._generate_audio", new_callable=AsyncMock)
def test_generate_podcast_creates_directory(mock_gen, tmp_path):
    output_path = str(tmp_path / "deep" / "nested" / "dir" / "test.mp3")
    generate_podcast("Hello", output_path)
    assert os.path.isdir(str(tmp_path / "deep" / "nested" / "dir"))


# ---------------------------------------------------------------------------
# write_podcast_to_vault
# ---------------------------------------------------------------------------


@patch("src.tts.generate_podcast")
def test_write_podcast_to_vault_metadata(mock_gen, tmp_path):
    mock_gen.return_value = str(tmp_path / "ai-news" / "podcasts" / "2026-03-27.mp3")

    result = write_podcast_to_vault(str(tmp_path), "2026-03-27", "Test script text")

    assert result["date"] == "2026-03-27"
    assert result["vault_file"] == "ai-news/podcasts/2026-03-27.mp3"
    assert result["voice"] == DEFAULT_VOICE
    assert result["script_length"] == len("Test script text")


@patch("src.tts.generate_podcast")
def test_write_podcast_to_vault_path(mock_gen, tmp_path):
    mock_gen.return_value = str(tmp_path / "ai-news" / "podcasts" / "2026-03-27.mp3")

    write_podcast_to_vault(str(tmp_path), "2026-03-27", "Script", voice="en-US-AvaMultilingualNeural")

    expected_path = str(tmp_path / "ai-news" / "podcasts" / "2026-03-27.mp3")
    mock_gen.assert_called_once_with("Script", expected_path, "en-US-AvaMultilingualNeural")
