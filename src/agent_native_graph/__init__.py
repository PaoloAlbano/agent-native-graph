"""Agent-Native graph access for Python applications, transports and research."""

from agent_native_graph.backends.neo4j.connection import connect_neo4j
from agent_native_graph.core.backend import AgentGraphBackend
from agent_native_graph.core.tool_contract import ToolContract, get_tool_contract
from agent_native_graph.core.tool_specs import get_tool_specs

__all__ = [
    "AgentGraphBackend",
    "ToolContract",
    "__version__",
    "connect_neo4j",
    "get_tool_contract",
    "get_tool_specs",
]

__version__ = "0.1.0"
