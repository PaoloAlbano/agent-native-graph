import pytest

from agent_native_graph.interfaces.mcp import (
    MCP_EXTRA_INSTALL_HINT,
    McpInterfaceConfig,
    create_mcp_server,
    mcp_tool_catalog,
)


def test_mcp_tool_catalog_uses_registered_tool_specs() -> None:
    catalog = mcp_tool_catalog()
    names = {tool["name"] for tool in catalog}

    assert "schema_overview" in names
    assert "entity_resolve" in names
    assert "fetch" in names
    assert "schema_inspect" not in names
    assert all("inputSchema" in tool for tool in catalog)


def test_mcp_tool_catalog_rejects_extra_top_level_properties() -> None:
    catalog = mcp_tool_catalog()
    schema_overview = next(tool for tool in catalog if tool["name"] == "schema_overview")

    assert schema_overview["inputSchema"]["additionalProperties"] is False


def test_mcp_tool_catalog_can_expose_planning_tools() -> None:
    catalog = mcp_tool_catalog(McpInterfaceConfig(enable_planning_tools=True))
    names = {tool["name"] for tool in catalog}

    assert "draft_tool_plan" in names
    assert "validate_tool_plan" in names


def test_mcp_config_validates_schema_entry() -> None:
    with pytest.raises(ValueError, match="schema_entry must be one of"):
        McpInterfaceConfig(schema_entry="unknown")


def test_create_mcp_server_reports_missing_optional_dependency() -> None:
    try:
        import mcp.server.fastmcp  # noqa: F401
    except ImportError:
        with pytest.raises(RuntimeError, match="Install MCP support"):
            create_mcp_server()
    else:
        pytest.skip("MCP dependency is installed in this environment.")

    assert "uv sync --extra mcp" in MCP_EXTRA_INSTALL_HINT
