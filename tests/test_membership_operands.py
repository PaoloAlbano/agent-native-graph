"""Membership operators reject collections without rewriting the agent's arguments."""

import json
from copy import deepcopy
from datetime import date
from unittest.mock import MagicMock

import pytest

from agent_native_graph.application import neo4j_benchmark
from agent_native_graph.backends.neo4j import backend as backend_module
from agent_native_graph.backends.neo4j.backend import Neo4jGraphBackend
from agent_native_graph.core.graph_utils import _cypher_filter_clause, _predicate


@pytest.fixture
def graph():
    graph = Neo4jGraphBackend.__new__(Neo4jGraphBackend)
    graph._driver = MagicMock()
    graph.last_fetch = None
    graph._schema = {
        "labels": ["Device", "Group"],
        "relationship_types": ["taggedWith", "reviewedBy"],
        "node_properties": [
            {
                "nodeType": f":`{label}`",
                "nodeLabels": [label],
                "propertyName": prop,
                "propertyTypes": [kind],
                "mandatory": False,
            }
            for label in ("Device", "Group")
            for prop, kind in (("name", "STRING"), ("tags", "LIST<STRING>"))
        ],
        "relationship_properties": [
            {
                "relType": ":`taggedWith`",
                "propertyName": "roles",
                "propertyTypes": ["LIST<STRING>"],
                "mandatory": False,
            }
        ],
        "label_relationships": [
            {"source_label": "Device", "relationship_type": rel, "target_label": "Group"}
            for rel in ("taggedWith", "reviewedBy")
        ],
    }
    return graph


@pytest.mark.parametrize("op", ["in", "not_in"])
@pytest.mark.parametrize(
    "value", [[], ["private-member"], ["a", "b"], {}, {"x": 1}, ("a",), {"a"}, frozenset({"a"})]
)
def test_membership_rejects_non_scalar_operands_in_python_and_cypher(op, value):
    for actual in ([], ["a"], None):
        with pytest.raises(ValueError, match="requires a scalar member value") as error:
            _predicate(actual, op, value)
        assert "private-member" not in str(error.value)
    with pytest.raises(ValueError, match="requires a scalar member value"):
        _cypher_filter_clause({"var": "n", "property": "tags", "op": op, "value": value}, 0)


@pytest.mark.parametrize("op", ["in", "not_in"])
@pytest.mark.parametrize("value", ["public", 7, False, 1.25, date(2020, 1, 1)])
def test_valid_members_are_preserved_without_coercion(op, value):
    clause, params = _cypher_filter_clause(
        {"var": "n", "property": "tags", "op": op, "value": value}, 0
    )
    assert "IN n.`tags`" in clause
    assert params["filter_0"] is value
    assert _predicate([value], op, value) == (op == "in")
    assert _predicate([], op, value) == (op == "not_in")
    assert not _predicate(None, op, value)


def test_other_operators_and_existing_null_operands_are_unchanged():
    assert _predicate(["a"], "eq", ["a"])
    assert _predicate(["a"], "neq", ["b"])
    for op in ("eq", "neq"):
        _, params = _cypher_filter_clause(
            {"var": "n", "property": "tags", "op": op, "value": ["a"]}, 0
        )
        assert params["filter_0"] == ["a"]
    for op in ("in", "not_in"):
        _, params = _cypher_filter_clause(
            {"var": "n", "property": "tags", "op": op, "value": None}, 0
        )
        assert params["filter_0"] is None


@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize("op", ["in", "not_in"])
def test_local_filter_rejects_before_creating_handle_even_for_empty_input(graph, empty, op):
    rows = (
        []
        if empty
        else [{"d": {"labels": ["Device"], "properties": {"name": "A", "tags": ["public"]}}}]
    )
    parent = graph._store(rows, focus="d")
    original_counter = graph._counter
    args = {"from": parent["handle"], "var": "d", "property": "tags", "op": op, "value": ["public"]}
    original = deepcopy(args)
    with pytest.raises(ValueError, match="requires a scalar member value"):
        graph.call("filter", args)
    assert args == original and graph._counter == original_counter
    assert graph.last_fetch is None
    graph._driver.session.assert_not_called()


