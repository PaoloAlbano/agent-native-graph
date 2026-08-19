"""ANA tool definitions and execution helpers.

Tool modules register their callable surface by decorating functions with
`@tool(...)`. Importing those modules is what attaches metadata to the central
registry.
"""


def load_tool_modules() -> None:
    """Import tool modules so their `@tool(...)` decorators populate the registry."""
    import agent_native_graph.tools.diagnostics  # noqa: F401
    import agent_native_graph.tools.operations  # noqa: F401
    import agent_native_graph.tools.schema  # noqa: F401
