"""Neo4j schema and graph-discovery runtime helpers."""

from typing import Annotated, Any

from agent_native_graph.core.graph_utils import (
    _inferred_type,
    _int_arg,
    _is_lookup_property,
    _operators_for_property,
    _properties_by_label,
    _properties_by_relationship,
    _relationship_affordance,
    _safe_name,
    _safe_start_score,
    _schema_paths,
    _temporal_relationship_affordances,
    _token_variants,
    _tokens,
    _tool_value,
    _top_schema_matches,
)
from agent_native_graph.core.tooling import ToolParam


def schema_inspect(backend) -> dict[str, Any]:
    return {"schema": backend._schema_get(), "affordance": backend._schema_affordance()}


def schema_overview(backend) -> dict[str, Any]:
    affordance = backend._schema_affordance()
    schema = backend._schema_get()
    if getattr(backend, "_schema_entry", "overview") in {
        "overview_light",
        "overview_light_expand_first",
    }:
        return {
            "labels": [
                {
                    "label": item["label"],
                    "count": item.get("count"),
                    "lookup_properties": item.get("lookup_properties", []),
                }
                for item in affordance["labels"]
            ],
            "relationship_types": schema["relationship_types"],
            "relationship_patterns_sample": schema["relationship_patterns"][:12],
            "safe_start_points": affordance["safe_start_points"][:8],
            "next_actions": [
                {
                    "when": "Need exact schema names for question words or synonyms",
                    "tool": "schema_search",
                    "args": {"query": "<keywords from the question>"},
                },
                {
                    "when": "Need properties/examples for one label",
                    "tool": "schema_describe_label",
                    "args": {"label": "<label from labels>"},
                },
                {
                    "when": "Need direction/properties for one relationship",
                    "tool": "schema_describe_relationship",
                    "args": {"relationship_type": "<relationship_type>"},
                },
            ],
            "planning_hints": [
                "This is a lightweight overview; do not infer path directions from it alone.",
                "Use schema_search to map question words to exact schema names.",
                "Use schema_describe_relationship before traversing a relationship.",
                "Use schema_describe_label before filtering/projecting properties.",
            ],
        }
    label_summaries = [
        {
            "label": item["label"],
            "count": item.get("count"),
            "lookup_properties": item.get("lookup_properties", []),
            "property_names": [prop["name"] for prop in item.get("properties", [])],
            "safe_start_score": item.get("safe_start_score"),
        }
        for item in affordance["labels"]
    ]
    return {
        "labels": label_summaries,
        "relationship_types": schema["relationship_types"],
        "relationship_patterns": schema["relationship_patterns"],
        "relationship_navigation": [
            {
                "relationship_type": item["relationship_type"],
                "pattern": item["pattern"],
                "direction_rule": item["direction_rule"],
                "semantic_direction_examples": item["semantic_direction_examples"],
                "forward_expand": item["forward_expand"],
                "reverse_expand": item["reverse_expand"],
            }
            for item in affordance["relationship_traversals"]
        ],
        "safe_start_points": affordance["safe_start_points"],
        "temporal_relationships": affordance["temporal_relationships"],
        "set_operation_patterns": affordance["set_operation_patterns"],
        "next_actions": [
            {
                "when": "Need exact schema names for question words or synonyms",
                "tool": "schema_search",
                "args": {"query": "<keywords from the question>"},
            },
            {
                "when": "Need to filter/project properties for one label",
                "tool": "schema_describe_label",
                "args": {"label": "<label from labels>"},
            },
            {
                "when": "Need to traverse one relationship or apply temporal relationship filters",
                "tool": "schema_describe_relationship",
                "args": {"relationship_type": "<relationship_type>"},
            },
        ],
        "planning_hints": [
            "Use schema_search(query) to find likely labels, relationships, and properties for the question.",
            "Use schema_describe_label(label) before filtering/projecting properties for that label.",
            "Use schema_describe_relationship(type) before choosing hop direction or relationship filters.",
            "Copy forward_expand/reverse_expand instead of inventing relationship directions.",
            "Use inspect_paths when multiple relationship directions or multi-hop paths are possible.",
            "For grouped counts, build the entity handle first and then call group_handle.",
            "For optional zero-count grouped counts, build source entities first and call optional_expand_count.",
            "Use shared_role_aggregate only for peer-through-shared-node questions: seed -> shared <- peer.",
            "Use same_target_role_intersection when one entity must satisfy multiple roles against the same target.",
        ],
    }


