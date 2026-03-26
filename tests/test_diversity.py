"""Tests for diversity scoring module."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.diversity import compute_diversity_score


@pytest.fixture
def mock_storage():
    return MagicMock()


def test_no_suggestions(mock_storage):
    mock_storage.get_recent_suggestions.return_value = []
    result = compute_diversity_score(mock_storage, days=14)
    assert result["score"] == 0.0
    assert result["rating"] == "no data"
    assert result["warning"] is not None


def test_single_suggestion(mock_storage):
    mock_storage.get_recent_suggestions.return_value = [
        {"source": "github", "title": "Fix auth", "content_hash": "abc123", "domain": "auth"}
    ]
    mock_storage.get_recent_suggestion_domains.return_value = ["auth"]
    result = compute_diversity_score(mock_storage, days=14)
    assert result["total_suggestions"] == 1
    assert result["unique_domains"] == 1
    assert result["score"] > 0


def test_diverse_suggestions(mock_storage):
    suggestions = [
        {"source": "github", "title": "Fix auth", "content_hash": "a1", "domain": "auth"},
        {"source": "obsidian", "title": "Build CLI", "content_hash": "b2", "domain": "cli"},
        {"source": "github", "title": "Add tests", "content_hash": "c3", "domain": "testing"},
        {"source": "obsidian", "title": "New API", "content_hash": "d4", "domain": "api"},
    ]
    mock_storage.get_recent_suggestions.return_value = suggestions
    mock_storage.get_recent_suggestion_domains.side_effect = lambda days: (
        ["auth", "cli", "testing", "api"] if days <= 14
        else ["auth", "cli", "testing", "api", "old-domain"]
    )

    result = compute_diversity_score(mock_storage, days=14)
    assert result["unique_domains"] == 4
    assert result["domain_spread"] == 1.0
    assert result["rating"] in ("high", "moderate")
    assert result["score"] >= 40


def test_repetitive_suggestions(mock_storage):
    suggestions = [
        {"source": "obsidian", "title": "Same idea", "content_hash": "aaa", "domain": "cli"},
        {"source": "obsidian", "title": "Same idea", "content_hash": "aaa", "domain": "cli"},
        {"source": "obsidian", "title": "Same idea", "content_hash": "aaa", "domain": "cli"},
        {"source": "obsidian", "title": "Same idea", "content_hash": "aaa", "domain": "cli"},
    ]
    mock_storage.get_recent_suggestions.return_value = suggestions
    mock_storage.get_recent_suggestion_domains.return_value = ["cli"]

    result = compute_diversity_score(mock_storage, days=14)
    assert result["unique_domains"] == 1
    assert result["most_repeated"][0]["count"] == 4
    assert result["rating"] == "low"
    assert result["warning"] is not None


def test_source_imbalance(mock_storage):
    suggestions = [
        {"source": "obsidian", "title": f"Idea {i}", "content_hash": f"h{i}", "domain": f"d{i}"}
        for i in range(10)
    ]
    mock_storage.get_recent_suggestions.return_value = suggestions
    mock_storage.get_recent_suggestion_domains.return_value = [f"d{i}" for i in range(10)]

    result = compute_diversity_score(mock_storage, days=14)
    assert result["source_spread"] == {"obsidian": 10}
    # Should have some source balance penalty since 100% from one source
    assert result["score"] < 100


def test_most_repeated_only_includes_repeats(mock_storage):
    suggestions = [
        {"source": "github", "title": "Unique A", "content_hash": "u1", "domain": "a"},
        {"source": "github", "title": "Unique B", "content_hash": "u2", "domain": "b"},
    ]
    mock_storage.get_recent_suggestions.return_value = suggestions
    mock_storage.get_recent_suggestion_domains.return_value = ["a", "b"]

    result = compute_diversity_score(mock_storage, days=14)
    assert result["most_repeated"] == []
