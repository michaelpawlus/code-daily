"""Tests for the LLM client and AI quest enhancement."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.storage import CommitStorage
from src.quest_manager import QuestManager
from src.llm_client import (
    ClaudeClient,
    EnhancementResult,
    LLMConfigError,
    LLMRateLimitError,
    LLMError,
)


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


class TestClaudeClientConfiguration:
    """Tests for Claude client configuration."""

    def test_is_configured_without_key(self):
        """Client reports not configured without API key."""
        with patch("src.llm_client.ANTHROPIC_API_KEY", None):
            client = ClaudeClient()
            assert client.is_configured is False

    def test_is_configured_with_placeholder(self):
        """Client reports not configured with placeholder key."""
        with patch("src.llm_client.ANTHROPIC_API_KEY", "your_api_key_here"):
            client = ClaudeClient()
            assert client.is_configured is False

    def test_is_configured_with_real_key(self):
        """Client reports configured with real API key."""
        with patch("src.llm_client.ANTHROPIC_API_KEY", "sk-ant-api03-real-key"):
            client = ClaudeClient()
            assert client.is_configured is True

    def test_get_client_raises_without_key(self):
        """Getting client raises LLMConfigError without API key."""
        with patch("src.llm_client.ANTHROPIC_API_KEY", None):
            client = ClaudeClient()
            with pytest.raises(LLMConfigError) as exc_info:
                client._get_client()
            assert "not configured" in str(exc_info.value).lower()


class TestEnhanceTodo:
    """Tests for TODO enhancement functionality."""

    def test_enhance_todo_returns_result(self, storage):
        """Enhancement returns proper result structure."""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps({
                    "description": "Fix the authentication flow",
                    "difficulty": 3,
                    "difficulty_reasoning": "Requires understanding of auth system",
                })
            )
        ]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("src.llm_client.ANTHROPIC_API_KEY", "sk-test-key"):
            client = ClaudeClient(storage=storage)

            with patch.object(client, "_get_client", return_value=mock_client):
                result = client.enhance_todo("Fix auth bug", "src/auth.py")

        assert isinstance(result, EnhancementResult)
        assert result.description == "Fix the authentication flow"
        assert result.difficulty == 3
        assert result.difficulty_reasoning == "Requires understanding of auth system"

    def test_enhance_todo_caches_result(self, storage):
        """Enhancement result is cached."""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps({
                    "description": "Cached description",
                    "difficulty": 2,
                    "difficulty_reasoning": "Simple task",
                })
            )
        ]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("src.llm_client.ANTHROPIC_API_KEY", "sk-test-key"):
            client = ClaudeClient(storage=storage)

            with patch.object(client, "_get_client", return_value=mock_client):
                # First call
                result1 = client.enhance_todo("Cache test", "test.py")

            # Second call should use cache (no mock needed)
            result2 = client.enhance_todo("Cache test", "test.py")

        assert result1.description == result2.description
        assert result1.difficulty == result2.difficulty
        # API should only be called once
        assert mock_client.messages.create.call_count == 1

    def test_enhance_todo_handles_markdown_response(self, storage):
        """Enhancement handles JSON wrapped in markdown code blocks."""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text='```json\n{"description": "Markdown wrapped", "difficulty": 1, "difficulty_reasoning": "Quick fix"}\n```'
            )
        ]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("src.llm_client.ANTHROPIC_API_KEY", "sk-test-key"):
            client = ClaudeClient(storage=storage)

            with patch.object(client, "_get_client", return_value=mock_client):
                result = client.enhance_todo("Test markdown", "test.py")

        assert result.description == "Markdown wrapped"

    def test_enhance_todo_clamps_difficulty(self, storage):
        """Enhancement clamps difficulty to 1-5 range."""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps({
                    "description": "Out of range difficulty",
                    "difficulty": 10,
                    "difficulty_reasoning": "Invalid rating",
                })
            )
        ]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("src.llm_client.ANTHROPIC_API_KEY", "sk-test-key"):
            client = ClaudeClient(storage=storage)

            with patch.object(client, "_get_client", return_value=mock_client):
                result = client.enhance_todo("High difficulty", "test.py")

        assert result.difficulty == 5  # Clamped to max

    def test_enhance_todo_handles_rate_limit(self, storage):
        """Enhancement raises LLMRateLimitError on rate limit."""
        import anthropic

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = anthropic.RateLimitError(
            message="Rate limit exceeded",
            response=MagicMock(status_code=429),
            body={"error": {"message": "Rate limit exceeded"}},
        )

        with patch("src.llm_client.ANTHROPIC_API_KEY", "sk-test-key"):
            client = ClaudeClient(storage=storage)

            with patch.object(client, "_get_client", return_value=mock_client):
                with pytest.raises(LLMRateLimitError):
                    client.enhance_todo("Rate limit test", "test.py")

    def test_enhance_todo_handles_invalid_json(self, storage):
        """Enhancement raises LLMError on invalid JSON response."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="This is not valid JSON")]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("src.llm_client.ANTHROPIC_API_KEY", "sk-test-key"):
            client = ClaudeClient(storage=storage)

            with patch.object(client, "_get_client", return_value=mock_client):
                with pytest.raises(LLMError) as exc_info:
                    client.enhance_todo("Invalid JSON test", "test.py")
                assert "json" in str(exc_info.value).lower()

    def test_enhance_todo_handles_missing_fields(self, storage):
        """Enhancement raises LLMError when response missing required fields."""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps({
                    "description": "Missing other fields",
                })
            )
        ]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("src.llm_client.ANTHROPIC_API_KEY", "sk-test-key"):
            client = ClaudeClient(storage=storage)

            with patch.object(client, "_get_client", return_value=mock_client):
                with pytest.raises(LLMError) as exc_info:
                    client.enhance_todo("Missing fields test", "test.py")
                assert "missing" in str(exc_info.value).lower()


