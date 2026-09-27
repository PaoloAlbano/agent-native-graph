import json
import os
from pathlib import Path
from typing import Any

import pytest

from agent_native_graph.backends.neo4j.backend import (
    Neo4jGraphBackend,
    Handle,
    _ambiguous_relationship_only_constraints,
    _evaluation_fetch_all_pages,
    _guarded_action,
    _latest_fetchable_handle,
    _next_action,
    _predicate,
    _relationship_uniqueness_clauses,
    _summarize_llm_metrics,
    _summarize_tool_metrics,
    _tool_specs,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return json.loads((ROOT / "data" / "company_schema.json").read_text(encoding="utf-8"))


@pytest.fixture()
def planning_backend(schema: dict[str, Any]) -> Any:
    tool_backend = Neo4jGraphBackend.__new__(Neo4jGraphBackend)
    tool_backend._schema = schema
    return tool_backend


def test_draft_tool_plan_is_schema_driven_for_or_count_question(planning_backend: Any) -> None:
    plan = planning_backend.call(
        "draft_tool_plan",
        {
            "question": (
                "How many companies either operate in logistics or have "
                "Christiana Smith Shi as a board member?"
            )
        },
    )

    assert plan["features"]["count"] is True
    assert plan["features"]["or"] is True
    assert plan["validation_required"] is True
    assert "entity_set_operation" in plan["recommended_tools"]
    assert any(step["tool"] == "schema_overview" for step in plan["plan_outline"])


def test_constraint_query_flags_ambiguous_repeated_relationship_only_target() -> None:
    ambiguous = _ambiguous_relationship_only_constraints(
        [
            {"relationship_type": "hasCEO", "direction": "in", "target_label": "Company"},
            {"relationship_type": "foundedBy", "direction": "in", "target_label": "Company"},
        ]
    )
    disambiguated = _ambiguous_relationship_only_constraints(
        [
            {
                "relationship_type": "hasCEO",
                "direction": "in",
                "target_label": "Company",
                "property": "name",
                "value": "Acme",
            },
            {"relationship_type": "foundedBy", "direction": "in", "target_label": "Company"},
        ]
    )

    assert ambiguous == ("Company", ["hasCEO", "foundedBy"])
    assert disambiguated is None


def test_validate_tool_plan_flags_unknown_relationship_and_unbound_filter(
    planning_backend: Any,
) -> None:
    validation = planning_backend.call(
        "validate_tool_plan",
        {
            "plan": [
                {"tool": "schema_overview", "args": {}},
                {
                    "tool": "pattern_query",
                    "args": {
                        "start_label": "Company",
                        "start_as": "company",
                        "filters": [
                            {
                                "var": "industry",
                                "property": "name",
                                "op": "eq",
                                "value": "logistics",
                            }
                        ],
                        "hops": [
                            {
                                "relationship_type": "madeUpRelationship",
                                "direction": "out",
                                "target_label": "Person",
                                "as": "person",
                            }
                        ],
                    },
                },
            ]
        },
    )

    assert validation["valid"] is False
    messages = [warning["message"] for warning in validation["warnings"]]
    assert any("Unknown relationship_type" in message for message in messages)
    assert any("unbound variable" in message for message in messages)


def _schema_only_backend(schema: dict[str, Any]) -> Neo4jGraphBackend:
    backend = Neo4jGraphBackend.__new__(Neo4jGraphBackend)
    backend._schema = schema
    backend._label_counts = lambda labels: {label: index + 1 for index, label in enumerate(labels)}
    return backend


def test_schema_overview_exposes_ready_direction_rules(schema: dict[str, Any]) -> None:
    backend = _schema_only_backend(schema)

    overview = backend.call("schema_overview", {})
    based_in = next(
        item
        for item in overview["relationship_navigation"]
        if item["relationship_type"] == "basedIn"
    )

    assert based_in["pattern"] == "(:Company)-[:basedIn]->(:Country)"
    assert based_in["forward_expand"] == {
        "source_label": "Company",
        "direction": "out",
        "relationship_type": "basedIn",
        "target_label": "Country",
    }
    assert based_in["reverse_expand"] == {
        "source_label": "Country",
        "direction": "in",
        "relationship_type": "basedIn",
        "target_label": "Company",
    }
    subsidiary_of = next(
        item
        for item in overview["relationship_navigation"]
        if item["relationship_type"] == "subsidiaryOf"
    )
    assert any(
        example["phrase_shape"] == "companies of <Company>"
        and example["use"]
        == {"source_label": "Company", "direction": "in", "target_label": "Company"}
        for example in subsidiary_of["semantic_direction_examples"]
    )
    assert any(action["tool"] == "schema_search" for action in overview["next_actions"])


def test_tool_dispatch_ignores_unexpected_model_arguments(schema: dict[str, Any]) -> None:
    backend = _schema_only_backend(schema)

    overview = backend.call(
        "schema_overview",
        {"description": "Model-generated stray argument that is not part of the tool schema."},
    )

    assert "labels" in overview


def test_schema_search_returns_ready_to_use_relationship_args(schema: dict[str, Any]) -> None:
    backend = _schema_only_backend(schema)

    result = backend.call("schema_search", {"query": "subsidiaries board members"})
    relationships = {item["relationship_type"]: item for item in result["relationships"]}

    assert "subsidiaryOf" in relationships
    assert relationships["subsidiaryOf"]["ready_to_use"][
        "when_current_source_label_is_target_label"
    ] == {
        "relationship_type": "subsidiaryOf",
        "direction": "in",
        "target_label": "Company",
        "as": "company",
    }
    assert any(
        example["use"]["direction"] == "in"
        for example in relationships["subsidiaryOf"]["semantic_direction_examples"]
    )
    assert "hasBoardMember" in relationships


def test_schema_describe_relationship_is_copyable_for_reverse_traversal(
    schema: dict[str, Any],
) -> None:
    backend = _schema_only_backend(schema)

    result = backend.call("schema_describe_relationship", {"relationship_type": "basedIn"})

    assert result["canonical_pattern"] == "(:Company)-[:basedIn]->(:Country)"
    assert result["ready_to_use"]["from_target_label"] == {
        "relationship_type": "basedIn",
        "direction": "in",
        "target_label": "Company",
        "as": "company",
    }
    assert any("Direction is relative" in hint for hint in result["planning_hints"])

    temporal = backend.call("schema_describe_relationship", {"relationship_type": "hasCEO"})
    assert temporal["temporal"][0]["active_at_year_filter_template"] == [
        {"property": "start_year", "op": "lte", "value": "YEAR"},
        {"property": "end_year", "op": "gte_or_null", "value": "YEAR"},
    ]


def test_pattern_query_rejects_relationship_name_used_as_property(schema: dict[str, Any]) -> None:
    backend = Neo4jGraphBackend.__new__(Neo4jGraphBackend)
    backend._schema = schema

    with pytest.raises(ValueError, match="relationship 'basedIn' was used as property"):
        backend.call(
            "pattern_query",
            {
                "start_label": "Company",
                "start_as": "company",
                "filters": [
                    {
                        "var": "company",
                        "property": "basedIn",
                        "op": "eq",
                        "value": "Canada",
                    }
                ],
                "hops": [
                    {
                        "relationship_type": "operatesIn",
                        "direction": "out",
                        "target_label": "Industry",
                        "as": "industry",
                    }
                ],
                "group_by": [{"var": "industry", "property": "name", "alias": "industry"}],
                "metrics": [{"op": "count_distinct", "var": "company", "alias": "company_count"}],
            },
        )


def test_pattern_query_rejects_list_property_contains_operator(schema: dict[str, Any]) -> None:
    backend = Neo4jGraphBackend.__new__(Neo4jGraphBackend)
    backend._schema = schema

    with pytest.raises(ValueError, match="country_of_citizenship is list\\[string\\]"):
        backend.call(
            "pattern_query",
            {
                "start_label": "Person",
                "start_as": "person",
                "filters": [
                    {
                        "var": "person",
                        "property": "country_of_citizenship",
                        "op": "not_contains",
                        "value": "Austria",
                    }
                ],
                "select": [{"var": "person", "property": "name", "alias": "name"}],
            },
        )


def test_filter_normalizes_scalar_operators_for_list_properties(schema: dict[str, Any]) -> None:
    backend = Neo4jGraphBackend.__new__(Neo4jGraphBackend)
    backend._schema = schema
    backend._counter = 1
    backend._handles = {
        "h1": Handle(
            id="h1",
            focus="person",
            rows=[
                {
                    "person": {
                        "labels": ["Person"],
                        "properties": {
                            "id": "p1",
                            "name": "Austrian Person",
                            "country_of_citizenship": ["Austria"],
                        },
                    },
                    "__rel_ids": [],
                },
                {
                    "person": {
                        "labels": ["Person"],
                        "properties": {
                            "id": "p2",
                            "name": "German Person",
                            "country_of_citizenship": ["Germany"],
                        },
                    },
                    "__rel_ids": [],
                },
            ],
        )
    }

    equals_result = backend.call(
        "filter",
        {
            "from": "h1",
            "var": "person",
            "property": "country_of_citizenship",
            "op": "eq",
            "value": "Austria",
        },
    )
    not_equals_result = backend.call(
        "filter",
        {
            "from": "h1",
            "var": "person",
            "property": "country_of_citizenship",
            "op": "neq",
            "value": "Austria",
        },
    )

    assert equals_result["preview"] == ["Austrian Person"]
    assert not_equals_result["preview"] == ["German Person"]


def test_entity_set_operation_rejects_mismatched_entity_labels(schema: dict[str, Any]) -> None:
    backend = Neo4jGraphBackend.__new__(Neo4jGraphBackend)
    backend._schema = schema
    backend._handles = {
        "h1": type(
            "HandleLike",
            (),
            {
                "id": "h1",
                "rows": [{"company": {"labels": ["Company"], "properties": {"id": "c1"}}}],
            },
        )(),
        "h2": type(
            "HandleLike",
            (),
            {
                "id": "h2",
                "rows": [{"person": {"labels": ["Person"], "properties": {"id": "p1"}}}],
            },
        )(),
    }

    with pytest.raises(ValueError, match="same entity label/type"):
        backend.call(
            "entity_set_operation",
            {
                "op": "union",
                "operands": [
                    {"handle": "h1", "var": "company"},
                    {"handle": "h2", "var": "person"},
                ],
                "as": "entity",
            },
        )


def test_entity_set_operation_unions_multiple_entity_handles_with_next_step_hint(
    schema: dict[str, Any],
) -> None:
    backend = Neo4jGraphBackend.__new__(Neo4jGraphBackend)
    backend._schema = schema
    backend._handles = {
        "h1": Handle(
            id="h1",
            rows=[{"company": {"labels": ["Company"], "properties": {"id": "c1", "name": "A"}}}],
            focus="company",
        ),
        "h2": Handle(
            id="h2",
            rows=[{"company": {"labels": ["Company"], "properties": {"id": "c2", "name": "B"}}}],
            focus="company",
        ),
        "h3": Handle(
            id="h3",
            rows=[{"company": {"labels": ["Company"], "properties": {"id": "c1", "name": "A"}}}],
            focus="company",
        ),
    }
    backend._counter = 3

    result = backend.call(
        "entity_set_operation",
        {
            "op": "union",
            "operands": [
                {"handle": "h1", "var": "company"},
                {"handle": "h2", "var": "company"},
                {"handle": "h3", "var": "company"},
            ],
            "as": "company",
        },
    )

    rows = backend._handle(result["handle"]).rows
    assert sorted(row["company"]["properties"]["name"] for row in rows) == ["A", "B"]
    assert "count_handle" in result["set_operation_hint"]
    assert "project" in result["set_operation_hint"]
    assert "distinct=false" in result["set_operation_hint"]


def test_set_count_by_patterns_counts_or_branches_server_side(schema: dict[str, Any]) -> None:
    backend, driver = _fake_backend(schema)

    result = backend.call(
        "set_count_by_patterns",
        {
            "op": "union",
            "branches": [
                {
                    "start_label": "Company",
                    "start_as": "company",
                    "return_var": "company",
                    "hops": [
                        {
                            "relationship_type": "basedIn",
                            "direction": "out",
                            "target_label": "Country",
                            "as": "country",
                        }
                    ],
                    "filters": [
                        {
                            "var": "country",
                            "property": "name",
                            "op": "eq",
                            "value": "United States of America",
                        }
                    ],
                },
                {
                    "start_label": "Company",
                    "start_as": "company",
                    "return_var": "company",
                    "hops": [
                        {
                            "relationship_type": "subsidiaryOf",
                            "direction": "in",
                            "target_label": "Company",
                            "as": "subsidiary",
                        }
                    ],
                    "filters": [
                        {
                            "var": "subsidiary",
                            "property": "name",
                            "op": "eq",
                            "value": "Mentor Graphics (Hungary)",
                        }
                    ],
                },
            ],
            "alias": "company_count",
        },
    )

    query, params = driver.queries[-1]
    assert "CALL () {" in query
    assert " UNION " in query
    assert "RETURN company.id AS entity_id" in query
    assert "count(DISTINCT entity_id) AS `company_count`" in query
    assert "toLower(toString(" in query
    assert "LIMIT" not in query
    assert "United States of America" in params.values()
    assert "Mentor Graphics (Hungary)" in params.values()
    assert fetch_rows(backend, result["handle"]) == [[41091]]


def test_set_count_by_patterns_rejects_mismatched_return_labels(schema: dict[str, Any]) -> None:
    backend, _driver = _fake_backend(schema)

    with pytest.raises(ValueError, match="same entity label/type"):
        backend.call(
            "set_count_by_patterns",
            {
                "branches": [
                    {"start_label": "Company", "start_as": "company", "return_var": "company"},
                    {"start_label": "Person", "start_as": "person", "return_var": "person"},
                ],
            },
        )


def test_count_handle_optimizes_union_entity_set_with_server_side_metadata(
    schema: dict[str, Any],
) -> None:
    backend, driver = _fake_backend(schema)
    left = backend._store(
        [
            {
                "company": {
                    "labels": ["Company"],
                    "properties": {"id": "c1", "name": "A"},
                }
            }
        ],
        focus="company",
        metadata={
            "server_side_entity_query": {
                "query": (
                    "MATCH (company:`Company`) "
                    "MATCH (company)-[r0:`basedIn`]->(country:`Country`) "
                    "WHERE country.`name` = $filter_0 "
                    "RETURN company.id AS entity_id"
                ),
                "params": {"filter_0": "United States of America"},
                "var": "company",
                "label": "Company",
            }
        },
    )
    right = backend._store(
        [
            {
                "company": {
                    "labels": ["Company"],
                    "properties": {"id": "c2", "name": "B"},
                }
            }
        ],
        focus="company",
        metadata={
            "server_side_entity_query": {
                "query": (
                    "MATCH (company:`Company`) "
                    "MATCH (company)-[r1:`operatesIn`]->(industry:`Industry`) "
                    "WHERE industry.`name` = $filter_0 "
                    "RETURN company.id AS entity_id"
                ),
                "params": {"filter_0": "publishing"},
                "var": "company",
                "label": "Company",
            }
        },
    )

    combined = backend.call(
        "entity_set_operation",
        {
            "op": "union",
            "operands": [
                {"handle": left["handle"], "var": "company"},
                {"handle": right["handle"], "var": "company"},
            ],
            "as": "company",
        },
    )
    counted = backend.call(
        "count_handle",
        {"from": combined["handle"], "var": "company", "distinct": True, "alias": "n"},
    )

    query, params = driver.queries[-1]
    assert "CALL () {" in query
    assert " UNION " in query
    assert "count(DISTINCT entity_id) AS `count`" in query
    assert params["b0_filter_0"] == "United States of America"
    assert params["b1_filter_0"] == "publishing"
    assert fetch_rows(backend, counted["handle"]) == [[41091]]


def test_latest_fetchable_handle_ignores_diagnostic_results() -> None:
    transcript = [
        {"action": {"tool": "schema_inspect"}, "result": {"schema": {}}},
        {"action": {"tool": "draft_tool_plan"}, "result": {"handle": "not_fetchable"}},
        {"action": {"tool": "pattern_query"}, "result": {"handle": "h1"}},
        {"action": {"tool": "repair_empty_result"}, "result": {"handle": "also_not_fetchable"}},
        {"action": {"tool": "project"}, "result": {"handle": "h2"}},
    ]

    assert _latest_fetchable_handle(transcript) == "h2"


def test_latest_fetchable_handle_skips_exploratory_entity_handles() -> None:
    transcript = [
        {"action": {"tool": "node_scan"}, "result": {"handle": "h1", "kind": "rows"}},
        {"action": {"tool": "expand"}, "result": {"handle": "h2", "kind": "rows"}},
    ]

    assert _latest_fetchable_handle(transcript) is None


def test_latest_fetchable_handle_allows_table_results() -> None:
    transcript = [
        {"action": {"tool": "node_scan"}, "result": {"handle": "h1", "kind": "rows"}},
        {"action": {"tool": "count_handle"}, "result": {"handle": "h2", "kind": "table"}},
    ]

    assert _latest_fetchable_handle(transcript) == "h2"


def test_latest_fetchable_handle_allows_constraint_query_results() -> None:
    transcript = [
        {"action": {"tool": "schema_inspect"}, "result": {"schema": {}}},
        {"action": {"tool": "constraint_query"}, "result": {"handle": "h1", "kind": "table"}},
    ]

    assert _latest_fetchable_handle(transcript) == "h1"


def test_guarded_action_fetches_after_finalization_hint() -> None:
    transcript = [
        {
            "action": {"tool": "optional_expand_count"},
            "result": {
                "handle": "h1",
                "kind": "table",
                "finalization_hint": "fetch this table",
            },
        }
    ]

    guarded = _guarded_action(
        "question",
        transcript,
        {"tool": "project", "args": {"from": "h1", "select": []}},
    )

    assert guarded["tool"] == "fetch"
    assert guarded["args"] == {"from": "h1", "limit": 1000}
    assert guarded["reason"] == "finalization_hint_guard"


def test_guarded_action_replaces_duplicate_schema_overview_with_schema_search() -> None:
    transcript = [{"action": {"tool": "schema_overview"}, "result": {"labels": []}}]

    guarded = _guarded_action(
        "Who founded SpaceX?", transcript, {"tool": "schema_overview", "args": {}}
    )

    assert guarded["tool"] == "schema_search"
    assert guarded["args"]["query"] == "Who founded SpaceX?"


def test_summarize_llm_metrics_counts_finish_reasons_retries_and_usage() -> None:
    summary = _summarize_llm_metrics(
        [
            {
                "finish_reason": "tool_calls",
                "initial_finish_reason": "length",
                "low_effort_retry": True,
                "rate_limit_retries": 1,
                "http_retries": 0,
                "request_attempts": 2,
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30,
                    "completion_tokens_details": {"reasoning_tokens": 7},
                },
                "initial_usage": {"prompt_tokens": 10, "completion_tokens": 8000},
            },
            {
                "finish_reason": "stop",
                "initial_finish_reason": "stop",
                "low_effort_retry": False,
                "request_attempts": 1,
                "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
            },
        ]
    )

    assert summary["finish_reasons"] == {"tool_calls": 1, "stop": 1}
    assert summary["initial_finish_reasons"] == {"length": 1, "stop": 1}
    assert summary["low_effort_retry_count"] == 1
    assert summary["rate_limit_retries"] == 1
    assert summary["request_attempts"] == 3
    assert summary["usage_totals"] == {
        "prompt_tokens": 13,
        "completion_tokens": 24,
        "total_tokens": 37,
    }
    assert summary["completion_tokens_details_totals"] == {"reasoning_tokens": 7}