def schema_search(
    backend,
    query: Annotated[
        str,
        ToolParam("Concise keywords from the question, e.g. 'company founder board member'."),
    ],
    limit: Annotated[
        int | None,
        ToolParam("Maximum candidates per section. Default: 8, max: 25.", required=False),
    ] = None,
) -> dict[str, Any]:
    args = {"query": query, "limit": limit}
    query = str(query or "")
    limit = _int_arg(args, "limit", 8, min_value=1, max_value=25)
    tokens = set(_tokens(query))
    if not tokens:
        return {
            "query": query,
            "labels": [],
            "relationships": [],
            "node_properties": [],
            "relationship_properties": [],
        }

    affordance = backend._schema_affordance()
    label_rows = [
        (backend._schema_score(tokens, [item["label"], *item.get("lookup_properties", [])]), item)
        for item in affordance["labels"]
    ]
    relationship_rows = [
        (
            backend._schema_score(
                tokens,
                [
                    item["relationship_type"],
                    item.get("source_label", ""),
                    item.get("target_label", ""),
                    item.get("pattern", ""),
                ],
            ),
            item,
        )
        for item in affordance["relationship_traversals"]
    ]
    property_rows = [
        (
            backend._schema_score(
                tokens, [item["label"], item["property"], *item.get("examples", [])]
            ),
            item,
        )
        for item in affordance["property_affordances"]
    ]
    relationship_property_rows = [
        (
            backend._schema_score(
                tokens, [item["relationship_type"], item["property"], *item.get("examples", [])]
            ),
            item,
        )
        for item in affordance["relationship_property_affordances"]
    ]
    return {
        "query": query,
        "labels": [
            {
                "label": item["label"],
                "count": item.get("count"),
                "lookup_properties": item.get("lookup_properties", []),
                "property_names": [prop["name"] for prop in item.get("properties", [])],
                "score": score,
            }
            for score, item in _top_schema_matches(label_rows, limit)
            if score > 0
        ],
        "relationships": [
            {
                "relationship_type": item["relationship_type"],
                "source_label": item["source_label"],
                "target_label": item["target_label"],
                "pattern": item["pattern"],
                "direction_rule": item["direction_rule"],
                "semantic_direction_examples": item["semantic_direction_examples"],
                "forward_expand": item["forward_expand"],
                "reverse_expand": item["reverse_expand"],
                "ready_to_use": item["ready_to_use"],
                "score": score,
            }
            for score, item in _top_schema_matches(relationship_rows, limit)
            if score > 0
        ],
        "node_properties": [
            {
                "label": item["label"],
                "property": item["property"],
                "inferred_type": item["inferred_type"],
                "operators": item["operators"],
                "lookup_candidate": item["lookup_candidate"],
                "examples": item.get("examples", [])[:3],
                "score": score,
            }
            for score, item in _top_schema_matches(property_rows, limit)
            if score > 0
        ],
        "relationship_properties": [
            {
                "relationship_type": item["relationship_type"],
                "property": item["property"],
                "inferred_type": item["inferred_type"],
                "operators": item["operators"],
                "examples": item.get("examples", [])[:3],
                "score": score,
            }
            for score, item in _top_schema_matches(relationship_property_rows, limit)
            if score > 0
        ],
        "next_actions": [
            "For named entities in the user question, call entity_resolve after choosing the label.",
            "For a relationship candidate you will traverse, call schema_describe_relationship or copy ready_to_use.",
            "For a property candidate you will filter/project, call schema_describe_label for its label.",
        ],
        "planning_hints": [
            "Call schema_describe_label for labels you will filter/project.",
            "Call schema_describe_relationship for relationships you will use as hops.",
            "Use ready_to_use when available; direction is relative to the current source variable.",
        ],
    }


