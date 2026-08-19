"""Provider contract for model access.

The rest of the application should depend on this shape instead of a concrete
gateway. That keeps benchmark orchestration independent from OpenAI-compatible,
Anthropic, local vLLM, or future provider quirks.
"""

from typing import Any, Protocol


class LLMProvider(Protocol):
    """Minimal chat interface needed by ANA benchmark runners."""

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return an assistant message, optionally using native tool-call metadata."""

    def complete(self, messages: list[dict[str, str]]) -> str:
        """Return only textual content for non-tool-call evaluation flows."""
