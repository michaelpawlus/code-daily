"""Tests for the circle-back system."""

import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from src.circleback import CircleBackError, CircleBackManager, parse_priority
from src.storage import CommitStorage


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def storage(temp_db):
    return CommitStorage(temp_db)


@pytest.fixture
def cm(storage):
    return CircleBackManager(storage)


class TestStorage:
    def test_create_and_get(self, storage):
        item_id = storage.create_circleback_item("Revisit caching layer")
        item = storage.get_circleback_item(item_id)
        assert item["content"] == "Revisit caching layer"
        assert item["status"] == "open"
        assert item["kind"] == "idea"
        assert item["priority"] == 2

    def test_dedup_helper(self, storage):
        storage.create_circleback_item(
            "x", source="newsandideas", source_ref="ref-1"
        )
        assert storage.circleback_exists_by_source_ref("newsandideas", "ref-1")
        assert not storage.circleback_exists_by_source_ref("newsandideas", "ref-2")

    def test_ordering_by_priority_then_date(self, storage):
        storage.create_circleback_item("low", priority=3)
        storage.create_circleback_item(
            "high-soon", priority=1, circle_back_date="2026-01-01"
        )
        storage.create_circleback_item(
            "high-later", priority=1, circle_back_date="2026-12-01"
        )
        items = storage.get_circleback_items()
        assert [i["content"] for i in items][:3] == [
            "high-soon",
            "high-later",
            "low",
        ]

    def test_update_fields_clear_date(self, storage):
        item_id = storage.create_circleback_item("x", circle_back_date="2026-06-01")
        assert storage.update_circleback_fields(item_id, circle_back_date="")
        assert storage.get_circleback_item(item_id)["circle_back_date"] is None

    def test_set_issue_marks_promoted(self, storage):
        item_id = storage.create_circleback_item("x")
        storage.set_circleback_issue(item_id, "https://github.com/o/r/issues/5")
        item = storage.get_circleback_item(item_id)
        assert item["status"] == "promoted"
        assert item["issue_url"].endswith("/issues/5")


class TestParsePriority:
    def test_words_and_ints(self):
        assert parse_priority("high") == 1
        assert parse_priority("LOW") == 3
        assert parse_priority(2) == 2
        assert parse_priority("3") == 3
        assert parse_priority(None) == 2

    def test_invalid(self):
        with pytest.raises(CircleBackError):
            parse_priority("urgent")
        with pytest.raises(CircleBackError):
            parse_priority(9)


class TestManager:
    def test_add_validates_kind(self, cm):
        with pytest.raises(CircleBackError):
            cm.add("x", kind="bogus")

    def test_add_validates_date(self, cm):
        with pytest.raises(CircleBackError):
            cm.add("x", circle_back_date="June 1st")

    def test_add_rejects_empty(self, cm):
        with pytest.raises(CircleBackError):
            cm.add("   ")

    def test_add_decorates_priority_label(self, cm):
        item = cm.add("x", priority="high")
        assert item["priority"] == 1
        assert item["priority_label"] == "high"

    def test_add_dedups_on_source_ref(self, cm):
        a = cm.add("x", source="newsandideas", source_ref="r1")
        b = cm.add("x again", source="newsandideas", source_ref="r1")
        assert a["id"] == b["id"]
        assert len(cm.list_items()) == 1

    def test_due_includes_undated_and_past(self, cm):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        cm.add("undated")
        cm.add("past", circle_back_date=yesterday)
        cm.add("future", circle_back_date=tomorrow)
        due = {i["content"] for i in cm.due_items()}
        assert due == {"undated", "past"}
        upcoming = {i["content"] for i in cm.upcoming_items()}
        assert upcoming == {"future"}

    def test_snooze_then_not_due(self, cm):
        item = cm.add("x")
        future = (date.today() + timedelta(days=5)).isoformat()
        cm.snooze(item["id"], future)
        assert cm.due_items() == []
        assert len(cm.upcoming_items()) == 1

    def test_done_and_drop(self, cm):
        a = cm.add("a")
        b = cm.add("b")
        cm.mark_done(a["id"])
        cm.drop(b["id"])
        assert cm.list_items(status="open") == []
        assert len(cm.list_items(status="done")) == 1
        assert len(cm.list_items(status="dropped")) == 1

    def test_build_agent_context(self, cm):
        cm.add("continue this", kind="continue", priority="high")
        cm.add(
            "future",
            circle_back_date=(date.today() + timedelta(days=3)).isoformat(),
        )
        ctx = cm.build_agent_context()
        assert ctx["due_count"] == 1
        assert ctx["upcoming_count"] == 1
        assert ctx["by_kind"]["continue"][0]["content"] == "continue this"
        assert "high-priority" in ctx["summary"]

    def test_promote_to_issue_success(self, cm):
        item = cm.add("ship it", note="some context")
        fake = {"created": True, "url": "https://github.com/o/r/issues/9"}
        with patch("src.gh_issues.create_issue", return_value=fake) as mock_create:
            result = cm.promote_to_issue(item["id"], repo="o/r")
        assert result["ok"]
        assert result["issue_url"].endswith("/issues/9")
        # body should carry the note + metadata
        _, kwargs = mock_create.call_args
        assert "some context" in kwargs["body"]
        assert cm.get(item["id"])["status"] == "promoted"

    def test_promote_to_issue_failure_keeps_open(self, cm):
        item = cm.add("nope")
        fake = {"created": False, "error": "gh not found"}
        with patch("src.gh_issues.create_issue", return_value=fake):
            result = cm.promote_to_issue(item["id"])
        assert not result["ok"]
        assert cm.get(item["id"])["status"] == "open"

    def test_promote_missing_item(self, cm):
        result = cm.promote_to_issue(999)
        assert not result["ok"]
        assert "not found" in result["error"]
