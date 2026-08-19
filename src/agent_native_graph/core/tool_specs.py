"""Native LLM tool specifications and system prompt for ANA Neo4j tools."""

from typing import Any

from agent_native_graph.core.tooling import registered_tool_specs
from agent_native_graph.tools import load_tool_modules

load_tool_modules()


NATIVE_SYSTEM_PROMPT = """You are an agent that answers graph questions by calling tools.
Do not write Cypher. Do not answer from general knowledge.

## Tool usage rules
- For each new question, first call schema_overview unless it is already present
  in previous_tool_results for this same question.
- After schema_overview, call draft_tool_plan only when the question is composite:
  OR/AND, grouped count/ranking, comparison/superlative, multi-hop, or more than
  one named entity. For simple one-hop lookup/list questions, execute directly.
- If previous_tool_results already contains an auto draft_tool_plan result, do
  not call draft_tool_plan again; use that planning context.
- Call validate_tool_plan at most once, only for a concrete multi-step plan with
  specific tool names and args. Do not validate vague outlines, and do not call
  validate_tool_plan again after it returns valid=true unless the plan changed.
- Call exactly ONE tool at a time.
- Use fetch only when the current handle already contains the final answer rows.
- If a tool returns an error, choose a safer alternative tool or fix the missing
  arguments. Do not repeat the same failing call unchanged.
- Do not repeat the same successful tool call with the same arguments. If the
  latest handle is final, call fetch; otherwise call a different next tool that
  adds missing graph facts, combines handles, aggregates, or projects final rows.
- If expand fails because the input is too large, do not retry another broad
  expand. Use pattern_query, multi_hop_query, relationship_query,
  expand_aggregate, or a narrower anchored handle so traversal stays server-side.
- If pattern_query, relationship_query, or expand returns
  matched_count=0 and the question does not clearly expect an empty answer, the
  next call should be repair_empty_result or inspect_paths.
- Use inspect_paths before retrying a path with changed directions, changed
  relationship type, or changed start label.
- Use summarize_handle before combining/projecting a handle whose variables or
  row type are unclear.
- Use repair_empty_result after zero-row results or contract errors to get
  schema-grounded repair suggestions.
## Tool selection policy
- Use schema_search to map question words to candidate labels, relationship
  types, and properties. Then call schema_describe_label or
  schema_describe_relationship only for the candidates you need.
- Prefer copying ready-to-use arguments returned by schema_describe_relationship,
  schema_describe_label, inspect_paths, or schema_search instead of inventing
  relationship directions.
- Prefer pattern_query for anchored path/list questions that can be expressed as
  one graph pattern with filters and projected properties.
- Prefer pattern_query or multi_hop_query over expand when the source handle may
  contain thousands of rows; expand is for small already-focused source sets.
- For grouped aggregate questions such as "for each X count Y", first build the
  correct entity handle with entity_resolve, constraint_query, expand,
  pattern_query, or entity_set_operation. Then call group_handle on that handle.
- For multi-hop or reverse-worded questions, use inspect_paths once after
  schema_overview/schema_search when you are not fully certain of the path direction.
- Prefer same_target_role_intersection when the same entity must satisfy multiple
  roles against the same related entity, e.g. "founder and board member of the
  same company".
- If a question says an entity has two roles with a related entity of the same
  label, and it does not explicitly say the related entities may differ, assume
  the roles share the same target and use same_target_role_intersection.
- For same-target multi-role questions that ask for values inside a list
  property, use same_target_role_intersection with select[].explode=true, or
  call project with explode=true after same_target_role_intersection.
- Prefer constraint_query for simple "find nodes where all of these one-hop
  relationship/property constraints hold" questions. It is intentionally simpler
  than Cypher and avoids manual expand/project/count choreography.
- Prefer optional_expand_count when the question asks for each source entity and
  a count of related targets, while preserving sources with zero matches.
  This corresponds to OPTIONAL MATCH + count in Cypher.
- Prefer optional_count_by_pattern when the source entities themselves must be
  found by a pattern first, then each source needs an optional related count.
  This is the safest one-call tool for "all X ... and how many Y" questions.
- If the question asks for all source rows plus counts, omit limit. Use limit
  only for explicit top-N, first-N, preview, or user-limited requests.
- Prefer top_entities_by_property for superlatives or ranking by one property,
  such as youngest, oldest, earliest, latest, highest, lowest, first, or last.
  Do not hand-build pattern_query order_by + limit for those questions.
- For questions like "CEO in 1999", "board member during 2006", or "active in
  YEAR", do NOT use top_entities_by_property. Use schema_describe_relationship
  for the relationship and copy active_at_year_filter_template into hop
  relationship_filters with YEAR replaced by the requested year.
- When a graph query returns a large or capped handle, do not fetch it unless
  the user asks for raw rows. If the question asks "how many", "for each", or
  any grouped summary, call count_handle, group_handle, project, or another
  server-side aggregate on the handle first.
- If the question asks for candidates of one label with one or more one-hop AND
  constraints on related nodes, call constraint_query as the first graph data
  tool after schema_overview/schema_search. Do not resolve each related named entity first when
  a related-node property filter like name='Elon Musk' is enough.
- Prefer entity_set_operation for explicit OR/NOT between entity sets already
  stored in handles. It can combine two or more handles in one call.
- For OR questions, build each OR branch as a separate entity handle, then call
  entity_set_operation with op='union'. Each branch must return the same answer
  entity type. Do not project scalar columns before the union; project or count
  only after the final combined handle.
- After entity_set_operation, the combined handle is already distinct by entity.
  When projecting properties from it, use distinct=false unless the user asks
  for unique scalar values. Do not set limit unless the user asks for a top-N,
  first-N, or otherwise limited answer.
- Do not use entity_set_operation as the first choice for AND/both questions.
  Prefer a single pattern_query, constraint_query, same_target_role_intersection,
  or optional_count_by_pattern when the constraints can be expressed in one graph
  pattern. Use op='intersect' only when the question explicitly requires combining
  two independently built entity sets.
- For "entities connected to both named seed A and named seed B", resolve A and
  B separately, expand each seed to the requested related entity type, then call
  entity_set_operation op='intersect' on those related entity handles. Do not
  intersect the seed handles themselves, and do not union them.
- If you need scalar columns before a later set operation, compare, or expand,
  call project with keep_entities=true so entity variables remain available.
- Use entity_resolve for named entities from user text before starting a traversal
  from that entity. Names may differ by aliases, punctuation, or casing.
- Use count_nodes for whole-label counts. Do NOT use node_scan just to count.
- Avoid node_scan unless the question asks to list all nodes of a small label
  and no safer anchored or aggregate query fits.
- Use group_handle for GROUP BY/count/max/min/sum/avg over an existing handle.
- Use lower-level expand, aggregate, combine, and project only when the higher
  level pattern tools do not fit.

## Graph semantics
- Relationship directions matter. Follow schema_overview, schema_search,
  schema_describe_relationship, and inspect_paths relationship patterns.
- In tool args, direction is always relative to the current source variable.
  If schema says (:Company)-[:basedIn]->(:Country), then from Company use
  direction='out'; from Country use direction='in'.
- Use count_distinct for graph entities unless the question explicitly asks for
  relationship rows or duplicate occurrences.
- Use exact schema names from schema tools. Do not invent relationship types
  such as hasSubsidiary if the schema says subsidiaryOf.

## Output format
- When calling a tool, output only the native tool call.
- Never include explanatory text together with a tool call.
- After fetch, stop; the fetched rows are the benchmark answer. There is no done
  tool in benchmark runs.
"""

