import re
from pathlib import Path
from unittest.mock import MagicMock

from agent_native_graph.backends.neo4j import backend as backend_module
from agent_native_graph.backends.neo4j import introspection
from agent_native_graph.backends.neo4j.backend import Neo4jGraphBackend


def test_documented_library_example_uses_own_graph_and_closes_driver(monkeypatch, capsys):
    guide = Path(__file__).resolve().parents[1] / "docs/library-and-server.md"
    snippets = re.findall(r"```python\n(.*?)```", guide.read_text(), re.DOTALL)
    assert len(snippets) == 1
    monkeypatch.setenv("NEO4J_URI", "bolt://example.invalid:7687")
    monkeypatch.setenv("NEO4J_USER", "reader")
    monkeypatch.setenv("NEO4J_PASSWORD", "test-only")
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("API_KEY_FILE", raising=False)
    monkeypatch.delenv("NEO4J_DATABASE", raising=False)
    discover = MagicMock(
        return_value={
            "labels": ["Device"],
            "relationship_types": [],
            "node_properties": [],
            "relationship_properties": [],
            "label_relationships": [],
        }
    )
    monkeypatch.setattr(introspection, "introspect_schema", discover)
    driver = MagicMock()
    session = driver.session.return_value.__enter__.return_value
    session.run.return_value.single.return_value = {"node_count": 2, "count": 2}
    connect = MagicMock(return_value=driver)
    monkeypatch.setattr(backend_module.GraphDatabase, "driver", connect)

    exec(compile(snippets[0], str(guide), "exec"), {})

    discover.assert_called_once_with(
        "bolt://example.invalid:7687", "reader", "test-only", query_timeout_s=30
    )
    assert connect.call_args.kwargs["auth"] == ("reader", "test-only")
    query = session.run.call_args.args[0]
    assert query.timeout == 30 and "MATCH (n:`Device`)" in query.text
    assert "Device ['node_count'] [[2]]" in capsys.readouterr().out
    driver.close.assert_called_once()


def test_documented_small_fetch_pages_do_not_skip_table_rows():
    backend = Neo4jGraphBackend.__new__(Neo4jGraphBackend)
    handle = backend._store([{"value": i} for i in range(25)], kind="table", columns=["value"])
    first = backend.call("fetch", {"from": handle["handle"], "limit": 20, "offset": 0})
    assert first["returned_count"] == len(first["rows"]) == 20
    assert first["next_offset"] == 20 and first["truncated"]
    second = backend.call(
        "fetch", {"from": handle["handle"], "limit": 20, "offset": first["next_offset"]}
    )
    assert second["returned_count"] == len(second["rows"]) == 5
    assert second["next_offset"] is None and not second["truncated"]
    assert first["rows"] + second["rows"] == [[i] for i in range(25)]