def test_summarize_tool_metrics_counts_schema_noise() -> None:
    summary = _summarize_tool_metrics(
        [
            {"action": {"tool": "schema_overview", "args": {}}, "result": {}},
            {"action": {"tool": "schema_overview", "args": {"unexpected": True}}, "result": {}},
            {
                "action": {"tool": "schema_search", "args": {"query": "CEO", "limit": 8}},
                "result": {},
            },
            {
                "action": {"tool": "schema_search", "args": {"query": "CEO", "payload": {}}},
                "result": {},
            },
            {"action": {"tool": "fetch", "args": {"from": "h1"}}, "result": {}},
        ]
    )

    assert summary["tool_counts"]["schema_overview"] == 2
    assert summary["tool_counts"]["fetch"] == 1
    assert summary["duplicate_schema_overview_calls"] == 1
    assert summary["repeated_targeted_schema_calls"] == 1
    assert summary["dirty_schema_args"] == 2


def test_constraint_query_is_exposed_without_planning_tools() -> None:
    specs = _tool_specs(enable_planning_tools=False)
    tool_names = {spec["function"]["name"] for spec in specs}

    assert "constraint_query" in tool_names
    assert "shared_role_aggregate" in tool_names
    assert "optional_count_by_pattern" in tool_names
    assert "shared_target_role_count" not in tool_names
    assert "set_count_by_patterns" not in tool_names
    assert "done" not in tool_names
    assert "draft_tool_plan" not in tool_names
    assert "validate_tool_plan" not in tool_names
    shared_role = next(
        spec for spec in specs if spec["function"]["name"] == "shared_role_aggregate"
    )
    assert "metrics" in shared_role["function"]["parameters"]["properties"]
    assert "seed_from" in shared_role["function"]["parameters"]["properties"]
    pattern_query = next(spec for spec in specs if spec["function"]["name"] == "pattern_query")
    assert "optional_expand_count" in pattern_query["function"]["description"]
    assert pattern_query["function"]["parameters"]["required"] == ["start_label", "hops"]
    multi_hop = next(spec for spec in specs if spec["function"]["name"] == "multi_hop_query")
    assert multi_hop["function"]["parameters"]["required"] == ["start_label", "hops"]
    top_entities = next(
        spec for spec in specs if spec["function"]["name"] == "top_entities_by_property"
    )
    assert "youngest" in top_entities["function"]["description"]
    assert "active-at-year" in top_entities["function"]["description"]
    assert "property" in top_entities["function"]["parameters"]["properties"]
    assert "order" in top_entities["function"]["parameters"]["properties"]
    constraint_query = next(
        spec for spec in specs if spec["function"]["name"] == "constraint_query"
    )
    assert "same_target_role_intersection" in constraint_query["function"]["description"]
    assert "property='name'" in constraint_query["function"]["description"]
    assert "return_properties" in constraint_query["function"]["parameters"]["properties"]
    entity_set = next(spec for spec in specs if spec["function"]["name"] == "entity_set_operation")
    assert "OR/either" in entity_set["function"]["description"]
    assert "count_handle" in entity_set["function"]["description"]
    assert "distinct=false" in entity_set["function"]["description"]
    assert "same-target" in entity_set["function"]["description"]
    assert (
        "same answer entity type"
        in entity_set["function"]["parameters"]["properties"]["operands"]["description"]
    )
    project = next(spec for spec in specs if spec["function"]["name"] == "project")
    assert (
        "entity_set_operation"
        in project["function"]["parameters"]["properties"]["distinct"]["description"]
    )
    assert "Omit this" in project["function"]["parameters"]["properties"]["limit"]["description"]
    assert "group_by" not in project["function"]["parameters"]["properties"]
    assert "metrics" not in project["function"]["parameters"]["properties"]
    assert project["function"]["parameters"]["required"] == ["from", "select"]
    same_target = next(
        spec for spec in specs if spec["function"]["name"] == "same_target_role_intersection"
    )
    assert "keep_entities" in same_target["function"]["parameters"]["properties"]
    optional_count = next(
        spec for spec in specs if spec["function"]["name"] == "optional_count_by_pattern"
    )
    assert "zero-count source entities" in optional_count["function"]["description"]
    assert "hops" in optional_count["function"]["parameters"]["required"]
    assert "optional_relationship" in optional_count["function"]["parameters"]["required"]
    assert "group_by" in optional_count["function"]["parameters"]["required"]
    repair = next(spec for spec in specs if spec["function"]["name"] == "repair_empty_result")
    assert set(repair["function"]["parameters"]["properties"]) == {
        "args",
        "error",
        "reason",
        "tool",
    }
    assert repair["function"]["parameters"]["required"] == ["tool", "args"]
    entity_resolve = next(spec for spec in specs if spec["function"]["name"] == "entity_resolve")
    entity_resolve_params = entity_resolve["function"]["parameters"]["properties"]
    assert "context_terms" in entity_resolve_params


def test_expand_first_profiles_hide_monolithic_pattern_tools() -> None:
    specs = _tool_specs(
        enable_planning_tools=False,
        schema_entry="overview_light_expand_first",
    )
    tool_names = {spec["function"]["name"] for spec in specs}

    assert "pattern_query" not in tool_names
    assert "multi_hop_query" not in tool_names
    assert "optional_count_by_pattern" not in tool_names
    assert "optional_expand_count" in tool_names


class _RecordingChatClient:
    def __init__(self) -> None:
        self.tool_choices: list[str | dict[str, Any] | None] = []

    def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        self.tool_choices.append(kwargs.get("tool_choice"))
        return {
            "tool_calls": [
                {
                    "function": {
                        "name": "schema_overview",
                        "arguments": "{}",
                    }
                }
            ],
            "__chat_meta": {"finish_reason": "tool_calls"},
        }


def test_native_next_action_forwards_configured_tool_choice() -> None:
    llm = _RecordingChatClient()

    action = _next_action(
        llm,  # type: ignore[arg-type]
        "Which companies are based in Italy?",
        [],
        native_tools=True,
        tool_choice="auto",
        enable_planning_tools=False,
        schema_entry="overview",
    )

    assert llm.tool_choices == ["auto"]
    assert action["tool"] == "schema_overview"


class _FakeRecord:
    def __init__(self, values: dict[str, Any]) -> None:
        self._values = values

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def keys(self) -> list[str]:
        return list(self._values)


class _FakeNode(dict):
    def __init__(self, labels: list[str], **properties: Any) -> None:
        super().__init__(properties)
        self.labels = set(labels)


class _FakeSession:
    def __init__(self, driver: "_FakeDriver") -> None:
        self._driver = driver

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def run(self, query: str, **params: Any) -> list[_FakeRecord]:
        self._driver.queries.append((query, params))
        if "count(DISTINCT entity_id)" in query:
            return [_FakeRecord({"company_count": 41091, "count": 41091})]
        if "__project_order_0" in query:
            return [
                _FakeRecord({"name": "New Co", "__project_order_0": 2020}),
                _FakeRecord({"name": "Old Co", "__project_order_0": 1980}),
            ]
        if "person AS person" in query and "company AS company" in query:
            return [
                _FakeRecord(
                    {
                        "person": _FakeNode(["Person"], id="p1", name="Ada"),
                        "company": _FakeNode(["Company"], id="c1", name="Analytical Engines"),
                        "name": "Ada",
                    }
                )
            ]
        if "related_count" in query:
            return [
                _FakeRecord(
                    {
                        "row_index": row["row_index"],
                        "related_count": 1 if row["row_index"] else 0,
                    }
                )
                for row in params.get("rows", [])
            ]
        if "shared_members" in query:
            return [_FakeRecord({"company": "Cardinal Health", "shared_members": 1})]
        return [_FakeRecord({"name": "SpaceX"})]


class _FakeDriver:
    def __init__(self) -> None:
        self.queries: list[tuple[str, dict[str, Any]]] = []

    def session(self) -> _FakeSession:
        return _FakeSession(self)


def _fake_backend(schema: dict[str, Any]) -> tuple[Neo4jGraphBackend, _FakeDriver]:
    driver = _FakeDriver()
    backend = Neo4jGraphBackend.__new__(Neo4jGraphBackend)
    backend._driver = driver
    backend._schema = schema
    backend._query_timeout_s = None
    backend._handles = {}
    backend._counter = 0
    backend.last_fetch = None
    return backend, driver


