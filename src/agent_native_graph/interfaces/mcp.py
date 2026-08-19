"""Optional MCP transport adapter for Agent-Native Graph.

This module defines the MCP boundary without making MCP a required dependency
for the core package. The ANA tool contracts remain defined by decorators in
`agent_native_graph.tools`; this adapter only translates that registry into an
MCP server shape.
"""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from agent_native_graph.core.tool_specs import SCHEMA_ENTRY_MODES, _tool_specs

MCP_EXTRA_INSTALL_HINT = "Install MCP support with `uv sync --extra mcp`."


@dataclass(frozen=True)
class McpInterfaceConfig:
    """Configuration for the future MCP transport surface."""

    name: str = "agent-native-graph"
    enable_planning_tools: bool = False
    schema_entry: str = "overview"
    expose_tool_dispatch: bool = False

    def __post_init__(self) -> None:
        if self.schema_entry not in SCHEMA_ENTRY_MODES:
            allowed = ", ".join(SCHEMA_ENTRY_MODES)
            raise ValueError(f"schema_entry must be one of: {allowed}")


def mcp_tool_catalog(config: McpInterfaceConfig | None = None) -> list[dict[str, Any]]:
    """Return the ANA tools that this MCP adapter would expose."""
    config = config or McpInterfaceConfig()
    catalog: list[dict[str, Any]] = []
    for spec in _tool_specs(
        enable_planning_tools=config.enable_planning_tools,
        schema_entry=config.schema_entry,
    ):
        input_schema = deepcopy(spec["function"]["parameters"])
        input_schema["additionalProperties"] = False
        catalog.append(
            {
                "name": spec["function"]["name"],
                "description": spec["function"]["description"],
                "inputSchema": input_schema,
            }
        )
    return catalog


def create_mcp_server(
    *,
    backend_factory: Callable[[], Any] | None = None,
    config: McpInterfaceConfig | None = None,
) -> Any:
    """Create an MCP server instance when the optional MCP package is installed.

    The first slice exposes discovery-only metadata by default. Passing
    `expose_tool_dispatch=True` enables a generic `call_ana_tool` bridge, useful
    for local experiments before we map each ANA tool to a first-class MCP tool.
    """
    config = config or McpInterfaceConfig()
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - depends on optional extra.
        raise RuntimeError(MCP_EXTRA_INSTALL_HINT) from exc

    server = FastMCP(config.name)

    @server.tool(
        name="list_ana_tools",
        description=(
            "Lists Agent-Native Graph tools available through this MCP adapter. "
            "Use this to inspect names, descriptions, and input schemas before calling tools."
        ),
    )
    def list_ana_tools() -> list[dict[str, Any]]:
        return mcp_tool_catalog(config)

    if config.expose_tool_dispatch:
        if backend_factory is None:
            raise ValueError("backend_factory is required when expose_tool_dispatch=True")

        @server.tool(
            name="call_ana_tool",
            description=(
                "Calls one Agent-Native Graph tool by name with JSON arguments. "
                "This is a temporary bridge; future MCP slices should expose selected "
                "ANA tools as first-class MCP tools."
            ),
        )
        def call_ana_tool(tool: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
            return backend_factory().call(tool, args or {})

    return server


__all__ = [
    "MCP_EXTRA_INSTALL_HINT",
    "McpInterfaceConfig",
    "create_mcp_server",
    "mcp_tool_catalog",
]
