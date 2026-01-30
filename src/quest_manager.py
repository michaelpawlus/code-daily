"""
Quest management for code-daily.

Provides lifecycle management for coding quests: creation, acceptance,
completion, and skipping with save-as-idea functionality.
"""

from src.storage import CommitStorage


class QuestManager:
    """Manages the quest lifecycle."""

    def __init__(self, storage: CommitStorage | None = None):
        """
        Initialize the quest manager.

        Args:
            storage: CommitStorage instance. Creates default if not provided.
        """
        self.storage = storage or CommitStorage()

    def get_pending_quests(self, limit: int = 5) -> list[dict]:
        """
        Get pending quests for display.

        Args:
            limit: Maximum number of quests to return

        Returns:
            List of pending quest dictionaries
        """
        return self.storage.get_quests(status="pending", limit=limit)

    def get_active_quests(self) -> list[dict]:
        """
        Get currently active quests.

        Returns:
            List of active quest dictionaries
        """
        return self.storage.get_quests(status="active")

    def get_all_quests(self) -> list[dict]:
        """
        Get all quests regardless of status.

        Returns:
            List of all quest dictionaries
        """
        return self.storage.get_quests()

    def add_manual_quest(self, title: str, description: str | None = None) -> dict:
        """
        Add a new manual quest.

        Args:
            title: Quest title
            description: Optional description

        Returns:
            Created quest dictionary
        """
        quest_id = self.storage.create_quest(
            title=title,
            source="manual",
            description=description,
        )
        return self.storage.get_quest(quest_id)

    def accept_quest(self, quest_id: int) -> dict | None:
        """
        Accept a quest (mark as active).

        Args:
            quest_id: The quest ID to accept

        Returns:
            Updated quest dictionary or None if not found
        """
        success = self.storage.update_quest_status(quest_id, "active")
        if success:
            return self.storage.get_quest(quest_id)
        return None

    def complete_quest(self, quest_id: int) -> dict | None:
        """
        Complete a quest.

        Args:
            quest_id: The quest ID to complete

        Returns:
            Updated quest dictionary or None if not found
        """
        success = self.storage.update_quest_status(quest_id, "completed")
        if success:
            return self.storage.get_quest(quest_id)
        return None

    def skip_quest(
        self,
        quest_id: int,
        action: str = "archive",
        save_as_idea: bool = False,
    ) -> dict:
        """
        Skip a quest with optional save-as-idea.

        Args:
            quest_id: The quest ID to skip
            action: What to do ('archive' or 'skip')
            save_as_idea: If True, save quest title as a new idea

        Returns:
            Dictionary with skip result and optionally the created idea
        """
        quest = self.storage.get_quest(quest_id)
        if not quest:
            return {"success": False, "error": "Quest not found"}

        status = "archived" if action == "archive" else "skipped"
        self.storage.update_quest_status(quest_id, status)

        result = {"success": True, "quest": self.storage.get_quest(quest_id)}

        if save_as_idea:
            idea_content = quest["title"]
            if quest.get("description"):
                idea_content += f" - {quest['description']}"
            idea_id = self.storage.create_idea(idea_content)
            result["idea"] = self.storage.get_idea(idea_id)

        return result

    def promote_idea_to_quest(self, idea_id: int) -> dict | None:
        """
        Promote an idea to a quest.

        Args:
            idea_id: The idea ID to promote

        Returns:
            Created quest dictionary or None if idea not found
        """
        idea = self.storage.get_idea(idea_id)
        if not idea:
            return None

        quest_id = self.storage.create_quest(
            title=idea["content"],
            source="ideas_md",
            source_ref=f"idea:{idea_id}",
        )

        self.storage.update_idea_status(idea_id, "promoted")

        return self.storage.get_quest(quest_id)

    def get_quest_summary(self) -> dict:
        """
        Get a summary of quest counts by status.

        Returns:
            Dictionary with counts per status
        """
        all_quests = self.storage.get_quests()

        summary = {
            "total": len(all_quests),
            "pending": 0,
            "active": 0,
            "completed": 0,
            "skipped": 0,
            "archived": 0,
        }

        for quest in all_quests:
            status = quest.get("status", "pending")
            if status in summary:
                summary[status] += 1

        return summary