def test_constraint_query_builds_simple_and_query_without_neo4j(schema: dict[str, Any]) -> None:
    backend, driver = _fake_backend(schema)

    result = backend.call(
        "constraint_query",
        {
            "find": {"label": "Company", "as": "company"},
            "where": [
                {
                    "relationship_type": "hasCEO",
                    "direction": "out",
                    "target_label": "Person",
                    "property": "name",
                    "op": "eq",
                    "value": "Elon Musk",
                },
                {
                    "relationship_type": "basedIn",
                    "direction": "out",
                    "target_label": "Country",
                    "property": "name",
                    "op": "eq",
                    "value": "United States of America",
                },
            ],
            "return_mode": "names",
            "limit": 10,
        },
    )

    query, params = driver.queries[0]
    assert "MATCH (company:`Company`)" in query
    assert "MATCH (company)-[cq_r0:`hasCEO`]->(person:`Person`)" in query
    assert "MATCH (company)-[cq_r1:`basedIn`]->(country:`Country`)" in query
    assert "WHERE person.`name` = $filter_0 AND country.`name` = $filter_1" in query
    assert "RETURN DISTINCT company.`name` AS `name`" in query
    assert "SKIP $offset LIMIT $limit" in query
    assert params == {
        "filter_0": "Elon Musk",
        "filter_1": "United States of America",
        "limit": 10,
        "offset": 0,
    }
    assert fetch_rows(backend, result["handle"]) == [["SpaceX"]]


def test_constraint_query_can_return_extra_candidate_properties_without_neo4j(
    schema: dict[str, Any],
) -> None:
    backend, driver = _fake_backend(schema)

    backend.call(
        "constraint_query",
        {
            "find": {"label": "Company", "as": "company"},
            "where": [
                {
                    "relationship_type": "subsidiaryOf",
                    "direction": "out",
                    "target_label": "Company",
                    "property": "name",
                    "op": "eq",
                    "value": "Interscope Records",
                }
            ],
            "return_mode": "names",
            "return_properties": [{"property": "launch_year", "alias": "launch_year"}],
            "limit": 10,
        },
    )

    query, _params = driver.queries[0]
    assert (
        "RETURN DISTINCT company.`name` AS `name`, company.`launch_year` AS `launch_year`"
    ) in query


def test_pattern_query_supports_relationship_filters_without_neo4j(schema: dict[str, Any]) -> None:
    backend, driver = _fake_backend(schema)

    backend.call(
        "pattern_query",
        {
            "start_label": "Company",
            "start_as": "company",
            "hops": [
                {
                    "relationship_type": "hasBoardMember",
                    "direction": "out",
                    "target_label": "Person",
                    "as": "person",
                    "rel_as": "membership",
                    "relationship_filters": [
                        {"property": "start_year", "op": "lte", "value": 2009},
                        {"property": "end_year", "op": "gte_or_null", "value": 2009},
                    ],
                }
            ],
            "select": [{"var": "person", "property": "name", "alias": "name"}],
        },
    )

    query, params = driver.queries[-1]
    assert "[membership:`hasBoardMember`]" in query
    assert "membership.`start_year` <= $filter_0" in query
    assert "(membership.`end_year` IS NULL OR membership.`end_year` >= $filter_1)" in query
    assert params["filter_0"] == 2009
    assert params["filter_1"] == 2009


def test_top_entities_by_property_builds_ranked_pattern_without_neo4j(
    schema: dict[str, Any],
) -> None:
    backend, driver = _fake_backend(schema)

    result = backend.call(
        "top_entities_by_property",
        {
            "start_label": "Company",
            "start_as": "company",
            "hops": [
                {
                    "relationship_type": "hasBoardMember",
                    "direction": "out",
                    "target_label": "Person",
                    "as": "person",
                }
            ],
            "target": "person",
            "property": "date_of_birth",
            "order": "desc",
            "limit": 1,
        },
    )

    query, params = driver.queries[-1]
    assert "MATCH (company:`Company`)" in query
    assert "MATCH (company)-[r0:`hasBoardMember`]->(person:`Person`)" in query
    assert "person.`date_of_birth` IS NOT NULL" not in query
    assert "WITH DISTINCT person" in query
    assert (
        "RETURN person.`name` AS `name`, person.`date_of_birth` AS `__rank_value`, "
        "person.`id` AS `__rank_tie_id`"
    ) in query
    assert "ORDER BY `__rank_value` DESC, `__rank_tie_id` ASC" in query
    assert "LIMIT $limit" in query
    assert params["limit"] == 1
    assert result["ranking"] == {
        "target": "person",
        "property": "date_of_birth",
        "order": "desc",
        "limit": 1,
    }
    assert "fetch" in result["finalization_hint"]


def test_top_entities_by_property_reports_property_owner_hint_without_neo4j(
    schema: dict[str, Any],
) -> None:
    backend, _driver = _fake_backend(schema)

    with pytest.raises(ValueError, match="Variables in this pattern that have this property"):
        backend.call(
            "top_entities_by_property",
            {
                "start_label": "Person",
                "start_as": "person",
                "hops": [
                    {
                        "relationship_type": "hasBoardMember",
                        "direction": "in",
                        "target_label": "Company",
                        "as": "company",
                    }
                ],
                "target": "company",
                "property": "date_of_birth",
                "order": "desc",
                "limit": 1,
            },
        )


def test_fetch_warns_when_returning_only_one_page(schema: dict[str, Any]) -> None:
    backend, _driver = _fake_backend(schema)
    result = backend._store(
        [{"name": f"row-{index}"} for index in range(12)],
        kind="table",
        columns=["name"],
    )

    first_page = backend.call("fetch", {"from": result["handle"], "limit": 5})

    assert first_page["truncated"] is True
    assert first_page["next_offset"] == 5
    assert "count_handle or group_handle" in first_page["pagination_hint"]


def test_fetch_treats_null_pagination_args_as_defaults(schema: dict[str, Any]) -> None:
    backend, _driver = _fake_backend(schema)
    result = backend._store(
        [{"name": "Alice"}, {"name": "Bob"}],
        kind="table",
        columns=["name"],
    )

    page = backend.call("fetch", {"from": result["handle"], "limit": None, "offset": None})

    assert page["rows"] == [["Alice"], ["Bob"]]
    assert page["next_offset"] is None


def test_evaluation_fetch_all_pages_replaces_paginated_last_fetch(schema: dict[str, Any]) -> None:
    backend, _driver = _fake_backend(schema)
    result = backend._store(
        [{"name": f"row-{index}"} for index in range(25)],
        kind="table",
        columns=["name"],
    )
    first_page = backend.call("fetch", {"from": result["handle"], "limit": 10})

    full_page = _evaluation_fetch_all_pages(
        backend,
        {"args": {"from": result["handle"], "limit": 10}},
        first_page,
    )

    assert first_page["truncated"] is True
    assert full_page["evaluation_fetch_all_pages"] is True
    assert full_page["returned_count"] == 25
    assert full_page["truncated"] is False
    assert backend.last_fetch == [[f"row-{index}"] for index in range(25)]


def test_large_handle_includes_server_side_aggregation_hint(schema: dict[str, Any]) -> None:
    backend, _driver = _fake_backend(schema)

    result = backend._store(
        [{"name": f"row-{index}"} for index in range(1000)],
        kind="table",
        columns=["name"],
    )

    assert result["matched_count"] == 1000
    assert "large or may be capped" in result["large_result_hint"]


def test_same_target_role_intersection_keep_entities_keeps_handle_composable(
    schema: dict[str, Any],
) -> None:
    backend, driver = _fake_backend(schema)

    result = backend.call(
        "same_target_role_intersection",
        {
            "source_label": "Person",
            "source_as": "person",
            "target_label": "Company",
            "target_as": "company",
            "relationships": [
                {"relationship_type": "foundedBy", "direction": "in"},
                {"relationship_type": "hasBoardMember", "direction": "in"},
            ],
            "select": [{"var": "person", "property": "name", "alias": "name"}],
            "keep_entities": True,
        },
    )

    query, _params = driver.queries[-1]
    assert "person AS person" in query
    assert "company AS company" in query
    assert "person.`name` AS `name`" in query
    assert "finalization_hint" not in result
    assert "continuation_hint" in result
    handle = backend._handle(result["handle"])
    assert {"person", "company", "name"}.issubset(handle.rows[0])


def test_same_target_role_intersection_orders_by_hidden_property(
    schema: dict[str, Any],
) -> None:
    backend, driver = _fake_backend(schema)

    result = backend.call(
        "same_target_role_intersection",
        {
            "source_label": "Company",
            "source_as": "company",
            "target_label": "Person",
            "target_as": "person",
            "relationships": [
                {"relationship_type": "foundedBy", "direction": "out"},
                {"relationship_type": "hasBoardMember", "direction": "out"},
            ],
            "select": [{"var": "company", "property": "name", "alias": "name"}],
            "order_by": [{"var": "company", "property": "launch_year", "direction": "asc"}],
        },
    )

    query, _params = driver.queries[-1]
    assert "company.`launch_year` AS `__project_order_0`" in query
    assert backend._handle(result["handle"]).columns == ["name"]
    assert backend.call("fetch", {"from": result["handle"]})["rows"] == [
        ["Old Co"],
        ["New Co"],
    ]
    assert all(
        "__project_order_" not in key
        for row in backend._handle(result["handle"]).rows
        for key in row
    )


def test_project_keep_entities_returns_continuation_hint(schema: dict[str, Any]) -> None:
    backend, _driver = _fake_backend(schema)
    source = backend._store(
        [
            {
                "person": {"labels": ["Person"], "properties": {"id": "p1", "name": "Ada"}},
                "__rel_ids": [],
            }
        ],
        focus="person",
    )

    projected = backend.call(
        "project",
        {
            "from": source["handle"],
            "select": [{"var": "person", "property": "name", "alias": "name"}],
            "keep_entities": True,
        },
    )

    assert "continuation_hint" in projected
    assert "Do not call project again" in projected["continuation_hint"]
    handle = backend._handle(projected["handle"])
    assert "person" in handle.rows[0]
    assert "name" in handle.rows[0]
    assert handle.columns == ["name"]


def test_relationship_query_normalizes_single_relationship_alias_without_neo4j(
    schema: dict[str, Any],
) -> None:
    backend, driver = _fake_backend(schema)

    backend.call(
        "relationship_query",
        {
            "source_label": "Company",
            "source_as": "company",
            "relationship_type": "hasCEO",
            "target_label": "Person",
            "target_as": "person",
            "filters": [{"var": "rel_prop", "property": "start_year", "op": "lte", "value": 2009}],
            "select": [{"var": "rel_prop", "property": "start_year", "alias": "start_year"}],
        },
    )

    query, params = driver.queries[-1]
    assert "[rel:`hasCEO`]" in query
    assert "rel.`start_year` <= $filter_0" in query
    assert "rel.`start_year` AS `start_year`" in query
    assert params["filter_0"] == 2009


def test_project_can_keep_entities_for_later_graph_operations(schema: dict[str, Any]) -> None:
    backend, _ = _fake_backend(schema)
    source = backend._store(
        [
            {
                "company": {
                    "labels": ["Company", "Entity"],
                    "properties": {"id": "c1", "name": "Left Co", "launch_year": 1999},
                }
            },
            {
                "company": {
                    "labels": ["Company", "Entity"],
                    "properties": {"id": "c2", "name": "Right Co", "launch_year": 2001},
                }
            },
        ],
        focus="company",
    )

    projected = backend.call(
        "project",
        {
            "from": source["handle"],
            "select": [{"var": "company", "property": "name", "alias": "name"}],
            "keep_entities": True,
        },
    )

    handle = backend._handle(projected["handle"])
    assert handle.kind == "table"
    assert handle.columns == ["name"]
    assert projected["entity_variables"] == ["company"]
    assert projected["columns"] == ["name"]
    assert "entity_set_operation" in projected["composition_hint"]
    assert handle.rows[0]["company"]["properties"]["name"] == "Left Co"
    assert backend.call("fetch", {"from": projected["handle"]})["rows"] == [
        ["Left Co"],
        ["Right Co"],
    ]


def test_project_orders_by_hidden_entity_property_without_returning_it(
    schema: dict[str, Any],
) -> None:
    backend, _ = _fake_backend(schema)
    source = backend._store(
        [
            {
                "company": {
                    "labels": ["Company", "Entity"],
                    "properties": {"id": "c1", "name": "New Co", "launch_year": 2020},
                }
            },
            {
                "company": {
                    "labels": ["Company", "Entity"],
                    "properties": {"id": "c2", "name": "Old Co", "launch_year": 1980},
                }
            },
        ],
        focus="company",
    )

    projected = backend.call(
        "project",
        {
            "from": source["handle"],
            "select": [{"var": "company", "property": "name", "alias": "name"}],
            "order_by": [{"var": "company", "property": "launch_year", "direction": "asc"}],
        },
    )

    assert backend._handle(projected["handle"]).columns == ["name"]
    assert backend.call("fetch", {"from": projected["handle"]})["rows"] == [
        ["Old Co"],
        ["New Co"],
    ]
    assert all(
        "__project_order_" not in key
        for row in backend._handle(projected["handle"]).rows
        for key in row
    )


def test_project_distinct_preserves_hidden_order_before_deduping(
    schema: dict[str, Any],
) -> None:
    backend, _ = _fake_backend(schema)
    source = backend._store(
        [
            {
                "company": {
                    "labels": ["Company", "Entity"],
                    "properties": {"id": "c1", "name": "Shared Name", "launch_year": 2020},
                }
            },
            {
                "company": {
                    "labels": ["Company", "Entity"],
                    "properties": {"id": "c2", "name": "Other", "launch_year": 2000},
                }
            },
            {
                "company": {
                    "labels": ["Company", "Entity"],
                    "properties": {"id": "c3", "name": "Shared Name", "launch_year": 1980},
                }
            },
        ],
        focus="company",
    )

    projected = backend.call(
        "project",
        {
            "from": source["handle"],
            "select": [{"var": "company", "property": "name", "alias": "name"}],
            "distinct": True,
            "order_by": [{"var": "company", "property": "launch_year", "direction": "asc"}],
        },
    )

    assert backend.call("fetch", {"from": projected["handle"]})["rows"] == [
        ["Shared Name"],
        ["Other"],
    ]


def test_project_distinct_preserves_entity_set_duplicate_scalar_values(
    schema: dict[str, Any],
) -> None:
    backend, _ = _fake_backend(schema)
    source = backend._store(
        [
            {
                "company": {
                    "labels": ["Company", "Entity"],
                    "properties": {"id": "c1", "name": "Shared Name"},
                }
            },
            {
                "company": {
                    "labels": ["Company", "Entity"],
                    "properties": {"id": "c2", "name": "Shared Name"},
                }
            },
        ],
        focus="company",
        metadata={"entity_set_operation": True},
    )

    projected = backend.call(
        "project",
        {
            "from": source["handle"],
            "select": [{"var": "company", "property": "name", "alias": "name"}],
            "distinct": True,
        },
    )
    scalar_projected = backend.call(
        "project",
        {
            "from": source["handle"],
            "select": [{"var": "company", "property": "name", "alias": "name"}],
            "distinct": True,
            "distinct_scope": "scalar",
        },
    )

    assert backend.call("fetch", {"from": projected["handle"]})["rows"] == [
        ["Shared Name"],
        ["Shared Name"],
    ]
    assert backend.call("fetch", {"from": scalar_projected["handle"]})["rows"] == [
        ["Shared Name"],
    ]


