"""
Quest management for code-daily.

Provides lifecycle management for coding quests: creation, acceptance,
completion, and skipping with save-as-idea functionality.
"""

from datetime import datetime

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

    def calculate_priority_score(
        self, quest: dict, previous_source: str | None = None
    ) -> int:
        """
        Calculate priority score for a quest (higher = more priority).

        Args:
            quest: Quest dictionary with source, created_at, description
            previous_source: Source of previously scored quest (for variety bonus)

        Returns:
            Integer priority score
        """
        score = 0

        # Age factor: older quests get boosted (max +10 points)
        created_at_str = quest.get("created_at")
        if created_at_str:
            try:
                created_at = datetime.fromisoformat(created_at_str)
                age_days = (datetime.now() - created_at).days
                score += min(age_days, 10)
            except (ValueError, TypeError):
                pass  # Skip age bonus if date parsing fails

        # Source priority: external commitments rank higher
        source_scores = {
            "github_issue": 3,
            "todo_scan": 2,
            "ideas_md": 1,
            "manual": 0,
        }
        score += source_scores.get(quest.get("source", ""), 0)

        # Description bonus: more context = more actionable
        if quest.get("description"):
            score += 2

        # Variety bonus: mix sources rather than showing all from one type
        if previous_source and quest.get("source") != previous_source:
            score += 3

        return score

    def get_prioritized_quests(
        self, status: str = "pending", limit: int = 5
    ) -> list[dict]:
        """
        Get quests sorted by priority score.

        Args:
            status: Quest status to filter by
            limit: Maximum number of quests to return

        Returns:
            List of quest dictionaries with priority_score added, sorted by score descending
        """
        quests = self.storage.get_quests(status=status)

        if not quests:
            return []

        # First pass: calculate base scores
        for quest in quests:
            quest["priority_score"] = self.calculate_priority_score(quest)

        # Sort by base score descending
        quests.sort(key=lambda q: q["priority_score"], reverse=True)

        # Second pass: apply variety bonus to reorder
        # Take top candidates and interleave sources when possible
        result = []
        remaining = quests.copy()
        prev_source = None

        while remaining and len(result) < limit:
            # Find best quest considering variety bonus
            best_idx = 0
            best_score = remaining[0]["priority_score"]

            if prev_source:
                for i, quest in enumerate(remaining[: min(5, len(remaining))]):
                    adjusted_score = quest["priority_score"]
                    if quest.get("source") != prev_source:
                        adjusted_score += 3  # variety bonus
                    if adjusted_score > best_score:
                        best_score = adjusted_score
                        best_idx = i

            selected = remaining.pop(best_idx)
            selected["priority_score"] = best_score  # Update with variety bonus
            result.append(selected)
            prev_source = selected.get("source")

        return result

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

    def sync_github_issues(self, issues: list[dict]) -> dict:
        """
        Sync GitHub issues to quests, skipping duplicates.

        Creates new quests from GitHub issues that haven't been synced before.
        Pull requests are filtered out (they appear in /issues API but have 'pull_request' key).

        Args:
            issues: List of issue dictionaries from GitHub API

        Returns:
            Dictionary with 'added' and 'skipped' counts
        """
        added = 0
        skipped = 0

        for issue in issues:
            # Skip pull requests (they appear in /issues API with a pull_request key)
            if "pull_request" in issue:
                continue

            issue_url = issue.get("html_url", "")
            if not issue_url:
                continue

            # Check if we already have a quest for this issue
            if self.storage.quest_exists_by_source_ref("github_issue", issue_url):
                skipped += 1
                continue

            # Extract repo name from URL: https://github.com/owner/repo/issues/123
            repo_name = ""
            if "github.com/" in issue_url:
                parts = issue_url.split("github.com/")[1].split("/")
                if len(parts) >= 2:
                    repo_name = f"{parts[0]}/{parts[1]}"

            # Build title with repo prefix
            title = issue.get("title", "Untitled issue")
            if repo_name:
                title = f"[{repo_name}] {title}"

            # Truncate description to 200 chars
            description = issue.get("body") or ""
            if len(description) > 200:
                description = description[:197] + "..."

            self.storage.create_quest(
                title=title,
                source="github_issue",
                source_ref=issue_url,
                description=description if description else None,
            )
            added += 1

        return {"added": added, "skipped": skipped}

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

    def sync_todo_comments(self, todos: list) -> dict:
        """
        Sync TODO/FIXME comments to quests, skipping duplicates.

        Creates new quests from TODO comments that haven't been synced before.

        Args:
            todos: List of TodoComment objects from the scanner

        Returns:
            Dictionary with 'added' and 'skipped' counts
        """
        added = 0
        skipped = 0

        for todo in todos:
            source_ref = todo.source_ref

            # Check if we already have a quest for this TODO
            if self.storage.quest_exists_by_source_ref("todo_scan", source_ref):
                skipped += 1
                continue

            # Build title with comment type prefix
            title = f"[{todo.comment_type}] {todo.content}"

            # Truncate title if too long
            if len(title) > 200:
                title = title[:197] + "..."

            self.storage.create_quest(
                title=title,
                source="todo_scan",
                source_ref=source_ref,
            )
            added += 1

        return {"added": added, "skipped": skipped}
