"""Schema and graph-discovery ANA tool wrappers."""

from typing import Annotated, Any

from agent_native_graph.core.backend import AgentGraphBackend
from agent_native_graph.core.enums import ToolProfile, ToolStatus
from agent_native_graph.core.tooling import ToolParam, tool


@tool(
    name="schema_inspect",
    status=ToolStatus.EXPERIMENTAL,
    profile=ToolProfile.READONLY,
    purpose="Return full schema plus affordances in one legacy call.",
    description=(
        "Legacy schema inspection tool. Use schema_overview for normal runs. "
        "Do NOT use when schema_overview, schema_search, schema_describe_label, "
        "or schema_describe_relationship can provide a smaller targeted payload."
    ),
    legacy=True,
)
def schema_inspect(backend: AgentGraphBackend) -> dict[str, Any]:
    return backend._schema_inspect()


@tool(
    name="schema_overview",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Return a bounded overview of labels, relationships, properties, and graph affordances.",
    description=(
        "Returns the starting schema overview for planning graph tool calls. "
        "Use this at the beginning of a new graph question to discover labels, "
        "relationship types, safe starting points, direction hints, and next schema actions. "
        "Do NOT use repeatedly after it is already present for the same question."
    ),
)
def schema_overview(backend: AgentGraphBackend) -> dict[str, Any]:
    return backend._schema_overview()


@tool(
    name="schema_search",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Map natural-language keywords to candidate labels, relationships, and properties.",
    description=(
        "Searches schema labels, relationship types, node properties, and relationship "
        "properties using concise keywords from the user question. Use this when the "
        "question words do not exactly match known schema names or when choosing between "
        "candidate labels/properties. Do NOT use for graph data lookup; use entity_resolve "
        "or node_search after choosing the schema element."
    ),
)
def schema_search(
    backend: AgentGraphBackend,
    query: Annotated[
        str,
        ToolParam("Concise keywords from the question, e.g. 'company founder board member'."),
    ],
    limit: Annotated[
        int | None,
        ToolParam("Maximum candidates per section. Default: 8, max: 25.", required=False),
    ] = None,
) -> dict[str, Any]:
    return backend._schema_search({"query": query, "limit": limit})


@tool(
    name="schema_describe_label",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Describe one label with properties, examples, lookup candidates, and traversals.",
    description=(
        "Describes one node label in detail, including property names, examples, lookup "
        "properties, and traversals connected to that label. Use this before filtering "
        "or projecting properties for a specific entity type. Do NOT call it for every "
        "label; call it only for labels relevant to the current question."
    ),
)
def schema_describe_label(
    backend: AgentGraphBackend,
    label: Annotated[
        str,
        ToolParam("Exact node label from schema_overview or schema_search, e.g. 'Company'."),
    ],
) -> dict[str, Any]:
    return backend._schema_describe_label({"label": label})


@tool(
    name="schema_describe_relationship",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Describe one relationship type, endpoints, direction, properties, and temporal hints.",
    description=(
        "Describes one relationship type, including valid endpoint labels, direction "
        "relative to source/target labels, copyable traversal args, properties, and "
        "temporal hints. Use this before traversing a relationship or filtering "
        "relationship properties. Do NOT guess direction when this tool can provide it."
    ),
)
def schema_describe_relationship(
    backend: AgentGraphBackend,
    relationship_type: Annotated[
        str,
        ToolParam("Exact relationship type from schema_overview or schema_search."),
    ],
) -> dict[str, Any]:
    return backend._schema_describe_relationship({"relationship_type": relationship_type})


@tool(
    name="schema_get",
    status=ToolStatus.EXPERIMENTAL,
    profile=ToolProfile.READONLY,
    purpose="Return raw schema metadata for legacy flows.",
    description=(
        "Legacy raw schema tool. Prefer schema_overview for planning or targeted "
        "schema_search/schema_describe_* calls for smaller payloads."
    ),
    legacy=True,
)
def schema_get(backend: AgentGraphBackend) -> dict[str, Any]:
    return backend._schema_get()


@tool(
    name="schema_affordance",
    status=ToolStatus.EXPERIMENTAL,
    profile=ToolProfile.READONLY,
    purpose="Return derived schema affordances for legacy flows.",
    description=(
        "Legacy derived schema affordance tool. Prefer schema_overview or targeted "
        "schema description tools in normal agent runs."
    ),
    legacy=True,
)
def schema_affordance(backend: AgentGraphBackend) -> dict[str, Any]:
    return backend._schema_affordance()


@tool(
    name="inspect_paths",
    status=ToolStatus.CORE,
    profile=ToolProfile.READONLY,
    purpose="Find possible schema paths between labels.",
    description=(
        "Finds possible schema-level paths between labels. Use this when multi-hop "
        "structure, relationship direction, or the best path between labels is uncertain. "
        "Returned paths are schema possibilities, not proof that matching data exists."
    ),
)
def inspect_paths(
    backend: AgentGraphBackend,
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
    return backend._inspect_paths(
        {
            "source_label": source_label,
            "target_label": target_label,
            "relationship_type": relationship_type,
            "max_hops": max_hops,
            "limit": limit,
        }
    )


__all__ = [
    "schema_inspect",
    "schema_overview",
    "schema_search",
    "schema_describe_label",
    "schema_describe_relationship",
    "schema_get",
    "schema_affordance",
    "inspect_paths",
]