FILTER_SCHEMA = {
    "type": "array",
    "description": (
        "Server-side property filters. Use exact schema property names. "
        "Example: [{'var':'company','property':'name','op':'eq','value':'<company name>'}]."
    ),
    "items": {
        "type": "object",
        "properties": {
            "var": {
                "type": "string",
                "description": "Variable to filter. Must match start_as or a hop as value, e.g. 'company'.",
            },
            "property": {
                "type": "string",
                "description": "Property name from schema_inspect, e.g. 'name', 'launch_year', 'date_of_birth'.",
            },
            "op": {
                "type": "string",
                "enum": [
                    "eq",
                    "neq",
                    "gt",
                    "gte",
                    "gte_or_null",
                    "lt",
                    "lte",
                    "lte_or_null",
                    "contains",
                    "not_contains",
                    "in",
                    "not_in",
                    "is_null",
                    "is_not_null",
                ],
                "description": (
                    "Filter operator. Use 'in'/'not_in' for list properties such as country_of_citizenship. "
                    "Use 'lte' on start_year and 'gte_or_null' on end_year for active-at-year relationship intervals."
                ),
            },
            "value": {
                "description": "Filter value. Required except for is_null/is_not_null. Use strings for dates like '1940-05-05'.",
            },
            "value_type": {
                "type": "string",
                "enum": ["date", "string", "integer"],
                "description": "Optional type hint. Use 'date' for ISO date comparisons.",
            },
        },
        "required": ["var", "property", "op"],
        "additionalProperties": True,
    },
}

