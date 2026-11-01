"""Validate optional argument defaults against the tool contract."""

from copy import deepcopy
from unittest.mock import MagicMock

import pytest
from neo4j.graph import Graph, Node
from schema_fixture import company_schema

from agent_native_graph.backends.neo4j.backend import Neo4jGraphBackend


def company_node(key, name):
    return Node(Graph(), key, 0, ["Company", "Entity"], {"id": key, "name": name})


def graph_with_executor(execute):
    graph = Neo4jGraphBackend.__new__(Neo4jGraphBackend)
    graph._driver = MagicMock()
    graph._schema = company_schema()
    graph._query_timeout_s = None
    graph.last_fetch = None
    session = graph._driver.session.return_value.__enter__.return_value
    session.run.side_effect = execute
    return graph, session.run


@pytest.mark.parametrize("return_mode", ["entities", "names", "count"])
@pytest.mark.parametrize("limit_args", [{}, {"limit": None}, {"limit": 17}])
@pytest.mark.parametrize("offset", [0, 5])
def test_constraint_query_only_limits_when_requested(return_mode, limit_args, offset):
    nodes = [company_node(f"c{i}", f"Asset {i:04}") for i in range(1207)]

    def execute(query, **params):
        if "count(" in query:
            return [{"total": len(nodes)}]
        start = params["offset"]
        page = nodes[start : start + params["limit"]] if "LIMIT $limit" in query else nodes[start:]
        if return_mode == "entities":
            return [{"asset": node} for node in page]
        return [{"name": node["name"]} for node in page]

    graph, run = graph_with_executor(execute)
    args = {
        "find": {"label": "Company", "as": "asset"},
        "where": [{"relationship_type": "basedIn", "direction": "out", "target_label": "Country"}],
        "return_mode": return_mode,
        "alias": "total" if return_mode == "count" else "name",
        "offset": offset,
        **limit_args,
    }
    original = deepcopy(args)
    result = graph.call("constraint_query", args)
    query = run.call_args.args[0]
    params = run.call_args.kwargs
    explicit_limit = limit_args.get("limit")
    expected_size = min(1207 - offset, explicit_limit) if explicit_limit else 1207 - offset
    assert args == original
    assert params["offset"] == offset
    if return_mode == "count":
        assert "SKIP" not in query and "LIMIT" not in query
        assert graph.call("fetch", {"from": result["handle"]})["rows"] == [[1207]]
    else:
        assert "SKIP $offset" in query
        assert ("LIMIT $limit" in query) == (explicit_limit is not None)
        assert result["matched_count"] == expected_size
        if return_mode == "entities":
            stored = graph._handle(result["handle"]).rows
            assert [r["asset"]["properties"]["id"] for r in stored] == [
                n["id"] for n in nodes[offset : offset + expected_size]
            ]
            hint = result.get("large_result_hint", "")
            assert ("requested limit" in hint) == (explicit_limit is not None)
        else:
            assert "ORDER BY `name` ASC SKIP $offset" in query
    if explicit_limit is None:
        assert "limit" not in params
    else:
        assert params["limit"] == explicit_limit


def test_constraint_query_preserves_ordering_offset_limit_and_source_metadata():
    graph, run = graph_with_executor(lambda query, **params: [])
    result = graph.call(
        "constraint_query",
        {
            "find": {"label": "Company", "as": "asset"},
            "where": [
                {
                    "relationship_type": "basedIn",
                    "direction": "out",
                    "target_label": "Country",
                    "property": "name",
                    "value": "Sample country",
                }
            ],
            "return_mode": "entities",
            "limit": 10,
            "offset": 20,
            "order_by": [{"var": "asset", "property": "name", "direction": "desc"}],
        },
    )
    query = run.call_args.args[0]
    assert "ORDER BY asset.`name` DESC SKIP $offset LIMIT $limit" in query
    assert run.call_args.kwargs == {"offset": 20, "limit": 10, "filter_0": "Sample country"}
    assert result["matched_count"] == 0 and "large_result_hint" not in result
    source = graph._handle(result["handle"]).metadata["server_side_entity_query"]
    assert source["params"] == {"filter_0": "Sample country"}
    assert "LIMIT" not in source["query"] and "SKIP" not in source["query"]


def shared_args():
    return {
        "seed_label": "Company",
        "shared_label": "Industry",
        "peer_label": "Company",
        "seed_relationship": {"relationship_type": "operatesIn", "direction": "out"},
        "peer_relationship": {"relationship_type": "operatesIn", "direction": "out"},
        "select": [{"var": "peer", "property": "name", "alias": "name"}],
    }


def test_shared_role_omitted_null_and_true_preserve_homonymous_entities():
    # One entity has two matching paths; another has the same projected name.
    paths = [
        company_node("c1", "Same name"),
        company_node("c1", "Same name"),
        company_node("c2", "Same name"),
    ]

    def execute(query, **params):
        if "WITH DISTINCT peer RETURN" in query:
            nodes = list({n["id"]: n for n in paths}.values())
        elif "RETURN DISTINCT" in query:
            nodes = list({n["name"]: n for n in paths}.values())
        else:
            nodes = paths
        return [{"name": n["name"]} for n in nodes]

    graph, run = graph_with_executor(execute)
    for options in ({}, {"distinct": None}, {"distinct": True}):
        args = {**shared_args(), **options}
        original = deepcopy(args)
        result = graph.call("shared_role_aggregate", args)
        assert args == original
        assert graph.call("fetch", {"from": result["handle"]})["rows"] == [
            ["Same name"],
            ["Same name"],
        ]
    queries = [call.args[0] for call in run.call_args_list]
    assert len(queries) == 3 and len(set(queries)) == 1
    assert "WITH DISTINCT peer RETURN peer.`name` AS `name`" in queries[0]
    assert "RETURN DISTINCT peer.`name`" not in queries[0]
    assert all(call.kwargs["limit"] == 1000 for call in run.call_args_list)

    result = graph.call("shared_role_aggregate", {**shared_args(), "distinct": False})
    assert "WITH DISTINCT" not in run.call_args.args[0]
    assert "RETURN DISTINCT" not in run.call_args.args[0]
    assert graph.call("fetch", {"from": result["handle"]})["rows"] == [["Same name"]] * 3


def test_shared_role_distinct_default_does_not_change_grouped_metrics():
    graph, run = graph_with_executor(lambda query, **params: [{"name": "Same name", "total": 2}])
    for options in ({}, {"distinct": None}, {"distinct": True}, {"distinct": False}):
        result = graph.call(
            "shared_role_aggregate",
            {
                **shared_args(),
                **options,
                "metrics": [{"op": "count_distinct", "var": "shared", "alias": "total"}],
            },
        )
        assert graph.call("fetch", {"from": result["handle"]})["rows"] == [["Same name", 2]]
    queries = [call.args[0] for call in run.call_args_list]
    assert len(queries) == 4 and len(set(queries)) == 1
    assert "count(DISTINCT shared)" in queries[0]
    assert "WITH DISTINCT peer" not in queries[0]
