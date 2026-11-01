"""Preserve expansion multiplicity, row provenance and bounds across source batches."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agent_native_graph.backends.neo4j.backend import Neo4jGraphBackend


class Node(dict):
    labels = ["Device"]

    def __init__(self, key):
        super().__init__(id=key, name="Same name")
        self.element_id = str(key)


def payload(key):
    return {"labels": ["Device"], "properties": {"id": key, "name": "Same name"}}


@pytest.fixture
def graph():
    graph = Neo4jGraphBackend.__new__(Neo4jGraphBackend)
    graph._driver = MagicMock()
    graph._query_timeout_s = None
    graph._schema = {"labels": ["Device"], "relationship_types": ["LINK"]}
    graph.last_fetch = None
    run = graph._driver.session.return_value.__enter__.return_value.run
    edges = [("a", "x", "r1"), ("a", "x", "r2"), ("b", "y", "r3"), ("x", "b", "r4")]

    def execute(query, **params):
        direct = len(params["rows"]) == 1 or getattr(graph, "_identity", None) is not None
        if direct:
            assert query.startswith("UNWIND $rows AS row MATCH")
            assert "ORDER BY" not in query and "source_ids" not in params
        else:
            assert "IN $source_ids MATCH" in query
            assert "ORDER BY row_index LIMIT $limit" in query
            assert params["source_ids"] == list(
                dict.fromkeys(r["source_id"] for r in params["rows"])
            )
        records = []
        for row in params["rows"]:
            for start, target, rel in edges:
                neighbor = None
                if "(s)-[r:`LINK`]->" in query and start == row["source_id"]:
                    neighbor = target
                elif "(s)<-[r:`LINK`]-" in query and target == row["source_id"]:
                    neighbor = start
                elif "(s)-[r:`LINK`]-(t:" in query:
                    if start == row["source_id"]:
                        neighbor = target
                    elif target == row["source_id"]:
                        neighbor = start
                if neighbor is not None and rel not in row["rel_ids"]:
                    records.append(
                        {"row_index": row["row_index"], "rel_id": rel, "t": Node(neighbor)}
                    )
        return records[: params["limit"]]

    run.side_effect = execute
    return graph, run


def expand(graph, rows, **kwargs):
    parent = graph._store(rows, focus="source")
    return graph._expand(
        {
            "from": parent["handle"],
            "source": "source",
            "as": "neighbor",
            "relationship_type": "LINK",
            "target_label": "Device",
            **kwargs,
        }
    )


def test_duplicate_sources_retain_each_row_and_its_relationship_exclusions(graph):
    g, run = graph
    rows = [
        {"other": 1},
        {"source": payload("a"), "tag": "first", "__rel_ids": ["r1"]},
        {"source": payload("a"), "tag": "second", "__rel_ids": ["r2"]},
        {"source": payload("a"), "tag": "third"},
        {"source": payload("b"), "tag": "fourth"},
    ]
    original = deepcopy(rows)
    result = expand(g, rows)
    actual = g._handle(result["handle"]).rows
    assert [(r["tag"], r["neighbor"]["properties"]["id"], r["__rel_ids"][-1]) for r in actual] == [
        ("first", "x", "r2"),
        ("second", "x", "r1"),
        ("third", "x", "r1"),
        ("third", "x", "r2"),
        ("fourth", "y", "r3"),
    ]
    assert run.call_count == 1 and rows == original
    assert result["input_count"] == 4 and result["pages"] == 1
    metadata = g._handle(result["handle"]).metadata["server_side_entity_query"]
    assert metadata["params"] == {"source_ids": ["a", "b"]}
    assert "UNWIND" not in metadata["query"]


@pytest.mark.parametrize("page_size", [1, 2, 20])
@pytest.mark.parametrize("limit", [1, 2, 4, 100])
def test_pages_respect_one_global_limit(graph, page_size, limit):
    g, run = graph
    result = expand(
        g,
        [{"source": payload(k)} for k in ("a", "b", "gone", "a")],
        page_size=page_size,
        limit=limit,
    )
    assert result["matched_count"] == min(limit, 5)
    assert result["limited"] == (limit <= 5)
    remaining = limit
    for call in run.call_args_list:
        assert call.kwargs["limit"] == remaining
        assert len(call.kwargs["rows"]) <= page_size
        # Compute each page's expected cardinality independently of the query stub.
        page_count = sum({"a": 2, "b": 1}.get(row["source_id"], 0) for row in call.kwargs["rows"])
        remaining -= min(remaining, page_count)
    assert remaining == max(0, limit - 5)


@pytest.mark.parametrize(
    "direction,expected", [("out", ["b"]), ("in", ["a", "a"]), ("both", ["a", "a", "b"])]
)
def test_relationship_direction(graph, direction, expected):
    g, _ = graph
    result = expand(g, [{"source": payload("x")}], direction=direction)
    assert (
        sorted(row["neighbor"]["properties"]["id"] for row in g._handle(result["handle"]).rows)
        == expected
    )


def test_identity_types_are_not_stringified(graph):
    g, run = graph
    result = expand(g, [{"source": payload(7)}, {"source": payload("7")}])
    assert run.call_args.kwargs["source_ids"] == [7, "7"]
    assert g._handle(result["handle"]).metadata["server_side_entity_query"]["params"][
        "source_ids"
    ] == [7, "7"]


@pytest.mark.parametrize("page_size", [1, 2, 100])
def test_transaction_identity_uses_direct_seeks(graph, page_size):
    g, run = graph
    g._identity = SimpleNamespace(
        key=lambda value: value["properties"]["id"], queries=g._driver.session
    )
    result = expand(g, [{"source": payload("a")}, {"source": payload("b")}], page_size=page_size)
    for call in run.call_args_list:
        query = call.args[0]
        assert "elementId(s) = row.source_id" in query
        assert "ORDER BY" not in query and "s.id" not in query
        assert "source_ids" not in call.kwargs
    assert (
        "elementId(t) AS entity_id"
        in g._handle(result["handle"]).metadata["server_side_entity_query"]["query"]
    )


@pytest.mark.parametrize("transaction", [False, True])
def test_high_degree_single_source_stops_at_small_limit(graph, transaction):
    g, run = graph
    if transaction:
        g._identity = SimpleNamespace(
            key=lambda value: value["properties"]["id"], queries=g._driver.session
        )

    def high_degree(query, **params):
        assert query.startswith("UNWIND $rows AS row MATCH")
        assert "ORDER BY" not in query and params["limit"] == 1
        yield {"row_index": 0, "rel_id": "first", "t": Node("x")}
        raise AssertionError("Expansion consumed neighbors beyond its limit")

    run.side_effect = high_degree
    result = expand(g, [{"source": payload("a")}], limit=1)
    assert result["matched_count"] == 1 and result["limited"]
    assert run.call_count == 1


@pytest.mark.parametrize("rows", [[], [{"other": 1}]])
def test_empty_source_skips_database(graph, rows):
    g, run = graph
    assert expand(g, rows)["matched_count"] == 0
    run.assert_not_called()


def test_interrupted_batch_does_not_store_partial_rows(graph):
    g, run = graph

    def partial(*args, **kwargs):
        yield {"row_index": 0, "rel_id": "r1", "t": Node("x")}
        raise RuntimeError("interrupted")

    run.side_effect = partial
    source = g._store([{"source": payload("a")}], focus="source")
    counter = g._counter
    with pytest.raises(RuntimeError, match="interrupted"):
        g._expand(
            {
                "from": source["handle"],
                "source": "source",
                "as": "neighbor",
                "relationship_type": "LINK",
                "target_label": "Device",
            }
        )
    assert g._counter == counter