def test_project_dedupes_selected_entities_for_role_intersection_handles(
    schema: dict[str, Any],
) -> None:
    backend, _ = _fake_backend(schema)
    source = backend._store(
        [
            {
                "company": {
                    "labels": ["Company", "Entity"],
                    "properties": {"id": "c1", "name": "Shared Name"},
                },
                "person": {
                    "labels": ["Person", "Entity"],
                    "properties": {"id": "p1", "name": "Ada"},
                },
            },
            {
                "company": {
                    "labels": ["Company", "Entity"],
                    "properties": {"id": "c1", "name": "Shared Name"},
                },
                "person": {
                    "labels": ["Person", "Entity"],
                    "properties": {"id": "p2", "name": "Grace"},
                },
            },
            {
                "company": {
                    "labels": ["Company", "Entity"],
                    "properties": {"id": "c2", "name": "Other"},
                },
                "person": {
                    "labels": ["Person", "Entity"],
                    "properties": {"id": "p3", "name": "Linus"},
                },
            },
        ],
        focus="company",
        metadata={"entity_projection_distinct_default": True},
    )

    projected = backend.call(
        "project",
        {
            "from": source["handle"],
            "select": [{"var": "company", "property": "name", "alias": "name"}],
            "distinct": False,
        },
    )

    assert backend.call("fetch", {"from": projected["handle"]})["rows"] == [
        ["Shared Name"],
        ["Other"],
    ]
    assert backend.call("fetch", {"from": source["handle"]})["rows"] == [
        ["Shared Name"],
        ["Other"],
    ]


def test_entity_set_operation_union_uses_right_operand_variable_payload(
    schema: dict[str, Any],
) -> None:
    backend, _ = _fake_backend(schema)
    founded = backend._store(
        [
            {
                "company": {
                    "labels": ["Company", "Entity"],
                    "properties": {"id": "c1", "name": "Founded Co"},
                }
            }
        ],
        focus="company",
    )
    subsidiaries = backend._store(
        [
            {
                "parent": {
                    "labels": ["Company", "Entity"],
                    "properties": {"id": "p1", "name": "Parent Co"},
                },
                "subsidiary": {
                    "labels": ["Company", "Entity"],
                    "properties": {"id": "c2", "name": "Subsidiary Co"},
                },
            }
        ],
        focus="subsidiary",
    )

    combined = backend.call(
        "entity_set_operation",
        {
            "op": "union",
            "operands": [
                {"handle": founded["handle"], "var": "company"},
                {"handle": subsidiaries["handle"], "var": "subsidiary"},
            ],
            "as": "company",
        },
    )

    assert sorted(fetch_rows(backend, combined["handle"])) == [
        ["Founded Co"],
        ["Subsidiary Co"],
    ]


def test_fetch_role_intersection_handle_prefers_selected_columns(
    schema: dict[str, Any],
) -> None:
    backend, _ = _fake_backend(schema)
    source = backend._store(
        [
            {
                "person": {
                    "labels": ["Person", "Entity"],
                    "properties": {"id": "p1", "name": "Ada"},
                },
                "company": {
                    "labels": ["Company", "Entity"],
                    "properties": {"id": "c1", "name": "Analytical Engines"},
                },
                "company_name": "Analytical Engines",
                "launch_year": 1837,
            }
        ],
        focus="company",
        metadata={
            "entity_projection_distinct_default": True,
            "preferred_fetch_columns": ["company_name", "launch_year"],
        },
    )

    assert backend.call("fetch", {"from": source["handle"]})["rows"] == [
        ["Analytical Engines", 1837],
    ]


def test_project_with_group_by_metrics_delegates_to_group_handle(schema: dict[str, Any]) -> None:
    backend, _ = _fake_backend(schema)
    source = backend._store(
        [
            {
                "ceo": {
                    "labels": ["Person", "Entity"],
                    "properties": {"id": "p1", "name": "Ada"},
                },
                "company": {
                    "labels": ["Company", "Entity"],
                    "properties": {"id": "c1", "name": "A Co"},
                },
            },
            {
                "ceo": {
                    "labels": ["Person", "Entity"],
                    "properties": {"id": "p1", "name": "Ada"},
                },
                "company": {
                    "labels": ["Company", "Entity"],
                    "properties": {"id": "c2", "name": "B Co"},
                },
            },
        ],
        focus="company",
    )

    grouped = backend.call(
        "project",
        {
            "from": source["handle"],
            "group_by": [{"var": "ceo", "property": "name", "alias": "ceo_name"}],
            "metrics": [{"op": "count_distinct", "var": "company", "alias": "company_count"}],
        },
    )

    assert fetch_rows(backend, grouped["handle"]) == [["Ada", 2]]


def test_project_explodes_list_properties_before_distinct(schema: dict[str, Any]) -> None:
    backend, _ = _fake_backend(schema)
    source = backend._store(
        [
            {
                "person": {
                    "labels": ["Person", "Entity"],
                    "properties": {
                        "id": "p1",
                        "name": "Ada",
                        "country_of_citizenship": ["Italy", "France"],
                    },
                }
            },
            {
                "person": {
                    "labels": ["Person", "Entity"],
                    "properties": {
                        "id": "p2",
                        "name": "Grace",
                        "country_of_citizenship": ["Italy"],
                    },
                }
            },
            {
                "person": {
                    "labels": ["Person", "Entity"],
                    "properties": {
                        "id": "p3",
                        "name": "No Country",
                        "country_of_citizenship": None,
                    },
                }
            },
        ],
        focus="person",
    )

    projected = backend.call(
        "project",
        {
            "from": source["handle"],
            "select": [
                {
                    "var": "person",
                    "property": "country_of_citizenship",
                    "alias": "country",
                    "explode": True,
                }
            ],
            "distinct": True,
        },
    )

    assert sorted(fetch_rows(backend, projected["handle"])) == [["France"], ["Italy"]]


def test_project_filter_and_group_handle_support_scalar_table_columns(
    schema: dict[str, Any],
) -> None:
    backend, _ = _fake_backend(schema)
    source = backend._store(
        [
            {"company_name": "Boeing", "shared_count": 3},
            {"company_name": "Airbus", "shared_count": 2},
            {"company_name": "Airbus", "shared_count": 4},
        ],
        kind="table",
        columns=["company_name", "shared_count"],
    )

    filtered = backend.call(
        "filter",
        {
            "from": source["handle"],
            "var": "company_name",
            "property": "company_name",
            "op": "not_contains",
            "value": "Boeing",
        },
    )
    projected = backend.call(
        "project",
        {
            "from": filtered["handle"],
            "select": [
                {"var": "company_name", "property": "company_name", "alias": "company"},
                {"var": "shared_count", "property": "shared_count", "alias": "count"},
            ],
            "distinct": True,
        },
    )
    grouped = backend.call(
        "group_handle",
        {
            "from": filtered["handle"],
            "group_by": [{"var": "company_name", "property": "company_name", "alias": "company"}],
            "metrics": [{"op": "max", "var": "shared_count", "alias": "max_count"}],
        },
    )

    assert fetch_rows(backend, projected["handle"]) == [["Airbus", 2], ["Airbus", 4]]
    assert fetch_rows(backend, grouped["handle"]) == [["Airbus", 4]]


def test_filter_not_in_matches_cypher_null_semantics() -> None:
    assert _predicate(["Austria", "Germany"], "not_in", "Austria") is False
    assert _predicate(["Germany"], "not_in", "Austria") is True
    assert _predicate(None, "not_in", "Austria") is False
    assert _predicate("Germany", "not_in", "Austria") is False


def test_pattern_query_distinct_projects_distinct_entities_before_scalar_values(
    schema: dict[str, Any],
) -> None:
    backend, driver = _fake_backend(schema)

    backend.call(
        "pattern_query",
        {
            "start_label": "Country",
            "start_as": "country",
            "filters": [
                {"var": "country", "property": "name", "op": "eq", "value": "Czech Republic"}
            ],
            "hops": [
                {
                    "relationship_type": "basedIn",
                    "direction": "in",
                    "target_label": "Company",
                    "as": "company",
                },
                {
                    "relationship_type": "hasCEO",
                    "direction": "out",
                    "target_label": "Person",
                    "as": "ceo",
                },
            ],
            "select": [{"var": "ceo", "property": "name", "alias": "ceo_name"}],
            "distinct": True,
        },
    )

    query, _ = driver.queries[-1]
    assert "WITH DISTINCT ceo RETURN ceo.`name` AS `ceo_name`" in query


def test_shared_role_aggregate_treats_select_as_group_by_when_metrics_are_present(
    schema: dict[str, Any],
) -> None:
    backend, driver = _fake_backend(schema)

    result = backend.call(
        "shared_role_aggregate",
        {
            "seed_label": "Company",
            "seed_as": "boeing",
            "seed_filters": [{"var": "boeing", "property": "name", "op": "eq", "value": "Boeing"}],
            "shared_label": "Person",
            "shared_as": "person",
            "seed_relationship": {"relationship_type": "hasBoardMember", "direction": "out"},
            "peer_label": "Company",
            "peer_as": "peer_company",
            "peer_relationship": {"relationship_type": "hasBoardMember", "direction": "out"},
            "select": [{"var": "peer_company", "property": "name", "alias": "company"}],
            "metrics": [{"op": "count_distinct", "var": "person", "alias": "shared_members"}],
        },
    )

    query, _ = driver.queries[-1]
    assert "peer_company.`name` AS `company`" in query
    assert "count(DISTINCT person) AS `shared_members`" in query
    assert fetch_rows(backend, result["handle"]) == [["Cardinal Health", 1]]


def test_shared_role_aggregate_can_anchor_seed_from_handle(schema: dict[str, Any]) -> None:
    backend, driver = _fake_backend(schema)
    seed = backend._store(
        [
            {
                "boeing": {
                    "labels": ["Company", "Entity"],
                    "properties": {"id": "boeing-id", "name": "Boeing"},
                }
            }
        ],
        focus="boeing",
    )

    backend.call(
        "shared_role_aggregate",
        {
            "seed_label": "Company",
            "seed_as": "boeing",
            "seed_from": seed["handle"],
            "shared_label": "Person",
            "shared_as": "person",
            "seed_relationship": {"relationship_type": "hasBoardMember", "direction": "out"},
            "peer_label": "Company",
            "peer_as": "peer_company",
            "peer_relationship": {"relationship_type": "hasBoardMember", "direction": "out"},
            "group_by": [{"var": "peer_company", "property": "name", "alias": "company"}],
            "metrics": [{"op": "count_distinct", "var": "person", "alias": "shared_members"}],
        },
    )

    query, params = driver.queries[-1]
    assert "boeing.id IN $seed_ids" in query
    assert params["seed_ids"] == ["boeing-id"]


def test_shared_role_aggregate_infers_seed_alias_from_single_entity_handle(
    schema: dict[str, Any],
) -> None:
    backend, driver = _fake_backend(schema)
    seed = backend._store(
        [
            {
                "boeing": {
                    "labels": ["Company", "Entity"],
                    "properties": {"id": "boeing-id", "name": "Boeing"},
                }
            }
        ],
        focus="boeing",
    )

    backend.call(
        "shared_role_aggregate",
        {
            "seed_label": "Company",
            "seed_from": seed["handle"],
            "shared_label": "Person",
            "shared_as": "person",
            "seed_relationship": {"relationship_type": "hasBoardMember", "direction": "out"},
            "peer_label": "Company",
            "peer_as": "peer_company",
            "peer_relationship": {"relationship_type": "hasBoardMember", "direction": "out"},
            "group_by": [{"var": "peer_company", "property": "name", "alias": "company"}],
            "metrics": [{"op": "count_distinct", "var": "person", "alias": "shared_members"}],
        },
    )

    query, params = driver.queries[-1]
    assert "MATCH (boeing:`Company`)-[seed_rel:`hasBoardMember`]->(person:`Person`)" in query
    assert "boeing.id IN $seed_ids" in query
    assert params["seed_ids"] == ["boeing-id"]


def test_join_handles_rejects_different_entity_labels(schema: dict[str, Any]) -> None:
    backend, _ = _fake_backend(schema)
    company = backend._store(
        [
            {
                "company": {
                    "labels": ["Company", "Entity"],
                    "properties": {"id": "c1", "name": "SpaceX"},
                }
            }
        ],
        focus="company",
    )
    country = backend._store(
        [
            {
                "country": {
                    "labels": ["Country", "Entity"],
                    "properties": {"id": "co1", "name": "United States of America"},
                }
            }
        ],
        focus="country",
    )

    with pytest.raises(ValueError, match="same label/type"):
        backend.call(
            "join_handles",
            {
                "left": company["handle"],
                "right": country["handle"],
                "left_var": "company",
                "right_var": "country",
            },
        )


def test_compare_reports_projected_scalar_handle_repair_hint(schema: dict[str, Any]) -> None:
    backend, _ = _fake_backend(schema)
    source = backend._store(
        [
            {
                "company": {
                    "labels": ["Company", "Entity"],
                    "properties": {"id": "c1", "name": "Left Co", "launch_year": 1999},
                }
            }
        ],
        focus="company",
    )
    projected = backend.call(
        "project",
        {
            "from": source["handle"],
            "select": [{"var": "company", "property": "launch_year", "alias": "launch_year"}],
        },
    )

    with pytest.raises(ValueError, match="keep_entities=true"):
        backend.call(
            "compare",
            {
                "left": projected["handle"],
                "left_var": "company",
                "right": projected["handle"],
                "right_var": "company",
                "property": "launch_year",
                "op": "eq",
            },
        )


