"""Diagnostic and repair ANA tool wrappers."""

from typing import Annotated, Any

from agent_native_graph.core.backend import AgentGraphBackend
from agent_native_graph.core.enums import ToolProfile, ToolStatus
from agent_native_graph.core.tooling import ToolParam, tool


@tool(
    name="repair_empty_result",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Return schema-grounded repair suggestions for empty or failed tool calls.",
    description=(
        "Returns schema-grounded repair suggestions for a zero-row result or tool "
        "contract error. Use after pattern_query, relationship_query, expand, or "
        "entity_set_operation fails or returns empty. It suggests direction fixes, "
        "bound-variable fixes, and safer diagnostic tools without using dataset-specific rules."
    ),
)
def repair_empty_result(
    backend: AgentGraphBackend,
    failed_tool: Annotated[
        str,
        ToolParam("Name of the tool that failed or returned zero rows.", alias="tool"),
    ],
    failed_args: Annotated[
        dict[str, Any],
        ToolParam("Arguments passed to the failed tool.", alias="args"),
    ],
    error: Annotated[
        str | None,
        ToolParam("Optional error text from the failed call.", required=False),
    ] = None,
    reason: Annotated[
        str | None,
        ToolParam("Optional short reason, e.g. 'zero_rows' or 'tool_error'.", required=False),
    ] = None,
) -> dict[str, Any]:
    return backend._repair_empty_result(
        {
            "failed_tool": failed_tool,
            "failed_args": failed_args,
            "error": error,
            "reason": reason,
        }
    )


__all__ = ["repair_empty_result"]
