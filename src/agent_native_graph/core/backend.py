"""Core backend protocol for Agent-Native graph tools.

Tool functions depend on this small contract instead of a concrete database
driver. Concrete backends, such as Neo4j, can keep their storage/query details
outside the tool layer while exposing the same callable surface.
"""

from typing import Any, Protocol

from agent_native_graph.domain.handles import Handle


class AgentGraphBackend(Protocol):
    """Protocol implemented by backends that can execute ANA tool calls."""

    last_fetch: list[list[Any]] | None

    def call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        """Execute one registered tool by name."""
        ...

    def close(self) -> None:
        """Release backend resources such as database connections."""
        ...

    def _handle(self, handle_id: str) -> Handle:
        """Return a server-side handle by id."""
        ...

    def _store(
        self,
        rows: list[dict[str, Any]],
        *,
        focus: str | None = None,
        kind: str = "rows",
        columns: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Store intermediate rows and return a handle descriptor."""
        ...