HOPS_SCHEMA = {
    "type": "array",
    "description": (
        "Ordered traversal hops. Each hop starts from the previous variable. "
        "Use schema_inspect to choose direction."
    ),
    "items": {
        "type": "object",
        "properties": {
            "relationship_type": {
                "type": "string",
                "description": "Relationship type exactly as shown in schema_inspect, e.g. 'hasCEO', 'subsidiaryOf'.",
            },
            "direction": {
                "type": "string",
                "enum": ["out", "in"],
                "description": "Use 'out' for (current)-[:R]->(target), 'in' for (current)<-[:R]-(target).",
            },
            "target_label": {
                "type": "string",
                "description": "Target node label reached by this hop, e.g. 'Person', 'Company', 'Industry'.",
            },
            "as": {
                "type": "string",
                "description": "Short snake_case variable name for the reached node, e.g. 'ceo', 'industry'.",
            },
            "rel_as": {
                "type": "string",
                "description": "Optional relationship variable name, e.g. 'role' or 'membership'. Use when filtering relationship properties.",
            },
            "relationship_filters": {
                "type": "array",
                "description": (
                    "Filters on this relationship's properties, e.g. "
                    "[{'property':'start_year','op':'lte','value':2009}, "
                    "{'property':'end_year','op':'gte_or_null','value':2009}]."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "property": {
                            "type": "string",
                            "description": "Relationship property, e.g. 'start_year'.",
                        },
                        "op": {
                            "type": "string",
                            "enum": [
                                "eq",
                                "neq",
                                "gt",
                                "gte",
                                "lt",
                                "lte",
                                "gte_or_null",
                                "lte_or_null",
                                "is_null",
                                "is_not_null",
                            ],
                            "description": "Temporal interval filters often use start_year <= year and end_year >= year OR null.",
                        },
                        "value": {"description": "Filter value, e.g. 2009."},
                        "value_type": {"type": "string", "enum": ["date", "string", "integer"]},
                    },
                    "required": ["property", "op"],
                    "additionalProperties": True,
                },
            },
        },
        "required": ["relationship_type", "direction", "target_label", "as"],
        "additionalProperties": True,
    },
}

SELECT_SCHEMA = {
    "type": "array",
    "description": (
        "Properties to return as table columns. Use this when the question asks "
        "for names, years, or attributes. For list properties where the question "
        "asks for unique values, each value, or Cypher UNWIND semantics, set "
        "explode=true on that selected property."
    ),
    "items": {
        "type": "object",
        "properties": {
            "var": {"type": "string", "description": "Variable to project from, e.g. 'company'."},
            "property": {
                "type": "string",
                "description": "Property to return, e.g. 'name' or 'launch_year'.",
            },
            "alias": {
                "type": "string",
                "description": "Output column name. Use concise names like 'name', 'year'.",
            },
            "value_type": {
                "type": "string",
                "enum": ["date", "string", "integer"],
                "description": "Optional type hint.",
            },
            "explode": {
                "type": "boolean",
                "description": (
                    "Set true only for list properties when the answer needs one "
                    "row per list item, e.g. unique countries from "
                    "person.country_of_citizenship. This is equivalent to "
                    "UNWIND on that property before DISTINCT/fetch."
                ),
            },
        },
        "required": ["var", "property"],
        "additionalProperties": True,
    },
}

GROUP_BY_SCHEMA = {
    "type": "array",
    "description": "Properties to group by for aggregate outputs. Required for grouped count questions.",
    "items": {
        "type": "object",
        "properties": {
            "var": {"type": "string", "description": "Variable to group by, e.g. 'industry'."},
            "property": {"type": "string", "description": "Property to group by, usually 'name'."},
            "alias": {"type": "string", "description": "Output column alias, e.g. 'industry'."},
            "value_type": {
                "type": "string",
                "enum": ["date", "string", "integer"],
                "description": "Optional type hint.",
            },
        },
        "required": ["var", "property", "alias"],
        "additionalProperties": True,
    },
}