def test_optional_expand_count_builds_left_preserving_count_without_neo4j(
    schema: dict[str, Any],
) -> None:
    backend, driver = _fake_backend(schema)
    source = backend._store(
        [
            {
                "founder": {
                    "labels": ["Person", "Entity"],
                    "properties": {"id": "p1", "name": "Zero Founder"},
                }
            },
            {
                "founder": {
                    "labels": ["Person", "Entity"],
                    "properties": {"id": "p2", "name": "One Founder"},
                }
            },
            {
                "founder": {
                    "labels": ["Person", "Entity"],
                    "properties": {"id": "p2", "name": "One Founder"},
                }
            },
        ],
        focus="founder",
    )

    result = backend.call(
        "optional_expand_count",
        {
            "from": source["handle"],
            "source": "founder",
            "relationship_type": "hasCEO",
            "direction": "in",
            "target_label": "Company",
            "group_by": [{"var": "founder", "property": "name", "alias": "name"}],
            "alias": "num",
        },
    )

    query, params = driver.queries[-1]
    assert "OPTIONAL MATCH (s)<-[r:`hasCEO`]-(t:`Company`)" in query
    assert "NOT elementId(r) IN row.rel_ids" not in query
    assert "LIMIT $limit" not in query
    assert "limit" not in params
    assert params["rows"] == [
        {"row_index": 0, "source_id": "p1", "rel_ids": []},
        {"row_index": 1, "source_id": "p2", "rel_ids": []},
    ]
    assert "fetch" in result["finalization_hint"]
    assert result["columns"] == ["name", "num"]
    assert fetch_rows(backend, result["handle"]) == [["Zero Founder", 0], ["One Founder", 1]]


def test_optional_expand_count_can_exclude_already_traversed_relationships(
    schema: dict[str, Any],
) -> None:
    backend, driver = _fake_backend(schema)
    source = backend._store(
        [
            {
                "company": {
                    "labels": ["Company", "Entity"],
                    "properties": {"id": "c1", "name": "Acme"},
                },
                "founder": {
                    "labels": ["Person", "Entity"],
                    "properties": {"id": "p1", "name": "Ada"},
                },
                "__rel_ids": ["rel-1"],
            }
        ],
        focus="founder",
    )

    backend._optional_expand_count(
        {
            "from": source["handle"],
            "source": "founder",
            "relationship_type": "hasCEO",
            "direction": "in",
            "target_label": "Company",
            "exclude_traversed_relationships": True,
        },
    )

    query, params = driver.queries[-1]
    assert "WHERE r IS NULL OR NOT elementId(r) IN row.rel_ids" in query
    assert params["rows"] == [{"row_index": 0, "source_id": "p1", "rel_ids": ["rel-1"]}]


def test_optional_expand_count_keeps_explicit_limit(schema: dict[str, Any]) -> None:
    backend, driver = _fake_backend(schema)
    source = backend._store(
        [
            {
                "company": {
                    "labels": ["Company", "Entity"],
                    "properties": {"id": "c1", "name": "Acme"},
                }
            }
        ],
        focus="company",
    )

    backend.call(
        "optional_expand_count",
        {
            "from": source["handle"],
            "source": "company",
            "relationship_type": "foundedBy",
            "direction": "out",
            "target_label": "Person",
            "limit": 1,
        },
    )

    query, params = driver.queries[-1]
    assert "LIMIT $limit" in query
    assert params["limit"] == 1


def test_pattern_query_does_not_add_implicit_limit(schema: dict[str, Any]) -> None:
    backend, driver = _fake_backend(schema)

    backend.call(
        "pattern_query",
        {
            "start_label": "Company",
            "start_as": "company",
            "select": [{"var": "company", "property": "name", "alias": "name"}],
        },
    )

    query, params = driver.queries[-1]
    assert "LIMIT $limit" not in query
    assert "limit" not in params


def test_pattern_query_rejects_large_source_handle_without_opt_in(
    schema: dict[str, Any],
) -> None:
    backend, _driver = _fake_backend(schema)
    source = backend._store(
        [
            {
                "company": {
                    "labels": ["Company", "Entity"],
                    "properties": {"id": f"company-{index}", "name": f"Company {index}"},
                }
            }
            for index in range(5001)
        ],
        focus="company",
    )

    with pytest.raises(ValueError, match="pattern_query would consume a large handle"):
        backend.call(
            "pattern_query",
            {
                "from": source["handle"],
                "start_label": "Company",
                "start_as": "company",
                "hops": [
                    {
                        "relationship_type": "hasCEO",
                        "direction": "out",
                        "target_label": "Person",
                        "as": "person",
                    }
                ],
            },
        )


def test_same_target_role_intersection_rejects_multi_named_targets_for_repeated_role(
    schema: dict[str, Any],
) -> None:
    backend, _ = _fake_backend(schema)

    with pytest.raises(ValueError, match="common-neighbor questions"):
        backend.call(
            "same_target_role_intersection",
            {
                "source_label": "Person",
                "source_as": "person",
                "target_label": "Company",
                "target_as": "company",
                "relationships": [
                    {"relationship_type": "hasBoardMember", "direction": "in"},
                    {"relationship_type": "hasBoardMember", "direction": "in"},
                ],
                "filters": [
                    {
                        "var": "company",
                        "property": "name",
                        "op": "in",
                        "value": ["Company A", "Company B"],
                    }
                ],
                "select": [{"var": "person", "property": "name", "alias": "name"}],
            },
        )


@pytest.fixture(scope="module")
def backend(schema: dict[str, Any]) -> Any:
    tool_backend = Neo4jGraphBackend(
        os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687"),
        os.getenv("NEO4J_USER", "neo4j"),
        os.getenv("NEO4J_PASSWORD", "password"),
        schema,
        query_timeout_s=20,
    )
    try:
        tool_backend.call("count_nodes", {"label": "Country", "alias": "country_count"})
    except Exception as exc:  # pragma: no cover - depends on local Neo4j availability
        tool_backend.close()
        pytest.skip(f"Neo4j company benchmark dataset is not available: {exc}")
    yield tool_backend
    tool_backend.close()


def fetch_rows(backend: Any, handle: str, *, limit: int = 1000, offset: int = 0) -> list[list[Any]]:
    return backend.call("fetch", {"from": handle, "limit": limit, "offset": offset})["rows"]


def test_schema_tools_expose_company_graph_affordances(backend: Any) -> None:
    inspected = backend.call("schema_inspect", {})
    assert {"schema", "affordance"} == set(inspected)
    assert "Company" in inspected["schema"]["labels"]
    assert any(
        row["pattern"] == "(:Company)-[:hasCEO]->(:Person)"
        for row in inspected["affordance"]["relationship_traversals"]
    )

    schema = backend.call("schema_get", {})
    assert {"Company", "Person", "Country", "Industry"}.issubset(set(schema["labels"]))
    assert "hasCEO" in schema["relationship_types"]
    assert {
        "source_label": "Company",
        "relationship_type": "hasCEO",
        "target_label": "Person",
    } in [
        {
            "source_label": row["source_label"],
            "relationship_type": row["relationship_type"],
            "target_label": row["target_label"],
        }
        for row in schema["relationship_patterns"]
    ]

    affordance = backend.call("schema_affordance", {})
    label_counts = {row["label"]: row["count"] for row in affordance["labels"]}
    assert label_counts["Country"] == 217
    assert label_counts["Industry"] == 526
    assert any(
        row["pattern"] == "(:Company)-[:hasCEO]->(:Person)"
        for row in affordance["relationship_traversals"]
    )
    temporal = {row["relationship_type"]: row for row in affordance["temporal_relationships"]}
    assert temporal["hasBoardMember"]["start_property"] == "start_year"
    assert temporal["hasBoardMember"]["end_property"] == "end_year"
    assert temporal["hasBoardMember"]["active_at_year_filter_template"] == [
        {"property": "start_year", "op": "lte", "value": "YEAR"},
        {"property": "end_year", "op": "gte_or_null", "value": "YEAR"},
    ]
    person_props = {
        row["property"]: row
        for row in affordance["property_affordances"]
        if row["label"] == "Person"
    }
    assert person_props["country_of_citizenship"]["inferred_type"] == "list[string]"
    assert "not_in" in person_props["country_of_citizenship"]["operators"]


def test_inspect_paths_returns_directional_schema_hops(backend: Any) -> None:
    result = backend.call(
        "inspect_paths",
        {"source_label": "Industry", "target_label": "Company", "max_hops": 1},
    )

    assert any(
        path["hops"]
        == [
            {
                "relationship_type": "operatesIn",
                "direction": "in",
                "target_label": "Company",
                "as": "company",
            }
        ]
        for path in result["paths"]
    )


def test_summarize_handle_reports_entity_variables_and_next_traversals(backend: Any) -> None:
    company = backend.call(
        "node_search",
        {"label": "Company", "property": "name", "value": "SpaceX", "as": "company"},
    )

    summary = backend.call("summarize_handle", {"from": company["handle"]})
    variables = {item["name"]: item for item in summary["variables"]}

    assert summary["row_count"] == 1
    assert variables["company"]["shape"] == "entity"
    assert "Company" in variables["company"]["labels"]
    assert any(
        item["relationship_type"] == "hasCEO"
        and item["direction"] == "out"
        and item["target_label"] == "Person"
        for item in summary["next_traversals"]
    )


def test_unknown_handle_error_lists_available_handles(backend: Any) -> None:
    company = backend.call(
        "node_search",
        {"label": "Company", "property": "name", "value": "SpaceX", "as": "company"},
    )

    with pytest.raises(ValueError) as exc_info:
        backend.call("fetch", {"from": "h999"})

    message = str(exc_info.value)
    assert "Unknown handle: h999" in message
    assert company["handle"] in message
    assert "entity_variables" in message


def test_handle_recap_reports_lineage_and_available_handles(backend: Any) -> None:
    company = backend.call(
        "node_search",
        {"label": "Company", "property": "name", "value": "SpaceX", "as": "company"},
    )
    ceo = backend.call(
        "expand",
        {
            "from": company["handle"],
            "source": "company",
            "relationship_type": "hasCEO",
            "direction": "out",
            "target_label": "Person",
            "as": "ceo",
        },
    )

    recap = backend.call("handle_recap", {"from": ceo["handle"]})

    assert recap["handle"] == ceo["handle"]
    assert set(recap["entity_variables"]) == {"ceo", "company"}
    assert [step["tool"] for step in recap["lineage"]][-2:] == ["node_search", "expand"]
    assert recap["lineage"][-1]["parents"] == [company["handle"]]
    assert any(item["handle"] == company["handle"] for item in recap["available_handles"])


def test_repair_empty_result_suggests_schema_path_and_bound_var_fix(backend: Any) -> None:
    repair = backend.call(
        "repair_empty_result",
        {
            "failed_tool": "group_count_by_pattern",
            "reason": "zero_rows",
            "failed_args": {
                "start_label": "Company",
                "start_as": "company",
                "filters": [
                    {
                        "var": "industry",
                        "property": "name",
                        "op": "eq",
                        "value": "Video Game",
                    }
                ],
                "hops": [
                    {
                        "relationship_type": "subsidiaryOf",
                        "direction": "in",
                        "target_label": "Company",
                        "as": "subsidiary",
                    }
                ],
                "group_by": [{"var": "subsidiary", "property": "name", "alias": "name"}],
                "count_var": "missing_company",
            },
        },
    )

    actions = [item["action"] for item in repair["suggestions"]]
    assert "inspect_paths" in actions
    assert "fix_filter_var" in actions
    assert "fix_count_var" in actions


def test_count_nodes_returns_whole_label_cardinality_without_scan(backend: Any) -> None:
    country_count = backend.call("count_nodes", {"label": "Country", "alias": "country_count"})
    industry_count = backend.call("count_nodes", {"label": "Industry", "alias": "industry_count"})

    assert fetch_rows(backend, country_count["handle"]) == [[217]]
    assert fetch_rows(backend, industry_count["handle"]) == [[526]]


def test_node_scan_requires_explicit_large_opt_in(backend: Any) -> None:
    with pytest.raises(ValueError, match="node_scan is capped"):
        backend.call("node_scan", {"label": "Company", "as": "company", "limit": 50000})


def test_entity_lookup_and_expand_find_spacex_ceo(backend: Any) -> None:
    company = backend.call(
        "node_search",
        {"label": "Company", "property": "name", "value": "SpaceX", "as": "company"},
    )
    assert company["matched_count"] == 1
    assert company["preview"] == ["SpaceX"]

    ceo = backend.call(
        "expand",
        {
            "from": company["handle"],
            "source": "company",
            "relationship_type": "hasCEO",
            "direction": "out",
            "target_label": "Person",
            "as": "ceo",
        },
    )
    assert ceo["matched_count"] == 1
    assert ceo["preview"] == ["Elon Musk"]
    assert fetch_rows(backend, ceo["handle"]) == [["Elon Musk"]]


def test_entity_resolve_handles_non_exact_industry_names(backend: Any) -> None:
    result = backend.call(
        "entity_resolve",
        {"label": "Industry", "text": "footwear", "as": "industry", "limit": 20},
    )

    assert result["matched_count"] == 1
    assert result["preview"] == ["footwear industry"]


def test_entity_resolve_prefers_context_terms_for_qualified_company(backend: Any) -> None:
    generic = backend.call(
        "entity_resolve",
        {"label": "Company", "text": "Fresenius Kabi", "as": "company", "limit": 1},
    )
    qualified = backend.call(
        "entity_resolve",
        {
            "label": "Company",
            "text": "Fresenius Kabi",
            "context_terms": ["United States"],
            "as": "company",
            "limit": 1,
        },
    )

    assert generic["preview"] == ["Fresenius Kabi"]
    assert qualified["preview"] == ["Fresenius Kabi (United States)"]
    assert qualified["context_terms"] == ["united states"]


def test_entity_resolve_keeps_only_best_score_without_context_terms(backend: Any) -> None:
    result = backend.call(
        "entity_resolve",
        {"label": "Industry", "text": "Publishing", "as": "industry", "limit": 5},
    )

    assert result["matched_count"] == 1
    assert result["preview"] == ["publishing"]


def test_entity_resolve_surfaces_alternative_candidates(backend: Any) -> None:
    result = backend.call(
        "entity_resolve",
        {"label": "Industry", "text": "tire manufacturing", "as": "industry", "limit": 1},
    )

    assert result["preview"] == ["tire manufacturing"]
    assert any(
        candidate["name"] == "tyre industry"
        for candidate in result.get("alternative_candidates", [])
    )
    assert "candidate_hint" in result


