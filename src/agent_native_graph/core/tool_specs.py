"""Native LLM tool specifications for ANA graph tools."""

from typing import Any

from agent_native_graph.core.prompts import (
    NATIVE_SYSTEM_PROMPT as _PROMPT_NATIVE_SYSTEM_PROMPT,
)
from agent_native_graph.core.prompts import (
    native_system_prompt,
    schema_entry_prompt_section,
)
from agent_native_graph.core.tooling import registered_tool_specs
from agent_native_graph.tools import load_tool_modules

load_tool_modules()

NATIVE_SYSTEM_PROMPT = _PROMPT_NATIVE_SYSTEM_PROMPT


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
    return native_system_prompt(
        enable_planning_tools=enable_planning_tools,
        schema_entry=schema_entry,
    )


def _schema_entry_prompt_section(schema_entry: str) -> str:
    return schema_entry_prompt_section(schema_entry)


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
