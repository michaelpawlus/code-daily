"""Tests for the quest system."""

import tempfile
from pathlib import Path

import pytest

from src.storage import CommitStorage
from src.quest_manager import QuestManager


@pytest.fixture
def temp_db():
    """Create a temporary database file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def storage(temp_db):
    """Create a CommitStorage instance with a temporary database."""
    return CommitStorage(temp_db)


@pytest.fixture
def quest_manager(storage):
    """Create a QuestManager instance."""
    return QuestManager(storage)


class TestQuestStorage:
    """Tests for quest storage methods."""

    def test_create_quest(self, storage):
        """Can create a quest."""
        quest_id = storage.create_quest(
            title="Fix bug",
            source="manual",
            description="Fix the login bug",
        )
        assert quest_id is not None
        assert quest_id > 0

    def test_get_quest(self, storage):
        """Can retrieve a quest by ID."""
        quest_id = storage.create_quest(title="Test quest")
        quest = storage.get_quest(quest_id)

        assert quest is not None
        assert quest["id"] == quest_id
        assert quest["title"] == "Test quest"
        assert quest["status"] == "pending"
        assert quest["source"] == "manual"

    def test_get_quest_not_found(self, storage):
        """Returns None for non-existent quest."""
        quest = storage.get_quest(999)
        assert quest is None

    def test_get_quests_empty(self, storage):
        """Returns empty list when no quests."""
        quests = storage.get_quests()
        assert quests == []

    def test_get_quests_all(self, storage):
        """Returns all quests."""
        storage.create_quest(title="Quest 1")
        storage.create_quest(title="Quest 2")
        storage.create_quest(title="Quest 3")

        quests = storage.get_quests()
        assert len(quests) == 3

    def test_get_quests_by_status(self, storage):
        """Can filter quests by status."""
        q1 = storage.create_quest(title="Pending quest")
        q2 = storage.create_quest(title="Active quest")
        storage.update_quest_status(q2, "active")

        pending = storage.get_quests(status="pending")
        active = storage.get_quests(status="active")

        assert len(pending) == 1
        assert pending[0]["title"] == "Pending quest"
        assert len(active) == 1
        assert active[0]["title"] == "Active quest"

    def test_get_quests_with_limit(self, storage):
        """Can limit number of quests returned."""
        for i in range(10):
            storage.create_quest(title=f"Quest {i}")

        quests = storage.get_quests(limit=5)
        assert len(quests) == 5

    def test_update_quest_status(self, storage):
        """Can update quest status."""
        quest_id = storage.create_quest(title="Test quest")

        success = storage.update_quest_status(quest_id, "active")
        assert success is True

        quest = storage.get_quest(quest_id)
        assert quest["status"] == "active"

    def test_update_quest_status_not_found(self, storage):
        """Returns False when quest not found."""
        success = storage.update_quest_status(999, "active")
        assert success is False

    def test_delete_quest(self, storage):
        """Can delete a quest."""
        quest_id = storage.create_quest(title="Delete me")
        assert storage.get_quest(quest_id) is not None

        success = storage.delete_quest(quest_id)
        assert success is True
        assert storage.get_quest(quest_id) is None

    def test_delete_quest_not_found(self, storage):
        """Returns False when quest not found."""
        success = storage.delete_quest(999)
        assert success is False


class TestIdeasStorage:
    """Tests for ideas storage methods."""

    def test_create_idea(self, storage):
        """Can create an idea."""
        idea_id = storage.create_idea("Build a feature")
        assert idea_id is not None
        assert idea_id > 0

    def test_get_idea(self, storage):
        """Can retrieve an idea by ID."""
        idea_id = storage.create_idea("Test idea")
        idea = storage.get_idea(idea_id)

        assert idea is not None
        assert idea["id"] == idea_id
        assert idea["content"] == "Test idea"
        assert idea["status"] == "active"

    def test_get_idea_not_found(self, storage):
        """Returns None for non-existent idea."""
        idea = storage.get_idea(999)
        assert idea is None

    def test_get_ideas_empty(self, storage):
        """Returns empty list when no ideas."""
        ideas = storage.get_ideas()
        assert ideas == []

    def test_get_ideas_by_status(self, storage):
        """Can filter ideas by status."""
        i1 = storage.create_idea("Active idea")
        i2 = storage.create_idea("Completed idea")
        storage.update_idea_status(i2, "completed")

        active = storage.get_ideas(status="active")
        completed = storage.get_ideas(status="completed")

        assert len(active) == 1
        assert active[0]["content"] == "Active idea"
        assert len(completed) == 1
        assert completed[0]["content"] == "Completed idea"

    def test_update_idea_status(self, storage):
        """Can update idea status."""
        idea_id = storage.create_idea("Test idea")

        success = storage.update_idea_status(idea_id, "promoted")
        assert success is True

        idea = storage.get_idea(idea_id)
        assert idea["status"] == "promoted"

    def test_delete_idea(self, storage):
        """Can delete an idea."""
        idea_id = storage.create_idea("Delete me")
        assert storage.get_idea(idea_id) is not None

        success = storage.delete_idea(idea_id)
        assert success is True
        assert storage.get_idea(idea_id) is None


class TestQuestManager:
    """Tests for QuestManager class."""

    def test_add_manual_quest(self, quest_manager):
        """Can add a manual quest."""
        quest = quest_manager.add_manual_quest(
            title="Fix bug",
            description="Fix the login issue",
        )

        assert quest is not None
        assert quest["title"] == "Fix bug"
        assert quest["description"] == "Fix the login issue"
        assert quest["source"] == "manual"
        assert quest["status"] == "pending"

    def test_get_pending_quests(self, quest_manager):
        """Can get pending quests."""
        quest_manager.add_manual_quest(title="Quest 1")
        quest_manager.add_manual_quest(title="Quest 2")

        pending = quest_manager.get_pending_quests()
        assert len(pending) == 2

    def test_get_pending_quests_limit(self, quest_manager):
        """Respects limit on pending quests."""
        for i in range(10):
            quest_manager.add_manual_quest(title=f"Quest {i}")

        pending = quest_manager.get_pending_quests(limit=3)
        assert len(pending) == 3

    def test_accept_quest(self, quest_manager):
        """Can accept a quest."""
        created = quest_manager.add_manual_quest(title="Test quest")
        accepted = quest_manager.accept_quest(created["id"])

        assert accepted is not None
        assert accepted["status"] == "active"

    def test_accept_quest_not_found(self, quest_manager):
        """Returns None when quest not found."""
        result = quest_manager.accept_quest(999)
        assert result is None

    def test_complete_quest(self, quest_manager):
        """Can complete a quest."""
        created = quest_manager.add_manual_quest(title="Test quest")
        quest_manager.accept_quest(created["id"])
        completed = quest_manager.complete_quest(created["id"])

        assert completed is not None
        assert completed["status"] == "completed"

    def test_get_active_quests(self, quest_manager):
        """Can get active quests."""
        q1 = quest_manager.add_manual_quest(title="Quest 1")
        q2 = quest_manager.add_manual_quest(title="Quest 2")
        quest_manager.accept_quest(q1["id"])

        active = quest_manager.get_active_quests()
        assert len(active) == 1
        assert active[0]["title"] == "Quest 1"

    def test_skip_quest_archive(self, quest_manager):
        """Can skip and archive a quest."""
        created = quest_manager.add_manual_quest(title="Skip me")
        result = quest_manager.skip_quest(created["id"], action="archive")

        assert result["success"] is True
        assert result["quest"]["status"] == "archived"
        assert "idea" not in result

    def test_skip_quest_save_as_idea(self, quest_manager):
        """Can skip quest and save as idea."""
        created = quest_manager.add_manual_quest(
            title="Skip me",
            description="Some details",
        )
        result = quest_manager.skip_quest(
            created["id"],
            action="skip",
            save_as_idea=True,
        )

        assert result["success"] is True
        assert result["quest"]["status"] == "skipped"
        assert "idea" in result
        assert "Skip me" in result["idea"]["content"]

    def test_skip_quest_not_found(self, quest_manager):
        """Returns error when quest not found."""
        result = quest_manager.skip_quest(999)
        assert result["success"] is False
        assert "error" in result

    def test_promote_idea_to_quest(self, quest_manager, storage):
        """Can promote an idea to a quest."""
        idea_id = storage.create_idea("Build feature X")
        quest = quest_manager.promote_idea_to_quest(idea_id)

        assert quest is not None
        assert quest["title"] == "Build feature X"
        assert quest["source"] == "ideas_md"
        assert quest["status"] == "pending"

        # Check idea was marked as promoted
        idea = storage.get_idea(idea_id)
        assert idea["status"] == "promoted"

    def test_promote_idea_not_found(self, quest_manager):
        """Returns None when idea not found."""
        result = quest_manager.promote_idea_to_quest(999)
        assert result is None

    def test_get_quest_summary(self, quest_manager):
        """Can get quest summary."""
        q1 = quest_manager.add_manual_quest(title="Pending")
        q2 = quest_manager.add_manual_quest(title="Active")
        q3 = quest_manager.add_manual_quest(title="Completed")

        quest_manager.accept_quest(q2["id"])
        quest_manager.accept_quest(q3["id"])
        quest_manager.complete_quest(q3["id"])

        summary = quest_manager.get_quest_summary()

        assert summary["total"] == 3
        assert summary["pending"] == 1
        assert summary["active"] == 1
        assert summary["completed"] == 1
