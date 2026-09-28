"""Server-side handle storage for Agent-Native graph backends."""

import json
from typing import Any

from agent_native_graph.core.graph_utils import (
    _columns,
    _compact_tool_args,
    _extract_handle_refs,
    _handle_entity_vars,
    _preview,
)
from agent_native_graph.domain.handles import Handle


class HandleStore:
    """Owns intermediate handles and their lineage across tool calls."""

    def __init__(self) -> None:
        self.handles: dict[str, Handle] = {}
        self.lineage: dict[str, list[dict[str, Any]]] = {}
        self.counter = 0

    def store(
        self,
        rows: list[dict[str, Any]],
        *,
        focus: str | None = None,
        kind: str = "rows",
        columns: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Store rows and return the public descriptor given back to the agent."""

        self.counter += 1
        handle_id = f"h{self.counter}"
        handle = Handle(
            id=handle_id,
            rows=rows,
            focus=focus,
            kind=kind,
            columns=list(columns or []),
            metadata=dict(metadata or {}),
        )
        self.handles[handle_id] = handle
        result = {
            "handle": handle_id,
            "kind": kind,
            "focus": focus,
            "entity_variables": _handle_entity_vars(rows),
            "columns": list(columns or []),
            "matched_count": len(rows),
            "preview": _preview(rows, focus=focus, columns=columns),
            "truncated": len(rows) > 10,
        }
        if result["entity_variables"]:
            result["composition_hint"] = (
                "This handle still contains entity variables and can be used by "
                "expand, entity_set_operation, count_handle, group_handle, or project. "
                f"Use entity variables: {result['entity_variables']}."
            )
        elif kind == "table":
            result["composition_hint"] = (
                "This handle is scalar/table-shaped. It is safe to fetch as a final "
                "answer or aggregate as a table, but not for expand/entity_set_operation. "
                "For later graph/set work, keep an entity handle and project only after "
                "the graph/set operation, or use project with keep_entities=true."
            )
        if len(rows) >= 1000:
            result["large_result_hint"] = (
                "This handle is large or may be capped by the tool limit. Do not fetch it "
                "for count/grouped-summary questions; call count_handle, group_handle, "
                "project, or a more specific server-side graph query first."
            )
        return result

    def get(self, handle_id: str) -> Handle:
        """Return an existing handle or raise an agent-actionable error."""

        if handle_id not in self.handles:
            available = self.available_summaries()
            latest = available[-1]["handle"] if available else None
            repair_hint = (
                f"The latest available handle is {latest!r}. Use exactly one handle "
                "from available_handles; never predict the id of a future tool result."
                if latest
                else "No handles exist yet. Start with schema/entity/search/pattern tools "
                "that create a handle before using from/left/right operands."
            )
            raise ValueError(
                f"Unknown handle: {handle_id}. Available handles: {available}. "
                f"{repair_hint} Call handle_recap on an available handle if you are "
                "unsure which variable names it contains."
            )
        return self.handles[handle_id]

    def first_row(self, handle_id: str) -> dict[str, Any]:
        """Return the first row of a handle, validating empty handles."""

        handle = self.get(handle_id)
        if not handle.rows:
            raise ValueError(f"Handle {handle_id} is empty")
        return handle.rows[0]

    def record_lineage(self, tool: str, args: dict[str, Any], result: dict[str, Any]) -> None:
        """Attach tool-call lineage to a newly produced handle."""

        handle_id = result.get("handle")
        if not isinstance(handle_id, str) or handle_id not in self.handles:
            return
        parent_ids = [item for item in _extract_handle_refs(args) if item in self.handles]
        lineage: list[dict[str, Any]] = []
        seen_steps: set[str] = set()
        for parent_id in parent_ids:
            for step in self.lineage.get(parent_id, []):
                step_key = json.dumps(step, ensure_ascii=False, sort_keys=True)
                if step_key not in seen_steps:
                    lineage.append(step)
                    seen_steps.add(step_key)
        step = {
            "tool": tool,
            "args": _compact_tool_args(args),
            "parents": parent_ids,
            "produced": self.summary(handle_id),
        }
        lineage.append(step)
        self.lineage[handle_id] = lineage[-24:]

    def available_summaries(self) -> list[dict[str, Any]]:
        """Return compact descriptors for every known handle."""

        return [self.summary(handle_id) for handle_id in sorted(self.handles)]

    def summary(self, handle_id: str) -> dict[str, Any]:
        """Return a compact descriptor for one handle."""

        handle = self.handles[handle_id]
        return {
            "handle": handle.id,
            "kind": handle.kind,
            "focus": handle.focus,
            "row_count": len(handle.rows),
            "entity_variables": _handle_entity_vars(handle.rows),
            "columns": handle.columns or _columns(handle.rows),
            "preview": _preview(handle.rows, focus=handle.focus, columns=handle.columns)[:3],
        }
