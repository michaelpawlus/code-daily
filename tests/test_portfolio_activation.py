"""Tests for the portfolio activation panel."""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.portfolio_activation import compute_activation_health, render_activation_health
from src.storage import CommitStorage


@pytest.fixture
def storage():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield CommitStorage(db_path)
    if db_path.exists():
        db_path.unlink()


def _proj(name, path, grade, score, days_since=None):
    return {
        "name": name,
        "path": path,
        "grade": grade,
        "score": score,
        "categories": {},
        "raw": {},
        "days_since_last_commit": days_since,
        "commits_30d": None,
        "has_cli": None,
    }


def test_no_snapshots_returns_unavailable(storage):
    h = compute_activation_health(storage, days=30)
    assert h["available"] is False
    assert h["project_count"] == 0
    assert h["movements"] == {"up": 0, "down": 0, "flat": 0, "new": 0}
    assert h["headline"] is None


def test_only_recent_snapshot_marks_all_new(storage):
    now = datetime(2026, 4, 26, tzinfo=timezone.utc)
    fresh = now.isoformat(timespec="seconds")
    storage.save_portfolio_snapshot(
        fresh, [_proj("alpha", "/p/alpha", "B", 75)]
    )
    h = compute_activation_health(storage, days=30, now=now)
    assert h["available"] is True
    assert h["project_count"] == 1
    assert h["movements"]["new"] == 1
    assert h["movements"]["up"] == 0
    assert h["headline"] is None  # no upward grade movement


def test_diff_against_baseline_with_movers_and_headline(storage):
    now = datetime(2026, 4, 26, tzinfo=timezone.utc)
    old = (now - timedelta(days=45)).isoformat(timespec="seconds")
    fresh = now.isoformat(timespec="seconds")

    # Baseline: alpha=C(60), beta=D(40), gamma=B(80), epsilon=C(55)
    storage.save_portfolio_snapshot(old, [
        _proj("alpha", "/p/alpha", "C", 60, days_since=2),
        _proj("beta", "/p/beta", "D", 40, days_since=120),
        _proj("gamma", "/p/gamma", "B", 80, days_since=5),
        _proj("epsilon", "/p/epsilon", "C", 55, days_since=15),
    ])
    # Current: alpha=A(90)↑, beta=D(45)flat-with-score-bump, gamma=C(70)↓,
    # delta=A(95)new, epsilon=A(91)↑↑
    storage.save_portfolio_snapshot(fresh, [
        _proj("alpha", "/p/alpha", "A", 90, days_since=1),
        _proj("beta", "/p/beta", "D", 45, days_since=150),
        _proj("gamma", "/p/gamma", "C", 70, days_since=10),
        _proj("delta", "/p/delta", "A", 95, days_since=0),
        _proj("epsilon", "/p/epsilon", "A", 91, days_since=15),
    ])

    h = compute_activation_health(storage, days=30, now=now)

    assert h["available"] is True
    assert h["project_count"] == 5
    assert h["movements"] == {"up": 2, "down": 1, "flat": 1, "new": 1}
    assert h["grade_distribution"] == {"A": 3, "B": 0, "C": 1, "D": 1, "F": 0}

    # Two C→A jumps form the dominant upward bucket.
    assert h["headline"] == "Moved 2 repos from C to A in 30 days"

    # Top mover up by score delta: alpha (+30), epsilon (+36) → epsilon first.
    up_names = [m["name"] for m in h["top_movers_up"]]
    assert up_names[0] == "epsilon"
    assert "alpha" in up_names
    # beta has score delta +5 with grade flat — should appear in movers up too.
    assert "beta" in up_names

    # Top mover down: gamma (-10).
    assert h["top_movers_down"][0]["name"] == "gamma"
    assert h["top_movers_down"][0]["score_delta"] == -10

    # Stale list orders by days_since_last_commit DESC.
    stale_names = [s["name"] for s in h["stale"]["examples"]]
    assert stale_names[0] == "beta"  # 150d
    assert h["stale"]["count"] >= 1


def test_render_does_not_raise_on_unavailable(storage, capsys):
    h = compute_activation_health(storage, days=30)
    render_activation_health(h)
    out = capsys.readouterr().out
    assert "Portfolio Activation Health" in out
    assert "No portfolio snapshots yet" in out


def test_render_includes_headline_when_present(storage, capsys):
    now = datetime(2026, 4, 26, tzinfo=timezone.utc)
    old = (now - timedelta(days=45)).isoformat(timespec="seconds")
    fresh = now.isoformat(timespec="seconds")
    storage.save_portfolio_snapshot(old, [_proj("a", "/p/a", "C", 60)])
    storage.save_portfolio_snapshot(fresh, [_proj("a", "/p/a", "A", 92)])
    h = compute_activation_health(storage, days=30, now=now)
    render_activation_health(h)
    out = capsys.readouterr().out
    assert "C to A" in out
    assert "Top movers up" in out
    assert "↑ a:" in out
