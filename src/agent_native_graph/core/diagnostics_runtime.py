"""Runtime helpers for generic ANA diagnostics."""

from typing import Any

from agent_native_graph.core.graph_utils import _as_list, _pattern_bound_vars


def repair_empty_result(
    backend: Any,
    *,
    failed_tool: str,
    failed_args: dict[str, Any],
    error: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    failed_tool = str(failed_tool)
    failed_args = dict(failed_args or {})
    suggestions: list[dict[str, Any]] = []

    if failed_tool == "constraint_query":
        find = dict(failed_args.get("find") or {})
        find_label = str(find.get("label") or "")
        for constraint in _as_list(failed_args.get("where")):
            if isinstance(constraint, dict) and find_label:
                suggestions.append(
                    {
                        "action": "inspect_paths",
                        "args": {
                            "source_label": find_label,
                            **(
                                {"target_label": constraint.get("target_label")}
                                if constraint.get("target_label")
                                else {}
                            ),
                            "max_hops": 1,
                        },
                        "why": "Verify the one-hop relationship direction used by constraint_query.",
                    }
                )

    if failed_tool in {"pattern_query", "multi_hop_query", "group_count_by_pattern"}:
        start_label = str(failed_args.get("start_label") or "")
        hops = [hop for hop in _as_list(failed_args.get("hops")) if isinstance(hop, dict)]
        target_label = (
            str(hops[-1].get("target_label")) if hops and hops[-1].get("target_label") else None
        )
        if start_label:
            suggestions.append(
                {
                    "action": "inspect_paths",
                    "args": {
                        "source_label": start_label,
                        **({"target_label": target_label} if target_label else {}),
                        "max_hops": max(1, len(hops) or 2),
                    },
                    "why": "Verify the schema path and directions before retrying the pattern.",
                }
            )
        bound_vars = (
            _pattern_bound_vars(start_label, failed_args.get("start_as"), hops)
            if start_label
            else set()
        )
        for flt in _as_list(failed_args.get("filters")):
            if isinstance(flt, dict) and flt.get("var") and str(flt["var"]) not in bound_vars:
                suggestions.append(
                    {
                        "action": "fix_filter_var",
                        "unknown_var": str(flt["var"]),
                        "bound_vars": sorted(bound_vars),
                        "why": "The filter variable is not produced by the start node or hop aliases.",
                    }
                )
        count_var = failed_args.get("count_var")
        if count_var and bound_vars and str(count_var) not in bound_vars:
            suggestions.append(
                {
                    "action": "fix_count_var",
                    "unknown_var": str(count_var),
                    "bound_vars": sorted(bound_vars),
                    "why": "The counted variable must be one of the start or hop aliases.",
                }
            )

    if failed_tool in {"expand", "entity_set_operation", "combine", "project", "filter"}:
        for handle_key in ("from", "left", "right"):
            if failed_args.get(handle_key):
                suggestions.append(
                    {
                        "action": "summarize_handle",
                        "args": {"from": failed_args[handle_key]},
                        "why": "Inspect available variables and row shape before retrying.",
                    }
                )

    if failed_tool == "relationship_query":
        source_label = failed_args.get("source_label")
        target_label = failed_args.get("target_label")
        if source_label:
            suggestions.append(
                {
                    "action": "inspect_paths",
                    "args": {
                        "source_label": source_label,
                        **({"target_label": target_label} if target_label else {}),
                        "max_hops": 1,
                    },
                    "why": "Find the valid single-hop relationship pattern and required target_label.",
                }
            )

    if not suggestions:
        suggestions.append(
            {
                "action": "schema_overview",
                "args": {},
                "why": "Re-read labels, properties, and relationship directions before retrying.",
            }
        )

    return {
        "failed_tool": failed_tool,
        "reason": reason,
        "error": error,
        "suggestions": suggestions,
        "general_hints": [
            "After zero rows, prefer checking path direction and entity resolution before loosening filters.",
            "If an entity lookup returned multiple candidates, use summarize_handle or a stricter filter.",
            "If a handle is scalar/table-shaped, do not pass it to entity set operations.",
        ],
    }
