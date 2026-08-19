"""ANA tool backend entrypoint.

Import from this module in interfaces so they depend on the stable backend
entrypoint rather than the concrete Neo4j implementation module path.
"""

from agent_native_graph.backends.neo4j.backend import AgentToolBackend

__all__ = ["AgentToolBackend"]