def schema_describe_label(
    backend,
    label: Annotated[
        str,
        ToolParam("Exact node label from schema_overview or schema_search, e.g. 'Company'."),
    ],
) -> dict[str, Any]:
    label = str(label)
    affordance = backend._schema_affordance()
    label_info = next((item for item in affordance["labels"] if item["label"] == label), None)
    if label_info is None:
        raise ValueError(f"Unknown label: {label}. Supported: {backend._schema_get()['labels']}")
    traversals = [
        item
        for item in affordance["relationship_traversals"]
        if item["source_label"] == label or item["target_label"] == label
    ]
    return {
        **label_info,
        "relationship_traversals": traversals,
        "ready_to_use": {
            "entity_lookup": {
                "tool": "entity_resolve",
                "args": {
                    "label": label,
                    "text": "<named entity from question>",
                    "as": label.lower(),
                },
            },
            "exact_name_lookup": {
                "tool": "node_search",
                "args": {
                    "label": label,
                    "property": "name",
                    "value": "<exact name>",
                    "as": label.lower(),
                },
            },
        },
        "planning_hints": [
            "Use lookup_properties with entity_resolve or node_search for named entities.",
            "Use outgoing/reverse traversal specs from relationship_traversals for expand and pattern_query.",
            "If the label has high count, avoid node_scan; anchor by lookup property or related small label.",
            "Use operators listed on each property; list properties usually need in/not_in.",
        ],
    }


def schema_describe_relationship(
    backend,
    relationship_type: Annotated[
        str,
        ToolParam("Exact relationship type from schema_overview or schema_search."),
    ],
) -> dict[str, Any]:
    relationship_type = str(relationship_type)
    affordance = backend._schema_affordance()
    traversals = [
        item
        for item in affordance["relationship_traversals"]
        if item["relationship_type"] == relationship_type
    ]
    if not traversals:
        raise ValueError(
            f"Unknown relationship_type: {relationship_type}. Supported: {backend._schema_get()['relationship_types']}"
        )
    properties = [
        item
        for item in affordance["relationship_property_affordances"]
        if item["relationship_type"] == relationship_type
    ]
    temporal = [
        item
        for item in affordance["temporal_relationships"]
        if item["relationship_type"] == relationship_type
    ]
    return {
        "relationship_type": relationship_type,
        "patterns": traversals,
        "properties": properties,
        "temporal": temporal,
        "canonical_pattern": traversals[0]["pattern"],
        "ready_to_use": {
            "from_source_label": traversals[0]["ready_to_use"][
                "when_current_source_label_is_source_label"
            ],
            "from_target_label": traversals[0]["ready_to_use"][
                "when_current_source_label_is_target_label"
            ],
        },
        "next_actions": [
            {
                "when": "Current handle/source variable has source_label",
                "copy_args": traversals[0]["ready_to_use"][
                    "when_current_source_label_is_source_label"
                ],
            },
            {
                "when": "Current handle/source variable has target_label",
                "copy_args": traversals[0]["ready_to_use"][
                    "when_current_source_label_is_target_label"
                ],
            },
        ],
        "planning_hints": [
            "Direction is relative to the current source variable.",
            "Use forward_expand when traversing source_label -> target_label.",
            "Use reverse_expand when traversing target_label -> source_label.",
            "For natural-language phrases, compare the phrase to semantic_direction_examples before choosing direction.",
            "For active-in-year questions, apply temporal filters to relationship properties.",
            "For grouped counts, traverse first and aggregate only after the handle has the counted entity.",
        ],
    }


def schema_score(backend, query_tokens: set[str], values: list[Any]) -> int:
    expanded_query_tokens = _token_variants(query_tokens)
    haystack: set[str] = set()
    for value in values:
        if isinstance(value, list):
            for item in value:
                haystack.update(_tokens(str(item)))
        else:
            haystack.update(_tokens(str(value)))
    expanded_haystack = _token_variants(haystack)
    score = len(expanded_query_tokens & expanded_haystack)
    for token in expanded_query_tokens:
        if any(token in candidate or candidate in token for candidate in haystack):
            score += 1
    return score


def schema_get(backend) -> dict[str, Any]:
    return {
        "labels": [label for label in backend._schema["labels"] if label != "Entity"],
        "relationship_types": backend._schema["relationship_types"],
        "node_properties": backend._schema["node_properties"],
        "relationship_properties": backend._schema.get("relationship_properties", []),
        "relationship_patterns": [
            row
            for row in backend._schema["label_relationships"]
            if row["source_label"] != "Entity" and row["target_label"] != "Entity"
        ],
    }


