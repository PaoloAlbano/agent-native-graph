"""The shared ANA runtime must not carry a concrete engine's query path."""

import ast
import inspect

from agent_native_graph import SharedGraphBackend
from agent_native_graph.backends.neo4j.backend import Neo4jGraphBackend
from agent_native_graph.core import runtime, schema_runtime


def test_neo4j_reuses_engine_neutral_runtime():
    assert issubclass(Neo4jGraphBackend, SharedGraphBackend)
    assert Neo4jGraphBackend._project is SharedGraphBackend._project
    assert Neo4jGraphBackend._fetch is SharedGraphBackend._fetch
    assert "_project" not in Neo4jGraphBackend.__dict__


def test_shared_modules_have_no_driver_or_query_implementation():
    for module in (runtime, schema_runtime):
        tree = ast.parse(inspect.getsource(module))
        imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        assert not any(
            name and (name.startswith("neo4j") or ".backends.neo4j" in name) for name in imports
        )
        assert not any(
            isinstance(node, ast.Attribute) and node.attr in {"_run", "_session", "_driver"}
            for node in ast.walk(tree)
        )


def test_engine_sampling_hooks_are_explicit():
    assert {
        "_label_counts",
        "_node_property_samples",
        "_relationship_property_samples",
    } <= SharedGraphBackend.__abstractmethods__
