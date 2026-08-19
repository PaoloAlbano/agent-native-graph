"""Decorated ANA operation tool wrappers.

These wrappers are the public tool-call surface: metadata, LLM descriptions,
and parameter schemas live on @tool next to the callable. The heavy execution
body still delegates to the concrete backend methods until each operation is
split into smaller backend modules.
"""

from typing import Annotated, Any

from agent_native_graph.core.enums import ToolProfile, ToolStatus
from agent_native_graph.core.tooling import ToolParam, tool


@tool(
    name="summarize_handle",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Summarizes an existing handle: row count, kind, focus, variables, entity/table/scalar shape, sample values, and generic next traversals.",
    description="Summarizes an existing handle: row count, kind, focus, variables, entity/table/scalar shape, sample values, and generic next traversals. Use before projecting, filtering, or set-combining when you are not certain which variables are present.",
)
def tool_summarize_handle(
    backend,
    from_: Annotated[
        Any,
        ToolParam("Handle id to summarize, e.g. 'h3'.", alias="from", schema={"type": "string"}),
    ],
    sample_limit: Annotated[
        Any,
        ToolParam(
            "Number of sample rows/values. Default: 5.", required=False, schema={"type": "integer"}
        ),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["from"] = from_
    if sample_limit is not None:
        args["sample_limit"] = sample_limit
    return backend._summarize_handle(args)


@tool(
    name="handle_recap",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Explains how an existing handle was produced: the tool calls that created it, parent handles used as inputs, entity variables, row counts, and previews.",
    description="Explains how an existing handle was produced: the tool calls that created it, parent handles used as inputs, entity variables, row counts, and previews. Use this when you are unsure which handle id to fetch/project/combine, after an Unknown handle error, or before combining OR/AND branches with entity_set_operation. Do NOT use for schema discovery or to answer the user directly.",
)
def tool_handle_recap(
    backend,
    from_: Annotated[
        Any, ToolParam("Handle id to trace, e.g. 'h4'.", alias="from", schema={"type": "string"})
    ],
    limit: Annotated[
        Any,
        ToolParam(
            "Maximum lineage steps to return. Default: 12.",
            required=False,
            schema={"type": "integer"},
        ),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["from"] = from_
    if limit is not None:
        args["limit"] = limit
    return backend._handle_recap(args)


@tool(
    name="draft_tool_plan",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Drafts a schema-grounded, dataset-agnostic tool plan for the user question.",
    description="Drafts a schema-grounded, dataset-agnostic tool plan for the user question. Use this after schema_inspect and before executing graph data tools on non-trivial questions. It identifies likely answer shape, query features such as OR/AND/grouping/comparison, relevant schema labels/properties/relationship types, recommended tool families, and planning risks. It does not execute the query.",
)
def tool_draft_tool_plan(
    backend,
    question: Annotated[
        Any, ToolParam("The original user question, unchanged.", schema={"type": "string"})
    ],
    max_steps: Annotated[
        Any,
        ToolParam(
            "Maximum desired execution steps for the draft. Default: 6.",
            required=False,
            schema={"type": "integer"},
        ),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["question"] = question
    if max_steps is not None:
        args["max_steps"] = max_steps
    return backend._draft_tool_plan(args)


@tool(
    name="validate_tool_plan",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Validates a proposed generic tool plan before execution.",
    description="Validates a proposed generic tool plan before execution. Use this for multi-step, OR/AND, grouped, or comparison plans to catch invented labels, relationship types, invalid hop directions, and filters/counts that reference variables not produced by the plan. It does not execute the query.",
)
def tool_validate_tool_plan(
    backend,
    plan: Annotated[
        Any,
        ToolParam(
            "Ordered planned tool calls. Each item should have 'tool' and optional 'args'. Example: [{'tool':'entity_resolve','args':{'label':'Company','text':'<company name>','as':'company'}}, {'tool':'pattern_query','args':{'start_label':'Company','start_as':'company','hops':[...]}}]",
            schema={"type": "array", "items": {"type": "object", "additionalProperties": True}},
        ),
    ],
    question: Annotated[
        Any,
        ToolParam(
            "Optional original question for extra generic sanity checks.",
            required=False,
            schema={"type": "string"},
        ),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["plan"] = plan
    if question is not None:
        args["question"] = question
    return backend._validate_tool_plan(args)


@tool(
    name="entity_resolve",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Finds graph nodes for a named entity from user text using exact, case-insensitive, contains, and alias matching.",
    description="Finds graph nodes for a named entity from user text using exact, case-insensitive, contains, and alias matching. Use this when the question names a concrete company, person, place, or category. Prefer this before pattern_query when that named entity is the traversal anchor. Names may differ by aliases, punctuation, or casing. Do NOT use for broad scans, counts, or grouped aggregate questions.",
)
def tool_entity_resolve(
    backend,
    label: Annotated[
        Any,
        ToolParam(
            "Node label to search, e.g. 'Company', 'Person', 'Country', 'Industry'.",
            schema={"type": "string"},
        ),
    ],
    text: Annotated[
        Any,
        ToolParam(
            "Entity text from the question, e.g. 'United States of America'. Do not rewrite to an ID.",
            schema={"type": "string"},
        ),
    ],
    as_: Annotated[
        Any,
        ToolParam(
            "Variable name for the resolved node, e.g. 'company'. Default: lowercase label.",
            required=False,
            alias="as",
            schema={"type": "string"},
        ),
    ] = None,
    limit: Annotated[
        Any,
        ToolParam(
            "Maximum candidates. Default: 5, max 10 unless allow_large=true. Use small values unless disambiguating.",
            required=False,
            schema={"type": "integer"},
        ),
    ] = None,
    context_terms: Annotated[
        Any,
        ToolParam(
            "Optional disambiguating words from the original question, e.g. ['United States'] for 'Fresenius Kabi (United States)' or ['tyre industry'] when the exact category phrase matters. Use when several candidates share a name/alias or when a prior resolved candidate led to an empty traversal.",
            required=False,
            schema={"type": "array", "items": {"type": "string"}},
        ),
    ] = None,
    allow_large: Annotated[
        Any,
        ToolParam(
            "Set true only when intentionally inspecting many ambiguous candidates.",
            required=False,
            schema={"type": "boolean"},
        ),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["label"] = label
    args["text"] = text
    if as_ is not None:
        args["as"] = as_
    if limit is not None:
        args["limit"] = limit
    if context_terms is not None:
        args["context_terms"] = context_terms
    if allow_large is not None:
        args["allow_large"] = allow_large
    return backend._entity_resolve(args)


@tool(
    name="node_search",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Finds nodes by exact property equality.",
    description="Finds nodes by exact property equality. Use this when you know the exact property value from the question or a prior result. Prefer entity_resolve if spelling, aliases, or casing may differ. Do NOT use for contains/fuzzy lookup.",
)
def tool_node_search(
    backend,
    label: Annotated[Any, ToolParam("Node label from schema_inspect.", schema={"type": "string"})],
    value: Annotated[Any, ToolParam("Exact value to match, e.g. a company or person name.")],
    property: Annotated[
        Any,
        ToolParam(
            "Exact property to match. Default: 'name'.", required=False, schema={"type": "string"}
        ),
    ] = None,
    as_: Annotated[
        Any,
        ToolParam(
            "Variable name for matched nodes, e.g. 'company'.",
            required=False,
            alias="as",
            schema={"type": "string"},
        ),
    ] = None,
    limit: Annotated[
        Any, ToolParam("Maximum rows. Default: 1000.", required=False, schema={"type": "integer"})
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["label"] = label
    args["value"] = value
    if property is not None:
        args["property"] = property
    if as_ is not None:
        args["as"] = as_
    if limit is not None:
        args["limit"] = limit
    return backend._node_search(args)


@tool(
    name="node_scan",
    status=ToolStatus.EXPERIMENTAL,
    profile=ToolProfile.READONLY,
    purpose="Lists nodes of one label as a last-resort fallback.",
    description="Lists nodes of one label as a last-resort fallback. Use only for small-label listing questions like 'names of all countries'. Do NOT use for counts, joins, broad traversals, or when entity_resolve, pattern_query, group_handle, or count_nodes can answer.",
)
def tool_node_scan(
    backend,
    label: Annotated[Any, ToolParam("Node label to list.", schema={"type": "string"})],
    as_: Annotated[
        Any,
        ToolParam(
            "Variable name for returned nodes.",
            required=False,
            alias="as",
            schema={"type": "string"},
        ),
    ] = None,
    limit: Annotated[
        Any,
        ToolParam(
            "Maximum rows. Values over 5000 require allow_large=true.",
            required=False,
            schema={"type": "integer"},
        ),
    ] = None,
    allow_large: Annotated[
        Any,
        ToolParam(
            "Set true only when a large scan is explicitly intended.",
            required=False,
            schema={"type": "boolean"},
        ),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["label"] = label
    if as_ is not None:
        args["as"] = as_
    if limit is not None:
        args["limit"] = limit
    if allow_large is not None:
        args["allow_large"] = allow_large
    return backend._node_scan(args)


@tool(
    name="count_nodes",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Counts all nodes with a label server-side.",
    description="Counts all nodes with a label server-side. Use this for questions like 'How many countries are there?'. Do NOT use node_scan plus count_handle for whole-label counts.",
)
def tool_count_nodes(
    backend,
    label: Annotated[
        Any, ToolParam("Node label to count, e.g. 'Country'.", schema={"type": "string"})
    ],
    alias: Annotated[
        Any,
        ToolParam(
            "Output column name, e.g. 'country_count'.", required=False, schema={"type": "string"}
        ),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["label"] = label
    if alias is not None:
        args["alias"] = alias
    return backend._count_nodes(args)


@tool(
    name="count_handle",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Counts rows or distinct graph entities already stored in a handle.",
    description="Counts rows or distinct graph entities already stored in a handle. Use after entity_set_operation, combine, expand, or pattern_query when the question asks 'how many'. Do NOT use for whole-label counts.",
)
def tool_count_handle(
    backend,
    from_: Annotated[
        Any, ToolParam("Handle id to count, e.g. 'h3'.", alias="from", schema={"type": "string"})
    ],
    var: Annotated[
        Any,
        ToolParam(
            "Optional entity variable to count distinctly, e.g. 'company'.",
            required=False,
            schema={"type": "string"},
        ),
    ] = None,
    distinct: Annotated[
        Any,
        ToolParam(
            "Use true for graph entities unless duplicates are required.",
            required=False,
            schema={"type": "boolean"},
        ),
    ] = None,
    alias: Annotated[
        Any,
        ToolParam(
            "Output column name, e.g. 'company_count'.", required=False, schema={"type": "string"}
        ),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["from"] = from_
    if var is not None:
        args["var"] = var
    if distinct is not None:
        args["distinct"] = distinct
    if alias is not None:
        args["alias"] = alias
    return backend._count_handle(args)


@tool(
    name="expand",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Traverses exactly one relationship hop from an existing handle.",
    description="Traverses exactly one relationship hop from an existing handle. Use when a prior tool has produced a small set of source nodes and one more hop is needed. Do NOT use for broad multi-hop grouped queries; build a focused handle first, then use group_handle.",
)
def tool_expand(
    backend,
    from_: Annotated[
        Any, ToolParam("Source handle id, e.g. 'h1'.", alias="from", schema={"type": "string"})
    ],
    source: Annotated[
        Any,
        ToolParam("Source variable inside the handle, e.g. 'company'.", schema={"type": "string"}),
    ],
    relationship_type: Annotated[
        Any, ToolParam("Relationship type exactly from schema_inspect.", schema={"type": "string"})
    ],
    direction: Annotated[
        Any,
        ToolParam(
            "Direction relative to source. Prefer out/in from schema.",
            schema={"type": "string", "enum": ["out", "in", "both"]},
        ),
    ],
    target_label: Annotated[
        Any, ToolParam("Label reached by the traversal.", schema={"type": "string"})
    ],
    as_: Annotated[
        Any,
        ToolParam(
            "Variable name for target nodes.", required=False, alias="as", schema={"type": "string"}
        ),
    ] = None,
    limit: Annotated[
        Any,
        ToolParam(
            "Maximum returned rows. Default: 10000.", required=False, schema={"type": "integer"}
        ),
    ] = None,
    page_size: Annotated[
        Any,
        ToolParam(
            "Internal batch size. Default: 2000.", required=False, schema={"type": "integer"}
        ),
    ] = None,
    max_input_rows: Annotated[
        Any,
        ToolParam(
            "Safety cap for source rows consumed from the handle. Default: 5000.",
            required=False,
            schema={"type": "integer"},
        ),
    ] = None,
    allow_large: Annotated[
        Any,
        ToolParam(
            "Override broad-handle safety guards. Use only when the user explicitly needs the full traversal.",
            required=False,
            schema={"type": "boolean"},
        ),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["from"] = from_
    args["source"] = source
    args["relationship_type"] = relationship_type
    args["direction"] = direction
    args["target_label"] = target_label
    if as_ is not None:
        args["as"] = as_
    if limit is not None:
        args["limit"] = limit
    if page_size is not None:
        args["page_size"] = page_size
    if max_input_rows is not None:
        args["max_input_rows"] = max_input_rows
    if allow_large is not None:
        args["allow_large"] = allow_large
    return backend._expand(args)


@tool(
    name="expand_aggregate",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Traverses one hop from an existing handle and aggregates server-side.",
    description="Traverses one hop from an existing handle and aggregates server-side. Use when a source handle already exists and the next operation is one-hop grouped counting. This is mandatory inner traversal semantics; use optional_expand_count when zero-count source rows must be preserved.",
)
def tool_expand_aggregate(
    backend,
    from_: Annotated[Any, ToolParam("Source handle id.", alias="from", schema={"type": "string"})],
    source: Annotated[Any, ToolParam("Source variable in the handle.", schema={"type": "string"})],
    relationship_type: Annotated[
        Any, ToolParam("Relationship type from schema_inspect.", schema={"type": "string"})
    ],
    direction: Annotated[
        Any,
        ToolParam(
            "Direction relative to source.", schema={"type": "string", "enum": ["out", "in"]}
        ),
    ],
    target_label: Annotated[Any, ToolParam("Target node label.", schema={"type": "string"})],
    as_: Annotated[
        Any,
        ToolParam("Target variable name.", required=False, alias="as", schema={"type": "string"}),
    ] = None,
    group_by: Annotated[
        Any,
        ToolParam(
            "Properties to group by for aggregate outputs. Required for grouped count questions.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "var": {
                            "type": "string",
                            "description": "Variable to group by, e.g. 'industry'.",
                        },
                        "property": {
                            "type": "string",
                            "description": "Property to group by, usually 'name'.",
                        },
                        "alias": {
                            "type": "string",
                            "description": "Output column alias, e.g. 'industry'.",
                        },
                        "value_type": {
                            "type": "string",
                            "enum": ["date", "string", "integer"],
                            "description": "Optional type hint.",
                        },
                    },
                    "required": ["var", "property", "alias"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    metrics: Annotated[
        Any,
        ToolParam(
            "Aggregate metrics. Prefer count_distinct for companies, people, countries, and industries.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "op": {
                            "type": "string",
                            "enum": ["count", "count_distinct", "max", "min", "sum", "avg"],
                            "description": "Use count_distinct unless duplicates are explicitly meaningful. Use max/min/sum/avg for scalar table columns.",
                        },
                        "var": {
                            "type": "string",
                            "description": "Variable to count, e.g. 'company'.",
                        },
                        "property": {
                            "type": "string",
                            "description": "Optional scalar property for max/min/sum/avg, e.g. 'launch_year'. Do not use for count/count_distinct.",
                        },
                        "alias": {
                            "type": "string",
                            "description": "Output column name, e.g. 'company_count'.",
                        },
                    },
                    "required": ["op", "var", "alias"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    limit: Annotated[
        Any,
        ToolParam(
            "Maximum aggregate rows. Default: 1000.", required=False, schema={"type": "integer"}
        ),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["from"] = from_
    args["source"] = source
    args["relationship_type"] = relationship_type
    args["direction"] = direction
    args["target_label"] = target_label
    if as_ is not None:
        args["as"] = as_
    if group_by is not None:
        args["group_by"] = group_by
    if metrics is not None:
        args["metrics"] = metrics
    if limit is not None:
        args["limit"] = limit
    return backend._expand_aggregate(args)


@tool(
    name="optional_expand_count",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Left-preserving optional one-hop count from an existing entity handle.",
    description="Left-preserving optional one-hop count from an existing entity handle. Use when the question asks for each source entity plus how many related targets it has, and sources with no targets must still appear with count 0. This is the safe tool for OPTIONAL MATCH + count semantics, e.g. 'each source entity and the number of related target entities'. Do NOT replace this with expand + aggregate when zero-count sources matter. If the question asks for all source rows, omit limit; set limit only for explicit top-N, first-N, preview, or user-limited requests.",
)
def tool_optional_expand_count(
    backend,
    from_: Annotated[
        Any,
        ToolParam(
            "Source handle id containing entity rows.", alias="from", schema={"type": "string"}
        ),
    ],
    source: Annotated[
        Any,
        ToolParam(
            "Source entity variable in the handle, e.g. 'person'.", schema={"type": "string"}
        ),
    ],
    relationship_type: Annotated[
        Any, ToolParam("Relationship type from schema_inspect.", schema={"type": "string"})
    ],
    direction: Annotated[
        Any,
        ToolParam(
            "Direction relative to source.", schema={"type": "string", "enum": ["out", "in"]}
        ),
    ],
    target_label: Annotated[
        Any, ToolParam("Target node label to optionally count.", schema={"type": "string"})
    ],
    as_: Annotated[
        Any,
        ToolParam(
            "Optional target variable name. Default: lowercase target_label.",
            required=False,
            alias="as",
            schema={"type": "string"},
        ),
    ] = None,
    group_by: Annotated[
        Any,
        ToolParam(
            "Properties to group by for aggregate outputs. Required for grouped count questions.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "var": {
                            "type": "string",
                            "description": "Variable to group by, e.g. 'industry'.",
                        },
                        "property": {
                            "type": "string",
                            "description": "Property to group by, usually 'name'.",
                        },
                        "alias": {
                            "type": "string",
                            "description": "Output column alias, e.g. 'industry'.",
                        },
                        "value_type": {
                            "type": "string",
                            "enum": ["date", "string", "integer"],
                            "description": "Optional type hint.",
                        },
                    },
                    "required": ["var", "property", "alias"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    alias: Annotated[
        Any,
        ToolParam(
            "Count output column name. Default: count.", required=False, schema={"type": "string"}
        ),
    ] = None,
    distinct: Annotated[
        Any,
        ToolParam(
            "Count distinct target nodes. Default: true.",
            required=False,
            schema={"type": "boolean"},
        ),
    ] = None,
    limit: Annotated[
        Any,
        ToolParam(
            "Optional maximum output rows. Omit for all rows; set only for explicit top-N/first-N/preview requests.",
            required=False,
            schema={"type": "integer"},
        ),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["from"] = from_
    args["source"] = source
    args["relationship_type"] = relationship_type
    args["direction"] = direction
    args["target_label"] = target_label
    if as_ is not None:
        args["as"] = as_
    if group_by is not None:
        args["group_by"] = group_by
    if alias is not None:
        args["alias"] = alias
    if distinct is not None:
        args["distinct"] = distinct
    if limit is not None:
        args["limit"] = limit
    return backend._optional_expand_count(args)


@tool(
    name="optional_count_by_pattern",
    status=ToolStatus.EXPERIMENTAL,
    profile=ToolProfile.READONLY,
    purpose="Finds source entities with a server-side pattern, then performs a left-preserving optional one-hop count from each source.",
    description="Finds source entities with a server-side pattern, then performs a left-preserving optional one-hop count from each source. Use this for questions like 'all X matching a pattern and how many related Y each has', where X with zero Y must still appear with count 0. This is a generic OPTIONAL MATCH + count tool. Do NOT use pattern_query with metrics, expand_aggregate, or group_handle for these questions because those use inner-match semantics and can drop zero-count source entities. If the question asks for all rows, omit limit; set limit only for explicit top-N, first-N, preview, or user-limited requests.",
)
def tool_optional_count_by_pattern(
    backend,
    start_label: Annotated[
        Any,
        ToolParam(
            "Label of the starting node, e.g. 'Company'. Must exist in schema_inspect.",
            schema={"type": "string"},
        ),
    ],
    hops: Annotated[
        Any,
        ToolParam(
            "Ordered traversal hops. Each hop starts from the previous variable. Use schema_inspect to choose direction.",
            required=True,
            schema={
                "type": "array",
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
                            "description": "Filters on this relationship's properties, e.g. [{'property':'start_year','op':'lte','value':2009}, {'property':'end_year','op':'gte_or_null','value':2009}].",
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
                                    "value_type": {
                                        "type": "string",
                                        "enum": ["date", "string", "integer"],
                                    },
                                },
                                "required": ["property", "op"],
                                "additionalProperties": True,
                            },
                        },
                    },
                    "required": ["relationship_type", "direction", "target_label", "as"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    optional_relationship: Annotated[
        Any,
        ToolParam(
            "One optional relationship from source to counted target. Direction is relative to source.",
            required=True,
            schema={
                "type": "object",
                "properties": {
                    "relationship_type": {
                        "type": "string",
                        "description": "Relationship type from schema_inspect, e.g. 'hasBoardMember'.",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["out", "in"],
                        "description": "Direction relative to source.",
                    },
                    "target_label": {
                        "type": "string",
                        "description": "Target node label to count.",
                    },
                    "as": {
                        "type": "string",
                        "description": "Target variable name. Default: lowercase target_label.",
                    },
                    "rel_as": {
                        "type": "string",
                        "description": "Optional relationship variable name. Default: optional_rel.",
                    },
                    "relationship_filters": {
                        "type": "array",
                        "description": "Filters on this relationship's properties, e.g. [{'property':'start_year','op':'lte','value':2009}, {'property':'end_year','op':'gte_or_null','value':2009}].",
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
                                "value_type": {
                                    "type": "string",
                                    "enum": ["date", "string", "integer"],
                                },
                            },
                            "required": ["property", "op"],
                            "additionalProperties": True,
                        },
                    },
                },
                "required": ["relationship_type", "direction", "target_label"],
                "additionalProperties": True,
            },
        ),
    ] = None,
    group_by: Annotated[
        Any,
        ToolParam(
            "Properties to group by for aggregate outputs. Required for grouped count questions.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "var": {
                            "type": "string",
                            "description": "Variable to group by, e.g. 'industry'.",
                        },
                        "property": {
                            "type": "string",
                            "description": "Property to group by, usually 'name'.",
                        },
                        "alias": {
                            "type": "string",
                            "description": "Output column alias, e.g. 'industry'.",
                        },
                        "value_type": {
                            "type": "string",
                            "enum": ["date", "string", "integer"],
                            "description": "Optional type hint.",
                        },
                    },
                    "required": ["var", "property", "alias"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    start_as: Annotated[
        Any,
        ToolParam(
            "Variable name for the starting node. Default: lowercase start_label.",
            required=False,
            schema={"type": "string"},
        ),
    ] = None,
    from_: Annotated[
        Any,
        ToolParam(
            "Optional source handle. Use only to continue from a prior tool result.",
            required=False,
            alias="from",
            schema={"type": "string"},
        ),
    ] = None,
    filters: Annotated[
        Any,
        ToolParam(
            "Server-side property filters. Use exact schema property names. Example: [{'var':'company','property':'name','op':'eq','value':'<company name>'}].",
            required=False,
            schema={
                "type": "array",
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
                            "description": "Filter operator. Use 'in'/'not_in' for list properties such as country_of_citizenship. Use 'lte' on start_year and 'gte_or_null' on end_year for active-at-year relationship intervals.",
                        },
                        "value": {
                            "description": "Filter value. Required except for is_null/is_not_null. Use strings for dates like '1940-05-05'."
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
            },
        ),
    ] = None,
    select: Annotated[
        Any,
        ToolParam(
            "Properties to return as table columns. Use this when the question asks for names, years, or attributes. For list properties where the question asks for unique values, each value, or Cypher UNWIND semantics, set explode=true on that selected property.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "var": {
                            "type": "string",
                            "description": "Variable to project from, e.g. 'company'.",
                        },
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
                            "description": "Set true only for list properties when the answer needs one row per list item, e.g. unique countries from person.country_of_citizenship. This is equivalent to UNWIND on that property before DISTINCT/fetch.",
                        },
                    },
                    "required": ["var", "property"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    metrics: Annotated[
        Any,
        ToolParam(
            "Aggregate metrics. Prefer count_distinct for companies, people, countries, and industries.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "op": {
                            "type": "string",
                            "enum": ["count", "count_distinct", "max", "min", "sum", "avg"],
                            "description": "Use count_distinct unless duplicates are explicitly meaningful. Use max/min/sum/avg for scalar table columns.",
                        },
                        "var": {
                            "type": "string",
                            "description": "Variable to count, e.g. 'company'.",
                        },
                        "property": {
                            "type": "string",
                            "description": "Optional scalar property for max/min/sum/avg, e.g. 'launch_year'. Do not use for count/count_distinct.",
                        },
                        "alias": {
                            "type": "string",
                            "description": "Output column name, e.g. 'company_count'.",
                        },
                    },
                    "required": ["op", "var", "alias"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    order_by: Annotated[
        Any,
        ToolParam(
            "Sort output rows. Use field when ordering by a returned alias. Use var/property when the answer must be sorted by a graph property that should not be returned, e.g. RETURN company.name ORDER BY company.launch_year.",
            required=False,
            schema={
                "type": "array",
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
            },
        ),
    ] = None,
    distinct: Annotated[
        Any,
        ToolParam(
            "Apply DISTINCT to returned rows. Default: false, pattern_query sets true by default.",
            required=False,
            schema={"type": "boolean"},
        ),
    ] = None,
    limit: Annotated[
        Any,
        ToolParam(
            "Optional maximum rows returned into the handle. Omit for all rows; set only for explicit top-N/first-N/preview requests.",
            required=False,
            schema={"type": "integer"},
        ),
    ] = None,
    max_input_rows: Annotated[
        Any,
        ToolParam(
            "Safety cap when continuing from a source handle. Default: 5000.",
            required=False,
            schema={"type": "integer"},
        ),
    ] = None,
    allow_large: Annotated[
        Any,
        ToolParam(
            "Override broad-handle safety guards. Use only when the user explicitly needs a large traversal/materialized result.",
            required=False,
            schema={"type": "boolean"},
        ),
    ] = None,
    source: Annotated[
        Any,
        ToolParam(
            "Source variable to preserve and group/count from. Defaults to the final hop variable.",
            required=False,
            schema={"type": "string"},
        ),
    ] = None,
    alias: Annotated[
        Any,
        ToolParam(
            "Count output column name. Default: count.", required=False, schema={"type": "string"}
        ),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["start_label"] = start_label
    if hops is not None:
        args["hops"] = hops
    if optional_relationship is not None:
        args["optional_relationship"] = optional_relationship
    args["group_by"] = group_by
    if start_as is not None:
        args["start_as"] = start_as
    if from_ is not None:
        args["from"] = from_
    if filters is not None:
        args["filters"] = filters
    if select is not None:
        args["select"] = select
    if metrics is not None:
        args["metrics"] = metrics
    if order_by is not None:
        args["order_by"] = order_by
    if distinct is not None:
        args["distinct"] = distinct
    if limit is not None:
        args["limit"] = limit
    if max_input_rows is not None:
        args["max_input_rows"] = max_input_rows
    if allow_large is not None:
        args["allow_large"] = allow_large
    if source is not None:
        args["source"] = source
    if alias is not None:
        args["alias"] = alias
    return backend._optional_count_by_pattern(args)


@tool(
    name="relationship_query",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Runs a server-side single-hop relationship query without a prior handle.",
    description="Runs a server-side single-hop relationship query without a prior handle. Use for broad one-hop questions with filters, projection, or aggregation. Do NOT use for two or more hops; prefer pattern_query or build a handle and then call group_handle.",
)
def tool_relationship_query(
    backend,
    source_label: Annotated[
        Any, ToolParam("Source label in the relationship pattern.", schema={"type": "string"})
    ],
    relationship_type: Annotated[
        Any, ToolParam("Relationship type from schema_inspect.", schema={"type": "string"})
    ],
    target_label: Annotated[
        Any, ToolParam("Target label in the relationship pattern.", schema={"type": "string"})
    ],
    source_as: Annotated[
        Any,
        ToolParam(
            "Source variable name. Default: lowercase source_label.",
            required=False,
            schema={"type": "string"},
        ),
    ] = None,
    direction: Annotated[
        Any,
        ToolParam(
            "Direction relative to source_label. Default: out.",
            required=False,
            schema={"type": "string", "enum": ["out", "in"]},
        ),
    ] = None,
    rel_as: Annotated[
        Any,
        ToolParam(
            "Relationship variable name. Use when filtering or selecting relationship properties. Default: rel.",
            required=False,
            schema={"type": "string"},
        ),
    ] = None,
    target_as: Annotated[
        Any,
        ToolParam(
            "Target variable name. Default: lowercase target_label.",
            required=False,
            schema={"type": "string"},
        ),
    ] = None,
    filters: Annotated[
        Any,
        ToolParam(
            "Server-side property filters. Use exact schema property names. Example: [{'var':'company','property':'name','op':'eq','value':'<company name>'}].",
            required=False,
            schema={
                "type": "array",
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
                            "description": "Filter operator. Use 'in'/'not_in' for list properties such as country_of_citizenship. Use 'lte' on start_year and 'gte_or_null' on end_year for active-at-year relationship intervals.",
                        },
                        "value": {
                            "description": "Filter value. Required except for is_null/is_not_null. Use strings for dates like '1940-05-05'."
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
            },
        ),
    ] = None,
    select: Annotated[
        Any,
        ToolParam(
            "Properties to return as table columns. Use this when the question asks for names, years, or attributes. For list properties where the question asks for unique values, each value, or Cypher UNWIND semantics, set explode=true on that selected property.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "var": {
                            "type": "string",
                            "description": "Variable to project from, e.g. 'company'.",
                        },
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
                            "description": "Set true only for list properties when the answer needs one row per list item, e.g. unique countries from person.country_of_citizenship. This is equivalent to UNWIND on that property before DISTINCT/fetch.",
                        },
                    },
                    "required": ["var", "property"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    group_by: Annotated[
        Any,
        ToolParam(
            "Properties to group by for aggregate outputs. Required for grouped count questions.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "var": {
                            "type": "string",
                            "description": "Variable to group by, e.g. 'industry'.",
                        },
                        "property": {
                            "type": "string",
                            "description": "Property to group by, usually 'name'.",
                        },
                        "alias": {
                            "type": "string",
                            "description": "Output column alias, e.g. 'industry'.",
                        },
                        "value_type": {
                            "type": "string",
                            "enum": ["date", "string", "integer"],
                            "description": "Optional type hint.",
                        },
                    },
                    "required": ["var", "property", "alias"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    metrics: Annotated[
        Any,
        ToolParam(
            "Aggregate metrics. Prefer count_distinct for companies, people, countries, and industries.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "op": {
                            "type": "string",
                            "enum": ["count", "count_distinct", "max", "min", "sum", "avg"],
                            "description": "Use count_distinct unless duplicates are explicitly meaningful. Use max/min/sum/avg for scalar table columns.",
                        },
                        "var": {
                            "type": "string",
                            "description": "Variable to count, e.g. 'company'.",
                        },
                        "property": {
                            "type": "string",
                            "description": "Optional scalar property for max/min/sum/avg, e.g. 'launch_year'. Do not use for count/count_distinct.",
                        },
                        "alias": {
                            "type": "string",
                            "description": "Output column name, e.g. 'company_count'.",
                        },
                    },
                    "required": ["op", "var", "alias"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    order_by: Annotated[
        Any,
        ToolParam(
            "Sort output rows. Use field when ordering by a returned alias. Use var/property when the answer must be sorted by a graph property that should not be returned, e.g. RETURN company.name ORDER BY company.launch_year.",
            required=False,
            schema={
                "type": "array",
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
            },
        ),
    ] = None,
    distinct: Annotated[
        Any, ToolParam("Use true for unique rows.", required=False, schema={"type": "boolean"})
    ] = None,
    limit: Annotated[
        Any,
        ToolParam(
            "Optional maximum returned rows. Omit for all rows; set only for explicit top-N/first-N/preview requests.",
            required=False,
            schema={"type": "integer"},
        ),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["source_label"] = source_label
    args["relationship_type"] = relationship_type
    args["target_label"] = target_label
    if source_as is not None:
        args["source_as"] = source_as
    if direction is not None:
        args["direction"] = direction
    if rel_as is not None:
        args["rel_as"] = rel_as
    if target_as is not None:
        args["target_as"] = target_as
    if filters is not None:
        args["filters"] = filters
    if select is not None:
        args["select"] = select
    if group_by is not None:
        args["group_by"] = group_by
    if metrics is not None:
        args["metrics"] = metrics
    if order_by is not None:
        args["order_by"] = order_by
    if distinct is not None:
        args["distinct"] = distinct
    if limit is not None:
        args["limit"] = limit
    return backend._relationship_query(args)


@tool(
    name="multi_hop_query",
    status=ToolStatus.EXPERIMENTAL,
    profile=ToolProfile.READONLY,
    purpose="Runs a lower-level server-side multi-hop traversal.",
    description="Runs a lower-level server-side multi-hop traversal. Use when pattern_query is not expressive enough or when continuing from a handle via 'from'. Prefer pattern_query for normal path/list tasks. For grouped counts, build the entity handle first and then call group_handle.",
)
def tool_multi_hop_query(
    backend,
    start_label: Annotated[
        Any,
        ToolParam(
            "Label of the starting node, e.g. 'Company'. Must exist in schema_inspect.",
            schema={"type": "string"},
        ),
    ],
    hops: Annotated[
        Any,
        ToolParam(
            "Ordered traversal hops. Each hop starts from the previous variable. Use schema_inspect to choose direction.",
            required=False,
            schema={
                "type": "array",
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
                            "description": "Filters on this relationship's properties, e.g. [{'property':'start_year','op':'lte','value':2009}, {'property':'end_year','op':'gte_or_null','value':2009}].",
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
                                    "value_type": {
                                        "type": "string",
                                        "enum": ["date", "string", "integer"],
                                    },
                                },
                                "required": ["property", "op"],
                                "additionalProperties": True,
                            },
                        },
                    },
                    "required": ["relationship_type", "direction", "target_label", "as"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    start_as: Annotated[
        Any,
        ToolParam(
            "Variable name for the starting node. Default: lowercase start_label.",
            required=False,
            schema={"type": "string"},
        ),
    ] = None,
    from_: Annotated[
        Any,
        ToolParam(
            "Optional source handle. Use only to continue from a prior tool result.",
            required=False,
            alias="from",
            schema={"type": "string"},
        ),
    ] = None,
    filters: Annotated[
        Any,
        ToolParam(
            "Server-side property filters. Use exact schema property names. Example: [{'var':'company','property':'name','op':'eq','value':'<company name>'}].",
            required=False,
            schema={
                "type": "array",
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
                            "description": "Filter operator. Use 'in'/'not_in' for list properties such as country_of_citizenship. Use 'lte' on start_year and 'gte_or_null' on end_year for active-at-year relationship intervals.",
                        },
                        "value": {
                            "description": "Filter value. Required except for is_null/is_not_null. Use strings for dates like '1940-05-05'."
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
            },
        ),
    ] = None,
    select: Annotated[
        Any,
        ToolParam(
            "Properties to return as table columns. Use this when the question asks for names, years, or attributes. For list properties where the question asks for unique values, each value, or Cypher UNWIND semantics, set explode=true on that selected property.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "var": {
                            "type": "string",
                            "description": "Variable to project from, e.g. 'company'.",
                        },
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
                            "description": "Set true only for list properties when the answer needs one row per list item, e.g. unique countries from person.country_of_citizenship. This is equivalent to UNWIND on that property before DISTINCT/fetch.",
                        },
                    },
                    "required": ["var", "property"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    group_by: Annotated[
        Any,
        ToolParam(
            "Properties to group by for aggregate outputs. Required for grouped count questions.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "var": {
                            "type": "string",
                            "description": "Variable to group by, e.g. 'industry'.",
                        },
                        "property": {
                            "type": "string",
                            "description": "Property to group by, usually 'name'.",
                        },
                        "alias": {
                            "type": "string",
                            "description": "Output column alias, e.g. 'industry'.",
                        },
                        "value_type": {
                            "type": "string",
                            "enum": ["date", "string", "integer"],
                            "description": "Optional type hint.",
                        },
                    },
                    "required": ["var", "property", "alias"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    metrics: Annotated[
        Any,
        ToolParam(
            "Aggregate metrics. Prefer count_distinct for companies, people, countries, and industries.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "op": {
                            "type": "string",
                            "enum": ["count", "count_distinct", "max", "min", "sum", "avg"],
                            "description": "Use count_distinct unless duplicates are explicitly meaningful. Use max/min/sum/avg for scalar table columns.",
                        },
                        "var": {
                            "type": "string",
                            "description": "Variable to count, e.g. 'company'.",
                        },
                        "property": {
                            "type": "string",
                            "description": "Optional scalar property for max/min/sum/avg, e.g. 'launch_year'. Do not use for count/count_distinct.",
                        },
                        "alias": {
                            "type": "string",
                            "description": "Output column name, e.g. 'company_count'.",
                        },
                    },
                    "required": ["op", "var", "alias"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    order_by: Annotated[
        Any,
        ToolParam(
            "Sort output rows. Use field when ordering by a returned alias. Use var/property when the answer must be sorted by a graph property that should not be returned, e.g. RETURN company.name ORDER BY company.launch_year.",
            required=False,
            schema={
                "type": "array",
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
            },
        ),
    ] = None,
    distinct: Annotated[
        Any,
        ToolParam(
            "Apply DISTINCT to returned rows. Default: false, pattern_query sets true by default.",
            required=False,
            schema={"type": "boolean"},
        ),
    ] = None,
    limit: Annotated[
        Any,
        ToolParam(
            "Optional maximum rows returned into the handle. Omit for all rows; set only for explicit top-N/first-N/preview requests.",
            required=False,
            schema={"type": "integer"},
        ),
    ] = None,
    max_input_rows: Annotated[
        Any,
        ToolParam(
            "Safety cap when continuing from a source handle. Default: 5000.",
            required=False,
            schema={"type": "integer"},
        ),
    ] = None,
    allow_large: Annotated[
        Any,
        ToolParam(
            "Override broad-handle safety guards. Use only when the user explicitly needs a large traversal/materialized result.",
            required=False,
            schema={"type": "boolean"},
        ),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["start_label"] = start_label
    if hops is not None:
        args["hops"] = hops
    if start_as is not None:
        args["start_as"] = start_as
    if from_ is not None:
        args["from"] = from_
    if filters is not None:
        args["filters"] = filters
    if select is not None:
        args["select"] = select
    if group_by is not None:
        args["group_by"] = group_by
    if metrics is not None:
        args["metrics"] = metrics
    if order_by is not None:
        args["order_by"] = order_by
    if distinct is not None:
        args["distinct"] = distinct
    if limit is not None:
        args["limit"] = limit
    if max_input_rows is not None:
        args["max_input_rows"] = max_input_rows
    if allow_large is not None:
        args["allow_large"] = allow_large
    return backend._multi_hop_query(args)


@tool(
    name="pattern_query",
    status=ToolStatus.EXPERIMENTAL,
    profile=ToolProfile.READONLY,
    purpose="Answers path-shaped graph questions in one server-side call.",
    description="Answers path-shaped graph questions in one server-side call. Use when the question asks for entities or properties reachable through one or more relationship hops, with optional filters/order/limit. Examples: 'CEOs from a resolved company handle', 'companies founded by X and based in Y'. When a named entity from the question is the traversal seed, prefer entity_resolve first and pass its handle via from instead of guessing exact name filters inside pattern_query. Use relationship names only inside hops, never as filter properties. Do NOT use for grouped count questions as a shortcut; build the entity handle first, then call group_handle. Do NOT use for 'all X and how many related Y' questions when X with zero related Y must still appear; build the X handle first, then call optional_expand_count, or use optional_count_by_pattern to do both steps in one server-side call. Do NOT use one broad pattern_query to answer OR; build one entity handle per branch and combine them with entity_set_operation. If the result is large or capped, do NOT fetch it as a final answer for count/grouped questions; use count_handle, group_handle, or project server-side first.",
)
def tool_pattern_query(
    backend,
    start_label: Annotated[
        Any,
        ToolParam(
            "Label of the starting node, e.g. 'Company'. Must exist in schema_inspect.",
            schema={"type": "string"},
        ),
    ],
    hops: Annotated[
        Any,
        ToolParam(
            "Ordered traversal hops. Each hop starts from the previous variable. Use schema_inspect to choose direction.",
            required=False,
            schema={
                "type": "array",
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
                            "description": "Filters on this relationship's properties, e.g. [{'property':'start_year','op':'lte','value':2009}, {'property':'end_year','op':'gte_or_null','value':2009}].",
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
                                    "value_type": {
                                        "type": "string",
                                        "enum": ["date", "string", "integer"],
                                    },
                                },
                                "required": ["property", "op"],
                                "additionalProperties": True,
                            },
                        },
                    },
                    "required": ["relationship_type", "direction", "target_label", "as"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    start_as: Annotated[
        Any,
        ToolParam(
            "Variable name for the starting node. Default: lowercase start_label.",
            required=False,
            schema={"type": "string"},
        ),
    ] = None,
    from_: Annotated[
        Any,
        ToolParam(
            "Optional source handle. Use only to continue from a prior tool result.",
            required=False,
            alias="from",
            schema={"type": "string"},
        ),
    ] = None,
    filters: Annotated[
        Any,
        ToolParam(
            "Server-side property filters. Use exact schema property names. Example: [{'var':'company','property':'name','op':'eq','value':'<company name>'}].",
            required=False,
            schema={
                "type": "array",
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
                            "description": "Filter operator. Use 'in'/'not_in' for list properties such as country_of_citizenship. Use 'lte' on start_year and 'gte_or_null' on end_year for active-at-year relationship intervals.",
                        },
                        "value": {
                            "description": "Filter value. Required except for is_null/is_not_null. Use strings for dates like '1940-05-05'."
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
            },
        ),
    ] = None,
    select: Annotated[
        Any,
        ToolParam(
            "Properties to return as table columns. Use this when the question asks for names, years, or attributes. For list properties where the question asks for unique values, each value, or Cypher UNWIND semantics, set explode=true on that selected property.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "var": {
                            "type": "string",
                            "description": "Variable to project from, e.g. 'company'.",
                        },
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
                            "description": "Set true only for list properties when the answer needs one row per list item, e.g. unique countries from person.country_of_citizenship. This is equivalent to UNWIND on that property before DISTINCT/fetch.",
                        },
                    },
                    "required": ["var", "property"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    group_by: Annotated[
        Any,
        ToolParam(
            "Properties to group by for aggregate outputs. Required for grouped count questions.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "var": {
                            "type": "string",
                            "description": "Variable to group by, e.g. 'industry'.",
                        },
                        "property": {
                            "type": "string",
                            "description": "Property to group by, usually 'name'.",
                        },
                        "alias": {
                            "type": "string",
                            "description": "Output column alias, e.g. 'industry'.",
                        },
                        "value_type": {
                            "type": "string",
                            "enum": ["date", "string", "integer"],
                            "description": "Optional type hint.",
                        },
                    },
                    "required": ["var", "property", "alias"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    metrics: Annotated[
        Any,
        ToolParam(
            "Aggregate metrics. Prefer count_distinct for companies, people, countries, and industries.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "op": {
                            "type": "string",
                            "enum": ["count", "count_distinct", "max", "min", "sum", "avg"],
                            "description": "Use count_distinct unless duplicates are explicitly meaningful. Use max/min/sum/avg for scalar table columns.",
                        },
                        "var": {
                            "type": "string",
                            "description": "Variable to count, e.g. 'company'.",
                        },
                        "property": {
                            "type": "string",
                            "description": "Optional scalar property for max/min/sum/avg, e.g. 'launch_year'. Do not use for count/count_distinct.",
                        },
                        "alias": {
                            "type": "string",
                            "description": "Output column name, e.g. 'company_count'.",
                        },
                    },
                    "required": ["op", "var", "alias"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    order_by: Annotated[
        Any,
        ToolParam(
            "Sort output rows. Use field when ordering by a returned alias. Use var/property when the answer must be sorted by a graph property that should not be returned, e.g. RETURN company.name ORDER BY company.launch_year.",
            required=False,
            schema={
                "type": "array",
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
            },
        ),
    ] = None,
    distinct: Annotated[
        Any,
        ToolParam(
            "Apply DISTINCT to returned rows. Default: false, pattern_query sets true by default.",
            required=False,
            schema={"type": "boolean"},
        ),
    ] = None,
    limit: Annotated[
        Any,
        ToolParam(
            "Optional maximum rows returned into the handle. Omit for all rows; set only for explicit top-N/first-N/preview requests.",
            required=False,
            schema={"type": "integer"},
        ),
    ] = None,
    max_input_rows: Annotated[
        Any,
        ToolParam(
            "Safety cap when continuing from a source handle. Default: 5000.",
            required=False,
            schema={"type": "integer"},
        ),
    ] = None,
    allow_large: Annotated[
        Any,
        ToolParam(
            "Override broad-handle safety guards. Use only when the user explicitly needs a large traversal/materialized result.",
            required=False,
            schema={"type": "boolean"},
        ),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["start_label"] = start_label
    if hops is not None:
        args["hops"] = hops
    if start_as is not None:
        args["start_as"] = start_as
    if from_ is not None:
        args["from"] = from_
    if filters is not None:
        args["filters"] = filters
    if select is not None:
        args["select"] = select
    if group_by is not None:
        args["group_by"] = group_by
    if metrics is not None:
        args["metrics"] = metrics
    if order_by is not None:
        args["order_by"] = order_by
    if distinct is not None:
        args["distinct"] = distinct
    if limit is not None:
        args["limit"] = limit
    if max_input_rows is not None:
        args["max_input_rows"] = max_input_rows
    if allow_large is not None:
        args["allow_large"] = allow_large
    return backend._pattern_query(args)


@tool(
    name="top_entities_by_property",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Returns the top entities from a graph pattern ordered by one scalar property.",
    description="Returns the top entities from a graph pattern ordered by one scalar property. Use this for superlative questions such as youngest, oldest, earliest, latest, highest, lowest, first, or last. This is the safer alternative to hand-building pattern_query order_by + limit. For dates and years, use order='desc' for youngest/latest/most recent/largest value, and order='asc' for oldest/earliest/smallest value. Set target to the variable whose property should be ranked, e.g. target='person' when ordering by person.date_of_birth. Do NOT rank the start node just because the pattern starts there. Do NOT use for questions like 'CEO in 1999' or 'board member in 2009'; those are active-at-year relationship interval filters, not top/ranking questions. Do NOT use for grouped counts; use group_handle or relationship_query metrics instead.",
)
def tool_top_entities_by_property(
    backend,
    start_label: Annotated[
        Any,
        ToolParam(
            "Label of the starting node, e.g. 'Company'. Must exist in schema_inspect.",
            schema={"type": "string"},
        ),
    ],
    property: Annotated[
        Any,
        ToolParam(
            "Scalar property on the target variable used for ordering. Examples: date_of_birth belongs to Person, launch_year belongs to Company, imdb_rating belongs to Episode.",
            schema={"type": "string"},
        ),
    ],
    start_as: Annotated[
        Any,
        ToolParam(
            "Variable name for the starting node. Default: lowercase start_label.",
            required=False,
            schema={"type": "string"},
        ),
    ] = None,
    from_: Annotated[
        Any,
        ToolParam(
            "Optional source handle. Use only to continue from a prior tool result.",
            required=False,
            alias="from",
            schema={"type": "string"},
        ),
    ] = None,
    filters: Annotated[
        Any,
        ToolParam(
            "Server-side property filters. Use exact schema property names. Example: [{'var':'company','property':'name','op':'eq','value':'<company name>'}].",
            required=False,
            schema={
                "type": "array",
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
                            "description": "Filter operator. Use 'in'/'not_in' for list properties such as country_of_citizenship. Use 'lte' on start_year and 'gte_or_null' on end_year for active-at-year relationship intervals.",
                        },
                        "value": {
                            "description": "Filter value. Required except for is_null/is_not_null. Use strings for dates like '1940-05-05'."
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
            },
        ),
    ] = None,
    hops: Annotated[
        Any,
        ToolParam(
            "Ordered traversal hops. Each hop starts from the previous variable. Use schema_inspect to choose direction.",
            required=False,
            schema={
                "type": "array",
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
                            "description": "Filters on this relationship's properties, e.g. [{'property':'start_year','op':'lte','value':2009}, {'property':'end_year','op':'gte_or_null','value':2009}].",
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
                                    "value_type": {
                                        "type": "string",
                                        "enum": ["date", "string", "integer"],
                                    },
                                },
                                "required": ["property", "op"],
                                "additionalProperties": True,
                            },
                        },
                    },
                    "required": ["relationship_type", "direction", "target_label", "as"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    select: Annotated[
        Any,
        ToolParam(
            "Properties to return as table columns. Use this when the question asks for names, years, or attributes. For list properties where the question asks for unique values, each value, or Cypher UNWIND semantics, set explode=true on that selected property.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "var": {
                            "type": "string",
                            "description": "Variable to project from, e.g. 'company'.",
                        },
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
                            "description": "Set true only for list properties when the answer needs one row per list item, e.g. unique countries from person.country_of_citizenship. This is equivalent to UNWIND on that property before DISTINCT/fetch.",
                        },
                    },
                    "required": ["var", "property"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    group_by: Annotated[
        Any,
        ToolParam(
            "Properties to group by for aggregate outputs. Required for grouped count questions.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "var": {
                            "type": "string",
                            "description": "Variable to group by, e.g. 'industry'.",
                        },
                        "property": {
                            "type": "string",
                            "description": "Property to group by, usually 'name'.",
                        },
                        "alias": {
                            "type": "string",
                            "description": "Output column alias, e.g. 'industry'.",
                        },
                        "value_type": {
                            "type": "string",
                            "enum": ["date", "string", "integer"],
                            "description": "Optional type hint.",
                        },
                    },
                    "required": ["var", "property", "alias"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    metrics: Annotated[
        Any,
        ToolParam(
            "Aggregate metrics. Prefer count_distinct for companies, people, countries, and industries.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "op": {
                            "type": "string",
                            "enum": ["count", "count_distinct", "max", "min", "sum", "avg"],
                            "description": "Use count_distinct unless duplicates are explicitly meaningful. Use max/min/sum/avg for scalar table columns.",
                        },
                        "var": {
                            "type": "string",
                            "description": "Variable to count, e.g. 'company'.",
                        },
                        "property": {
                            "type": "string",
                            "description": "Optional scalar property for max/min/sum/avg, e.g. 'launch_year'. Do not use for count/count_distinct.",
                        },
                        "alias": {
                            "type": "string",
                            "description": "Output column name, e.g. 'company_count'.",
                        },
                    },
                    "required": ["op", "var", "alias"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    order_by: Annotated[
        Any,
        ToolParam(
            "Sort output rows. Use field when ordering by a returned alias. Use var/property when the answer must be sorted by a graph property that should not be returned, e.g. RETURN company.name ORDER BY company.launch_year.",
            required=False,
            schema={
                "type": "array",
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
            },
        ),
    ] = None,
    distinct: Annotated[
        Any,
        ToolParam(
            "Apply DISTINCT to returned rows. Default: false, pattern_query sets true by default.",
            required=False,
            schema={"type": "boolean"},
        ),
    ] = None,
    limit: Annotated[
        Any,
        ToolParam(
            "Optional maximum rows returned into the handle. Omit for all rows; set only for explicit top-N/first-N/preview requests.",
            required=False,
            schema={"type": "integer"},
        ),
    ] = None,
    max_input_rows: Annotated[
        Any,
        ToolParam(
            "Safety cap when continuing from a source handle. Default: 5000.",
            required=False,
            schema={"type": "integer"},
        ),
    ] = None,
    allow_large: Annotated[
        Any,
        ToolParam(
            "Override broad-handle safety guards. Use only when the user explicitly needs a large traversal/materialized result.",
            required=False,
            schema={"type": "boolean"},
        ),
    ] = None,
    target: Annotated[
        Any,
        ToolParam(
            "Entity variable to rank. Use the variable that owns the ranking property, e.g. 'person' for person.date_of_birth or 'company' for company.launch_year. Defaults to the final hop variable, or start_as for zero-hop patterns.",
            required=False,
            schema={"type": "string"},
        ),
    ] = None,
    order: Annotated[
        Any,
        ToolParam(
            "Sort direction. Use desc for youngest/latest/highest and asc for oldest/earliest/lowest.",
            required=False,
            schema={"type": "string", "enum": ["asc", "desc"]},
        ),
    ] = None,
    include_property: Annotated[
        Any,
        ToolParam(
            "Include the ranking property in output. Default false; set true only when the user asks for the value too.",
            required=False,
            schema={"type": "boolean"},
        ),
    ] = None,
    name_alias: Annotated[
        Any,
        ToolParam(
            "Output column name for target.name. Default: 'name'.",
            required=False,
            schema={"type": "string"},
        ),
    ] = None,
    property_alias: Annotated[
        Any,
        ToolParam(
            "Output column name for the ranking property. Default: property name.",
            required=False,
            schema={"type": "string"},
        ),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["start_label"] = start_label
    args["property"] = property
    if start_as is not None:
        args["start_as"] = start_as
    if from_ is not None:
        args["from"] = from_
    if filters is not None:
        args["filters"] = filters
    if hops is not None:
        args["hops"] = hops
    if select is not None:
        args["select"] = select
    if group_by is not None:
        args["group_by"] = group_by
    if metrics is not None:
        args["metrics"] = metrics
    if order_by is not None:
        args["order_by"] = order_by
    if distinct is not None:
        args["distinct"] = distinct
    if limit is not None:
        args["limit"] = limit
    if max_input_rows is not None:
        args["max_input_rows"] = max_input_rows
    if allow_large is not None:
        args["allow_large"] = allow_large
    if target is not None:
        args["target"] = target
    if order is not None:
        args["order"] = order
    if include_property is not None:
        args["include_property"] = include_property
    if name_alias is not None:
        args["name_alias"] = name_alias
    if property_alias is not None:
        args["property_alias"] = property_alias
    return backend._top_entities_by_property(args)


@tool(
    name="constraint_query",
    status=ToolStatus.EXPERIMENTAL,
    profile=ToolProfile.READONLY,
    purpose="Finds nodes of one label that satisfy simple AND constraints over one-hop relationships and related-node properties.",
    description="Finds nodes of one label that satisfy simple AND constraints over one-hop relationships and related-node properties. Use this for questions like 'companies based in Italy and with Tim Cook as a board member' or 'companies whose CEO is Elon Musk'. This tool is deliberately small: use it immediately after schema_inspect when all constraints apply to the same candidate node. Prefer it over entity_resolve + expand + project/count for these one-hop AND cases. If the answer is a candidate node and the question says it is related to named/category nodes A and B, put both as separate where items with property='name' filters instead of resolving A and B into handles first. Do NOT use for OR/NOT logic, grouped counts, multi-hop paths, or constraints that require comparing two separate candidate sets. When the user asks for the candidate name plus candidate properties such as launch_year or inception_date, keep return_mode='names' and add those fields in return_properties. Do NOT use when two or more relationship constraints from the same candidate should point to the same related target label (for example CEO and founder of the same company); use same_target_role_intersection instead.",
)
def tool_constraint_query(
    backend,
    find: Annotated[
        Any,
        ToolParam(
            "Candidate nodes to find.",
            schema={
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "description": "Candidate node label, e.g. 'Company'.",
                    },
                    "as": {
                        "type": "string",
                        "description": "Candidate variable name. Default: lowercase label.",
                    },
                },
                "required": ["label"],
                "additionalProperties": True,
            },
        ),
    ],
    where: Annotated[
        Any,
        ToolParam(
            "AND constraints. Each item is one relationship from the candidate node to a related node plus an optional property filter on that related node. These constraints are independent unless they use a more specific tool; do not use this shape to express two roles against the same related target entity.",
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "relationship_type": {
                            "type": "string",
                            "description": "Relationship type exactly from schema_inspect, e.g. 'hasCEO'.",
                        },
                        "direction": {
                            "type": "string",
                            "enum": ["out", "in"],
                            "description": "Direction relative to the candidate node.",
                        },
                        "target_label": {
                            "type": "string",
                            "description": "Related node label reached by this relationship, e.g. 'Person'.",
                        },
                        "target_as": {
                            "type": "string",
                            "description": "Optional variable name for the related node.",
                        },
                        "property": {
                            "type": "string",
                            "description": "Optional property to filter on the related node, usually 'name'.",
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
                            "description": "Filter operator. Use 'in'/'not_in' for list properties such as country_of_citizenship. Use 'lte' on start_year and 'gte_or_null' on end_year for active-at-year relationship intervals.",
                        },
                        "value": {
                            "description": "Filter value. Required except for is_null/is_not_null. Use strings for dates like '1940-05-05'."
                        },
                        "value_type": {
                            "type": "string",
                            "enum": ["date", "string", "integer"],
                            "description": "Optional type hint. Use 'date' for ISO date comparisons.",
                        },
                    },
                    "required": ["relationship_type", "direction", "target_label"],
                    "additionalProperties": True,
                },
            },
        ),
    ],
    return_mode: Annotated[
        Any,
        ToolParam(
            "Use 'names' for name lists, 'count' for how many candidates, 'entities' for an entity handle.",
            required=False,
            schema={"type": "string", "enum": ["entities", "names", "count"]},
        ),
    ] = None,
    return_property: Annotated[
        Any,
        ToolParam(
            "Property to return for return_mode='names'. Default: 'name'.",
            required=False,
            schema={"type": "string"},
        ),
    ] = None,
    return_properties: Annotated[
        Any,
        ToolParam(
            "Additional candidate-node properties to return with the main name/value when return_mode='names'. Use this when the user asks for both an entity and one or more of its properties, e.g. return_properties=[{'property':'launch_year','alias':'launch_year'}] for 'which company and what launch year'. Do not include sort-only properties unless the user asks to see them.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "property": {
                            "type": "string",
                            "description": "Candidate-node property to return, e.g. 'launch_year'.",
                        },
                        "alias": {
                            "type": "string",
                            "description": "Output column alias. Default: property name.",
                        },
                    },
                    "required": ["property"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    alias: Annotated[
        Any,
        ToolParam(
            "Output column alias. Default: return_property or '<var>_count'.",
            required=False,
            schema={"type": "string"},
        ),
    ] = None,
    distinct: Annotated[
        Any,
        ToolParam(
            "Deduplicate candidates/results. Default: true.",
            required=False,
            schema={"type": "boolean"},
        ),
    ] = None,
    order_by: Annotated[
        Any,
        ToolParam(
            "Sort output rows. Use field when ordering by a returned alias. Use var/property when the answer must be sorted by a graph property that should not be returned, e.g. RETURN company.name ORDER BY company.launch_year.",
            required=False,
            schema={
                "type": "array",
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
            },
        ),
    ] = None,
    limit: Annotated[
        Any,
        ToolParam(
            "Optional maximum rows. Omit for all rows; set only for explicit top-N/first-N/preview requests.",
            required=False,
            schema={"type": "integer"},
        ),
    ] = None,
    offset: Annotated[
        Any, ToolParam("Pagination offset. Default: 0.", required=False, schema={"type": "integer"})
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["find"] = find
    args["where"] = where
    if return_mode is not None:
        args["return_mode"] = return_mode
    if return_property is not None:
        args["return_property"] = return_property
    if return_properties is not None:
        args["return_properties"] = return_properties
    if alias is not None:
        args["alias"] = alias
    if distinct is not None:
        args["distinct"] = distinct
    if order_by is not None:
        args["order_by"] = order_by
    if limit is not None:
        args["limit"] = limit
    if offset is not None:
        args["offset"] = offset
    return backend._constraint_query(args)


@tool(
    name="group_count_by_pattern",
    status=ToolStatus.DEPRECATED,
    profile=ToolProfile.READONLY,
    purpose="Answers grouped aggregate graph questions in one server-side call.",
    description="Answers grouped aggregate graph questions in one server-side call. Use when the user asks 'for each X, how many Y', 'number of Y by X', or asks to rank groups by counts. Do NOT materialize rows and then aggregate manually unless this tool cannot express the pattern. Use relationship names only as hops, never as filter properties. If the grouped count is one branch of an OR/AND question, first produce compatible entity handles for each branch, combine them, then count/project the combined handle.",
)
def tool_group_count_by_pattern(
    backend,
    start_label: Annotated[
        Any,
        ToolParam(
            "Label of the starting node, e.g. 'Company'. Must exist in schema_inspect.",
            schema={"type": "string"},
        ),
    ],
    hops: Annotated[
        Any,
        ToolParam(
            "Ordered traversal hops. Each hop starts from the previous variable. Use schema_inspect to choose direction.",
            schema={
                "type": "array",
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
                            "description": "Filters on this relationship's properties, e.g. [{'property':'start_year','op':'lte','value':2009}, {'property':'end_year','op':'gte_or_null','value':2009}].",
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
                                    "value_type": {
                                        "type": "string",
                                        "enum": ["date", "string", "integer"],
                                    },
                                },
                                "required": ["property", "op"],
                                "additionalProperties": True,
                            },
                        },
                    },
                    "required": ["relationship_type", "direction", "target_label", "as"],
                    "additionalProperties": True,
                },
            },
        ),
    ],
    group_by: Annotated[
        Any,
        ToolParam(
            "Properties to group by for aggregate outputs. Required for grouped count questions.",
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "var": {
                            "type": "string",
                            "description": "Variable to group by, e.g. 'industry'.",
                        },
                        "property": {
                            "type": "string",
                            "description": "Property to group by, usually 'name'.",
                        },
                        "alias": {
                            "type": "string",
                            "description": "Output column alias, e.g. 'industry'.",
                        },
                        "value_type": {
                            "type": "string",
                            "enum": ["date", "string", "integer"],
                            "description": "Optional type hint.",
                        },
                    },
                    "required": ["var", "property", "alias"],
                    "additionalProperties": True,
                },
            },
        ),
    ],
    count_var: Annotated[
        Any, ToolParam("Variable to count, e.g. 'company'.", schema={"type": "string"})
    ],
    start_as: Annotated[
        Any,
        ToolParam(
            "Variable name for the starting node. Default: lowercase start_label.",
            required=False,
            schema={"type": "string"},
        ),
    ] = None,
    from_: Annotated[
        Any,
        ToolParam(
            "Optional source handle. Use only to continue from a prior tool result.",
            required=False,
            alias="from",
            schema={"type": "string"},
        ),
    ] = None,
    filters: Annotated[
        Any,
        ToolParam(
            "Server-side property filters. Use exact schema property names. Example: [{'var':'company','property':'name','op':'eq','value':'<company name>'}].",
            required=False,
            schema={
                "type": "array",
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
                            "description": "Filter operator. Use 'in'/'not_in' for list properties such as country_of_citizenship. Use 'lte' on start_year and 'gte_or_null' on end_year for active-at-year relationship intervals.",
                        },
                        "value": {
                            "description": "Filter value. Required except for is_null/is_not_null. Use strings for dates like '1940-05-05'."
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
            },
        ),
    ] = None,
    select: Annotated[
        Any,
        ToolParam(
            "Properties to return as table columns. Use this when the question asks for names, years, or attributes. For list properties where the question asks for unique values, each value, or Cypher UNWIND semantics, set explode=true on that selected property.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "var": {
                            "type": "string",
                            "description": "Variable to project from, e.g. 'company'.",
                        },
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
                            "description": "Set true only for list properties when the answer needs one row per list item, e.g. unique countries from person.country_of_citizenship. This is equivalent to UNWIND on that property before DISTINCT/fetch.",
                        },
                    },
                    "required": ["var", "property"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    metrics: Annotated[
        Any,
        ToolParam(
            "Aggregate metrics. Prefer count_distinct for companies, people, countries, and industries.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "op": {
                            "type": "string",
                            "enum": ["count", "count_distinct", "max", "min", "sum", "avg"],
                            "description": "Use count_distinct unless duplicates are explicitly meaningful. Use max/min/sum/avg for scalar table columns.",
                        },
                        "var": {
                            "type": "string",
                            "description": "Variable to count, e.g. 'company'.",
                        },
                        "property": {
                            "type": "string",
                            "description": "Optional scalar property for max/min/sum/avg, e.g. 'launch_year'. Do not use for count/count_distinct.",
                        },
                        "alias": {
                            "type": "string",
                            "description": "Output column name, e.g. 'company_count'.",
                        },
                    },
                    "required": ["op", "var", "alias"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    order_by: Annotated[
        Any,
        ToolParam(
            "Sort output rows. Use field when ordering by a returned alias. Use var/property when the answer must be sorted by a graph property that should not be returned, e.g. RETURN company.name ORDER BY company.launch_year.",
            required=False,
            schema={
                "type": "array",
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
            },
        ),
    ] = None,
    distinct: Annotated[
        Any,
        ToolParam(
            "Apply DISTINCT to returned rows. Default: false, pattern_query sets true by default.",
            required=False,
            schema={"type": "boolean"},
        ),
    ] = None,
    limit: Annotated[
        Any,
        ToolParam(
            "Optional maximum rows returned into the handle. Omit for all rows; set only for explicit top-N/first-N/preview requests.",
            required=False,
            schema={"type": "integer"},
        ),
    ] = None,
    max_input_rows: Annotated[
        Any,
        ToolParam(
            "Safety cap when continuing from a source handle. Default: 5000.",
            required=False,
            schema={"type": "integer"},
        ),
    ] = None,
    allow_large: Annotated[
        Any,
        ToolParam(
            "Override broad-handle safety guards. Use only when the user explicitly needs a large traversal/materialized result.",
            required=False,
            schema={"type": "boolean"},
        ),
    ] = None,
    alias: Annotated[
        Any,
        ToolParam(
            "Count column alias, e.g. 'company_count'. Default: '<count_var>_count'.",
            required=False,
            schema={"type": "string"},
        ),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["start_label"] = start_label
    args["hops"] = hops
    args["group_by"] = group_by
    args["count_var"] = count_var
    if start_as is not None:
        args["start_as"] = start_as
    if from_ is not None:
        args["from"] = from_
    if filters is not None:
        args["filters"] = filters
    if select is not None:
        args["select"] = select
    if metrics is not None:
        args["metrics"] = metrics
    if order_by is not None:
        args["order_by"] = order_by
    if distinct is not None:
        args["distinct"] = distinct
    if limit is not None:
        args["limit"] = limit
    if max_input_rows is not None:
        args["max_input_rows"] = max_input_rows
    if allow_large is not None:
        args["allow_large"] = allow_large
    if alias is not None:
        args["alias"] = alias
    return backend._group_count_by_pattern(args)


@tool(
    name="entity_set_operation",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Combines two or more entity handles by graph identity.",
    description="Combines two or more entity handles by graph identity. Use this when the question has explicit OR/either or NOT/exclusion between alternative graph conditions. For OR/either, build one entity handle per branch and call op='union'. For NOT/excluding, call op='difference'. Use op='intersect' only when the user explicitly asks to combine two independently built entity sets; do not use it for same-target multi-role patterns or simple AND constraints that fit one pattern. For common-neighbor questions such as 'people connected to both A and B', resolve A and B, expand each seed to the related entity type, then intersect those related entity handles; never intersect or union the seed handles themselves. Every operand must be the same answer entity type and must still contain entity rows, not scalar/table rows. Do NOT project names, scalar properties, or counts before this operation; after the combined handle is returned, use count_handle for 'how many' or project for requested properties. When projecting properties after this tool, use distinct=false unless the user explicitly asks for unique scalar values; the entity set is already deduplicated by identity.",
)
def tool_entity_set_operation(
    backend,
    op: Annotated[
        Any,
        ToolParam(
            "Set operation to apply: union for OR/either, difference for NOT/exclusion, intersect only for explicitly independent entity sets.",
            schema={"type": "string", "enum": ["union", "intersect", "difference"]},
        ),
    ],
    operands: Annotated[
        Any,
        ToolParam(
            "Two or more entity handles to combine. Each operand must use an entity variable from that handle and all operands should represent the same answer entity type. For difference, subtract later operands from the first.",
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "handle": {
                            "type": "string",
                            "description": "Handle id returned by a branch query, e.g. 'h1'.",
                        },
                        "var": {
                            "type": "string",
                            "description": "Entity variable in that handle. Use an entity variable, not a projected scalar alias.",
                        },
                    },
                    "required": ["handle", "var"],
                    "additionalProperties": True,
                },
            },
        ),
    ],
    as_: Annotated[
        Any,
        ToolParam(
            "Output entity variable name for the combined answer set.",
            required=False,
            alias="as",
            schema={"type": "string"},
        ),
    ] = None,
    max_operand_rows: Annotated[
        Any,
        ToolParam(
            "Safety cap for each materialized operand handle. Default: 10000.",
            required=False,
            schema={"type": "integer"},
        ),
    ] = None,
    allow_large: Annotated[
        Any,
        ToolParam(
            "Override broad materialized-set guards. Use only when the user explicitly needs the full combined entity set.",
            required=False,
            schema={"type": "boolean"},
        ),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["op"] = op
    args["operands"] = operands
    if as_ is not None:
        args["as"] = as_
    if max_operand_rows is not None:
        args["max_operand_rows"] = max_operand_rows
    if allow_large is not None:
        args["allow_large"] = allow_large
    return backend._entity_set_operation(args)


@tool(
    name="set_count_by_patterns",
    status=ToolStatus.DEPRECATED,
    profile=ToolProfile.READONLY,
    purpose="Counts distinct entities satisfying a set operation over multiple server-side graph patterns without materializing branch handles.",
    description="Counts distinct entities satisfying a set operation over multiple server-side graph patterns without materializing branch handles. Use this for 'how many X either/or ...' when one branch may be very large, e.g. many companies in a country OR companies matching another condition. For OR/either use op='union'. Do NOT use expand + entity_set_operation + count_handle for broad count questions because large branches can be capped before counting. Each branch must return the same answer entity type through return_var.",
)
def tool_set_count_by_patterns(
    backend,
    branches: Annotated[
        Any,
        ToolParam(
            "Two or more server-side pattern branches. Each branch uses pattern_query-style start_label/start_as/hops/filters and must set return_var to the answer entity variable to count.",
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
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
                        "filters": {
                            "type": "array",
                            "description": "Server-side property filters. Use exact schema property names. Example: [{'var':'company','property':'name','op':'eq','value':'<company name>'}].",
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
                                        "description": "Filter operator. Use 'in'/'not_in' for list properties such as country_of_citizenship. Use 'lte' on start_year and 'gte_or_null' on end_year for active-at-year relationship intervals.",
                                    },
                                    "value": {
                                        "description": "Filter value. Required except for is_null/is_not_null. Use strings for dates like '1940-05-05'."
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
                        },
                        "hops": {
                            "type": "array",
                            "description": "Ordered traversal hops. Each hop starts from the previous variable. Use schema_inspect to choose direction.",
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
                                        "description": "Filters on this relationship's properties, e.g. [{'property':'start_year','op':'lte','value':2009}, {'property':'end_year','op':'gte_or_null','value':2009}].",
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
                                                "value": {
                                                    "description": "Filter value, e.g. 2009."
                                                },
                                                "value_type": {
                                                    "type": "string",
                                                    "enum": ["date", "string", "integer"],
                                                },
                                            },
                                            "required": ["property", "op"],
                                            "additionalProperties": True,
                                        },
                                    },
                                },
                                "required": [
                                    "relationship_type",
                                    "direction",
                                    "target_label",
                                    "as",
                                ],
                                "additionalProperties": True,
                            },
                        },
                        "select": {
                            "type": "array",
                            "description": "Properties to return as table columns. Use this when the question asks for names, years, or attributes. For list properties where the question asks for unique values, each value, or Cypher UNWIND semantics, set explode=true on that selected property.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "var": {
                                        "type": "string",
                                        "description": "Variable to project from, e.g. 'company'.",
                                    },
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
                                        "description": "Set true only for list properties when the answer needs one row per list item, e.g. unique countries from person.country_of_citizenship. This is equivalent to UNWIND on that property before DISTINCT/fetch.",
                                    },
                                },
                                "required": ["var", "property"],
                                "additionalProperties": True,
                            },
                        },
                        "group_by": {
                            "type": "array",
                            "description": "Properties to group by for aggregate outputs. Required for grouped count questions.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "var": {
                                        "type": "string",
                                        "description": "Variable to group by, e.g. 'industry'.",
                                    },
                                    "property": {
                                        "type": "string",
                                        "description": "Property to group by, usually 'name'.",
                                    },
                                    "alias": {
                                        "type": "string",
                                        "description": "Output column alias, e.g. 'industry'.",
                                    },
                                    "value_type": {
                                        "type": "string",
                                        "enum": ["date", "string", "integer"],
                                        "description": "Optional type hint.",
                                    },
                                },
                                "required": ["var", "property", "alias"],
                                "additionalProperties": True,
                            },
                        },
                        "metrics": {
                            "type": "array",
                            "description": "Aggregate metrics. Prefer count_distinct for companies, people, countries, and industries.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "op": {
                                        "type": "string",
                                        "enum": [
                                            "count",
                                            "count_distinct",
                                            "max",
                                            "min",
                                            "sum",
                                            "avg",
                                        ],
                                        "description": "Use count_distinct unless duplicates are explicitly meaningful. Use max/min/sum/avg for scalar table columns.",
                                    },
                                    "var": {
                                        "type": "string",
                                        "description": "Variable to count, e.g. 'company'.",
                                    },
                                    "property": {
                                        "type": "string",
                                        "description": "Optional scalar property for max/min/sum/avg, e.g. 'launch_year'. Do not use for count/count_distinct.",
                                    },
                                    "alias": {
                                        "type": "string",
                                        "description": "Output column name, e.g. 'company_count'.",
                                    },
                                },
                                "required": ["op", "var", "alias"],
                                "additionalProperties": True,
                            },
                        },
                        "order_by": {
                            "type": "array",
                            "description": "Sort output rows. Use field when ordering by a returned alias. Use var/property when the answer must be sorted by a graph property that should not be returned, e.g. RETURN company.name ORDER BY company.launch_year.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "field": {
                                        "type": "string",
                                        "description": "Returned alias to order by.",
                                    },
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
                                    "value_type": {
                                        "type": "string",
                                        "enum": ["date", "string", "integer"],
                                    },
                                },
                                "additionalProperties": True,
                            },
                        },
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
                            "description": "Override broad-handle safety guards. Use only when the user explicitly needs a large traversal/materialized result.",
                        },
                        "return_var": {
                            "type": "string",
                            "description": "Entity variable in this branch to count, e.g. 'company'.",
                        },
                    },
                    "required": ["start_label", "return_var"],
                    "additionalProperties": True,
                },
            },
        ),
    ],
    op: Annotated[
        Any,
        ToolParam(
            "Set operation to count. Currently use 'union' for OR/either count questions.",
            required=False,
            schema={"type": "string", "enum": ["union"]},
        ),
    ] = None,
    alias: Annotated[
        Any,
        ToolParam(
            "Output count column alias. Default: count.", required=False, schema={"type": "string"}
        ),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["branches"] = branches
    if op is not None:
        args["op"] = op
    if alias is not None:
        args["alias"] = alias
    return backend._set_count_by_patterns(args)


@tool(
    name="filter",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Filters rows already stored in a handle by one node property.",
    description="Filters rows already stored in a handle by one node property. Use for simple post-filtering after a small result has been built. Do NOT use to filter large scans; put filters inside pattern_query or build a narrower handle first.",
)
def tool_filter(
    backend,
    from_: Annotated[
        Any, ToolParam("Handle id to filter.", alias="from", schema={"type": "string"})
    ],
    var: Annotated[Any, ToolParam("Variable in the handle to filter.", schema={"type": "string"})],
    property: Annotated[Any, ToolParam("Property to filter.", schema={"type": "string"})],
    op: Annotated[
        Any,
        ToolParam(
            "Filter operator. Use 'in'/'not_in' for list properties such as country_of_citizenship. Use 'lte' on start_year and 'gte_or_null' on end_year for active-at-year relationship intervals.",
            schema={
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
            },
        ),
    ],
    value: Annotated[
        Any,
        ToolParam(
            "Filter value. Required except for is_null/is_not_null. Use strings for dates like '1940-05-05'.",
            required=False,
        ),
    ] = None,
    value_type: Annotated[
        Any,
        ToolParam(
            "Optional type hint. Use 'date' for ISO date comparisons.",
            required=False,
            schema={"type": "string", "enum": ["date", "string", "integer"]},
        ),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["from"] = from_
    args["var"] = var
    args["property"] = property
    args["op"] = op
    if value is not None:
        args["value"] = value
    if value_type is not None:
        args["value_type"] = value_type
    return backend._filter(args)


@tool(
    name="filter_same_node",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Keeps rows where two variables inside the same handle reference the same graph node.",
    description="Keeps rows where two variables inside the same handle reference the same graph node. Use for same-entity constraints after a pattern produced both variables. Do NOT use across separate handles; use join_handles or entity_set_operation instead.",
)
def tool_filter_same_node(
    backend,
    from_: Annotated[
        Any, ToolParam("Handle containing both variables.", alias="from", schema={"type": "string"})
    ],
    left_var: Annotated[Any, ToolParam("First variable name.", schema={"type": "string"})],
    right_var: Annotated[Any, ToolParam("Second variable name.", schema={"type": "string"})],
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["from"] = from_
    args["left_var"] = left_var
    args["right_var"] = right_var
    return backend._filter_same_node(args)


@tool(
    name="join_handles",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Joins two separate handles by graph node identity.",
    description="Joins two separate handles by graph node identity. Use when two independent paths should refer to the same entity. Prefer entity_set_operation for pure set union/intersection/difference.",
)
def tool_join_handles(
    backend,
    left: Annotated[Any, ToolParam("Left handle id.", schema={"type": "string"})],
    right: Annotated[Any, ToolParam("Right handle id.", schema={"type": "string"})],
    left_var: Annotated[
        Any, ToolParam("Entity variable in left handle.", required=False, schema={"type": "string"})
    ] = None,
    right_var: Annotated[
        Any,
        ToolParam("Entity variable in right handle.", required=False, schema={"type": "string"}),
    ] = None,
    op: Annotated[
        Any,
        ToolParam(
            "Join type. Default: inner.",
            required=False,
            schema={"type": "string", "enum": ["inner", "left_semi", "left_anti"]},
        ),
    ] = None,
    as_: Annotated[
        Any,
        ToolParam("Output variable name.", required=False, alias="as", schema={"type": "string"}),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["left"] = left
    args["right"] = right
    if left_var is not None:
        args["left_var"] = left_var
    if right_var is not None:
        args["right_var"] = right_var
    if op is not None:
        args["op"] = op
    if as_ is not None:
        args["as"] = as_
    return backend._join_handles(args)


@tool(
    name="same_target_role_intersection",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Finds source entities that satisfy multiple relationship roles against the same target entity.",
    description="Finds source entities that satisfy multiple relationship roles against the same target entity. Use for questions like 'people who founded and served on the board of the same company' or 'companies where the same person is CEO and board member'. Do NOT use for roles that may apply to different targets; use entity_set_operation instead. Put source/target property filters, such as citizenship exclusions, directly in filters. When selecting a list property and the question asks for unique values, each value, or UNWIND-like semantics, put explode=true on that select item. If the question asks for names sorted by a property such as launch_year, put that property in order_by with var/property but do not include it in select unless the user asks to return it. Example: for 'company names sorted by launch year', select only company.name and set order_by to company.launch_year; do not select launch_year. If a later tool must filter, combine, expand, or project these entities again, set keep_entities=true.",
)
def tool_same_target_role_intersection(
    backend,
    source_label: Annotated[
        Any, ToolParam("Entity label to return, e.g. 'Person'.", schema={"type": "string"})
    ],
    target_label: Annotated[
        Any, ToolParam("Shared related entity label, e.g. 'Company'.", schema={"type": "string"})
    ],
    relationships: Annotated[
        Any,
        ToolParam(
            "Two or more roles that connect the same source and target.",
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "relationship_type": {
                            "type": "string",
                            "description": "Relationship type from schema_inspect.",
                        },
                        "direction": {
                            "type": "string",
                            "enum": ["in", "out"],
                            "description": "Direction relative to source entity.",
                        },
                    },
                    "required": ["relationship_type", "direction"],
                    "additionalProperties": True,
                },
            },
        ),
    ],
    source_as: Annotated[
        Any,
        ToolParam(
            "Variable for the returned source entity. Default: lowercase source_label.",
            required=False,
            schema={"type": "string"},
        ),
    ] = None,
    target_as: Annotated[
        Any,
        ToolParam(
            "Variable for the shared target entity. Default: lowercase target_label.",
            required=False,
            schema={"type": "string"},
        ),
    ] = None,
    filters: Annotated[
        Any,
        ToolParam(
            "Server-side property filters. Use exact schema property names. Example: [{'var':'company','property':'name','op':'eq','value':'<company name>'}].",
            required=False,
            schema={
                "type": "array",
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
                            "description": "Filter operator. Use 'in'/'not_in' for list properties such as country_of_citizenship. Use 'lte' on start_year and 'gte_or_null' on end_year for active-at-year relationship intervals.",
                        },
                        "value": {
                            "description": "Filter value. Required except for is_null/is_not_null. Use strings for dates like '1940-05-05'."
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
            },
        ),
    ] = None,
    select: Annotated[
        Any,
        ToolParam(
            "Properties to return as table columns. Use this when the question asks for names, years, or attributes. For list properties where the question asks for unique values, each value, or Cypher UNWIND semantics, set explode=true on that selected property.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "var": {
                            "type": "string",
                            "description": "Variable to project from, e.g. 'company'.",
                        },
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
                            "description": "Set true only for list properties when the answer needs one row per list item, e.g. unique countries from person.country_of_citizenship. This is equivalent to UNWIND on that property before DISTINCT/fetch.",
                        },
                    },
                    "required": ["var", "property"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    order_by: Annotated[
        Any,
        ToolParam(
            "Sort output rows. Use field when ordering by a returned alias. Use var/property when the answer must be sorted by a graph property that should not be returned, e.g. RETURN company.name ORDER BY company.launch_year.",
            required=False,
            schema={
                "type": "array",
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
            },
        ),
    ] = None,
    distinct: Annotated[
        Any, ToolParam("Default: true.", required=False, schema={"type": "boolean"})
    ] = None,
    limit: Annotated[
        Any, ToolParam("Maximum rows. Default: 1000.", required=False, schema={"type": "integer"})
    ] = None,
    keep_entities: Annotated[
        Any,
        ToolParam(
            "Preserve source and target entity variables together with selected columns. Use true when a later tool will filter, combine, expand, or project the entities again. Default false for final scalar rows.",
            required=False,
            schema={"type": "boolean"},
        ),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["source_label"] = source_label
    args["target_label"] = target_label
    args["relationships"] = relationships
    if source_as is not None:
        args["source_as"] = source_as
    if target_as is not None:
        args["target_as"] = target_as
    if filters is not None:
        args["filters"] = filters
    if select is not None:
        args["select"] = select
    if order_by is not None:
        args["order_by"] = order_by
    if distinct is not None:
        args["distinct"] = distinct
    if limit is not None:
        args["limit"] = limit
    if keep_entities is not None:
        args["keep_entities"] = keep_entities
    return backend._same_target_role_intersection(args)


@tool(
    name="shared_role_aggregate",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Finds peer entities that share one or more related entities with a seed entity, then optionally groups/aggregates the peers server-side.",
    description="Finds peer entities that share one or more related entities with a seed entity, then optionally groups/aggregates the peers server-side. Use this ONLY when the answer entity is a peer of the seed through a common intermediate node: seed -> shared <- peer or seed <- shared -> peer. Good fit: 'entities sharing related entities with a named entity', 'other entities connected to the same intermediate entities', or 'people/entities that held the same role on the same related entities'. If the named seed was already resolved with entity_resolve/node_search, pass that handle as seed_from instead of repeating name seed_filters. The aggregation is not fixed: use metrics with op='count_distinct' for counts, or max/min/sum/avg with metric.property for scalar properties. Do NOT use this for simple same-entity multi-role constraints, where the same entity must satisfy two roles against one target; use same_target_role_intersection instead.",
)
def tool_shared_role_aggregate(
    backend,
    seed_label: Annotated[
        Any,
        ToolParam(
            "Label of the named seed entity, e.g. 'Company' or 'Person'. The seed is not usually the answer entity.",
            schema={"type": "string"},
        ),
    ],
    shared_label: Annotated[
        Any,
        ToolParam(
            "Intermediate node label shared by both seed and peer. It must be connected to both sides.",
            schema={"type": "string"},
        ),
    ],
    seed_relationship: Annotated[
        Any,
        ToolParam(
            "Relationship from seed to shared node. Direction is relative to the seed entity.",
            schema={
                "type": "object",
                "properties": {
                    "relationship_type": {
                        "type": "string",
                        "description": "Relationship type from schema.",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["out", "in"],
                        "description": "Direction relative to seed.",
                    },
                },
                "required": ["relationship_type", "direction"],
                "additionalProperties": True,
            },
        ),
    ],
    peer_label: Annotated[
        Any,
        ToolParam(
            "Label of peer entities to return/group. This is the answer entity type. If the user is not asking for peers of the seed through shared intermediates, do not use this tool.",
            schema={"type": "string"},
        ),
    ],
    peer_relationship: Annotated[
        Any,
        ToolParam(
            "Relationship from peer to the same shared node. Direction is relative to the peer entity.",
            schema={
                "type": "object",
                "properties": {
                    "relationship_type": {
                        "type": "string",
                        "description": "Relationship type from schema.",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["out", "in"],
                        "description": "Direction relative to peer.",
                    },
                },
                "required": ["relationship_type", "direction"],
                "additionalProperties": True,
            },
        ),
    ],
    seed_as: Annotated[
        Any,
        ToolParam(
            "Seed variable name. Default: 'seed'.", required=False, schema={"type": "string"}
        ),
    ] = None,
    seed_from: Annotated[
        Any,
        ToolParam(
            "Optional handle id from entity_resolve/node_search for the seed entity. Use this when you already resolved the named seed, e.g. Boeing. This is safer than repeating seed_filters because it anchors by entity id.",
            required=False,
            schema={"type": "string"},
        ),
    ] = None,
    seed_filters: Annotated[
        Any,
        ToolParam(
            "Server-side property filters. Use exact schema property names. Example: [{'var':'company','property':'name','op':'eq','value':'<company name>'}].",
            required=False,
            schema={
                "type": "array",
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
                            "description": "Filter operator. Use 'in'/'not_in' for list properties such as country_of_citizenship. Use 'lte' on start_year and 'gte_or_null' on end_year for active-at-year relationship intervals.",
                        },
                        "value": {
                            "description": "Filter value. Required except for is_null/is_not_null. Use strings for dates like '1940-05-05'."
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
            },
        ),
    ] = None,
    shared_as: Annotated[
        Any,
        ToolParam(
            "Common related node variable. Default: 'shared'.",
            required=False,
            schema={"type": "string"},
        ),
    ] = None,
    peer_as: Annotated[
        Any,
        ToolParam(
            "Peer variable name. Default: 'peer'.", required=False, schema={"type": "string"}
        ),
    ] = None,
    peer_filters: Annotated[
        Any,
        ToolParam(
            "Server-side property filters. Use exact schema property names. Example: [{'var':'company','property':'name','op':'eq','value':'<company name>'}].",
            required=False,
            schema={
                "type": "array",
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
                            "description": "Filter operator. Use 'in'/'not_in' for list properties such as country_of_citizenship. Use 'lte' on start_year and 'gte_or_null' on end_year for active-at-year relationship intervals.",
                        },
                        "value": {
                            "description": "Filter value. Required except for is_null/is_not_null. Use strings for dates like '1940-05-05'."
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
            },
        ),
    ] = None,
    shared_filters: Annotated[
        Any,
        ToolParam(
            "Server-side property filters. Use exact schema property names. Example: [{'var':'company','property':'name','op':'eq','value':'<company name>'}].",
            required=False,
            schema={
                "type": "array",
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
                            "description": "Filter operator. Use 'in'/'not_in' for list properties such as country_of_citizenship. Use 'lte' on start_year and 'gte_or_null' on end_year for active-at-year relationship intervals.",
                        },
                        "value": {
                            "description": "Filter value. Required except for is_null/is_not_null. Use strings for dates like '1940-05-05'."
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
            },
        ),
    ] = None,
    exclude_seed: Annotated[
        Any,
        ToolParam(
            "When seed and peer have the same label, exclude the seed entity from peers. Default: true.",
            required=False,
            schema={"type": "boolean"},
        ),
    ] = None,
    select: Annotated[
        Any,
        ToolParam(
            "Properties to return as table columns. Use this when the question asks for names, years, or attributes. For list properties where the question asks for unique values, each value, or Cypher UNWIND semantics, set explode=true on that selected property.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "var": {
                            "type": "string",
                            "description": "Variable to project from, e.g. 'company'.",
                        },
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
                            "description": "Set true only for list properties when the answer needs one row per list item, e.g. unique countries from person.country_of_citizenship. This is equivalent to UNWIND on that property before DISTINCT/fetch.",
                        },
                    },
                    "required": ["var", "property"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    group_by: Annotated[
        Any,
        ToolParam(
            "Properties to group by for aggregate outputs. Required for grouped count questions.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "var": {
                            "type": "string",
                            "description": "Variable to group by, e.g. 'industry'.",
                        },
                        "property": {
                            "type": "string",
                            "description": "Property to group by, usually 'name'.",
                        },
                        "alias": {
                            "type": "string",
                            "description": "Output column alias, e.g. 'industry'.",
                        },
                        "value_type": {
                            "type": "string",
                            "enum": ["date", "string", "integer"],
                            "description": "Optional type hint.",
                        },
                    },
                    "required": ["var", "property", "alias"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    metrics: Annotated[
        Any,
        ToolParam(
            "Aggregate metrics. Prefer count_distinct for companies, people, countries, and industries.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "op": {
                            "type": "string",
                            "enum": ["count", "count_distinct", "max", "min", "sum", "avg"],
                            "description": "Use count_distinct unless duplicates are explicitly meaningful. Use max/min/sum/avg for scalar table columns.",
                        },
                        "var": {
                            "type": "string",
                            "description": "Variable to count, e.g. 'company'.",
                        },
                        "property": {
                            "type": "string",
                            "description": "Optional scalar property for max/min/sum/avg, e.g. 'launch_year'. Do not use for count/count_distinct.",
                        },
                        "alias": {
                            "type": "string",
                            "description": "Output column name, e.g. 'company_count'.",
                        },
                    },
                    "required": ["op", "var", "alias"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    order_by: Annotated[
        Any,
        ToolParam(
            "Sort output rows. Use field when ordering by a returned alias. Use var/property when the answer must be sorted by a graph property that should not be returned, e.g. RETURN company.name ORDER BY company.launch_year.",
            required=False,
            schema={
                "type": "array",
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
            },
        ),
    ] = None,
    distinct: Annotated[
        Any,
        ToolParam(
            "Deduplicate selected rows. Default: true when no metrics are used.",
            required=False,
            schema={"type": "boolean"},
        ),
    ] = None,
    limit: Annotated[
        Any,
        ToolParam(
            "Maximum returned rows. Default: 1000.", required=False, schema={"type": "integer"}
        ),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["seed_label"] = seed_label
    args["shared_label"] = shared_label
    args["seed_relationship"] = seed_relationship
    args["peer_label"] = peer_label
    args["peer_relationship"] = peer_relationship
    if seed_as is not None:
        args["seed_as"] = seed_as
    if seed_from is not None:
        args["seed_from"] = seed_from
    if seed_filters is not None:
        args["seed_filters"] = seed_filters
    if shared_as is not None:
        args["shared_as"] = shared_as
    if peer_as is not None:
        args["peer_as"] = peer_as
    if peer_filters is not None:
        args["peer_filters"] = peer_filters
    if shared_filters is not None:
        args["shared_filters"] = shared_filters
    if exclude_seed is not None:
        args["exclude_seed"] = exclude_seed
    if select is not None:
        args["select"] = select
    if group_by is not None:
        args["group_by"] = group_by
    if metrics is not None:
        args["metrics"] = metrics
    if order_by is not None:
        args["order_by"] = order_by
    if distinct is not None:
        args["distinct"] = distinct
    if limit is not None:
        args["limit"] = limit
    return backend._shared_role_aggregate(args)


@tool(
    name="combine",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Low-level two-handle set operation by graph identity.",
    description="Low-level two-handle set operation by graph identity. Use only when entity_set_operation is not convenient. Do NOT use for table rows or for more than two operands.",
)
def tool_combine(
    backend,
    left: Annotated[Any, ToolParam("Left handle id.", schema={"type": "string"})],
    right: Annotated[Any, ToolParam("Right handle id.", schema={"type": "string"})],
    op: Annotated[
        Any,
        ToolParam(
            "Set operation.",
            schema={"type": "string", "enum": ["union", "intersect", "difference"]},
        ),
    ],
    left_var: Annotated[
        Any, ToolParam("Entity variable in left handle.", required=False, schema={"type": "string"})
    ] = None,
    right_var: Annotated[
        Any,
        ToolParam("Entity variable in right handle.", required=False, schema={"type": "string"}),
    ] = None,
    as_: Annotated[
        Any,
        ToolParam("Output variable name.", required=False, alias="as", schema={"type": "string"}),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["left"] = left
    args["right"] = right
    args["op"] = op
    if left_var is not None:
        args["left_var"] = left_var
    if right_var is not None:
        args["right_var"] = right_var
    if as_ is not None:
        args["as"] = as_
    return backend._combine(args)


@tool(
    name="group_handle",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Groups an existing handle and computes aggregate metrics.",
    description="Groups an existing handle and computes aggregate metrics. Use this after the handle already contains the entities needed for the answer. This keeps planning explicit: first resolve/filter/traverse/combine, then aggregate. Supports count, count_distinct, max, min, sum, and avg through metrics. Do NOT use this for OPTIONAL MATCH semantics where source rows with no target must remain; use optional_expand_count.",
)
def tool_group_handle(
    backend,
    from_: Annotated[
        Any, ToolParam("Handle id to group, e.g. 'h3'.", alias="from", schema={"type": "string"})
    ],
    group_by: Annotated[
        Any,
        ToolParam(
            "Properties to group by for aggregate outputs. Required for grouped count questions.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "var": {
                            "type": "string",
                            "description": "Variable to group by, e.g. 'industry'.",
                        },
                        "property": {
                            "type": "string",
                            "description": "Property to group by, usually 'name'.",
                        },
                        "alias": {
                            "type": "string",
                            "description": "Output column alias, e.g. 'industry'.",
                        },
                        "value_type": {
                            "type": "string",
                            "enum": ["date", "string", "integer"],
                            "description": "Optional type hint.",
                        },
                    },
                    "required": ["var", "property", "alias"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    metrics: Annotated[
        Any,
        ToolParam(
            "Aggregate metrics. Prefer count_distinct for companies, people, countries, and industries.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "op": {
                            "type": "string",
                            "enum": ["count", "count_distinct", "max", "min", "sum", "avg"],
                            "description": "Use count_distinct unless duplicates are explicitly meaningful. Use max/min/sum/avg for scalar table columns.",
                        },
                        "var": {
                            "type": "string",
                            "description": "Variable to count, e.g. 'company'.",
                        },
                        "property": {
                            "type": "string",
                            "description": "Optional scalar property for max/min/sum/avg, e.g. 'launch_year'. Do not use for count/count_distinct.",
                        },
                        "alias": {
                            "type": "string",
                            "description": "Output column name, e.g. 'company_count'.",
                        },
                    },
                    "required": ["op", "var", "alias"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["from"] = from_
    if group_by is not None:
        args["group_by"] = group_by
    if metrics is not None:
        args["metrics"] = metrics
    return backend._aggregate(args)


@tool(
    name="aggregate",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Legacy alias for group_handle.",
    description="Legacy alias for group_handle. Groups existing handle rows and computes aggregate metrics. Prefer calling group_handle in new plans.",
)
def tool_aggregate(
    backend,
    from_: Annotated[
        Any, ToolParam("Handle id to aggregate.", alias="from", schema={"type": "string"})
    ],
    group_by: Annotated[
        Any,
        ToolParam(
            "Properties to group by for aggregate outputs. Required for grouped count questions.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "var": {
                            "type": "string",
                            "description": "Variable to group by, e.g. 'industry'.",
                        },
                        "property": {
                            "type": "string",
                            "description": "Property to group by, usually 'name'.",
                        },
                        "alias": {
                            "type": "string",
                            "description": "Output column alias, e.g. 'industry'.",
                        },
                        "value_type": {
                            "type": "string",
                            "enum": ["date", "string", "integer"],
                            "description": "Optional type hint.",
                        },
                    },
                    "required": ["var", "property", "alias"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    metrics: Annotated[
        Any,
        ToolParam(
            "Aggregate metrics. Prefer count_distinct for companies, people, countries, and industries.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "op": {
                            "type": "string",
                            "enum": ["count", "count_distinct", "max", "min", "sum", "avg"],
                            "description": "Use count_distinct unless duplicates are explicitly meaningful. Use max/min/sum/avg for scalar table columns.",
                        },
                        "var": {
                            "type": "string",
                            "description": "Variable to count, e.g. 'company'.",
                        },
                        "property": {
                            "type": "string",
                            "description": "Optional scalar property for max/min/sum/avg, e.g. 'launch_year'. Do not use for count/count_distinct.",
                        },
                        "alias": {
                            "type": "string",
                            "description": "Output column name, e.g. 'company_count'.",
                        },
                    },
                    "required": ["op", "var", "alias"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["from"] = from_
    if group_by is not None:
        args["group_by"] = group_by
    if metrics is not None:
        args["metrics"] = metrics
    return backend._aggregate(args)


@tool(
    name="project",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Projects properties from entities already present in a handle.",
    description="Projects properties from entities already present in a handle. Use when the handle contains the right entities but the answer needs specific columns, distinct, ordering, or limit. For ORDER BY on a property that should not be returned, set order_by with var/property and select only the requested output columns; do not include the sort-only property in select unless the user asks to see it. Example: for 'names sorted by launch year', select name only and use order_by on launch_year. Do not set limit unless the user asks for top-N, first-N, or a limited page. distinct=true deduplicates scalar output values; do not use it for 'all entities' unless the user asks for unique values. Do NOT use before building the correct entity handle. If a later tool still needs the entity variable, such as entity_set_operation, compare, or expand, set keep_entities=true. For list properties that should be returned as individual values, set select[].explode=true, e.g. unique countries of citizenship.",
)
def tool_project(
    backend,
    from_: Annotated[
        Any, ToolParam("Handle id to project.", alias="from", schema={"type": "string"})
    ],
    select: Annotated[
        Any,
        ToolParam(
            "Properties to return as table columns. Use this when the question asks for names, years, or attributes. For list properties where the question asks for unique values, each value, or Cypher UNWIND semantics, set explode=true on that selected property.",
            required=False,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "var": {
                            "type": "string",
                            "description": "Variable to project from, e.g. 'company'.",
                        },
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
                            "description": "Set true only for list properties when the answer needs one row per list item, e.g. unique countries from person.country_of_citizenship. This is equivalent to UNWIND on that property before DISTINCT/fetch.",
                        },
                    },
                    "required": ["var", "property"],
                    "additionalProperties": True,
                },
            },
        ),
    ] = None,
    group_by: Annotated[
        Any,
        ToolParam(
            "Optional grouping keys. If provided with metrics, project delegates to the grouped aggregate path.",
            required=False,
            schema={"type": "array", "items": {"type": "object", "additionalProperties": True}},
        ),
    ] = None,
    metrics: Annotated[
        Any,
        ToolParam(
            "Optional aggregate metrics. If provided with group_by, project delegates to the grouped aggregate path.",
            required=False,
            schema={"type": "array", "items": {"type": "object", "additionalProperties": True}},
        ),
    ] = None,
    distinct: Annotated[
        Any,
        ToolParam(
            "Use true only for unique scalar/projected rows. If the input handle is already an entity set from entity_set_operation and the user asks for properties of those entities, use false so different entities with the same property value are preserved.",
            required=False,
            schema={"type": "boolean"},
        ),
    ] = None,
    distinct_scope: Annotated[
        Any,
        ToolParam(
            "Advanced override for handles from entity_set_operation. Default 'entity' preserves one projected row per distinct entity. Use 'scalar' only when the user explicitly asks for unique scalar values.",
            required=False,
            schema={"type": "string", "enum": ["entity", "scalar"]},
        ),
    ] = None,
    order_by: Annotated[
        Any,
        ToolParam(
            "Sort output rows. Use field when ordering by a returned alias. Use var/property when the answer must be sorted by a graph property that should not be returned, e.g. RETURN company.name ORDER BY company.launch_year.",
            required=False,
            schema={
                "type": "array",
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
            },
        ),
    ] = None,
    limit: Annotated[
        Any,
        ToolParam(
            "Optional maximum rows after projection. Omit this when the question asks for all/list/provide entities. Set it only for explicit top-N, first-N, sample, or page-size requests.",
            required=False,
            schema={"type": "integer"},
        ),
    ] = None,
    keep_entities: Annotated[
        Any,
        ToolParam(
            "Preserve original entity variables in the output handle. Use true when you will later call entity_set_operation, compare, expand, or another graph operation on this projected handle. Default: false.",
            required=False,
            schema={"type": "boolean"},
        ),
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["from"] = from_
    if select is not None:
        args["select"] = select
    if group_by is not None:
        args["group_by"] = group_by
    if metrics is not None:
        args["metrics"] = metrics
    if distinct is not None:
        args["distinct"] = distinct
    if distinct_scope is not None:
        args["distinct_scope"] = distinct_scope
    if order_by is not None:
        args["order_by"] = order_by
    if limit is not None:
        args["limit"] = limit
    if keep_entities is not None:
        args["keep_entities"] = keep_entities
    return backend._project(args)


@tool(
    name="compare",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Compares the first row of two handles on one property.",
    description="Compares the first row of two handles on one property. Use only for questions comparing two known entities, such as which launched later or whether two companies have the same launch year. Do NOT use for ranking many entities; use pattern_query with order_by instead. Inputs must be entity handles. If you projected first, project with keep_entities=true or compare the original entity handles.",
)
def tool_compare(
    backend,
    left: Annotated[
        Any, ToolParam("Left handle id containing one entity.", schema={"type": "string"})
    ],
    left_var: Annotated[
        Any, ToolParam("Entity variable in left handle.", schema={"type": "string"})
    ],
    right: Annotated[
        Any, ToolParam("Right handle id containing one entity.", schema={"type": "string"})
    ],
    right_var: Annotated[
        Any, ToolParam("Entity variable in right handle.", schema={"type": "string"})
    ],
    property: Annotated[
        Any, ToolParam("Property to compare, e.g. 'launch_year'.", schema={"type": "string"})
    ],
    op: Annotated[
        Any,
        ToolParam(
            "Comparison operation.",
            schema={
                "type": "string",
                "enum": ["argmax", "argmin", "eq", "neq", "gt", "gte", "lt", "lte", "difference"],
            },
        ),
    ],
    alias: Annotated[
        Any, ToolParam("Output column name.", required=False, schema={"type": "string"})
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["left"] = left
    args["left_var"] = left_var
    args["right"] = right
    args["right_var"] = right_var
    args["property"] = property
    args["op"] = op
    if alias is not None:
        args["alias"] = alias
    return backend._compare(args)


@tool(
    name="fetch",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Fetches rows from a handle and makes them the final benchmark answer.",
    description="Fetches rows from a handle and makes them the final benchmark answer. Use this only after the answer handle is complete. Do NOT fetch intermediate handles unless you need the final answer rows now. Do NOT fetch a large/capped handle for count or grouped-summary questions; call count_handle, group_handle, project, or a server-side aggregate first.",
)
def tool_fetch(
    backend,
    from_: Annotated[
        Any, ToolParam("Final answer handle id.", alias="from", schema={"type": "string"})
    ],
    limit: Annotated[
        Any, ToolParam("Rows to return. Default: 1000.", required=False, schema={"type": "integer"})
    ] = None,
    offset: Annotated[
        Any, ToolParam("Pagination offset. Default: 0.", required=False, schema={"type": "integer"})
    ] = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {}
    args["from"] = from_
    if limit is not None:
        args["limit"] = limit
    if offset is not None:
        args["offset"] = offset
    return backend._fetch(args)


__all__ = [
    "tool_summarize_handle",
    "tool_handle_recap",
    "tool_draft_tool_plan",
    "tool_validate_tool_plan",
    "tool_entity_resolve",
    "tool_node_search",
    "tool_node_scan",
    "tool_count_nodes",
    "tool_count_handle",
    "tool_expand",
    "tool_expand_aggregate",
    "tool_optional_expand_count",
    "tool_optional_count_by_pattern",
    "tool_relationship_query",
    "tool_multi_hop_query",
    "tool_pattern_query",
    "tool_top_entities_by_property",
    "tool_constraint_query",
    "tool_group_count_by_pattern",
    "tool_entity_set_operation",
    "tool_set_count_by_patterns",
    "tool_filter",
    "tool_filter_same_node",
    "tool_join_handles",
    "tool_same_target_role_intersection",
    "tool_shared_role_aggregate",
    "tool_combine",
    "tool_group_handle",
    "tool_aggregate",
    "tool_project",
    "tool_compare",
    "tool_fetch",
]
