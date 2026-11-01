"""Batch lookup keeps the left-preserving, per-entity optional count contract."""

from copy import deepcopy
from unittest.mock import MagicMock

import pytest

from agent_native_graph.backends.neo4j.backend import Neo4jGraphBackend


def payload(key, name="Same name"):
    return {"labels": ["Device"], "properties": {"id": key, "name": name}}


@pytest.fixture
def graph():
    graph = Neo4jGraphBackend.__new__(Neo4jGraphBackend)
    graph._driver = MagicMock()
    graph._query_timeout_s = None
    graph._schema = {"labels": ["Device"], "relationship_types": ["LINK"]}
    graph.last_fetch = None
    run = graph._driver.session.return_value.__enter__.return_value.run
    edges = [("a", "x", "r1"), ("a", "x", "r2"), ("a", "y", "r3"), ("b", "x", "r4")]
    nodes = {"a", "b", "c", "x", "y", 7, "7"}

    def execute(query, **params):
        assert query.startswith("MATCH (s) WHERE s.id IN $source_ids OPTIONAL MATCH")
        assert "UNWIND" not in query and "LIMIT" not in query
        assert "RETURN s.id AS source_id" in query
        excluded = {
            row["source_id"]: row["rel_ids"] for row in params.get("excluded_relationships", [])
        }
        counts = []
        for source in reversed(params["source_ids"]):
            if source not in nodes:
                continue
            targets = [
                target if "(s)-[r:" in query else start
                for start, target, rel in edges
                if (start if "(s)-[r:" in query else target) == source
                and rel not in excluded.get(source, [])
            ]
            count = len(set(targets)) if "count(DISTINCT t)" in query else len(targets)
            counts.append({"source_id": source, "related_count": count})
        return counts

    run.side_effect = execute
    return graph, run


def optional(graph, rows, **args):
    parent = graph._store(rows, focus="device")
    return graph._optional_expand_count(
        {
            "from": parent["handle"],
            "source": "device",
            "relationship_type": "LINK",
            "target_label": "Device",
            "direction": "out",
            "alias": "total",
            **args,
        },
    )


def fetched(graph, result):
    return graph.call("fetch", {"from": result["handle"]})["rows"]


@pytest.mark.parametrize("distinct,count", [(None, 2), (True, 2), (False, 3)])
def test_one_batch_keeps_zeros_identity_and_input_order(graph, distinct, count):
    g, run = graph
    rows = [
        {"other": 1},
        {"device": payload("c")},
        {"device": payload("a")},
        {"device": payload("b")},
        {"device": payload("a", "Later duplicate")},
        {"device": payload("gone")},
    ]
    original = deepcopy(rows)
    result = optional(g, rows, distinct=distinct)
    assert fetched(g, result) == [
        ["Same name", 0],
        ["Same name", count],
        ["Same name", 1],
        ["Same name", 0],
    ]
    assert run.call_count == 1 and run.call_args.kwargs == {"source_ids": ["c", "a", "b", "gone"]}
    assert rows == original
    assert "fetch" in result["finalization_hint"] and result["columns"] == ["name", "total"]


@pytest.mark.parametrize(
    "limit,ids,counts",
    [(1, ["b"], [1]), (2, ["b", "a"], [1, 2]), (None, ["b", "a", "c"], [1, 2, 0])],
)
def test_limit_is_applied_to_ordered_unique_sources_before_query(graph, limit, ids, counts):
    g, run = graph
    result = optional(g, [{"device": payload(k)} for k in ("b", "b", "a", "c")], limit=limit)
    assert run.call_args.kwargs["source_ids"] == ids
    assert fetched(g, result) == [["Same name", n] for n in counts]


def test_incoming_direction_and_group_fields_are_preserved(graph):
    g, _ = graph
    result = optional(
        g,
        [{"device": payload("x", "First")}, {"device": payload("y", "Second")}],
        direction="in",
        group_by=[{"var": "device", "property": "id", "alias": "key"}],
    )
    assert fetched(g, result) == [["x", 2], ["y", 1]]


@pytest.mark.parametrize("exclude", [False, True])
def test_exclusions_are_source_scoped_not_a_global_union(graph, exclude):
    g, run = graph
    rows = [
        {"device": payload("a"), "__rel_ids": []},
        {"device": payload("b"), "__rel_ids": ["r1"]},
    ]
    result = optional(g, rows, exclude_traversed_relationships=exclude)
    assert fetched(g, result) == [["Same name", 2], ["Same name", 1]]
    assert ("excluded_relationships" in run.call_args.kwargs) == exclude


def test_excluding_all_relationships_keeps_a_zero_row(graph):
    g, run = graph
    result = optional(
        g,
        [{"device": payload("a"), "__rel_ids": ["r1", "r2", "r3"]}],
        exclude_traversed_relationships=True,
    )
    assert fetched(g, result) == [["Same name", 0]]
    assert "NONE(excluded IN $excluded_relationships" in run.call_args.args[0]


def test_empty_exclusions_do_not_add_per_relationship_checks(graph):
    g, run = graph
    optional(g, [{"device": payload("a")}], exclude_traversed_relationships=True)
    assert "excluded_relationships" not in run.call_args.kwargs
    assert "NONE(" not in run.call_args.args[0]


def test_scalar_identity_types_are_not_stringified(graph):
    g, run = graph
    result = optional(g, [{"device": payload(k)} for k in (7, "7")])
    assert run.call_args.kwargs["source_ids"] == [7, "7"]
    assert fetched(g, result) == [["Same name", 0], ["Same name", 0]]


@pytest.mark.parametrize("rows", [[], [{"other": "not an entity"}]])
def test_empty_source_avoids_database_access(graph, rows):
    g, run = graph
    result = optional(g, rows)
    assert fetched(g, result) == [] and result["columns"] == ["name", "total"]
    run.assert_not_called()
    g._driver.session.assert_not_called()


def test_failure_does_not_publish_partial_counts(graph):
    g, run = graph

    def incomplete(*args, **kwargs):
        yield {"source_id": "a", "related_count": 2}
        raise RuntimeError("Query interrupted")

    parent = g._store([{"device": payload("a")}, {"device": payload("b")}], focus="device")
    counter = g._counter
    run.side_effect = incomplete
    with pytest.raises(RuntimeError, match="interrupted"):
        g.call(
            "optional_expand_count",
            {
                "from": parent["handle"],
                "source": "device",
                "relationship_type": "LINK",
                "target_label": "Device",
                "direction": "out",
            },
        )
    assert g._counter == counter and g.last_fetch is None