@pytest.mark.parametrize("op", ["in", "not_in", "eq", "neq"])
@pytest.mark.parametrize("target", ["node", "relationship", "constraint"])
def test_database_filters_reject_collections_after_existing_list_normalization(graph, op, target):
    flt = {"var": "device", "property": "tags", "op": op, "value": ["public"]}
    if target == "constraint":
        name = "constraint_query"
        args = {
            "find": {"label": "Device"},
            "where": [
                {
                    "relationship_type": "taggedWith",
                    "direction": "out",
                    "target_label": "Group",
                    "property": "tags",
                    "op": op,
                    "value": ["public"],
                }
            ],
        }
    else:
        name = "relationship_query"
        if target == "relationship":
            flt.update(var="rel", property="roles")
        args = {
            "source_label": "Device",
            "target_label": "Group",
            "relationship_type": "taggedWith",
            "filters": [flt],
        }
    original = deepcopy(args)
    with pytest.raises(ValueError, match="requires a scalar member value"):
        graph.call(name, args)
    assert args == original
    graph._driver.session.assert_not_called()
    assert not graph._handles and graph.last_fetch is None


@pytest.mark.parametrize("policy", [None, "bounded-v1"])
def test_native_model_receives_membership_error_and_can_correct_it(graph, monkeypatch, policy):
    parent = graph._store(
        [
            {"d": {"labels": ["Device"], "properties": {"name": "A", "tags": ["blocked"]}}},
            {"d": {"labels": ["Device"], "properties": {"name": "B", "tags": ["public"]}}},
        ],
        focus="d",
    )
    monkeypatch.setattr(backend_module, "Neo4jGraphBackend", lambda *a, **kw: graph)
    base = {"from": parent["handle"], "var": "d", "property": "tags", "op": "not_in"}
    actions = [
        ("filter", {**base, "value": ["blocked"]}),
        ("filter", {**base, "value": "blocked"}),
        ("project", {"from": "h2", "select": [{"var": "d", "property": "name", "alias": "name"}]}),
        ("fetch", {"from": "h3"}),
    ]

    class Model:
        calls = 0

        def chat(self, messages, **kwargs):
            if self.calls == 1:
                result = json.loads(messages[-1]["content"])["previous_tool_results"][-1]["result"]
                assert result["status"] == "tool_error"
                assert "requires a scalar member value" in result["error"]
                assert "blocked" not in result["error"]
                assert graph._counter == 1 and graph.last_fetch is None
            name, args = actions[self.calls]
            self.calls += 1
            return {"tool_calls": [{"function": {"name": name, "arguments": json.dumps(args)}}]}

    row = neo4j_benchmark._run_agent_task(
        {
            "qid": "membership-recovery",
            "nl_question": "Find devices without the blocked tag",
            "gold_cypher": "RETURN 'B'",
            "answer_json": [["B"]],
        },
        llm=Model(),
        schema={},
        neo4j_uri="bolt://example.invalid",
        neo4j_user="test",
        neo4j_password="test",
        neo4j_query_timeout_s=30,
        max_steps=4,
        native_tools=True,
        tool_choice="auto",
        enable_planning_tools=False,
        schema_entry="overview",
        wrapper_planning=False,
        auto_fetch_on_done=False,
        evaluation_fetch_all_pages=False,
        enable_runner_guardrails=False,
        task_timeout_s=None,
        result_policy=policy,
    )
    assert row["ok"] and row["matches_answer_json"] and row["rows"] == [["B"]]
    assert row["llm_call_count"] == 4 and row["tool_error_count"] == 1
    graph._driver.session.assert_not_called()
    graph._driver.close.assert_called_once()