def test_compare_supports_boolean_equality(backend: Any) -> None:
    on2 = backend.call(
        "node_search",
        {"label": "Company", "property": "name", "value": "On2 Technologies", "as": "on2"},
    )
    lacie = backend.call(
        "node_search",
        {"label": "Company", "property": "name", "value": "LaCie", "as": "lacie"},
    )
    comparison = backend.call(
        "compare",
        {
            "left": on2["handle"],
            "left_var": "on2",
            "right": lacie["handle"],
            "right_var": "lacie",
            "property": "launch_year",
            "op": "eq",
            "alias": "same_year",
        },
    )

    assert fetch_rows(backend, comparison["handle"]) == [[False]]


def test_relationship_query_supports_server_side_count_distinct(backend: Any) -> None:
    result = backend.call(
        "relationship_query",
        {
            "source_label": "Company",
            "source_as": "company",
            "relationship_type": "hasCEO",
            "target_label": "Person",
            "target_as": "person",
            "metrics": [{"op": "count_distinct", "var": "person", "alias": "ceo_count"}],
            "limit": 1000,
        },
    )

    assert result["matched_count"] == 1
    assert fetch_rows(backend, result["handle"]) == [[4319]]


def test_combine_intersects_common_industries(backend: Any) -> None:
    cch = backend.call(
        "node_search",
        {"label": "Company", "property": "name", "value": "CCH", "as": "cch"},
    )
    adobe = backend.call(
        "node_search",
        {"label": "Company", "property": "name", "value": "Adobe", "as": "adobe"},
    )
    cch_industries = backend.call(
        "expand",
        {
            "from": cch["handle"],
            "source": "cch",
            "relationship_type": "operatesIn",
            "direction": "out",
            "target_label": "Industry",
            "as": "industry_cch",
        },
    )
    adobe_industries = backend.call(
        "expand",
        {
            "from": adobe["handle"],
            "source": "adobe",
            "relationship_type": "operatesIn",
            "direction": "out",
            "target_label": "Industry",
            "as": "industry_adobe",
        },
    )
    intersection = backend.call(
        "combine",
        {
            "left": cch_industries["handle"],
            "right": adobe_industries["handle"],
            "op": "intersect",
            "left_var": "industry_cch",
            "right_var": "industry_adobe",
            "as": "industry",
        },
    )

    assert fetch_rows(backend, intersection["handle"]) == [["software industry"]]


def test_count_handle_counts_distinct_entities_after_combine(backend: Any) -> None:
    cch = backend.call(
        "node_search",
        {"label": "Company", "property": "name", "value": "CCH", "as": "cch"},
    )
    adobe = backend.call(
        "node_search",
        {"label": "Company", "property": "name", "value": "Adobe", "as": "adobe"},
    )
    cch_industries = backend.call(
        "expand",
        {
            "from": cch["handle"],
            "source": "cch",
            "relationship_type": "operatesIn",
            "direction": "out",
            "target_label": "Industry",
            "as": "industry_cch",
        },
    )
    adobe_industries = backend.call(
        "expand",
        {
            "from": adobe["handle"],
            "source": "adobe",
            "relationship_type": "operatesIn",
            "direction": "out",
            "target_label": "Industry",
            "as": "industry_adobe",
        },
    )
    intersection = backend.call(
        "combine",
        {
            "left": cch_industries["handle"],
            "right": adobe_industries["handle"],
            "op": "intersect",
            "left_var": "industry_cch",
            "right_var": "industry_adobe",
            "as": "industry",
        },
    )
    count = backend.call(
        "count_handle",
        {"from": intersection["handle"], "var": "industry", "distinct": True, "alias": "n"},
    )

    assert fetch_rows(backend, count["handle"]) == [[1]]


def test_expand_aggregate_groups_without_materializing_second_hop(backend: Any) -> None:
    industry = backend.call(
        "entity_resolve",
        {"label": "Industry", "text": "educational technology", "as": "industry", "limit": 20},
    )
    companies = backend.call(
        "expand",
        {
            "from": industry["handle"],
            "source": "industry",
            "relationship_type": "operatesIn",
            "direction": "in",
            "target_label": "Company",
            "as": "company",
        },
    )
    result = backend.call(
        "expand_aggregate",
        {
            "from": companies["handle"],
            "source": "company",
            "relationship_type": "operatesIn",
            "direction": "out",
            "target_label": "Industry",
            "as": "industry",
            "group_by": [{"var": "industry", "property": "name", "alias": "industry"}],
            "metrics": [{"op": "count_distinct", "var": "company", "alias": "company_count"}],
            "limit": 100,
        },
    )
    rows = fetch_rows(backend, result["handle"], limit=100)

    assert result["matched_count"] == 13
    assert ["educational technology", 72] in rows
    assert ["software industry", 4] in rows
    assert ["information technology", 4] in rows


def test_multi_hop_query_groups_two_hop_result_server_side(backend: Any) -> None:
    result = backend.call(
        "multi_hop_query",
        {
            "start_label": "Country",
            "start_as": "country",
            "filters": [{"var": "country", "property": "name", "op": "eq", "value": "Canada"}],
            "hops": [
                {
                    "relationship_type": "basedIn",
                    "direction": "in",
                    "target_label": "Company",
                    "as": "company",
                },
                {
                    "relationship_type": "operatesIn",
                    "direction": "out",
                    "target_label": "Industry",
                    "as": "industry",
                },
            ],
            "group_by": [{"var": "industry", "property": "name", "alias": "industry"}],
            "metrics": [{"op": "count_distinct", "var": "company", "alias": "company_count"}],
            "limit": 1000,
        },
    )
    rows = fetch_rows(backend, result["handle"], limit=1000)

    software_rows = [row for row in rows if row[0] == "software industry"]
    assert software_rows
    assert software_rows[0][1] > 0
    assert result["matched_count"] >= 20


def test_pattern_query_defaults_to_final_entity_for_tool_chaining(backend: Any) -> None:
    result = backend.call(
        "pattern_query",
        {
            "start_label": "Company",
            "start_as": "company",
            "filters": [{"var": "company", "property": "name", "op": "eq", "value": "SpaceX"}],
            "hops": [
                {
                    "relationship_type": "hasCEO",
                    "direction": "out",
                    "target_label": "Person",
                    "as": "ceo",
                }
            ],
            "limit": 10,
        },
    )

    assert result["matched_count"] == 1
    handle = backend._handle(result["handle"])
    assert handle.focus == "ceo"
    assert handle.rows[0]["ceo"]["properties"]["name"] == "Elon Musk"


def test_pattern_query_returns_path_projection_server_side(backend: Any) -> None:
    result = backend.call(
        "pattern_query",
        {
            "start_label": "Company",
            "start_as": "company",
            "filters": [{"var": "company", "property": "name", "op": "eq", "value": "SpaceX"}],
            "hops": [
                {
                    "relationship_type": "hasCEO",
                    "direction": "out",
                    "target_label": "Person",
                    "as": "person",
                }
            ],
            "select": [{"var": "person", "property": "name", "alias": "name"}],
            "distinct": True,
            "limit": 100,
        },
    )

    assert result["matched_count"] == 1
    assert fetch_rows(backend, result["handle"]) == [["Elon Musk"]]


def test_relationship_uniqueness_clauses_enforce_pairwise_distinct_relationships() -> None:
    assert _relationship_uniqueness_clauses(["r0", "r1", "r2"]) == [
        "elementId(r0) <> elementId(r1)",
        "elementId(r0) <> elementId(r2)",
        "elementId(r1) <> elementId(r2)",
    ]


def test_pattern_query_does_not_reuse_same_relationship_across_hops(backend: Any) -> None:
    result = backend.call(
        "pattern_query",
        {
            "start_label": "Company",
            "start_as": "seed",
            "filters": [
                {"var": "seed", "property": "name", "op": "eq", "value": "Bardel Entertainment"}
            ],
            "hops": [
                {
                    "relationship_type": "operatesIn",
                    "direction": "out",
                    "target_label": "Industry",
                    "as": "industry",
                },
                {
                    "relationship_type": "operatesIn",
                    "direction": "in",
                    "target_label": "Company",
                    "as": "peer",
                },
            ],
            "select": [{"var": "peer", "property": "name", "alias": "company_name"}],
            "distinct": True,
            "limit": 1000,
        },
    )

    rows = backend._handle(result["handle"]).rows
    names = [row["company_name"] for row in rows]
    assert "Bardel Entertainment" not in names
    assert result["matched_count"] == 563
    assert len(rows) == 563
    assert names.count("Pathé") == 2


def test_pattern_query_supports_zero_hop_projection(backend: Any) -> None:
    result = backend.call(
        "pattern_query",
        {
            "start_label": "Industry",
            "start_as": "industry",
            "select": [{"var": "industry", "property": "name", "alias": "name"}],
            "distinct": True,
            "order_by": [{"field": "name", "direction": "asc"}],
            "limit": 1000,
        },
    )
    rows = fetch_rows(backend, result["handle"], limit=1000)

    assert result["matched_count"] >= 525
    assert rows == sorted(rows)


def test_constraint_query_finds_companies_by_related_node_property(backend: Any) -> None:
    result = backend.call(
        "constraint_query",
        {
            "find": {"label": "Company", "as": "company"},
            "where": [
                {
                    "relationship_type": "hasCEO",
                    "direction": "out",
                    "target_label": "Person",
                    "property": "name",
                    "op": "eq",
                    "value": "Elon Musk",
                }
            ],
            "return_mode": "names",
            "limit": 20,
        },
    )
    rows = fetch_rows(backend, result["handle"], limit=20)

    assert ["SpaceX"] in rows


def test_constraint_query_supports_multiple_and_constraints_and_count(backend: Any) -> None:
    names = backend.call(
        "constraint_query",
        {
            "find": {"label": "Company", "as": "company"},
            "where": [
                {
                    "relationship_type": "hasCEO",
                    "direction": "out",
                    "target_label": "Person",
                    "property": "name",
                    "op": "eq",
                    "value": "Elon Musk",
                },
                {
                    "relationship_type": "basedIn",
                    "direction": "out",
                    "target_label": "Country",
                    "property": "name",
                    "op": "eq",
                    "value": "United States of America",
                },
            ],
            "return_mode": "names",
            "limit": 100,
        },
    )
    count = backend.call(
        "constraint_query",
        {
            "find": {"label": "Company", "as": "company"},
            "where": [
                {
                    "relationship_type": "hasCEO",
                    "direction": "out",
                    "target_label": "Person",
                    "property": "name",
                    "op": "eq",
                    "value": "Elon Musk",
                },
                {
                    "relationship_type": "basedIn",
                    "direction": "out",
                    "target_label": "Country",
                    "property": "name",
                    "op": "eq",
                    "value": "United States of America",
                },
            ],
            "return_mode": "count",
            "alias": "company_count",
        },
    )

    name_rows = fetch_rows(backend, names["handle"], limit=100)
    assert ["SpaceX"] in name_rows
    assert fetch_rows(backend, count["handle"]) == [[len({row[0] for row in name_rows})]]


def test_constraint_query_finds_company_with_two_named_related_constraints(backend: Any) -> None:
    result = backend.call(
        "constraint_query",
        {
            "find": {"label": "Company", "as": "company"},
            "where": [
                {
                    "relationship_type": "subsidiaryOf",
                    "direction": "out",
                    "target_label": "Company",
                    "target_as": "parent",
                    "property": "name",
                    "op": "eq",
                    "value": "Meta Platforms",
                },
                {
                    "relationship_type": "operatesIn",
                    "direction": "out",
                    "target_label": "Industry",
                    "target_as": "industry",
                    "property": "name",
                    "op": "eq",
                    "value": "video game industry",
                },
            ],
            "return_mode": "names",
            "limit": 1000,
        },
    )

    assert fetch_rows(backend, result["handle"]) == [["Beat Games"]]


def test_constraint_query_returns_requested_candidate_property(backend: Any) -> None:
    result = backend.call(
        "constraint_query",
        {
            "find": {"label": "Company", "as": "company"},
            "where": [
                {
                    "relationship_type": "subsidiaryOf",
                    "direction": "out",
                    "target_label": "Company",
                    "target_as": "parent",
                    "property": "name",
                    "op": "eq",
                    "value": "Interscope Records",
                },
                {
                    "relationship_type": "foundedBy",
                    "direction": "out",
                    "target_label": "Person",
                    "target_as": "founder",
                    "property": "name",
                    "op": "eq",
                    "value": "Vincent Herbert",
                },
            ],
            "return_mode": "names",
            "return_properties": [{"property": "launch_year", "alias": "launch_year"}],
            "limit": 1000,
        },
    )

    assert fetch_rows(backend, result["handle"]) == [["Streamline Records", 2007]]


def test_constraint_query_rejects_invalid_schema_direction(backend: Any) -> None:
    with pytest.raises(ValueError, match="Relationship pattern is not in schema"):
        backend.call(
            "constraint_query",
            {
                "find": {"label": "Company", "as": "company"},
                "where": [
                    {
                        "relationship_type": "hasCEO",
                        "direction": "in",
                        "target_label": "Person",
                        "property": "name",
                        "op": "eq",
                        "value": "Elon Musk",
                    }
                ],
                "return_mode": "names",
            },
        )


def test_pattern_query_drops_unsafe_distinct_property_ordering(backend: Any) -> None:
    result = backend.call(
        "pattern_query",
        {
            "start_label": "Company",
            "start_as": "company",
            "hops": [
                {
                    "relationship_type": "subsidiaryOf",
                    "direction": "out",
                    "target_label": "Company",
                    "as": "parent",
                }
            ],
            "select": [{"var": "company", "property": "name", "alias": "name"}],
            "distinct": True,
            "order_by": [{"var": "company", "property": "launch_year", "direction": "desc"}],
            "limit": 5,
        },
    )

    assert result["matched_count"] == 5
    assert len(fetch_rows(backend, result["handle"])) == 5


def test_top_entities_by_property_finds_youngest_board_member(backend: Any) -> None:
    result = backend.call(
        "top_entities_by_property",
        {
            "start_label": "Company",
            "start_as": "company",
            "hops": [
                {
                    "relationship_type": "hasBoardMember",
                    "direction": "out",
                    "target_label": "Person",
                    "as": "person",
                }
            ],
            "target": "person",
            "property": "date_of_birth",
            "order": "desc",
            "limit": 1,
        },
    )

    rows = fetch_rows(backend, result["handle"])
    assert rows == [["Wayne J. Riley"]]
    assert result["preview"][0] == {"name": rows[0][0]}
    assert result["ranking"]["property"] == "date_of_birth"


