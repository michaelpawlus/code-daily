"""Tests for idea_generator module."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.idea_generator import (
    collect_idea_seeds,
    get_recent_commit_domains,
    write_project_ideas_to_vault,
)


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


@patch("src.idea_generator.collect_news")
@patch("src.idea_generator._get_user_interests")
@patch("src.idea_generator.CommitStorage")
def test_collect_idea_seeds_with_digest(mock_storage_cls, mock_interests, mock_collect):
    mock_storage = MagicMock()
    mock_storage.get_commits_since.return_value = [
        {"repo": "code-daily", "date": "2026-03-20", "commits": [], "commit_count": 0}
    ]
    mock_storage_cls.return_value = mock_storage
    mock_interests.return_value = [{"title": "Build a CLI", "source_file": "ideas.md"}]

    digest = {
        "date": "2026-03-25",
        "items": [
            {"title": "TurboQuant paper", "score": 495, "source": "hackernews"},
            {"title": "Intel GPU", "score": 752, "source": "reddit"},
        ],
        "sources": {},
    }

    seeds = collect_idea_seeds(digest=digest)

    assert seeds["trending_count"] == 2
    assert len(seeds["user_interests"]) == 1
    assert "code-daily" in seeds["recent_domains"]
    assert seeds["digest_date"] == "2026-03-25"
    assert "target_profile" in seeds


@patch("src.idea_generator.collect_news")
@patch("src.idea_generator._get_user_interests")
@patch("src.idea_generator.CommitStorage")
def test_collect_idea_seeds_fetches_fresh(mock_storage_cls, mock_interests, mock_collect):
    mock_storage = MagicMock()
    mock_storage.get_commits_since.return_value = []
    mock_storage_cls.return_value = mock_storage
    mock_interests.return_value = []
    mock_collect.return_value = {"date": "2026-03-25", "items": [], "sources": {}}

    seeds = collect_idea_seeds(digest=None, hours_back=12)

    mock_collect.assert_called_once_with(hours_back=12, limit=25)


def test_get_recent_commit_domains():
    mock_storage = MagicMock()
    mock_storage.get_commits_since.return_value = [
        {"repo": "code-daily", "date": "2026-03-20", "commits": [], "commit_count": 0},
        {"repo": "workout-app", "date": "2026-03-21", "commits": [], "commit_count": 0},
        {"repo": "code-daily", "date": "2026-03-22", "commits": [], "commit_count": 0},
    ]

    domains = get_recent_commit_domains(mock_storage, days=30)
    assert set(domains) == {"code-daily", "workout-app"}


def test_write_project_ideas_to_vault(tmp_path):
    ideas = {
        "ideas": [
            {
                "title": "LLM Supply Chain Auditor",
                "description": "Scan AI deps for vulnerabilities.",
                "why_now": "LiteLLM supply chain attack trending.",
                "skills_demonstrated": ["security", "CLI"],
                "trending_source": "HN + Reddit",
                "complexity": "weekend",
            },
        ],
        "generated_from": "2026-03-25",
    }

    rel_path = write_project_ideas_to_vault(str(tmp_path), ideas)
    assert rel_path.startswith("project-ideas/")
    assert (tmp_path / rel_path).exists()

    content = (tmp_path / rel_path).read_text()
    assert "LLM Supply Chain Auditor" in content
    assert "LiteLLM" in content
    assert "weekend" in content
