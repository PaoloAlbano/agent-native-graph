"""Backward-compatible import shim for the Neo4j backend.

The concrete implementation lives in `agent_native_graph.backends.neo4j.backend`.
This module remains temporarily so older tests, scripts, and notebooks can keep
their imports while the public package structure moves toward backend adapters.
"""

from agent_native_graph.backends.neo4j.backend import *  # noqa: F403