METRICS_SCHEMA = {
    "type": "array",
    "description": "Aggregate metrics. Prefer count_distinct for companies, people, countries, and industries.",
    "items": {
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "enum": ["count", "count_distinct", "max", "min", "sum", "avg"],
                "description": "Use count_distinct unless duplicates are explicitly meaningful. Use max/min/sum/avg for scalar table columns.",
            },
            "var": {"type": "string", "description": "Variable to count, e.g. 'company'."},
            "property": {
                "type": "string",
                "description": "Optional scalar property for max/min/sum/avg, e.g. 'launch_year'. Do not use for count/count_distinct.",
            },
            "alias": {"type": "string", "description": "Output column name, e.g. 'company_count'."},
        },
        "required": ["op", "var", "alias"],
        "additionalProperties": True,
    },
}

ORDER_BY_SCHEMA = {
    "type": "array",
    "description": (
        "Sort output rows. Use field when ordering by a returned alias. Use "
        "var/property when the answer must be sorted by a graph property that "
        "should not be returned, e.g. RETURN company.name ORDER BY company.launch_year."
    ),
    "items": {
        "type": "object",
        "properties": {
            "field": {"type": "string", "description": "Returned alias to order by."},
            "var": {
                "type": "string",
                "description": "Variable to order by when field is not used.",
            },
            "property": {
                "type": "string",
                "description": "Property to order by when field is not used.",
            },
            "direction": {
                "type": "string",
                "enum": ["asc", "desc"],
                "description": "Default: asc.",
            },
            "value_type": {"type": "string", "enum": ["date", "string", "integer"]},
        },
        "additionalProperties": True,
    },
}

PATTERN_QUERY_PROPERTIES = {
    "start_label": {
        "type": "string",
        "description": "Label of the starting node, e.g. 'Company'. Must exist in schema_inspect.",
    },
    "start_as": {
        "type": "string",
        "description": "Variable name for the starting node. Default: lowercase start_label.",
    },
    "from": {
        "type": "string",
        "description": "Optional source handle. Use only to continue from a prior tool result.",
    },
    "filters": FILTER_SCHEMA,
    "hops": HOPS_SCHEMA,
    "select": SELECT_SCHEMA,
    "group_by": GROUP_BY_SCHEMA,
    "metrics": METRICS_SCHEMA,
    "order_by": ORDER_BY_SCHEMA,
    "distinct": {
        "type": "boolean",
        "description": "Apply DISTINCT to returned rows. Default: false, pattern_query sets true by default.",
    },
    "limit": {
        "type": "integer",
        "description": "Optional maximum rows returned into the handle. Omit for all rows; set only for explicit top-N/first-N/preview requests.",
    },
    "max_input_rows": {
        "type": "integer",
        "description": "Safety cap when continuing from a source handle. Default: 5000.",
    },
    "allow_large": {
        "type": "boolean",
        "description": (
            "Override broad-handle safety guards. Use only when the user explicitly "
            "needs a large traversal/materialized result."
        ),
    },
}

DISABLED_TOOL_NAMES = {
    "done",
    "group_count_by_pattern",
    "schema_inspect",
    "schema_get",
    "schema_affordance",
    "set_count_by_patterns",
}
HIDDEN_DEFAULT_TOOL_NAMES = {"draft_tool_plan", "validate_tool_plan", *DISABLED_TOOL_NAMES}
LEGACY_TOOL_ORDER = [
    "schema_overview",
    "schema_search",
    "schema_describe_label",
    "schema_describe_relationship",
    "inspect_paths",
    "summarize_handle",
    "handle_recap",
    "repair_empty_result",
    "entity_resolve",
    "node_search",
    "node_scan",
    "count_nodes",
    "count_handle",
    "expand",
    "expand_aggregate",
    "optional_expand_count",
    "optional_count_by_pattern",
    "relationship_query",
    "multi_hop_query",
    "pattern_query",
    "top_entities_by_property",
    "constraint_query",
    "entity_set_operation",
    "filter",
    "filter_same_node",
    "join_handles",
    "same_target_role_intersection",
    "shared_role_aggregate",
    "combine",
    "group_handle",
    "aggregate",
    "project",
    "compare",
    "fetch",
]
SCHEMA_ENTRY_MODES = (
    "overview",
    "overview_light",
    "targeted_first",
    "overview_expand_first",
    "overview_light_expand_first",
)


