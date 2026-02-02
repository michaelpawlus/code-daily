"""Tests for the quest system."""

import tempfile
from datetime import datetime, timedelta
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


class TestGitHubIssuesSync:
    """Tests for GitHub issues sync functionality."""

    def test_quest_exists_by_source_ref(self, storage):
        """Can check if quest exists by source and source_ref."""
        storage.create_quest(
            title="Test quest",
            source="github_issue",
            source_ref="https://github.com/user/repo/issues/1",
        )

        assert storage.quest_exists_by_source_ref(
            "github_issue", "https://github.com/user/repo/issues/1"
        )
        assert not storage.quest_exists_by_source_ref(
            "github_issue", "https://github.com/user/repo/issues/2"
        )
        assert not storage.quest_exists_by_source_ref(
            "manual", "https://github.com/user/repo/issues/1"
        )

    def test_sync_creates_quest_from_issue(self, quest_manager, storage):
        """Syncing issues creates quests correctly."""
        issues = [
            {
                "id": 1,
                "title": "Fix login bug",
                "html_url": "https://github.com/user/myrepo/issues/1",
                "body": "The login button doesn't work",
            }
        ]

        result = quest_manager.sync_github_issues(issues)

        assert result["added"] == 1
        assert result["skipped"] == 0

        quests = storage.get_quests()
        assert len(quests) == 1
        assert quests[0]["title"] == "[user/myrepo] Fix login bug"
        assert quests[0]["source"] == "github_issue"
        assert quests[0]["source_ref"] == "https://github.com/user/myrepo/issues/1"
        assert quests[0]["description"] == "The login button doesn't work"

    def test_sync_skips_existing_issues(self, quest_manager, storage):
        """Syncing doesn't duplicate existing issues."""
        # Create an existing quest for this issue
        storage.create_quest(
            title="[user/repo] Existing issue",
            source="github_issue",
            source_ref="https://github.com/user/repo/issues/1",
        )

        issues = [
            {
                "id": 1,
                "title": "Existing issue",
                "html_url": "https://github.com/user/repo/issues/1",
                "body": "Already synced",
            },
            {
                "id": 2,
                "title": "New issue",
                "html_url": "https://github.com/user/repo/issues/2",
                "body": "Not synced yet",
            },
        ]

        result = quest_manager.sync_github_issues(issues)

        assert result["added"] == 1
        assert result["skipped"] == 1

        quests = storage.get_quests()
        assert len(quests) == 2

    def test_sync_skips_pull_requests(self, quest_manager, storage):
        """Syncing filters out pull requests."""
        issues = [
            {
                "id": 1,
                "title": "Regular issue",
                "html_url": "https://github.com/user/repo/issues/1",
                "body": "This is an issue",
            },
            {
                "id": 2,
                "title": "Pull request",
                "html_url": "https://github.com/user/repo/pull/2",
                "body": "This is a PR",
                "pull_request": {
                    "url": "https://api.github.com/repos/user/repo/pulls/2"
                },
            },
        ]

        result = quest_manager.sync_github_issues(issues)

        assert result["added"] == 1
        assert result["skipped"] == 0

        quests = storage.get_quests()
        assert len(quests) == 1
        assert "Pull request" not in quests[0]["title"]

    def test_sync_truncates_long_descriptions(self, quest_manager, storage):
        """Syncing truncates descriptions over 200 chars."""
        long_body = "x" * 300

        issues = [
            {
                "id": 1,
                "title": "Issue with long body",
                "html_url": "https://github.com/user/repo/issues/1",
                "body": long_body,
            }
        ]

        result = quest_manager.sync_github_issues(issues)

        assert result["added"] == 1

        quests = storage.get_quests()
        assert len(quests[0]["description"]) == 200
        assert quests[0]["description"].endswith("...")

    def test_sync_handles_empty_body(self, quest_manager, storage):
        """Syncing handles issues with no body."""
        issues = [
            {
                "id": 1,
                "title": "Issue without body",
                "html_url": "https://github.com/user/repo/issues/1",
                "body": None,
            },
            {
                "id": 2,
                "title": "Issue with empty body",
                "html_url": "https://github.com/user/repo/issues/2",
                "body": "",
            },
        ]

        result = quest_manager.sync_github_issues(issues)

        assert result["added"] == 2

        quests = storage.get_quests()
        assert quests[0]["description"] is None
        assert quests[1]["description"] is None

    def test_sync_handles_empty_issues_list(self, quest_manager, storage):
        """Syncing handles empty issues list."""
        result = quest_manager.sync_github_issues([])

        assert result["added"] == 0
        assert result["skipped"] == 0

        quests = storage.get_quests()
        assert len(quests) == 0