def schema_affordance(backend) -> dict[str, Any]:
    labels = [label for label in backend._schema["labels"] if label != "Entity"]
    label_props = _properties_by_label(backend._schema["node_properties"])
    rel_props = _properties_by_relationship(backend._schema.get("relationship_properties", []))
    rels = [
        row
        for row in backend._schema["label_relationships"]
        if row["source_label"] != "Entity" and row["target_label"] != "Entity"
    ]
    counts = backend._label_counts(labels)
    lookup_props = {
        label: [prop["name"] for prop in props if _is_lookup_property(prop["name"], prop["types"])]
        for label, props in label_props.items()
    }
    return {
        "labels": [
            {
                "label": label,
                "tokens": _tokens(label),
                "count": counts.get(label),
                "lookup_properties": lookup_props.get(label, []),
                "properties": backend._node_property_affordances(label, label_props.get(label, [])),
                "safe_start_score": _safe_start_score(
                    counts.get(label), lookup_props.get(label, [])
                ),
            }
            for label in labels
        ],
        "relationship_traversals": [
            _relationship_affordance(row, rel_props.get(row["relationship_type"], []))
            for row in rels
        ],
        "property_affordances": [
            {
                "label": label,
                "property": prop["name"],
                "tokens": _tokens(prop["name"]),
                "types": prop["types"],
                "inferred_type": _inferred_type(prop["types"]),
                "operators": _operators_for_property(prop["name"], prop["types"]),
                "lookup_candidate": prop["name"] in lookup_props.get(label, []),
                "examples": backend._node_property_samples(label, prop["name"]),
            }
            for label, props in label_props.items()
            for prop in props
        ],
        "relationship_property_affordances": [
            {
                "relationship_type": rel_type,
                "property": prop["name"],
                "tokens": _tokens(prop["name"]),
                "types": prop["types"],
                "inferred_type": _inferred_type(prop["types"]),
                "operators": _operators_for_property(prop["name"], prop["types"]),
                "examples": backend._relationship_property_samples(rel_type, prop["name"]),
            }
            for rel_type, props in rel_props.items()
            for prop in props
        ],
        "temporal_relationships": _temporal_relationship_affordances(rel_props),
        "set_operation_patterns": [
            {
                "intent": "OR",
                "flow": [
                    "query branch A as entity handle",
                    "query branch B as entity handle",
                    "entity_set_operation op='union'",
                    "count_handle or project",
                    "fetch",
                ],
            },
            {
                "intent": "AND between separate constraints",
                "flow": [
                    "query branch A as entity handle",
                    "query branch B as entity handle",
                    "entity_set_operation op='intersect'",
                    "count_handle or project",
                    "fetch",
                ],
            },
        ],
        "safe_start_points": [
            {
                "label": item["label"],
                "count": item["count"],
                "lookup_properties": item["lookup_properties"],
                "reason": "low cardinality and has lookup properties"
                if item["lookup_properties"]
                else "low cardinality",
            }
            for item in sorted(
                [
                    {
                        "label": label,
                        "count": counts.get(label),
                        "lookup_properties": lookup_props.get(label, []),
                        "score": _safe_start_score(counts.get(label), lookup_props.get(label, [])),
                    }
                    for label in labels
                ],
                key=lambda item: item["score"],
                reverse=True,
            )
            if item["score"] > 0 and item["count"] is not None and item["count"] <= 50000
        ],
        "planning_hints": [
            "Prefer node_search on lookup_properties when the question contains a named entity or value.",
            "Prefer starting from safe_start_points when a broad question names a value belonging to a small label.",
            "Use relationship_traversals.forward_expand when moving source_label to target_label, and reverse_expand when moving target_label to source_label.",
            "Avoid node_scan on high-cardinality labels unless no anchored lookup or smaller start point exists.",
            "Use same_target_role_intersection when one entity must satisfy multiple relationship roles against the same related entity.",
            "Use shared_role_aggregate only when the answer is a peer of a named seed through shared intermediate nodes.",
            "For OR, run separate branch queries that return the same entity type, combine them with entity_set_operation op='union', then count/project.",
            "For relationship names such as basedIn or hasCEO, use hops; do not use relationship names as node property filters.",
            "Use property operators from property_affordances. List properties usually need in/not_in rather than contains/not_contains.",
            "Use temporal_relationships for questions like 'in 2009' or 'at the time'; apply time to relationship properties, not node properties.",
            "When the question asks for counts by group, aggregate after the final traversal and use count_distinct for graph entities.",
        ],
    }