def test_project_accepts_property_order_by_shape(backend: Any) -> None:
    company = backend.call(
        "node_search",
        {"label": "Company", "property": "name", "value": "Cisco", "as": "company"},
    )
    board = backend.call(
        "expand",
        {
            "from": company["handle"],
            "source": "company",
            "relationship_type": "hasBoardMember",
            "direction": "out",
            "target_label": "Person",
            "as": "person",
        },
    )
    projected = backend.call(
        "project",
        {
            "from": board["handle"],
            "select": [{"var": "person", "property": "name", "alias": "name"}],
            "distinct": True,
            "order_by": [{"var": "person", "property": "name", "direction": "asc"}],
            "limit": 5,
        },
    )

    rows = fetch_rows(backend, projected["handle"])
    assert len(rows) == 5
    assert rows == sorted(rows)


def test_entity_set_operation_reports_scalar_handles_clearly(backend: Any) -> None:
    company = backend.call(
        "node_search",
        {"label": "Company", "property": "name", "value": "Cisco", "as": "company"},
    )
    projected = backend.call(
        "project",
        {
            "from": company["handle"],
            "select": [{"var": "company", "property": "name", "alias": "name"}],
        },
    )

    with pytest.raises(ValueError, match="[Aa]vailable entity variables"):
        backend.call(
            "entity_set_operation",
            {
                "op": "union",
                "operands": [
                    {"handle": projected["handle"], "var": "name"},
                    {"handle": projected["handle"], "var": "name"},
                ],
                "as": "company",
            },
        )


def test_entity_set_operation_reports_missing_entity_variable_hint(backend: Any) -> None:
    company = backend.call(
        "node_search",
        {"label": "Company", "property": "name", "value": "Cisco", "as": "company"},
    )
    projected = backend.call(
        "project",
        {
            "from": company["handle"],
            "select": [{"var": "company", "property": "name", "alias": "company_name"}],
            "keep_entities": True,
        },
    )

    with pytest.raises(ValueError, match="[Aa]vailable entity variables: \\['company'\\]"):
        backend.call(
            "entity_set_operation",
            {
                "op": "union",
                "operands": [
                    {"handle": projected["handle"], "var": "company_name"},
                    {"handle": projected["handle"], "var": "company"},
                ],
                "as": "company",
            },
        )


def test_entity_set_operation_rejects_large_materialized_operands(
    schema: dict[str, Any],
) -> None:
    backend, _driver = _fake_backend(schema)
    rows = [
        {
            "company": {
                "labels": ["Company", "Entity"],
                "properties": {"id": f"company-{index}", "name": f"Company {index}"},
            }
        }
        for index in range(10001)
    ]
    left = backend._store(rows, focus="company")
    right = backend._store(rows[:1], focus="company")

    with pytest.raises(ValueError, match="very large materialized handles"):
        backend.call(
            "entity_set_operation",
            {
                "op": "union",
                "operands": [
                    {"handle": left["handle"], "var": "company"},
                    {"handle": right["handle"], "var": "company"},
                ],
                "as": "company",
            },
        )


def test_group_count_by_pattern_rejects_unknown_filter_variable_before_cypher(backend: Any) -> None:
    with pytest.raises(ValueError, match="Filter references unknown variable"):
        backend.call(
            "group_count_by_pattern",
            {
                "start_label": "Company",
                "start_as": "company",
                "filters": [
                    {
                        "var": "missing_company",
                        "property": "name",
                        "op": "eq",
                        "value": "Viacom",
                    }
                ],
                "hops": [
                    {
                        "relationship_type": "operatesIn",
                        "direction": "out",
                        "target_label": "Industry",
                        "as": "industry",
                    }
                ],
                "group_by": [{"var": "industry", "property": "name", "alias": "industry"}],
                "count_var": "company",
                "alias": "company_count",
            },
        )


def test_group_count_by_pattern_rejects_unknown_count_variable_before_cypher(backend: Any) -> None:
    with pytest.raises(ValueError, match="Metric/count references unknown variable"):
        backend.call(
            "group_count_by_pattern",
            {
                "start_label": "Company",
                "start_as": "company",
                "hops": [
                    {
                        "relationship_type": "subsidiaryOf",
                        "direction": "out",
                        "target_label": "Company",
                        "as": "parent",
                    }
                ],
                "group_by": [{"var": "parent", "property": "name", "alias": "parent"}],
                "count_var": "sub",
                "alias": "sub_count",
            },
        )


def test_optional_expand_count_preserves_zero_count_sources(backend: Any) -> None:
    sumner = backend.call(
        "entity_resolve",
        {"label": "Person", "text": "Sumner Redstone", "as": "person", "limit": 1},
    )
    ralph = backend.call(
        "entity_resolve",
        {"label": "Person", "text": "Ralph Baruch", "as": "person", "limit": 1},
    )
    source = backend._store(
        [
            {"person": backend._handle(sumner["handle"]).rows[0]["person"], "__rel_ids": []},
            {"person": backend._handle(ralph["handle"]).rows[0]["person"], "__rel_ids": []},
        ],
        focus="person",
    )

    result = backend.call(
        "optional_expand_count",
        {
            "from": source["handle"],
            "source": "person",
            "relationship_type": "hasCEO",
            "direction": "in",
            "target_label": "Company",
            "group_by": [{"var": "person", "property": "name", "alias": "name"}],
            "alias": "num",
            "distinct": True,
        },
    )

    assert sorted(fetch_rows(backend, result["handle"])) == [
        ["Ralph Baruch", 0],
        ["Sumner Redstone", 1],
    ]


def test_pattern_query_default_entities_feed_optional_expand_count(backend: Any) -> None:
    founders = backend.call(
        "pattern_query",
        {
            "start_label": "Company",
            "start_as": "company",
            "filters": [{"var": "company", "property": "name", "op": "eq", "value": "Viacom"}],
            "hops": [
                {
                    "relationship_type": "foundedBy",
                    "direction": "out",
                    "target_label": "Person",
                    "as": "founder",
                }
            ],
            "limit": 1000,
        },
    )
    result = backend.call(
        "optional_expand_count",
        {
            "from": founders["handle"],
            "source": "founder",
            "relationship_type": "hasCEO",
            "direction": "in",
            "target_label": "Company",
            "group_by": [{"var": "founder", "property": "name", "alias": "founder_name"}],
            "alias": "ceo_company_count",
            "distinct": True,
        },
    )

    assert sorted(fetch_rows(backend, result["handle"])) == [
        ["Ralph Baruch", 0],
        ["Sumner Redstone", 1],
    ]


def test_optional_count_by_pattern_preserves_viacom_founders_without_ceo_roles(
    backend: Any,
) -> None:
    result = backend.call(
        "optional_count_by_pattern",
        {
            "start_label": "Company",
            "start_as": "company",
            "filters": [{"var": "company", "property": "name", "op": "eq", "value": "Viacom"}],
            "hops": [
                {
                    "relationship_type": "foundedBy",
                    "direction": "out",
                    "target_label": "Person",
                    "as": "founder",
                }
            ],
            "source": "founder",
            "optional_relationship": {
                "relationship_type": "hasCEO",
                "direction": "in",
                "target_label": "Company",
                "as": "ceo_company",
            },
            "group_by": [{"var": "founder", "property": "name", "alias": "founder_name"}],
            "alias": "ceo_company_count",
            "order_by": [{"field": "founder_name", "direction": "asc"}],
            "limit": 1000,
        },
    )

    assert fetch_rows(backend, result["handle"]) == [
        ["Ralph Baruch", 0],
        ["Sumner Redstone", 1],
    ]


def test_optional_count_by_pattern_reports_missing_optional_relationship(
    schema: dict[str, Any],
) -> None:
    backend, _driver = _fake_backend(schema)

    with pytest.raises(ValueError, match="requires optional_relationship"):
        backend.call(
            "optional_count_by_pattern",
            {
                "start_label": "Person",
                "start_as": "person",
                "hops": [
                    {
                        "relationship_type": "hasBoardMember",
                        "direction": "in",
                        "target_label": "Company",
                        "as": "company",
                    }
                ],
                "group_by": [{"var": "person", "property": "name", "alias": "name"}],
            },
        )


def test_optional_count_by_pattern_infers_source_from_group_by_entity(
    backend: Any,
) -> None:
    result = backend.call(
        "optional_count_by_pattern",
        {
            "start_label": "Company",
            "start_as": "company",
            "filters": [
                {"var": "board_member", "property": "name", "op": "eq", "value": "Amy Chang"}
            ],
            "hops": [
                {
                    "relationship_type": "hasBoardMember",
                    "direction": "out",
                    "target_label": "Person",
                    "as": "board_member",
                }
            ],
            "optional_relationship": {
                "relationship_type": "operatesIn",
                "direction": "out",
                "target_label": "Industry",
                "as": "industry",
            },
            "group_by": [{"var": "company", "property": "name", "alias": "company_name"}],
            "metrics": [{"op": "count_distinct", "var": "industry", "alias": "industry_count"}],
            "order_by": [{"field": "company_name", "direction": "asc"}],
            "limit": 1000,
        },
    )

    assert fetch_rows(backend, result["handle"]) == [
        ["Procter & Gamble", 1],
        ["The Walt Disney Company", 6],
    ]


def test_optional_count_by_pattern_preserves_liberty_media_subsidiaries_without_board_members(
    backend: Any,
) -> None:
    result = backend.call(
        "optional_count_by_pattern",
        {
            "start_label": "Company",
            "start_as": "parent",
            "filters": [
                {"var": "parent", "property": "name", "op": "eq", "value": "Liberty Media"}
            ],
            "hops": [
                {
                    "relationship_type": "subsidiaryOf",
                    "direction": "in",
                    "target_label": "Company",
                    "as": "subsidiary",
                }
            ],
            "source": "subsidiary",
            "optional_relationship": {
                "relationship_type": "hasBoardMember",
                "direction": "out",
                "target_label": "Person",
                "as": "board_member",
            },
            "group_by": [{"var": "subsidiary", "property": "name", "alias": "subsidiary_name"}],
            "alias": "board_member_count",
            "order_by": [{"field": "subsidiary_name", "direction": "asc"}],
            "limit": 1000,
        },
    )

    assert fetch_rows(backend, result["handle"]) == [
        ["1-800-FREE-411", 0],
        ["Discovery Holding Company", 0],
        ["Expedia Group", 1],
        ["Formula One Group", 0],
    ]


def test_optional_count_by_pattern_counts_optional_relationships_per_grouped_subsidiary(
    backend: Any,
) -> None:
    result = backend.call(
        "optional_count_by_pattern",
        {
            "start_label": "Company",
            "start_as": "company",
            "filters": [
                {"var": "parent", "property": "name", "op": "eq", "value": "Volkswagen Group"}
            ],
            "hops": [
                {
                    "relationship_type": "subsidiaryOf",
                    "direction": "out",
                    "target_label": "Company",
                    "as": "parent",
                }
            ],
            "optional_relationship": {
                "relationship_type": "hasCEO",
                "direction": "out",
                "target_label": "Person",
                "as": "ceo",
            },
            "group_by": [{"var": "company", "property": "name", "alias": "company_name"}],
            "metrics": [{"op": "count_distinct", "var": "ceo", "alias": "ceo_count"}],
            "order_by": [{"field": "company_name", "direction": "asc"}],
            "limit": 1000,
        },
    )

    rows = fetch_rows(backend, result["handle"], limit=1000)
    assert ["Audi AG", 6] in rows
    assert ["SEAT", 1] in rows
    assert ["MOIA", 0] in rows
    assert ["Volkswagen Group", 12] not in rows
    assert all(row[1] != 12 for row in rows)


def test_relationship_query_reports_missing_target_label_as_contract_error(backend: Any) -> None:
    with pytest.raises(ValueError, match="requires target_label"):
        backend.call(
            "relationship_query",
            {
                "source_label": "Industry",
                "source_as": "industry",
                "relationship_type": "operatesIn",
            },
        )


def test_filter_ignores_scalar_rows_instead_of_crashing(backend: Any) -> None:
    company = backend.call(
        "node_search",
        {"label": "Company", "property": "name", "value": "Cisco", "as": "company"},
    )
    projected = backend.call(
        "project",
        {
            "from": company["handle"],
            "select": [{"var": "company", "property": "name", "alias": "name"}],
        },
    )
    filtered = backend.call(
        "filter",
        {
            "from": projected["handle"],
            "var": "name",
            "property": "name",
            "op": "neq",
            "value": "Cisco",
        },
    )

    assert filtered["matched_count"] == 0


def test_filter_coerces_integer_value_type_for_in_memory_predicates(backend: Any) -> None:
    backend._handles["h_integer_filter"] = Handle(
        id="h_integer_filter",
        rows=[
            {
                "company": {
                    "labels": ["Company"],
                    "properties": {
                        "id": "company-1",
                        "name": "Modern Public Relations",
                        "launch_year": 1930,
                    },
                }
            }
        ],
        focus="company",
    )

    filtered = backend.call(
        "filter",
        {
            "from": "h_integer_filter",
            "var": "company",
            "property": "launch_year",
            "op": "gt",
            "value": "1927",
            "value_type": "integer",
        },
    )

    assert filtered["matched_count"] == 1


def test_group_count_by_pattern_groups_without_materializing_rows(backend: Any) -> None:
    result = backend.call(
        "group_count_by_pattern",
        {
            "start_label": "Country",
            "start_as": "country",
            "filters": [{"var": "country", "property": "name", "op": "eq", "value": "Canada"}],
            "hops": [
                {
                    "relationship_type": "basedIn",
                    "direction": "in",
                    "target_label": "Company",
                    "as": "company",
                },
                {
                    "relationship_type": "operatesIn",
                    "direction": "out",
                    "target_label": "Industry",
                    "as": "industry",
                },
            ],
            "group_by": [{"var": "industry", "property": "name", "alias": "industry"}],
            "count_var": "company",
            "alias": "company_count",
            "distinct": True,
            "limit": 1000,
        },
    )
    rows = fetch_rows(backend, result["handle"], limit=1000)

    software_rows = [row for row in rows if row[0] == "software industry"]
    assert software_rows
    assert software_rows[0][1] > 0
    assert result["matched_count"] >= 20