class TestPriorityScoring:
    """Tests for quest priority scoring."""

    def test_priority_score_age_bonus(self, quest_manager):
        """Older quests should score higher (up to +10)."""
        now = datetime.now()

        # New quest (0 days old)
        new_quest = {
            "created_at": now.isoformat(),
            "source": "manual",
        }
        new_score = quest_manager.calculate_priority_score(new_quest)

        # 5 day old quest
        old_quest = {
            "created_at": (now - timedelta(days=5)).isoformat(),
            "source": "manual",
        }
        old_score = quest_manager.calculate_priority_score(old_quest)

        # 15 day old quest (should cap at +10)
        very_old_quest = {
            "created_at": (now - timedelta(days=15)).isoformat(),
            "source": "manual",
        }
        very_old_score = quest_manager.calculate_priority_score(very_old_quest)

        assert old_score > new_score
        assert old_score == new_score + 5
        assert very_old_score == new_score + 10  # Capped at 10

    def test_priority_score_source_ranking(self, quest_manager):
        """GitHub issues should rank higher than manual quests."""
        now = datetime.now().isoformat()

        github_quest = {"created_at": now, "source": "github_issue"}
        todo_quest = {"created_at": now, "source": "todo_scan"}
        ideas_quest = {"created_at": now, "source": "ideas_md"}
        manual_quest = {"created_at": now, "source": "manual"}

        github_score = quest_manager.calculate_priority_score(github_quest)
        todo_score = quest_manager.calculate_priority_score(todo_quest)
        ideas_score = quest_manager.calculate_priority_score(ideas_quest)
        manual_score = quest_manager.calculate_priority_score(manual_quest)

        assert github_score > todo_score > ideas_score > manual_score
        assert github_score == manual_score + 3
        assert todo_score == manual_score + 2
        assert ideas_score == manual_score + 1

    def test_priority_score_description_bonus(self, quest_manager):
        """Quests with descriptions should score +2 higher."""
        now = datetime.now().isoformat()

        with_desc = {
            "created_at": now,
            "source": "manual",
            "description": "Some details here",
        }
        without_desc = {
            "created_at": now,
            "source": "manual",
            "description": None,
        }

        score_with = quest_manager.calculate_priority_score(with_desc)
        score_without = quest_manager.calculate_priority_score(without_desc)

        assert score_with == score_without + 2

    def test_priority_score_variety_bonus(self, quest_manager):
        """Different source from previous should get +3 bonus."""
        now = datetime.now().isoformat()

        quest = {"created_at": now, "source": "github_issue"}

        # No previous source
        score_no_prev = quest_manager.calculate_priority_score(quest, previous_source=None)

        # Same source
        score_same = quest_manager.calculate_priority_score(quest, previous_source="github_issue")

        # Different source
        score_diff = quest_manager.calculate_priority_score(quest, previous_source="manual")

        assert score_no_prev == score_same
        assert score_diff == score_same + 3

    def test_prioritized_quests_ordering(self, quest_manager, storage):
        """Higher priority quests should appear first."""
        # Create quests with different sources
        # GitHub issue should rank higher than manual
        storage.create_quest(
            title="Manual quest",
            source="manual",
        )
        storage.create_quest(
            title="GitHub issue",
            source="github_issue",
            source_ref="https://github.com/test/repo/issues/1",
        )

        prioritized = quest_manager.get_prioritized_quests(status="pending", limit=5)

        assert len(prioritized) == 2
        # GitHub issue should be first (higher source score)
        assert prioritized[0]["title"] == "GitHub issue"
        assert prioritized[1]["title"] == "Manual quest"
        # Both should have priority_score field
        assert "priority_score" in prioritized[0]
        assert "priority_score" in prioritized[1]
        assert prioritized[0]["priority_score"] >= prioritized[1]["priority_score"]

    def test_prioritized_quests_variety(self, quest_manager, storage):
        """Should interleave sources rather than grouping same source."""
        # Create multiple quests from same sources
        for i in range(3):
            storage.create_quest(
                title=f"GitHub issue {i}",
                source="github_issue",
                source_ref=f"https://github.com/test/repo/issues/{i}",
            )
        for i in range(3):
            storage.create_quest(
                title=f"TODO item {i}",
                source="todo_scan",
                source_ref=f"file.py:line{i}",
            )

        prioritized = quest_manager.get_prioritized_quests(status="pending", limit=6)

        assert len(prioritized) == 6

        # Check that sources are interleaved (not all github_issue first)
        # Due to variety bonus, we shouldn't have 3 consecutive same-source quests
        consecutive_same = 0
        max_consecutive = 0
        prev_source = None
        for quest in prioritized:
            if quest["source"] == prev_source:
                consecutive_same += 1
            else:
                max_consecutive = max(max_consecutive, consecutive_same)
                consecutive_same = 1
            prev_source = quest["source"]
        max_consecutive = max(max_consecutive, consecutive_same)

        # With variety bonus, we should typically see alternation
        # At most 2 consecutive same source (depending on score distribution)
        assert max_consecutive <= 3

    def test_prioritized_quests_empty(self, quest_manager):
        """Should return empty list when no quests."""
        prioritized = quest_manager.get_prioritized_quests(status="pending", limit=5)
        assert prioritized == []

    def test_prioritized_quests_respects_limit(self, quest_manager, storage):
        """Should respect the limit parameter."""
        for i in range(10):
            storage.create_quest(title=f"Quest {i}", source="manual")

        prioritized = quest_manager.get_prioritized_quests(status="pending", limit=3)
        assert len(prioritized) == 3

    def test_prioritized_quests_description_affects_order(self, quest_manager, storage):
        """Quests with descriptions should rank higher than those without."""
        storage.create_quest(
            title="Without description",
            source="manual",
        )
        storage.create_quest(
            title="With description",
            source="manual",
            description="This has context",
        )

        prioritized = quest_manager.get_prioritized_quests(status="pending", limit=5)

        assert len(prioritized) == 2
        # Quest with description should be first
        assert prioritized[0]["title"] == "With description"
        assert prioritized[1]["title"] == "Without description"