def node_property_affordances(
    backend, label: str, props: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        {
            **prop,
            "inferred_type": _inferred_type(prop["types"]),
            "operators": _operators_for_property(prop["name"], prop["types"]),
            "examples": backend._node_property_samples(label, prop["name"]),
        }
        for prop in props
    ]


def node_property_samples(backend, label: str, prop: str, *, limit: int = 3) -> list[Any]:
    if not hasattr(backend, "_driver"):
        return []
    safe_label = _safe_name(label)
    safe_prop = _safe_name(prop)
    query = (
        f"MATCH (n:`{safe_label}`) "
        f"WHERE n.`{safe_prop}` IS NOT NULL "
        f"RETURN n.`{safe_prop}` AS value LIMIT $limit"
    )
    try:
        with backend._driver.session() as session:
            return [
                _tool_value(record["value"]) for record in backend._run(session, query, limit=limit)
            ]
    except Exception:
        return []


def relationship_property_samples(
    backend, rel_type: str, prop: str, *, limit: int = 3
) -> list[Any]:
    if not hasattr(backend, "_driver"):
        return []
    safe_rel = _safe_name(rel_type)
    safe_prop = _safe_name(prop)
    query = (
        f"MATCH ()-[r:`{safe_rel}`]->() "
        f"WHERE r.`{safe_prop}` IS NOT NULL "
        f"RETURN r.`{safe_prop}` AS value LIMIT $limit"
    )
    try:
        with backend._driver.session() as session:
            return [
                _tool_value(record["value"]) for record in backend._run(session, query, limit=limit)
            ]
    except Exception:
        return []


def inspect_paths(
    backend,
    source_label: Annotated[str, ToolParam("Exact start node label, e.g. 'Company'.")],
    target_label: Annotated[
        str | None,
        ToolParam("Optional exact end node label, e.g. 'Person'.", required=False),
    ] = None,
    relationship_type: Annotated[
        str | None,
        ToolParam("Optional relationship type that must appear in the path.", required=False),
    ] = None,
    max_hops: Annotated[
        int | None,
        ToolParam("Maximum schema hops to search. Default: 2, max: 4.", required=False),
    ] = None,
    limit: Annotated[
        int | None,
        ToolParam("Maximum path candidates to return. Default: 20.", required=False),
    ] = None,
) -> dict[str, Any]:
    args = {
        "source_label": source_label,
        "target_label": target_label,
        "relationship_type": relationship_type,
        "max_hops": max_hops,
        "limit": limit,
    }
    source_label = _safe_name(str(source_label))
    target_label = _safe_name(str(target_label)) if target_label else None
    relationship_type = _safe_name(str(relationship_type)) if relationship_type else None
    max_hops = _int_arg(args, "max_hops", 2, min_value=1, max_value=4)
    limit = _int_arg(args, "limit", 20, min_value=1)
    paths = _schema_paths(
        backend._schema_relationships(),
        source_label=source_label,
        target_label=target_label,
        relationship_type=relationship_type,
        max_hops=max_hops,
        limit=limit,
    )
    return {
        "source_label": source_label,
        "target_label": target_label,
        "relationship_type": relationship_type,
        "max_hops": max_hops,
        "paths": paths,
        "planning_hints": [
            "Use a returned path.hops list directly in pattern_query or as the traversal before group_handle.",
            "Direction is relative to the current variable at each hop.",
            "If no path appears, relax target_label or increase max_hops up to 4.",
        ],
    }


__all__ = [
    "schema_inspect",
    "schema_overview",
    "schema_search",
    "schema_describe_label",
    "schema_describe_relationship",
    "schema_score",
    "schema_get",
    "schema_affordance",
    "node_property_affordances",
    "node_property_samples",
    "relationship_property_samples",
    "inspect_paths",
]