def test_group_count_by_pattern_rewrites_unknown_order_alias_to_metric(backend: Any) -> None:
    result = backend.call(
        "group_count_by_pattern",
        {
            "start_label": "Country",
            "start_as": "country",
            "filters": [{"var": "country", "property": "name", "op": "eq", "value": "Canada"}],
            "hops": [
                {
                    "relationship_type": "basedIn",
                    "direction": "in",
                    "target_label": "Company",
                    "as": "company",
                },
                {
                    "relationship_type": "operatesIn",
                    "direction": "out",
                    "target_label": "Industry",
                    "as": "industry",
                },
            ],
            "group_by": [{"var": "industry", "property": "name", "alias": "industry"}],
            "count_var": "company",
            "alias": "company_count",
            "order_by": [{"field": "invented_count_alias", "direction": "desc"}],
            "limit": 5,
        },
    )
    rows = fetch_rows(backend, result["handle"])

    assert len(rows) == 5
    assert [row[1] for row in rows] == sorted([row[1] for row in rows], reverse=True)


def test_filter_project_aggregate_and_fetch_pagination(backend: Any) -> None:
    cisco = backend.call(
        "node_search",
        {"label": "Company", "property": "name", "value": "Cisco", "as": "company"},
    )
    board = backend.call(
        "expand",
        {
            "from": cisco["handle"],
            "source": "company",
            "relationship_type": "hasBoardMember",
            "direction": "out",
            "target_label": "Person",
            "as": "person",
        },
    )
    assert board["matched_count"] == 12

    first_page = backend.call("fetch", {"from": board["handle"], "limit": 5, "offset": 0})
    second_page = backend.call("fetch", {"from": board["handle"], "limit": 5, "offset": 5})
    last_page = backend.call("fetch", {"from": board["handle"], "limit": 5, "offset": 10})
    assert first_page["returned_count"] == 5
    assert first_page["next_offset"] == 5
    assert first_page["truncated"] is True
    assert second_page["returned_count"] == 5
    assert second_page["next_offset"] == 10
    assert last_page["returned_count"] == 2
    assert last_page["next_offset"] is None
    assert last_page["truncated"] is False

    filtered = backend.call(
        "filter",
        {
            "from": board["handle"],
            "var": "person",
            "property": "date_of_birth",
            "op": "is_not_null",
        },
    )
    projected = backend.call(
        "project",
        {
            "from": filtered["handle"],
            "select": [{"var": "person", "property": "name", "alias": "name"}],
            "distinct": True,
            "order_by": [{"field": "name", "direction": "asc"}],
            "limit": 5,
        },
    )
    grouped = backend.call(
        "aggregate",
        {
            "from": board["handle"],
            "group_by": [{"var": "person", "property": "gender", "alias": "gender"}],
            "metrics": [{"op": "count_distinct", "var": "person", "alias": "people"}],
        },
    )

    assert fetch_rows(backend, projected["handle"]) == [
        ["Brent Saunders"],
        ["Lisa Su"],
        ["Michael Capellas"],
    ]
    assert sorted(fetch_rows(backend, grouped["handle"])) == [["female", 5], ["male", 7]]


def test_same_target_role_intersection_returns_people_with_two_roles(backend: Any) -> None:
    result = backend.call(
        "same_target_role_intersection",
        {
            "source_label": "Person",
            "source_as": "person",
            "target_label": "Company",
            "target_as": "company",
            "relationships": [
                {"relationship_type": "foundedBy", "direction": "in"},
                {"relationship_type": "hasCEO", "direction": "in"},
            ],
            "select": [{"var": "person", "property": "name", "alias": "name"}],
            "distinct": True,
            "limit": 5,
        },
    )

    assert fetch_rows(backend, result["handle"]) == [
        ["Tim Morten"],
        ["Wilhelm Wassermann-Glaettli"],
        ["Isona Passola i Vidal"],
        ["LockPickingLawyer"],
        ["Donald Sussman"],
    ]


def test_optional_numeric_and_boolean_nulls_use_tool_defaults(backend: Any) -> None:
    result = backend.call(
        "same_target_role_intersection",
        {
            "source_label": "Person",
            "source_as": "person",
            "target_label": "Company",
            "target_as": "company",
            "relationships": [
                {"relationship_type": "foundedBy", "direction": "in"},
                {"relationship_type": "hasCEO", "direction": "in"},
            ],
            "select": [{"var": "person", "property": "name", "alias": "name"}],
            "distinct": None,
            "limit": None,
        },
    )

    rows = fetch_rows(backend, result["handle"], limit=5)
    assert rows == [
        ["Tim Morten"],
        ["Wilhelm Wassermann-Glaettli"],
        ["Isona Passola i Vidal"],
        ["LockPickingLawyer"],
        ["Donald Sussman"],
    ]


def test_same_target_role_intersection_normalizes_list_property_filters(backend: Any) -> None:
    result = backend.call(
        "same_target_role_intersection",
        {
            "source_label": "Person",
            "source_as": "person",
            "target_label": "Company",
            "target_as": "company",
            "relationships": [
                {"relationship_type": "foundedBy", "direction": "in"},
                {"relationship_type": "hasBoardMember", "direction": "in"},
            ],
            "filters": [
                {
                    "var": "person",
                    "property": "country_of_citizenship",
                    "op": "neq",
                    "value": "Austria",
                }
            ],
            "select": [{"var": "person", "property": "name", "alias": "name"}],
            "distinct": True,
            "limit": 1000,
        },
    )

    rows = fetch_rows(backend, result["handle"], limit=1000)
    equivalent = backend.call(
        "same_target_role_intersection",
        {
            "source_label": "Person",
            "source_as": "person",
            "target_label": "Company",
            "target_as": "company",
            "relationships": [
                {"relationship_type": "foundedBy", "direction": "in"},
                {"relationship_type": "hasBoardMember", "direction": "in"},
            ],
            "filters": [
                {
                    "var": "person",
                    "property": "country_of_citizenship",
                    "op": "not_in",
                    "value": "Austria",
                }
            ],
            "select": [{"var": "person", "property": "name", "alias": "name"}],
            "distinct": True,
            "limit": 1000,
        },
    )

    assert rows
    assert rows == fetch_rows(backend, equivalent["handle"], limit=1000)
    assert ["Georg Hotar"] not in rows


def test_project_explodes_country_of_citizenship_for_ceo_founders(backend: Any) -> None:
    people = backend.call(
        "same_target_role_intersection",
        {
            "source_label": "Person",
            "source_as": "person",
            "target_label": "Company",
            "target_as": "company",
            "relationships": [
                {"relationship_type": "hasCEO", "direction": "in"},
                {"relationship_type": "foundedBy", "direction": "in"},
            ],
            "limit": 5000,
        },
    )

    countries = backend.call(
        "project",
        {
            "from": people["handle"],
            "select": [
                {
                    "var": "person",
                    "property": "country_of_citizenship",
                    "alias": "country",
                    "explode": True,
                }
            ],
            "distinct": True,
            "limit": 200,
        },
    )
    fetched = backend.call("fetch", {"from": countries["handle"], "limit": 200})
    rows = fetched["rows"]

    assert fetched["returned_count"] == 89
    assert ["United States of America"] in rows
    assert all(not isinstance(row[0], list) for row in rows)


def test_same_target_role_intersection_explodes_selected_list_property(backend: Any) -> None:
    countries = backend.call(
        "same_target_role_intersection",
        {
            "source_label": "Person",
            "source_as": "person",
            "target_label": "Company",
            "target_as": "company",
            "relationships": [
                {"relationship_type": "hasCEO", "direction": "in"},
                {"relationship_type": "foundedBy", "direction": "in"},
            ],
            "select": [
                {
                    "var": "person",
                    "property": "country_of_citizenship",
                    "alias": "country",
                    "explode": True,
                }
            ],
            "distinct": True,
            "limit": 5000,
        },
    )
    fetched = backend.call("fetch", {"from": countries["handle"], "limit": 200})
    rows = fetched["rows"]

    assert fetched["returned_count"] == 89
    assert ["United States of America"] in rows
    assert all(not isinstance(row[0], list) for row in rows)


def test_shared_role_aggregate_counts_companies_sharing_board_members(backend: Any) -> None:
    result = backend.call(
        "shared_role_aggregate",
        {
            "seed_label": "Company",
            "seed_as": "seed_company",
            "seed_filters": [
                {"var": "seed_company", "property": "name", "op": "eq", "value": "Boeing"}
            ],
            "shared_label": "Person",
            "shared_as": "shared_member",
            "seed_relationship": {"relationship_type": "hasBoardMember", "direction": "out"},
            "peer_label": "Company",
            "peer_as": "peer_company",
            "peer_relationship": {"relationship_type": "hasBoardMember", "direction": "out"},
            "exclude_seed": True,
            "group_by": [{"var": "peer_company", "property": "name", "alias": "company"}],
            "metrics": [
                {"op": "count_distinct", "var": "shared_member", "alias": "shared_members"}
            ],
            "order_by": [{"field": "company", "direction": "asc"}],
            "limit": 20,
        },
    )

    assert fetch_rows(backend, result["handle"], limit=20) == [
        ["Cardinal Health", 1],
        ["Caterpillar Inc.", 1],
        ["ExxonMobil", 1],
        ["Johnson & Johnson", 1],
    ]


def test_shared_role_aggregate_counts_ceos_sharing_norman_welsh_companies(backend: Any) -> None:
    result = backend.call(
        "shared_role_aggregate",
        {
            "seed_label": "Person",
            "seed_as": "seed_person",
            "seed_filters": [
                {"var": "seed_person", "property": "name", "op": "eq", "value": "Norman Welsh"}
            ],
            "shared_label": "Company",
            "shared_as": "company",
            "seed_relationship": {"relationship_type": "hasCEO", "direction": "in"},
            "peer_label": "Person",
            "peer_as": "peer_person",
            "peer_relationship": {"relationship_type": "hasCEO", "direction": "in"},
            "exclude_seed": True,
            "group_by": [{"var": "peer_person", "property": "name", "alias": "name"}],
            "metrics": [{"op": "count_distinct", "var": "company", "alias": "num"}],
            "order_by": [{"field": "name", "direction": "asc"}],
            "limit": 20,
        },
    )

    assert fetch_rows(backend, result["handle"], limit=20) == [
        ["Gregor Bigalke", 1],
        ["Maximilian Arzberger", 1],
    ]


def test_shared_role_aggregate_distincts_entities_before_projecting_names(backend: Any) -> None:
    result = backend.call(
        "shared_role_aggregate",
        {
            "seed_label": "Company",
            "seed_as": "seed",
            "seed_filters": [
                {"var": "seed", "property": "name", "op": "eq", "value": "Bardel Entertainment"}
            ],
            "shared_label": "Industry",
            "shared_as": "industry",
            "seed_relationship": {"relationship_type": "operatesIn", "direction": "out"},
            "peer_label": "Company",
            "peer_as": "peer",
            "peer_relationship": {"relationship_type": "operatesIn", "direction": "out"},
            "exclude_seed": True,
            "select": [{"var": "peer", "property": "name", "alias": "company_name"}],
            "distinct": True,
            "limit": 1000,
        },
    )

    fetch_result = backend.call("fetch", {"from": result["handle"], "limit": 1000})
    rows = backend.last_fetch
    names = [row[0] for row in rows]
    assert fetch_result["returned_count"] == 563
    assert len(rows) == 563
    assert names.count("Pathé") == 2


def test_filter_same_node_keeps_rows_where_two_vars_reference_same_node(backend: Any) -> None:
    spacex = backend.call(
        "node_search",
        {"label": "Company", "property": "name", "value": "SpaceX", "as": "company"},
    )
    lacie = backend.call(
        "node_search",
        {"label": "Company", "property": "name", "value": "LaCie", "as": "company"},
    )
    spacex_payload = backend._handle(spacex["handle"]).rows[0]["company"]
    lacie_payload = backend._handle(lacie["handle"]).rows[0]["company"]
    handle = backend._store(
        [
            {"left": spacex_payload, "right": spacex_payload},
            {"left": spacex_payload, "right": lacie_payload},
        ],
        focus="left",
    )

    result = backend.call(
        "filter_same_node",
        {"from": handle["handle"], "left_var": "left", "right_var": "right"},
    )

    assert result["matched_count"] == 1
    assert result["preview"] == ["SpaceX"]


def test_join_handles_matches_nodes_across_two_handles(backend: Any) -> None:
    spacex_left = backend.call(
        "node_search",
        {"label": "Company", "property": "name", "value": "SpaceX", "as": "left_company"},
    )
    spacex_right = backend.call(
        "node_search",
        {"label": "Company", "property": "name", "value": "SpaceX", "as": "right_company"},
    )
    result = backend.call(
        "join_handles",
        {
            "left": spacex_left["handle"],
            "right": spacex_right["handle"],
            "left_var": "left_company",
            "right_var": "right_company",
            "op": "inner",
            "as": "company",
        },
    )

    assert result["matched_count"] == 1
    assert result["preview"] == ["SpaceX"]


def test_entity_set_operation_intersects_entity_handles(backend: Any) -> None:
    cch = backend.call(
        "node_search",
        {"label": "Company", "property": "name", "value": "CCH", "as": "cch"},
    )
    adobe = backend.call(
        "node_search",
        {"label": "Company", "property": "name", "value": "Adobe", "as": "adobe"},
    )
    cch_industries = backend.call(
        "expand",
        {
            "from": cch["handle"],
            "source": "cch",
            "relationship_type": "operatesIn",
            "direction": "out",
            "target_label": "Industry",
            "as": "industry_cch",
        },
    )
    adobe_industries = backend.call(
        "expand",
        {
            "from": adobe["handle"],
            "source": "adobe",
            "relationship_type": "operatesIn",
            "direction": "out",
            "target_label": "Industry",
            "as": "industry_adobe",
        },
    )
    result = backend.call(
        "entity_set_operation",
        {
            "op": "intersect",
            "operands": [
                {"handle": cch_industries["handle"], "var": "industry_cch"},
                {"handle": adobe_industries["handle"], "var": "industry_adobe"},
            ],
            "as": "industry",
        },
    )

    assert fetch_rows(backend, result["handle"]) == [["software industry"]]