class TestQuestEnhancement:
    """Tests for quest enhancement via QuestManager."""

    def test_enhance_quest_success(self, quest_manager, storage):
        """Can enhance a quest successfully."""
        # Create a quest
        quest_id = storage.create_quest(
            title="Fix the login bug",
            source="todo_scan",
            source_ref="src/auth.py:42",
        )

        mock_result = EnhancementResult(
            description="Resolve authentication issue",
            difficulty=2,
            difficulty_reasoning="Small authentication fix",
        )

        with patch("src.quest_manager.ClaudeClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.is_configured = True
            mock_instance.enhance_todo.return_value = mock_result

            result = quest_manager.enhance_quest(quest_id)

        assert result["success"] is True
        assert result["quest"]["ai_description"] == "Resolve authentication issue"
        assert result["quest"]["difficulty"] == 2
        assert result["quest"]["difficulty_reasoning"] == "Small authentication fix"
        assert result["quest"]["enhanced_at"] is not None

    def test_enhance_quest_not_found(self, quest_manager):
        """Returns error for non-existent quest."""
        result = quest_manager.enhance_quest(999)

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_enhance_quest_not_configured(self, quest_manager, storage):
        """Returns error when AI not configured."""
        quest_id = storage.create_quest(title="Test quest")

        with patch("src.quest_manager.ClaudeClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.is_configured = False

            result = quest_manager.enhance_quest(quest_id)

        assert result["success"] is False
        assert "not configured" in result["error"].lower()

    def test_enhance_quest_rate_limit_error(self, quest_manager, storage):
        """Returns error on rate limit."""
        quest_id = storage.create_quest(title="Test quest")

        with patch("src.quest_manager.ClaudeClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.is_configured = True
            mock_instance.enhance_todo.side_effect = LLMRateLimitError("Rate limited")

            result = quest_manager.enhance_quest(quest_id)

        assert result["success"] is False
        assert "rate limit" in result["error"].lower()

    def test_enhance_pending_quests_batch(self, quest_manager, storage):
        """Can batch enhance multiple quests."""
        # Create quests
        for i in range(3):
            storage.create_quest(title=f"Quest {i}")

        mock_result = EnhancementResult(
            description="Enhanced description",
            difficulty=2,
            difficulty_reasoning="Reasoning",
        )

        with patch("src.quest_manager.ClaudeClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.is_configured = True
            mock_instance.enhance_todo.return_value = mock_result

            result = quest_manager.enhance_pending_quests(limit=3)

        assert result["success"] is True
        assert result["enhanced"] == 3
        assert len(result["quests"]) == 3
        assert len(result["errors"]) == 0

    def test_enhance_pending_quests_respects_limit(self, quest_manager, storage):
        """Batch enhancement respects limit."""
        for i in range(10):
            storage.create_quest(title=f"Quest {i}")

        mock_result = EnhancementResult(
            description="Enhanced",
            difficulty=1,
            difficulty_reasoning="Simple",
        )

        with patch("src.quest_manager.ClaudeClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.is_configured = True
            mock_instance.enhance_todo.return_value = mock_result

            result = quest_manager.enhance_pending_quests(limit=5)

        assert result["enhanced"] == 5
        assert result["total_requested"] == 5

    def test_enhance_pending_quests_max_limit(self, quest_manager, storage):
        """Batch enhancement enforces max limit of 20."""
        for i in range(25):
            storage.create_quest(title=f"Quest {i}")

        mock_result = EnhancementResult(
            description="Enhanced",
            difficulty=1,
            difficulty_reasoning="Simple",
        )

        with patch("src.quest_manager.ClaudeClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.is_configured = True
            mock_instance.enhance_todo.return_value = mock_result

            result = quest_manager.enhance_pending_quests(limit=50)

        # Should be capped at 20
        assert result["total_requested"] == 20

    def test_enhance_pending_quests_stops_on_rate_limit(self, quest_manager, storage):
        """Batch stops processing on rate limit error."""
        for i in range(5):
            storage.create_quest(title=f"Quest {i}")

        call_count = 0

        def mock_enhance(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                raise LLMRateLimitError("Rate limited")
            return EnhancementResult(
                description="Enhanced",
                difficulty=1,
                difficulty_reasoning="Simple",
            )

        with patch("src.quest_manager.ClaudeClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.is_configured = True
            mock_instance.enhance_todo.side_effect = mock_enhance

            result = quest_manager.enhance_pending_quests(limit=5)

        assert result["enhanced"] == 2
        assert len(result["errors"]) == 1
        assert "rate limit" in result["errors"][0]["error"].lower()

    def test_get_ai_status_enabled(self, quest_manager):
        """AI status reports enabled when configured."""
        with patch("src.quest_manager.ClaudeClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.is_configured = True

            status = quest_manager.get_ai_status()

        assert status["enabled"] is True
        assert "enabled" in status["message"].lower()

    def test_get_ai_status_disabled(self, quest_manager):
        """AI status reports disabled when not configured."""
        with patch("src.quest_manager.ClaudeClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.is_configured = False

            status = quest_manager.get_ai_status()

        assert status["enabled"] is False
        assert "ANTHROPIC_API_KEY" in status["message"]


class TestPriorityScoringWithAI:
    """Tests for priority scoring with AI fields."""

    def test_ai_description_bonus(self, quest_manager):
        """Quests with AI description get +1 bonus."""
        from datetime import datetime

        now = datetime.now().isoformat()

        with_ai = {
            "created_at": now,
            "source": "manual",
            "ai_description": "Enhanced description",
        }
        without_ai = {
            "created_at": now,
            "source": "manual",
            "ai_description": None,
        }

        score_with = quest_manager.calculate_priority_score(with_ai)
        score_without = quest_manager.calculate_priority_score(without_ai)

        assert score_with == score_without + 1

    def test_medium_difficulty_bonus(self, quest_manager):
        """Quests with difficulty 2-3 get +1 bonus."""
        from datetime import datetime

        now = datetime.now().isoformat()

        easy = {"created_at": now, "source": "manual", "difficulty": 1}
        medium = {"created_at": now, "source": "manual", "difficulty": 2}
        hard = {"created_at": now, "source": "manual", "difficulty": 5}

        score_easy = quest_manager.calculate_priority_score(easy)
        score_medium = quest_manager.calculate_priority_score(medium)
        score_hard = quest_manager.calculate_priority_score(hard)

        assert score_medium == score_easy + 1
        assert score_medium == score_hard + 1


class TestStorageAIFields:
    """Tests for storage AI field methods."""

    def test_update_quest_ai_fields(self, storage):
        """Can update AI fields on a quest."""
        quest_id = storage.create_quest(title="Test quest")

        success = storage.update_quest_ai_fields(
            quest_id=quest_id,
            ai_description="AI generated description",
            difficulty=3,
            difficulty_reasoning="Medium complexity",
        )

        assert success is True

        quest = storage.get_quest(quest_id)
        assert quest["ai_description"] == "AI generated description"
        assert quest["difficulty"] == 3
        assert quest["difficulty_reasoning"] == "Medium complexity"
        assert quest["enhanced_at"] is not None

    def test_update_quest_ai_fields_not_found(self, storage):
        """Returns False for non-existent quest."""
        success = storage.update_quest_ai_fields(
            quest_id=999,
            ai_description="Test",
            difficulty=1,
            difficulty_reasoning="Test",
        )

        assert success is False

    def test_get_quests_without_ai(self, storage):
        """Can get quests that haven't been enhanced."""
        # Create some quests
        q1 = storage.create_quest(title="Unenhanced 1")
        q2 = storage.create_quest(title="Unenhanced 2")
        q3 = storage.create_quest(title="Enhanced")

        # Enhance one
        storage.update_quest_ai_fields(
            quest_id=q3,
            ai_description="Enhanced",
            difficulty=1,
            difficulty_reasoning="Quick",
        )

        quests = storage.get_quests_without_ai(limit=10)

        assert len(quests) == 2
        titles = [q["title"] for q in quests]
        assert "Unenhanced 1" in titles
        assert "Unenhanced 2" in titles
        assert "Enhanced" not in titles

    def test_get_quests_without_ai_respects_limit(self, storage):
        """Respects limit parameter."""
        for i in range(10):
            storage.create_quest(title=f"Quest {i}")

        quests = storage.get_quests_without_ai(limit=3)

        assert len(quests) == 3

    def test_get_quests_without_ai_only_pending(self, storage):
        """Only returns pending quests."""
        q1 = storage.create_quest(title="Pending")
        q2 = storage.create_quest(title="Active")
        storage.update_quest_status(q2, "active")

        quests = storage.get_quests_without_ai(limit=10)

        assert len(quests) == 1
        assert quests[0]["title"] == "Pending"
