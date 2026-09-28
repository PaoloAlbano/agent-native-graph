"""Abstract backend contract for Agent-Native graph tools.

The tool layer calls these methods through a backend instance. Concrete
adapters, such as Neo4j, keep database-specific query construction and storage
details behind this boundary. A future ArangoDB, Memgraph, or GraphArrow backend
should implement this class and can then reuse the same ANA tool definitions and
interfaces.
"""

from abc import ABC, abstractmethod
from typing import Any

from agent_native_graph.domain.handles import Handle


class AgentGraphBackend(ABC):
    """Base class for graph engines that execute ANA tool operations."""

    last_fetch: list[list[Any]] | None

    @abstractmethod
    def call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        """Execute one registered tool by name."""

    @abstractmethod
    def close(self) -> None:
        """Release backend resources such as database connections."""

    @abstractmethod
    def _handle(self, handle_id: str) -> Handle:
        """Return a server-side handle by id."""

    @abstractmethod
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

    @abstractmethod
    def _schema_overview(self) -> dict[str, Any]:
        """Return a bounded schema overview."""

    @abstractmethod
    def _schema_search(self, args: dict[str, Any]) -> dict[str, Any]:
        """Search labels, relationships, and properties from natural-language hints."""

    @abstractmethod
    def _schema_describe_label(self, args: dict[str, Any]) -> dict[str, Any]:
        """Describe one node label."""

    @abstractmethod
    def _schema_describe_relationship(self, args: dict[str, Any]) -> dict[str, Any]:
        """Describe one relationship type."""

    @abstractmethod
    def _inspect_paths(self, args: dict[str, Any]) -> dict[str, Any]:
        """Find schema-level paths between labels."""

    @abstractmethod
    def _summarize_handle(self, args: dict[str, Any]) -> dict[str, Any]:
        """Summarize an intermediate handle."""

    @abstractmethod
    def _handle_recap(self, args: dict[str, Any]) -> dict[str, Any]:
        """Explain how an intermediate handle was produced."""

    @abstractmethod
    def _repair_empty_result(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return repair suggestions for failed or empty tool results."""

    @abstractmethod
    def _entity_resolve(self, args: dict[str, Any]) -> dict[str, Any]:
        """Resolve a named entity into graph nodes."""

    @abstractmethod
    def _node_search(self, args: dict[str, Any]) -> dict[str, Any]:
        """Find nodes by exact property equality."""

    @abstractmethod
    def _value_search(self, args: dict[str, Any]) -> dict[str, Any]:
        """Find real property values in the graph before using them as filters."""

    @abstractmethod
    def _node_scan(self, args: dict[str, Any]) -> dict[str, Any]:
        """List nodes of one label."""

    @abstractmethod
    def _count_nodes(self, args: dict[str, Any]) -> dict[str, Any]:
        """Count nodes for a label."""

    @abstractmethod
    def _count_handle(self, args: dict[str, Any]) -> dict[str, Any]:
        """Count rows or entities stored in a handle."""

    @abstractmethod
    def _expand(self, args: dict[str, Any]) -> dict[str, Any]:
        """Traverse one relationship hop from a handle."""

    @abstractmethod
    def _expand_aggregate(self, args: dict[str, Any]) -> dict[str, Any]:
        """Traverse one hop and aggregate server-side."""

    @abstractmethod
    def _optional_expand_count(self, args: dict[str, Any]) -> dict[str, Any]:
        """Perform left-preserving optional one-hop counts."""

    @abstractmethod
    def _optional_count_by_pattern(self, args: dict[str, Any]) -> dict[str, Any]:
        """Find source rows by pattern and count optional related targets."""

    @abstractmethod
    def _relationship_query(self, args: dict[str, Any]) -> dict[str, Any]:
        """Run a single-hop relationship query without a prior handle."""

    @abstractmethod
    def _multi_hop_query(self, args: dict[str, Any]) -> dict[str, Any]:
        """Run a bounded multi-hop traversal."""

    @abstractmethod
    def _pattern_query(self, args: dict[str, Any]) -> dict[str, Any]:
        """Run a path-shaped graph query."""

    @abstractmethod
    def _top_entities_by_property(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return top entities ordered by a scalar property."""

    @abstractmethod
    def _constraint_query(self, args: dict[str, Any]) -> dict[str, Any]:
        """Find nodes satisfying one-hop relationship/property constraints."""

    @abstractmethod
    def _entity_set_operation(self, args: dict[str, Any]) -> dict[str, Any]:
        """Combine entity handles by graph identity."""

    @abstractmethod
    def _filter(self, args: dict[str, Any]) -> dict[str, Any]:
        """Filter an existing handle by property."""

    @abstractmethod
    def _filter_same_node(self, args: dict[str, Any]) -> dict[str, Any]:
        """Keep rows where two variables point to the same graph node."""

    @abstractmethod
    def _join_handles(self, args: dict[str, Any]) -> dict[str, Any]:
        """Join two handles by graph node identity."""

    @abstractmethod
    def _same_target_role_intersection(self, args: dict[str, Any]) -> dict[str, Any]:
        """Find sources that satisfy multiple roles against the same target."""

    @abstractmethod
    def _shared_role_aggregate(self, args: dict[str, Any]) -> dict[str, Any]:
        """Find peers sharing related entities with a seed, optionally aggregated."""

    @abstractmethod
    def _combine(self, args: dict[str, Any]) -> dict[str, Any]:
        """Legacy two-handle set operation."""

    @abstractmethod
    def _aggregate(self, args: dict[str, Any]) -> dict[str, Any]:
        """Group existing handle rows and compute metrics."""

    @abstractmethod
    def _project(self, args: dict[str, Any]) -> dict[str, Any]:
        """Project scalar properties from entities in a handle."""

    @abstractmethod
    def _compare(self, args: dict[str, Any]) -> dict[str, Any]:
        """Compare scalar values from two handles."""

    @abstractmethod
    def _scalar_compute(self, args: dict[str, Any]) -> dict[str, Any]:
        """Compute scalar arithmetic or reductions over projected handle values."""

    @abstractmethod
    def _fetch(self, args: dict[str, Any]) -> dict[str, Any]:
        """Fetch rows from a handle as final output."""
