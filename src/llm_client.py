"""
Claude LLM client for AI-powered quest enhancement.

Provides AI-generated descriptions and difficulty ratings for quests
using the Anthropic API with caching support.
"""

import hashlib
import json
from dataclasses import dataclass

from src.config import ANTHROPIC_API_KEY

# Optional import for anthropic
try:
    import anthropic

    ANTHROPIC_AVAILABLE = True
except ImportError:
    anthropic = None
    ANTHROPIC_AVAILABLE = False


class LLMConfigError(Exception):
    """Raised when LLM is not configured (missing API key)."""

    pass


class LLMRateLimitError(Exception):
    """Raised when LLM API rate limit is exceeded."""

    pass


class LLMError(Exception):
    """Generic LLM error."""

    pass


@dataclass
class EnhancementResult:
    """Result of AI enhancement for a quest."""

    description: str
    difficulty: int
    difficulty_reasoning: str


# Prompt for TODO enhancement
ENHANCE_PROMPT = """Analyze this TODO/task from a codebase. Return a JSON object with:
- "description": A clear, actionable 1-3 sentence description that explains what needs to be done. Focus on the goal, not just repeating the TODO text.
- "difficulty": An integer 1-5 rating where:
  1 = Quick fix (< 30 minutes, simple change)
  2 = Small task (30 min - 2 hours, straightforward)
  3 = Medium task (2-4 hours, some complexity)
  4 = Large task (4-8 hours, significant work)
  5 = Major task (> 8 hours, complex changes)
- "difficulty_reasoning": A brief explanation (1 sentence) for the difficulty rating

Context:
- File: {file_path}
- Content: {content}

Respond with only valid JSON, no markdown or explanation."""

CACHE_TTL_HOURS = 168  # 1 week


class ClaudeClient:
    """Client for Claude API with caching support."""

    def __init__(self, storage=None):
        """
        Initialize the Claude client.

        Args:
            storage: CommitStorage instance for caching. Optional.
        """
        self.storage = storage
        self._client = None

    @property
    def is_configured(self) -> bool:
        """Check if the API key is configured."""
        return bool(ANTHROPIC_API_KEY) and ANTHROPIC_API_KEY != "your_api_key_here"

    def _get_client(self):
        """Get or create the Anthropic client."""
        if not self.is_configured:
            raise LLMConfigError(
                "Anthropic API key not configured. "
                "Set ANTHROPIC_API_KEY in your .env file."
            )

        if not ANTHROPIC_AVAILABLE:
            raise LLMError(
                "anthropic package not installed. Run: pip install anthropic"
            )

        if self._client is None:
            self._client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        return self._client

    def _cache_key(self, content: str, file_path: str) -> str:
        """Generate a cache key for the enhancement request."""
        data = f"{file_path}:{content}"
        return f"llm_enhance:{hashlib.sha256(data.encode()).hexdigest()[:16]}"

    def enhance_todo(
        self, content: str, file_path: str = "unknown"
    ) -> EnhancementResult:
        """
        Enhance a TODO comment with AI-generated description and difficulty.

        Args:
            content: The TODO content/title
            file_path: Path to the source file (for context)

        Returns:
            EnhancementResult with description, difficulty, and reasoning

        Raises:
            LLMConfigError: If API key is not configured
            LLMRateLimitError: If rate limit is exceeded
            LLMError: For other API errors
        """
        # Check cache first
        if self.storage:
            cache_key = self._cache_key(content, file_path)
            cached = self.storage.get_cache(cache_key)
            if cached:
                data = json.loads(cached)
                return EnhancementResult(
                    description=data["description"],
                    difficulty=data["difficulty"],
                    difficulty_reasoning=data["difficulty_reasoning"],
                )

        # Make API call
        client = self._get_client()
        prompt = ENHANCE_PROMPT.format(content=content, file_path=file_path)

        try:
            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.RateLimitError as e:
            raise LLMRateLimitError(
                "Rate limit exceeded. Please wait before making more requests."
            ) from e
        except anthropic.APIError as e:
            raise LLMError(f"API error: {e}") from e

        # Parse response
        response_text = message.content[0].text.strip()

        # Handle potential markdown code blocks
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            # Remove first line (```json or ```) and last line (```)
            response_text = "\n".join(lines[1:-1])

        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as e:
            raise LLMError(f"Failed to parse AI response as JSON: {e}")

        # Validate required fields
        if not all(k in data for k in ["description", "difficulty", "difficulty_reasoning"]):
            raise LLMError("AI response missing required fields")

        # Validate difficulty is 1-5
        difficulty = int(data["difficulty"])
        if not 1 <= difficulty <= 5:
            difficulty = max(1, min(5, difficulty))  # Clamp to valid range

        result = EnhancementResult(
            description=str(data["description"]),
            difficulty=difficulty,
            difficulty_reasoning=str(data["difficulty_reasoning"]),
        )

        # Cache the result
        if self.storage:
            cache_data = {
                "description": result.description,
                "difficulty": result.difficulty,
                "difficulty_reasoning": result.difficulty_reasoning,
            }
            self.storage.set_cache(cache_key, json.dumps(cache_data), hours=CACHE_TTL_HOURS)

        return result