def _tool_specs(
    *, enable_planning_tools: bool, schema_entry: str = "overview"
) -> list[dict[str, Any]]:
    specs = _merged_tool_specs()
    hidden_names = set(DISABLED_TOOL_NAMES)
    if schema_entry == "targeted_first":
        hidden_names.add("schema_overview")
    if schema_entry in {"overview_expand_first", "overview_light_expand_first"}:
        hidden_names.update({"multi_hop_query", "optional_count_by_pattern", "pattern_query"})
    if enable_planning_tools:
        visible_specs = [spec for spec in specs if spec["function"]["name"] not in hidden_names]
        return _apply_legacy_tool_contract_overrides(visible_specs)
    hidden_names.update({"draft_tool_plan", "validate_tool_plan"})
    visible_specs = [spec for spec in specs if spec["function"]["name"] not in hidden_names]
    return _apply_legacy_tool_contract_overrides(visible_specs)


def _merged_tool_specs() -> list[dict[str, Any]]:
    """Return native tool specs generated from `@tool(...)` decorators."""
    order = {name: index for index, name in enumerate(LEGACY_TOOL_ORDER)}
    return sorted(
        registered_tool_specs(),
        key=lambda spec: order.get(str(spec["function"]["name"]), len(order)),
    )


def _apply_legacy_tool_contract_overrides(
    specs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep the LLM-facing contract aligned with the original investigation runner.

    The implementation is now decorator-based and split across modules, but the
    benchmark baseline depends on the exact tool surface that produced the best
    historical results. These overrides preserve that surface while allowing the
    runtime code to stay refactored.
    """
    overrides: dict[str, dict[str, Any]] = {
        "schema_overview": {
            "description": (
                "Returns the first compact schema map for a graph question. Use this "
                "as the first tool for every new question. It gives labels, counts, "
                "relationship patterns, safe start labels, direction rules, and "
                "recommended next schema tools. Do NOT use it as the final answer. "
                "For large graphs, this intentionally avoids full property samples; "
                "call schema_search, schema_describe_label, or "
                "schema_describe_relationship only for relevant details."
            ),
        },
        "schema_search": {
            "description": (
                "Searches schema labels, relationship types, node properties, and "
                "relationship properties using words from the question. Use after "
                "schema_overview when you need to map user words to exact schema names "
                "without loading the full schema. It returns candidate relationships "
                "with ready-to-copy forward/reverse traversal args. Example queries: "
                "'subsidiaries board members', 'CEO in 1999', 'country of citizenship'. "
                "Do NOT use for graph data lookup; use entity_resolve or graph query "
                "tools after selecting schema names."
            ),
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language keywords from the question.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum candidates per category. Default: 8.",
                },
            },
            "required": ["query"],
        },
        "schema_describe_label": {
            "description": (
                "Returns detailed metadata for one node label: count, lookup "
                "properties, property types/operators/examples, and incoming/outgoing "
                "relationship traversals. Use this when you plan to filter/project a "
                "label or start traversal from that label. It returns ready-to-copy "
                "expand/pattern directions. Use only for labels you actually need."
            ),
            "properties": {
                "label": {
                    "type": "string",
                    "description": "Node label to describe exactly, e.g. 'Company'.",
                }
            },
            "required": ["label"],
        },
        "schema_describe_relationship": {
            "description": (
                "Returns detailed metadata for one relationship type: source/target "
                "label patterns, direction hints, relationship properties, temporal "
                "affordances, and ready-to-copy expand/pattern args. Use before any "
                "hop where direction is uncertain, especially reverse-worded questions "
                "like 'entities based in a named place' or temporal questions such as "
                "'CEO in 1999'."
            ),
            "properties": {
                "relationship_type": {
                    "type": "string",
                    "description": (
                        "Relationship type to describe exactly, e.g. 'hasBoardMember'."
                    ),
                }
            },
            "required": ["relationship_type"],
        },
        "inspect_paths": {
            "description": (
                "Finds generic schema paths between labels and returns ready-to-use "
                "hop specs with correct directions. Use this BEFORE guessing a "
                "relationship direction or multi-hop path. Works for any graph schema; "
                "it does not contain dataset-specific business logic."
            ),
            "properties": {
                "source_label": {
                    "type": "string",
                    "description": "Starting node label, e.g. 'Industry'.",
                },
                "target_label": {
                    "type": "string",
                    "description": "Optional desired ending label, e.g. 'Company'.",
                },
                "relationship_type": {
                    "type": "string",
                    "description": "Optional relationship type to prefer/filter.",
                },
                "max_hops": {
                    "type": "integer",
                    "description": "Maximum schema hops to inspect. Default: 2, max: 4.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum candidate paths to return. Default: 20.",
                },
            },
            "required": ["source_label"],
        },
        "repair_empty_result": {
            "properties": {
                "tool": {
                    "type": "string",
                    "description": "Tool name that failed or returned zero rows.",
                },
                "args": {"type": "object", "description": "Arguments passed to that tool."},
                "error": {
                    "type": "string",
                    "description": "Optional error text from the failed call.",
                },
                "reason": {
                    "type": "string",
                    "description": "Optional short reason, e.g. 'zero_rows' or 'tool_error'.",
                },
            },
            "required": ["tool", "args"],
        },
        "multi_hop_query": {"required": ["start_label", "hops"]},
        "optional_count_by_pattern": {
            "required": ["start_label", "hops", "optional_relationship", "group_by"]
        },
        "pattern_query": {"required": ["start_label", "hops"]},
        "project": {
            "drop_properties": {"group_by", "metrics"},
            "required": ["from", "select"],
        },
    }
    output: list[dict[str, Any]] = []
    for spec in specs:
        copied = {
            **spec,
            "function": {
                **spec["function"],
                "parameters": {
                    **spec["function"]["parameters"],
                    "properties": dict(spec["function"]["parameters"].get("properties") or {}),
                    "required": list(spec["function"]["parameters"].get("required") or []),
                },
            },
        }
        function = copied["function"]
        params = function["parameters"]
        params["additionalProperties"] = True
        override = overrides.get(str(function["name"]))
        if override:
            if "description" in override:
                function["description"] = override["description"]
            if "properties" in override:
                params["properties"] = dict(override["properties"])
            for prop in override.get("drop_properties", set()):
                params["properties"].pop(prop, None)
            if "required" in override:
                params["required"] = list(override["required"])
        output.append(copied)
    return output


def _native_system_prompt(
    *,
    enable_planning_tools: bool,
    schema_entry: str,
) -> str:
    prompt = NATIVE_SYSTEM_PROMPT
    if schema_entry == "targeted_first":
        prompt = prompt.replace(
            "- For each new question, first call schema_overview unless it is already present\n"
            "  in previous_tool_results for this same question.",
            "- For each new question, first call schema_search with concise keywords\n"
            "  extracted from the question unless schema_search is already present\n"
            "  in previous_tool_results for this same question.",
        )
        prompt = prompt.replace(
            "schema_overview/schema_search",
            "schema_search/schema_describe_label/schema_describe_relationship",
        )
        prompt = prompt.replace(
            "after schema_overview/schema_search",
            "after schema_search or targeted schema description",
        )
    elif schema_entry == "overview_light":
        prompt = prompt.replace(
            "- For each new question, first call schema_overview unless it is already present\n"
            "  in previous_tool_results for this same question.",
            "- For each new question, first call schema_overview unless it is already present\n"
            "  in previous_tool_results for this same question. In this run schema_overview\n"
            "  is intentionally lightweight; use schema_search and targeted schema\n"
            "  description tools before choosing paths or properties.",
        )
    elif schema_entry == "overview_expand_first":
        prompt = prompt.replace(
            "- Prefer pattern_query for anchored path/list questions that can be expressed as\n"
            "  one graph pattern with filters and projected properties.",
            "- Prefer composable handle operations: entity_resolve, expand, project,\n"
            "  group_handle, count_handle, entity_set_operation, and fetch.\n"
            "- Build multi-step graph answers incrementally instead of using one broad\n"
            "  monolithic pattern tool.",
        )
    elif schema_entry == "overview_light_expand_first":
        prompt = prompt.replace(
            "- For each new question, first call schema_overview unless it is already present\n"
            "  in previous_tool_results for this same question.",
            "- For each new question, first call schema_overview unless it is already present\n"
            "  in previous_tool_results for this same question. In this run schema_overview\n"
            "  is intentionally lightweight; use schema_search and targeted schema\n"
            "  description tools before choosing paths or properties.",
        )
        prompt = prompt.replace(
            "- Prefer pattern_query for anchored path/list questions that can be expressed as\n"
            "  one graph pattern with filters and projected properties.",
            "- Prefer composable handle operations: entity_resolve, expand, project,\n"
            "  group_handle, count_handle, entity_set_operation, and fetch.\n"
            "- Build multi-step graph answers incrementally instead of using one broad\n"
            "  monolithic pattern tool.",
        )
    if enable_planning_tools:
        return prompt
    planning_block = """- After schema_overview, call draft_tool_plan only when the question is composite:
  OR/AND, grouped count/ranking, comparison/superlative, multi-hop, or more than
  one named entity. For simple one-hop lookup/list questions, execute directly.
- If previous_tool_results already contains an auto draft_tool_plan result, do
  not call draft_tool_plan again; use that planning context.
- Call validate_tool_plan at most once, only for a concrete multi-step plan with
  specific tool names and args. Do not validate vague outlines, and do not call
  validate_tool_plan again after it returns valid=true unless the plan changed.
"""
    prompt = prompt.replace(planning_block, "")
    prompt = prompt.replace(
        "## Tool selection policy",
        "## Tool selection policy\n"
        "- Planning tools are disabled in this run. Execute with graph data tools directly.\n",
    )
    return prompt


def _schema_entry_prompt_section(schema_entry: str) -> str:
    if schema_entry == "targeted_first":
        return (
            "## Schema entry policy\n"
            "- For each new question, first call schema_search with concise keywords "
            "unless schema_search is already present for this same question.\n"
            "- Use schema_describe_label and schema_describe_relationship before choosing "
            "paths, properties, or directions."
        )
    if schema_entry in {"overview_light", "overview_light_expand_first"}:
        extra = ""
        if schema_entry == "overview_light_expand_first":
            extra = (
                "\n- Prefer composable handle operations: entity_resolve, expand, "
                "project, group_handle, count_handle, entity_set_operation, and fetch."
                "\n- Build multi-step graph answers incrementally instead of using one "
                "broad monolithic pattern tool."
            )
        return (
            "## Schema entry policy\n"
            "- For each new question, first call schema_overview unless it is already present "
            "for this same question.\n"
            "- schema_overview is intentionally lightweight in this mode; use schema_search "
            "and targeted schema description tools before choosing paths or properties."
            f"{extra}"
        )
    if schema_entry == "overview_expand_first":
        return (
            "## Schema entry policy\n"
            "- For each new question, first call schema_overview unless it is already present "
            "for this same question.\n"
            "- Prefer composable handle operations: entity_resolve, expand, project, "
            "group_handle, count_handle, entity_set_operation, and fetch.\n"
            "- Build multi-step graph answers incrementally instead of using one broad "
            "monolithic pattern tool."
        )
    return (
        "## Schema entry policy\n"
        "- For each new question, first call schema_overview unless it is already present "
        "for this same question.\n"
        "- Use schema_search when question words do not exactly match schema names."
    )


def _planning_prompt_section(enable_planning_tools: bool) -> str:
    if enable_planning_tools:
        return (
            "## Planning policy\n"
            "- Use planning tools only for composite questions: OR/AND, grouped counts, "
            "ranking, comparison, multi-hop, or multiple named entities.\n"
            "- Do not call planning tools repeatedly for the same question."
        )
    return (
        "## Planning policy\n"
        "- Planning tools are disabled in this run. Execute with graph data tools directly."
    )


def _tool_guidance_prompt_section(specs: list[dict[str, Any]]) -> str:
    lines = ["## Available tool guidance"]
    for spec in specs:
        function = spec["function"]
        name = function["name"]
        description = " ".join(str(function.get("description") or "").split())
        required = function.get("parameters", {}).get("required", [])
        suffix = f" Required args: {', '.join(required)}." if required else ""
        lines.append(f"- {name}: {description}{suffix}")
    return "\n".join(lines)
