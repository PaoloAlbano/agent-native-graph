"""Benchmark runner entrypoints.

This module is the application-level boundary for running the current
CypherBench/Neo4j ANA experiment. External interfaces should import from here
instead of depending on the concrete backend module path.
"""

from agent_native_graph.backends.neo4j.backend import main as run_neo4j_tools_benchmark

__all__ = ["run_neo4j_tools_benchmark"]
