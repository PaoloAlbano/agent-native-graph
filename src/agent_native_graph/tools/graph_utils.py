"""Pure graph/query utility helpers for the ANA Neo4j prototype."""

import json
import re
from typing import Any

from neo4j.graph import Node, Relationship

from agent_native_graph.domain.handles import Handle

__all__ = [
    "_as_list",
    "_row_property",
    "_metric_identity",
    "_metric_scalar_value",
    "_handle_var_labels",
    "_predicate",
    "_safe_name",
    "_server_side_entity_branches",
    "_cypher_filter_clause",
    "_cypher_property_expr",
    "_shared_role_pattern",
    "_metric_expr",
    "_return_items",
    "_normalize_aggregate_select_to_group_by",
    "_distinct_projection_vars",
    "_return_aliases",
    "_pattern_bound_vars",
    "_pattern_var_labels",
    "_pattern_var_contexts",
    "_normalize_pattern_var_references",
    "_normalize_pattern_var_reference",
    "_relationship_alias_replacement",
    "_validate_filter_binding",
    "_validate_metric_binding",
    "_question_features",
    "_schema_candidates",
    "_requires_wrapper_planning",
    "_dedupe_preserve_order",
    "_schema_paths",
    "_node_payload",
    "_tool_value",
    "_schema_path_payload",
    "_unique_var",
    "_is_node_payload",
    "_summarize_row",
    "_project_select_fields",
    "_same_target_select_fields",
    "_project_order_field",
    "_project_hidden_order_key",
    "_strip_project_hidden_order_keys",
    "_limit_clause",
    "_int_arg",
    "_int_value",
    "_bool_arg_default",
    "_distinct_rows_by_selected_entities",
    "_has_aggregation",
    "_is_valid_metric",
    "_prefer_metric_order_by",
    "_metric_alias",
    "_optional_count_source_from_group_by",
    "_safe_cypher_order_by",
    "_relationship_uniqueness_clauses",
    "_cypher_order_by",
    "_safe_constraint_order_by",
    "_constraint_return_properties",
    "_unique_query_var",
    "_looks_like_iso_date",
    "_primary_label",
    "_properties_by_label",
    "_properties_by_relationship",
    "_relationship_affordance",
    "_semantic_direction_examples",
    "_label_plural",
    "_inferred_type",
    "_temporal_relationship_affordances",
    "_temporal_affordance_for_properties",
    "_is_lookup_property",
    "_operators_for_property",
    "_safe_start_score",
    "_top_schema_matches",
    "_extract_handle_refs",
    "_compact_tool_args",
    "_expand_projected_rows",
    "_ambiguous_relationship_only_constraints",
    "_bool_arg",
    "_tokens",
    "_token_variants",
    "_distinctive_entity_search_tokens",
    "_columns",
    "_entity_vars",
    "_handle_entity_vars",
    "_distinct_rows",
    "_preview",
]


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _row_property(row: dict[str, Any], var: str, prop: str) -> Any:
    value = row.get(var)
    if isinstance(value, dict) and "properties" in value:
        return value["properties"].get(prop)
    if isinstance(value, dict):
        return value.get(prop)
    if var in row and prop == var:
        return value
    return None


def _metric_identity(row: dict[str, Any], var: str) -> Any:
    value = row.get(var)
    if _is_node_payload(value):
        return value["properties"]["id"]
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _metric_scalar_value(row: dict[str, Any], var: str, prop: Any = None) -> Any:
    if prop:
        return _row_property(row, var, str(prop))
    value = row.get(var)
    if _is_node_payload(value):
        return value["properties"].get("name") or value["properties"].get("id")
    return value


def _handle_var_labels(handle: Handle, var: str) -> set[str]:
    labels: set[str] = set()
    for row in handle.rows:
        value = row.get(var)
        if _is_node_payload(value):
            labels.update(label for label in value.get("labels", []) if label != "Entity")
    return labels


def _predicate(actual: Any, op: str, expected: Any) -> bool:
    if op == "eq":
        return actual == expected
    if op == "neq":
        return actual != expected
    if op == "gt":
        return actual is not None and actual > expected
    if op == "gte":
        return actual is not None and actual >= expected
    if op == "lt":
        return actual is not None and actual < expected
    if op == "lte":
        return actual is not None and actual <= expected
    if op == "contains":
        return actual is not None and str(expected) in str(actual)
    if op == "not_contains":
        return actual is None or str(expected) not in str(actual)
    if op == "in":
        return isinstance(actual, list) and expected in actual
    if op == "not_in":
        return isinstance(actual, list) and expected not in actual
    if op == "is_null":
        return actual is None
    if op == "is_not_null":
        return actual is not None
    raise ValueError(f"Unsupported filter op: {op}")


def _safe_name(name: str) -> str:
    return name.replace("`", "``")


def _server_side_entity_branches(
    handle: Handle, var: str
) -> tuple[list[dict[str, Any]], str | None]:
    query_metadata = handle.metadata.get("server_side_entity_query")
    if isinstance(query_metadata, dict) and str(query_metadata.get("var") or "") == var:
        return [query_metadata], str(query_metadata.get("label") or "")

    set_metadata = handle.metadata.get("server_side_entity_set")
    if isinstance(set_metadata, dict) and str(set_metadata.get("var") or "") == var:
        branches = [
            branch for branch in set_metadata.get("branches", []) if isinstance(branch, dict)
        ]
        return branches, str(set_metadata.get("label") or "")

    return [], None


def _cypher_filter_clause(flt: dict[str, Any], index: int) -> tuple[str, dict[str, Any]]:
    var = _safe_name(str(flt["var"]))
    prop = _safe_name(str(flt["property"]))
    op = str(flt["op"])
    value = flt.get("value")
    param = f"filter_{index}"
    expr = _cypher_property_expr(var, prop, flt.get("value_type"))
    param_expr = f"${param}"
    if _looks_like_iso_date(value) or str(flt.get("value_type", "")).lower() == "date":
        param_expr = f"date(${param})"
    if op == "eq":
        return f"{expr} = {param_expr}", {param: value}
    if op == "eq_ci":
        return f"toLower(toString({expr})) = toLower(toString(${param}))", {param: value}
    if op == "neq":
        return f"{expr} <> {param_expr}", {param: value}
    if op == "gt":
        return f"{expr} > {param_expr}", {param: value}
    if op == "gte":
        return f"{expr} >= {param_expr}", {param: value}
    if op == "gte_or_null":
        return f"({expr} IS NULL OR {expr} >= {param_expr})", {param: value}
    if op == "lt":
        return f"{expr} < {param_expr}", {param: value}
    if op == "lte":
        return f"{expr} <= {param_expr}", {param: value}
    if op == "lte_or_null":
        return f"({expr} IS NULL OR {expr} <= {param_expr})", {param: value}
    if op == "contains":
        return f"toString({expr}) CONTAINS ${param}", {param: value}
    if op == "not_contains":
        return f"NOT toString({expr}) CONTAINS ${param}", {param: value}
    if op == "in":
        return f"${param} IN {expr}", {param: value}
    if op == "not_in":
        return f"NOT ${param} IN {expr}", {param: value}
    if op == "is_null":
        return f"{expr} IS NULL", {}
    if op == "is_not_null":
        return f"{expr} IS NOT NULL", {}
    raise ValueError(f"Unsupported Cypher filter op: {op}")


def _cypher_property_expr(var: str, prop: str, value_type: Any = None) -> str:
    expr = f"{_safe_name(var)}.`{_safe_name(prop)}`"
    if str(value_type or "").lower() == "date":
        return expr
    return expr


def _shared_role_pattern(
    *,
    left_var: str,
    left_label: str,
    rel_var: str,
    rel_type: str,
    right_var: str,
    right_label: str,
    direction: str,
) -> str:
    if direction == "out":
        return (
            f"({left_var}:`{left_label}`)-[{rel_var}:`{rel_type}`]->({right_var}:`{right_label}`)"
        )
    if direction == "in":
        return (
            f"({left_var}:`{left_label}`)<-[{rel_var}:`{rel_type}`]-({right_var}:`{right_label}`)"
        )
    raise ValueError(f"Unsupported shared_role_aggregate direction: {direction}")


def _metric_expr(metric: dict[str, Any]) -> str:
    op = str(metric["op"])
    var = _safe_name(str(metric["var"]))
    alias = _safe_name(str(metric["alias"]))
    if op == "count_distinct":
        return f"count(DISTINCT {var}) AS `{alias}`"
    if op == "count":
        return f"count({var}) AS `{alias}`"
    if op in {"max", "min", "sum", "avg"}:
        prop = metric.get("property")
        expr = _cypher_property_expr(var, str(prop), metric.get("value_type")) if prop else var
        return f"{op}({expr}) AS `{alias}`"
    raise ValueError(f"Unsupported server-side metric op: {op}")


def _return_items(args: dict[str, Any]) -> list[str]:
    group_by = [item for item in _as_list(args.get("group_by")) if isinstance(item, dict)]
    metrics = [item for item in _as_list(args.get("metrics")) if isinstance(item, dict)]
    select = [item for item in _as_list(args.get("select")) if isinstance(item, dict)]
    if group_by or metrics:
        return_items = [
            f"{_cypher_property_expr(str(item['var']), str(item['property']), item.get('value_type'))} AS `{_safe_name(str(item['alias']))}`"
            for item in group_by
            if "var" in item and "property" in item and "alias" in item
        ]
        return_items.extend(_metric_expr(metric) for metric in metrics if _is_valid_metric(metric))
        return return_items
    return [
        f"{_cypher_property_expr(str(item['var']), str(item['property']), item.get('value_type'))} AS `{_safe_name(str(item.get('alias') or item['property']))}`"
        for item in select
        if "var" in item and "property" in item
    ]


def _normalize_aggregate_select_to_group_by(args: dict[str, Any]) -> dict[str, Any]:
    metrics = [item for item in _as_list(args.get("metrics")) if isinstance(item, dict)]
    group_by = [item for item in _as_list(args.get("group_by")) if isinstance(item, dict)]
    select = [item for item in _as_list(args.get("select")) if isinstance(item, dict)]
    if not metrics or group_by or not select:
        return args
    normalized = dict(args)
    normalized["group_by"] = [
        {
            "var": item["var"],
            "property": item["property"],
            "alias": item.get("alias") or item["property"],
            **({"value_type": item["value_type"]} if "value_type" in item else {}),
        }
        for item in select
        if "var" in item and "property" in item
    ]
    normalized.pop("select", None)
    return normalized


def _distinct_projection_vars(args: dict[str, Any]) -> list[str]:
    if not _bool_arg(args.get("distinct")):
        return []
    if _as_list(args.get("group_by")) or _as_list(args.get("metrics")):
        return []
    select = [item for item in _as_list(args.get("select")) if isinstance(item, dict)]
    if not select:
        return []
    vars_in_order: list[str] = []
    for item in select:
        var = item.get("var")
        if var is None:
            return []
        safe_var = _safe_name(str(var))
        if safe_var not in vars_in_order:
            vars_in_order.append(safe_var)
    return vars_in_order


def _return_aliases(args: dict[str, Any]) -> set[str]:
    aliases: set[str] = set()
    for item in _as_list(args.get("group_by")):
        if isinstance(item, dict) and item.get("alias"):
            aliases.add(_safe_name(str(item["alias"])))
    for metric in _as_list(args.get("metrics")):
        if isinstance(metric, dict) and metric.get("alias"):
            aliases.add(_safe_name(str(metric["alias"])))
    for item in _as_list(args.get("select")):
        if isinstance(item, dict) and item.get("var") and item.get("property"):
            aliases.add(_safe_name(str(item.get("alias") or item["property"])))
    return aliases


def _pattern_bound_vars(start_label: str, start_as: Any, hops: list[dict[str, Any]]) -> set[str]:
    current_var = str(start_as or start_label.lower())
    bound = {current_var}
    for hop in hops:
        if not isinstance(hop, dict):
            continue
        target_label = str(hop.get("target_label") or "result")
        target_var = str(hop.get("as") or target_label.lower())
        bound.add(target_var)
        current_var = target_var
    return bound


def _pattern_var_labels(
    start_label: str, start_as: Any, hops: list[dict[str, Any]]
) -> dict[str, str]:
    current_var = str(start_as or start_label.lower())
    labels = {current_var: start_label}
    for hop in hops:
        if not isinstance(hop, dict):
            continue
        target_label = str(hop.get("target_label") or "result")
        target_var = str(hop.get("as") or target_label.lower())
        labels[target_var] = target_label
        current_var = target_var
    return labels


def _pattern_var_contexts(
    start_label: str, start_as: Any, hops: list[dict[str, Any]]
) -> dict[str, dict[str, str]]:
    start_var = str(start_as or start_label.lower())
    contexts = {start_var: {"kind": "node", "label": str(start_label)}}
    for index, hop in enumerate(hops):
        if not isinstance(hop, dict):
            continue
        rel_type = str(hop.get("relationship_type") or "")
        rel_var = str(hop.get("rel_as") or f"r{index}")
        target_label = str(hop.get("target_label") or "result")
        target_var = str(hop.get("as") or target_label.lower())
        contexts[rel_var] = {"kind": "relationship", "relationship_type": rel_type}
        contexts[target_var] = {"kind": "node", "label": target_label}
    return contexts


def _normalize_pattern_var_references(
    args: dict[str, Any], contexts: dict[str, dict[str, str]]
) -> dict[str, Any]:
    relationship_vars = [
        var for var, context in contexts.items() if context.get("kind") == "relationship"
    ]
    if not relationship_vars:
        return args
    normalized = dict(args)
    for section in ("filters", "select", "group_by", "order_by"):
        normalized[section] = [
            _normalize_pattern_var_reference(item, contexts, relationship_vars)
            if isinstance(item, dict)
            else item
            for item in _as_list(normalized.get(section))
        ]
    return normalized


def _normalize_pattern_var_reference(
    item: dict[str, Any],
    contexts: dict[str, dict[str, str]],
    relationship_vars: list[str],
) -> dict[str, Any]:
    var = item.get("var")
    if not var or str(var) in contexts:
        return item
    replacement = _relationship_alias_replacement(str(var), contexts, relationship_vars)
    if not replacement:
        return item
    normalized = dict(item)
    normalized["var"] = replacement
    return normalized


def _relationship_alias_replacement(
    var: str, contexts: dict[str, dict[str, str]], relationship_vars: list[str]
) -> str | None:
    if len(relationship_vars) != 1:
        return None
    lowered = var.lower()
    rel_var = relationship_vars[0]
    rel_type = contexts[rel_var].get("relationship_type", "")
    if lowered in {"rel", "relationship", "edge", "r", "rel_prop", "relation"}:
        return rel_var
    if lowered == rel_type.lower():
        return rel_var
    return None


def _validate_filter_binding(filter_spec: Any, bound_vars: set[str]) -> None:
    if not isinstance(filter_spec, dict) or not filter_spec.get("var"):
        return
    var = str(filter_spec["var"])
    if var not in bound_vars:
        raise ValueError(
            f"Filter references unknown variable {var!r}; bound variables are "
            f"{sorted(bound_vars)}. Use a var from the start node or one of the hop aliases."
        )


def _validate_metric_binding(var: str, bound_vars: set[str]) -> None:
    if var not in bound_vars:
        raise ValueError(
            f"Metric/count references unknown variable {var!r}; bound variables are "
            f"{sorted(bound_vars)}. Count one of the start or hop aliases."
        )


def _question_features(question: str) -> dict[str, bool]:
    lowered = question.lower()
    tokens = set(_tokens(question))
    return {
        "count": bool(
            re.search(r"\bhow many\b|\bcount\b|\bnumber of\b", lowered) or "count" in tokens
        ),
        "grouped_count": bool(
            re.search(
                r"\bper\b|\bfor each\b|\bgroup\b|\bhow many .* (?:by|in which|where)", lowered
            )
        ),
        "or": bool(re.search(r"\bor\b|\beither\b", lowered)),
        "and": bool(re.search(r"\band\b|\bboth\b", lowered)),
        "comparison": bool(
            re.search(
                r"\bmore\b|\bless\b|\blater\b|\bearlier\b|\byoungest\b|\boldest\b|\bearliest\b|\blatest\b|\bdifference\b",
                lowered,
            )
        ),
        "superlative": bool(
            re.search(
                r"\byoungest\b|\boldest\b|\bearliest\b|\blatest\b|\bmost\b|\bleast\b|\bhighest\b|\blowest\b",
                lowered,
            )
        ),
        "multi_hop": bool(
            re.search(
                r"\bsubsidiar(?:y|ies) of\b|\bfounded by .* served\b|\bserved .* companies .* based\b",
                lowered,
            )
            or len(re.findall(r"\bof\b", lowered)) >= 2
        ),
    }


def _schema_candidates(schema: dict[str, Any], question: str) -> dict[str, Any]:
    question_tokens = set(_tokens(question))
    labels = [
        label
        for label in schema.get("labels", [])
        if label != "Entity" and question_tokens.intersection(_tokens(str(label)))
    ]
    properties = [
        {"label": row.get("label"), "property": row.get("property")}
        for row in schema.get("node_properties", [])
        if question_tokens.intersection(_tokens(str(row.get("property", ""))))
    ]
    relationship_types = [
        rel
        for rel in schema.get("relationship_types", [])
        if question_tokens.intersection(_tokens(str(rel)))
    ]
    entity_like_mentions = re.findall(
        r"(?:'([^']+)'|\"([^\"]+)\"|\b([A-Z][\w.&-]*(?:\s+[A-Z][\w.&-]*)+)\b)",
        question,
    )
    named_entities = [next(part for part in match if part) for match in entity_like_mentions]
    return {
        "labels": labels,
        "properties": properties[:20],
        "relationship_types": relationship_types,
        "named_entity_likely": bool(named_entities),
        "named_entity_examples": named_entities[:8],
    }


def _requires_wrapper_planning(schema: dict[str, Any], question: str) -> bool:
    features = _question_features(question)
    candidates = _schema_candidates(schema, question)
    return bool(
        features["or"]
        or features["and"]
        or features["grouped_count"]
        or features["comparison"]
        or features["superlative"]
        or features["multi_hop"]
        or len(candidates["named_entity_examples"]) > 1
    )


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _schema_paths(
    relationships: list[dict[str, str]],
    *,
    source_label: str,
    target_label: str | None,
    relationship_type: str | None,
    max_hops: int,
    limit: int,
) -> list[dict[str, Any]]:
    queue: list[tuple[str, list[dict[str, Any]]]] = [(source_label, [])]
    results: list[dict[str, Any]] = []
    while queue and len(results) < limit:
        current_label, path = queue.pop(0)
        if path and (target_label is None or current_label == target_label):
            results.append(_schema_path_payload(source_label, current_label, path))
            continue
        if len(path) >= max_hops:
            continue
        seen_labels = {source_label}
        for hop in path:
            seen_labels.add(str(hop["target_label"]))
        for rel in relationships:
            candidates = []
            if rel["source_label"] == current_label:
                candidates.append(
                    {
                        "relationship_type": rel["relationship_type"],
                        "direction": "out",
                        "target_label": rel["target_label"],
                    }
                )
            if rel["target_label"] == current_label:
                candidates.append(
                    {
                        "relationship_type": rel["relationship_type"],
                        "direction": "in",
                        "target_label": rel["source_label"],
                    }
                )
            for candidate in candidates:
                if relationship_type and candidate["relationship_type"] != relationship_type:
                    continue
                next_label = candidate["target_label"]
                if next_label in seen_labels and next_label != target_label:
                    continue
                next_var = _unique_var(next_label.lower(), path)
                queue.append((next_label, [*path, {**candidate, "as": next_var}]))
    return results


def _schema_path_payload(
    source_label: str, end_label: str, hops: list[dict[str, Any]]
) -> dict[str, Any]:
    pieces = [f"(:{source_label})"]
    for hop in hops:
        rel = hop["relationship_type"]
        target = hop["target_label"]
        if hop["direction"] == "out":
            pieces.append(f"-[:{rel}]->(:{target})")
        else:
            pieces.append(f"<-[:{rel}]-(:{target})")
    return {
        "source_label": source_label,
        "end_label": end_label,
        "hop_count": len(hops),
        "hops": hops,
        "cypher_shape": "".join(pieces),
        "use_with": {
            "pattern_query": {"start_label": source_label, "hops": hops},
            "group_handle": {
                "note": "First build this path into a handle, then group_handle that handle."
            },
        },
    }


def _node_payload(node: Any) -> dict[str, Any]:
    return {
        "labels": sorted(node.labels),
        "properties": {str(key): _tool_value(value) for key, value in dict(node).items()},
    }


def _tool_value(value: Any) -> Any:
    if isinstance(value, Node):
        return _node_payload(value)
    if isinstance(value, Relationship):
        return {
            "id": value.element_id,
            "type": value.type,
            "start": value.start_node.element_id,
            "end": value.end_node.element_id,
            "properties": {str(key): _tool_value(item) for key, item in dict(value).items()},
        }
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, list):
        return [_tool_value(item) for item in value]
    if isinstance(value, tuple):
        return [_tool_value(item) for item in value]
    return value


def _unique_var(base: str, existing_hops: list[dict[str, Any]]) -> str:
    safe = _safe_name(base)
    used = {str(hop.get("as")) for hop in existing_hops if hop.get("as")}
    if safe not in used:
        return safe
    index = 2
    while f"{safe}_{index}" in used:
        index += 1
    return f"{safe}_{index}"


def _is_node_payload(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("properties"), dict)
        and "id" in value["properties"]
    )


def _summarize_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if key == "__rel_ids":
            continue
        if _is_node_payload(value):
            out[key] = {
                "shape": "entity",
                "labels": value.get("labels", []),
                "name": value.get("properties", {}).get("name"),
                "id": value.get("properties", {}).get("id"),
            }
        else:
            out[key] = {"shape": "scalar", "value": value}
    return out


def _project_select_fields(select: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    fields: dict[tuple[str, str], str] = {}
    for item in select:
        if not isinstance(item, dict) or "var" not in item or "property" not in item:
            continue
        var = str(item["var"])
        prop = str(item["property"])
        fields[(var, prop)] = str(item.get("alias") or f"{var}.{prop}")
    return fields


def _same_target_select_fields(select: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    fields: dict[tuple[str, str], str] = {}
    for item in select:
        if not isinstance(item, dict) or "var" not in item or "property" not in item:
            continue
        fields[(str(item["var"]), str(item["property"]))] = _safe_name(
            str(item.get("alias") or item["property"])
        )
    return fields


def _project_order_field(
    order: dict[str, Any], selectable_fields: dict[tuple[str, str], str]
) -> str | None:
    if order.get("field"):
        return str(order["field"])
    if order.get("var") and order.get("property"):
        return selectable_fields.get((str(order["var"]), str(order["property"])))
    return None


def _project_hidden_order_key(index: int) -> str:
    return f"__project_order_{index}"


def _strip_project_hidden_order_keys(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not str(key).startswith("__project_order_")}


def _limit_clause(
    args: dict[str, Any], params: dict[str, Any], *, default: int | None = None
) -> str:
    raw_limit = args.get("limit", default)
    if raw_limit is None:
        return ""
    params["limit"] = _int_value(raw_limit, default=default or 0, min_value=1)
    return " LIMIT $limit"


def _int_arg(
    args: dict[str, Any],
    name: str,
    default: int,
    *,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    return _int_value(args.get(name), default=default, min_value=min_value, max_value=max_value)


def _int_value(
    value: Any,
    *,
    default: int,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    # Native tool calls may include explicit null for optional params; treat it
    # like omission so tool defaults remain stable across models.
    if value is None:
        value = default
    result = int(value)
    if min_value is not None:
        result = max(min_value, result)
    if max_value is not None:
        result = min(max_value, result)
    return result


def _bool_arg_default(value: Any, default: bool) -> bool:
    if value is None:
        return default
    return _bool_arg(value)


def _distinct_rows_by_selected_entities(
    rows: list[dict[str, Any]], select: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    selected_vars = [
        str(item["var"])
        for item in select
        if isinstance(item, dict) and item.get("var") is not None
    ]
    seen: set[tuple[tuple[str, str], ...]] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        key_parts: list[tuple[str, str]] = []
        for var in selected_vars:
            value = row.get(var)
            if not _is_node_payload(value):
                continue
            props = value.get("properties", {})
            entity_id = props.get("id") or props.get("name")
            if entity_id is not None:
                key_parts.append((var, str(entity_id)))
        if not key_parts:
            out.append(row)
            continue
        key = tuple(key_parts)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _has_aggregation(args: dict[str, Any]) -> bool:
    return bool(_as_list(args.get("group_by")) or _as_list(args.get("metrics")))


def _is_valid_metric(metric: dict[str, Any]) -> bool:
    return all(key in metric for key in ("op", "var", "alias"))


def _prefer_metric_order_by(args: dict[str, Any], metric_alias: str) -> list[dict[str, Any]]:
    order_by = [item for item in _as_list(args.get("order_by")) if isinstance(item, dict)]
    if not order_by:
        return []
    valid_aliases = _return_aliases(args) | {_safe_name(metric_alias)}
    safe: list[dict[str, Any]] = []
    for item in order_by:
        field = item.get("field")
        if field and _safe_name(str(field)) in valid_aliases:
            safe.append(item)
            continue
        safe.append({"field": metric_alias, "direction": item.get("direction", "desc")})
    return safe


def _metric_alias(args: dict[str, Any]) -> str | None:
    metrics = [item for item in _as_list(args.get("metrics")) if isinstance(item, dict)]
    if len(metrics) == 1 and metrics[0].get("alias"):
        return str(metrics[0]["alias"])
    return None


def _optional_count_source_from_group_by(
    group_by: list[dict[str, Any]],
    contexts: dict[str, dict[str, str]],
) -> str | None:
    node_vars = {
        str(item["var"])
        for item in group_by
        if str(item.get("var")) in contexts and contexts[str(item["var"])].get("kind") == "node"
    }
    if len(node_vars) == 1:
        return next(iter(node_vars))
    return None


def _safe_cypher_order_by(args: dict[str, Any]) -> str:
    order_by = [item for item in _as_list(args.get("order_by")) if isinstance(item, dict)]
    if not order_by:
        return ""
    if _bool_arg(args.get("distinct")) or _has_aggregation(args):
        valid_aliases = _return_aliases(args)
        order_by = [
            item
            for item in order_by
            if item.get("field") and _safe_name(str(item["field"])) in valid_aliases
        ]
    return _cypher_order_by(order_by)


def _relationship_uniqueness_clauses(relationship_vars: list[str]) -> list[str]:
    safe_vars = [_safe_name(str(var)) for var in relationship_vars]
    clauses: list[str] = []
    for left_index, left_var in enumerate(safe_vars):
        for right_var in safe_vars[left_index + 1 :]:
            clauses.append(f"elementId({left_var}) <> elementId({right_var})")
    return clauses


def _cypher_order_by(order_by: list[dict[str, Any]]) -> str:
    parts = []
    for item in order_by:
        direction = "DESC" if str(item.get("direction", "asc")).lower() == "desc" else "ASC"
        if item.get("field"):
            parts.append(f"`{_safe_name(str(item['field']))}` {direction}")
        elif item.get("var") and item.get("property"):
            parts.append(
                f"{_cypher_property_expr(str(item['var']), str(item['property']), item.get('value_type'))} {direction}"
            )
    return ", ".join(parts)


def _safe_constraint_order_by(args: dict[str, Any], find_var: str, return_mode: str) -> str:
    order_by = [item for item in _as_list(args.get("order_by")) if isinstance(item, dict)]
    if not order_by:
        if return_mode == "names":
            prop = _safe_name(str(args.get("return_property") or "name"))
            return f"`{_safe_name(str(args.get('alias') or prop))}` ASC"
        return ""
    safe: list[dict[str, Any]] = []
    alias = _safe_name(str(args.get("alias") or args.get("return_property") or "name"))
    for item in order_by:
        if item.get("field") and _safe_name(str(item["field"])) == alias:
            safe.append(item)
        elif item.get("var") == find_var and item.get("property"):
            safe.append(item)
    return _cypher_order_by(safe)


def _constraint_return_properties(args: dict[str, Any]) -> list[dict[str, str]]:
    properties: list[dict[str, str]] = []
    seen_aliases = {_safe_name(str(args.get("alias") or args.get("return_property") or "name"))}
    for item in _as_list(args.get("return_properties")):
        if isinstance(item, str):
            prop = item
            alias = item
        elif isinstance(item, dict) and item.get("property"):
            prop = str(item["property"])
            alias = str(item.get("alias") or prop)
        else:
            continue
        safe_alias = _safe_name(alias)
        if safe_alias in seen_aliases:
            continue
        seen_aliases.add(safe_alias)
        properties.append({"property": prop, "alias": alias})
    return properties


def _unique_query_var(base: str, used: set[str]) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]+", "_", base).strip("_") or "node"
    if safe not in used:
        return safe
    index = 2
    while f"{safe}_{index}" in used:
        index += 1
    return f"{safe}_{index}"


def _looks_like_iso_date(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None


def _primary_label(labels: list[str]) -> str:
    for label in labels:
        if label != "Entity":
            return label
    return labels[0] if labels else "Entity"


def _properties_by_label(raw_props: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for prop in raw_props:
        prop_name = str(prop["propertyName"])
        prop_types = [str(item) for item in prop.get("propertyTypes", [])]
        for label in prop.get("nodeLabels", []):
            if label == "Entity":
                continue
            out.setdefault(label, {})[prop_name] = {
                "name": prop_name,
                "tokens": _tokens(prop_name),
                "types": prop_types,
                "mandatory": bool(prop.get("mandatory")),
            }
    return {label: list(props.values()) for label, props in out.items()}


def _properties_by_relationship(raw_props: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for prop in raw_props:
        rel_type = str(prop.get("relType") or "").replace(":`", "").replace("`", "")
        if not rel_type:
            continue
        prop_name = str(prop["propertyName"])
        prop_types = [str(item) for item in prop.get("propertyTypes", [])]
        out.setdefault(rel_type, {})[prop_name] = {
            "name": prop_name,
            "tokens": _tokens(prop_name),
            "types": prop_types,
            "mandatory": bool(prop.get("mandatory")),
        }
    return {rel_type: list(props.values()) for rel_type, props in out.items()}


def _relationship_affordance(
    row: dict[str, Any], properties: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    source = str(row["source_label"])
    rel_type = str(row["relationship_type"])
    target = str(row["target_label"])
    rel_properties = [
        {
            **prop,
            "inferred_type": _inferred_type(prop["types"]),
            "operators": _operators_for_property(prop["name"], prop["types"]),
        }
        for prop in properties or []
    ]
    return {
        "source_label": source,
        "relationship_type": rel_type,
        "target_label": target,
        "tokens": _tokens(rel_type),
        "pattern": f"(:{source})-[:{rel_type}]->(:{target})",
        "direction_rule": (
            f"From {source}, use direction='out' to reach {target}. "
            f"From {target}, use direction='in' to reach {source}."
        ),
        "semantic_direction_examples": _semantic_direction_examples(source, rel_type, target),
        "properties": rel_properties,
        "temporal": _temporal_affordance_for_properties(rel_type, properties or []),
        "forward_expand": {
            "source_label": source,
            "direction": "out",
            "relationship_type": rel_type,
            "target_label": target,
        },
        "reverse_expand": {
            "source_label": target,
            "direction": "in",
            "relationship_type": rel_type,
            "target_label": source,
        },
        "ready_to_use": {
            "when_current_source_label_is_source_label": {
                "relationship_type": rel_type,
                "direction": "out",
                "target_label": target,
                "as": target.lower(),
            },
            "when_current_source_label_is_target_label": {
                "relationship_type": rel_type,
                "direction": "in",
                "target_label": source,
                "as": source.lower(),
            },
        },
    }


def _semantic_direction_examples(source: str, rel_type: str, target: str) -> list[dict[str, Any]]:
    rel_words = " ".join(_tokens(rel_type)) or rel_type
    source_plural = _label_plural(source)
    examples = [
        {
            "phrase_shape": f"{source} {rel_words} {target}",
            "meaning": f"current {source} reaches related {target}",
            "use": {"source_label": source, "direction": "out", "target_label": target},
        },
        {
            "phrase_shape": f"{target} with incoming {rel_words} from {source}",
            "meaning": f"current {target} reaches related {source}",
            "use": {"source_label": target, "direction": "in", "target_label": source},
        },
    ]
    lowered = rel_type.lower()
    if lowered.endswith("of"):
        examples.append(
            {
                "phrase_shape": f"{source_plural} of <{target}>",
                "meaning": (
                    f"the named entity is the {target}; find {source} nodes that point to it"
                ),
                "use": {"source_label": target, "direction": "in", "target_label": source},
            }
        )
    if lowered.endswith("by"):
        examples.append(
            {
                "phrase_shape": f"{source_plural} by <{target}>",
                "meaning": (
                    f"the named entity is the {target}; find {source} nodes that point to it"
                ),
                "use": {"source_label": target, "direction": "in", "target_label": source},
            }
        )
    if lowered.startswith("has"):
        examples.append(
            {
                "phrase_shape": f"{source.lower()} has {target.lower()}",
                "meaning": f"the named entity is the {source}; find related {target}",
                "use": {"source_label": source, "direction": "out", "target_label": target},
            }
        )
    return examples


def _label_plural(label: str) -> str:
    lowered = label.lower()
    if lowered.endswith("y"):
        return lowered[:-1] + "ies"
    if lowered.endswith("s"):
        return lowered
    return lowered + "s"


def _inferred_type(types: list[str]) -> str:
    joined = " ".join(types).upper()
    if "LIST" in joined:
        if "STRING" in joined:
            return "list[string]"
        if "INTEGER" in joined:
            return "list[integer]"
        return "list"
    if "INTEGER" in joined:
        return "integer"
    if "FLOAT" in joined:
        return "float"
    if "BOOLEAN" in joined:
        return "boolean"
    if "DATE" in joined:
        return "date"
    if "STRING" in joined:
        return "string"
    return "unknown"


def _temporal_relationship_affordances(
    rel_props: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    return [
        temporal
        for rel_type, props in rel_props.items()
        if (temporal := _temporal_affordance_for_properties(rel_type, props))
    ]


def _temporal_affordance_for_properties(
    rel_type: str, props: list[dict[str, Any]]
) -> dict[str, Any] | None:
    prop_names = {prop["name"] for prop in props}
    start_candidates = ["start_year", "start_date", "from_year", "from_date", "since"]
    end_candidates = ["end_year", "end_date", "to_year", "to_date", "until"]
    start_prop = next((name for name in start_candidates if name in prop_names), None)
    end_prop = next((name for name in end_candidates if name in prop_names), None)
    if not start_prop and not end_prop:
        return None
    granularity = (
        "year"
        if any(
            (start_prop or "").endswith("_year") or (end_prop or "").endswith("_year") for _ in [0]
        )
        else "date"
    )
    return {
        "relationship_type": rel_type,
        "kind": "interval",
        "granularity": granularity,
        "start_property": start_prop,
        "end_property": end_prop,
        "active_at_year_rule": (
            f"{start_prop} <= YEAR and ({end_prop} IS NULL OR {end_prop} >= YEAR)"
            if start_prop and end_prop
            else "Use the available temporal boundary property with the requested year."
        ),
        "active_at_year_filter_template": [
            {"property": start_prop, "op": "lte", "value": "YEAR"} for _ in [0] if start_prop
        ]
        + [{"property": end_prop, "op": "gte_or_null", "value": "YEAR"} for _ in [0] if end_prop],
        "tool_hint": (
            "Apply temporal constraints to relationship properties for questions "
            "like 'in 2009', not to the source or target node properties."
        ),
    }


def _is_lookup_property(name: str, types: list[str]) -> bool:
    lowered = name.lower()
    if lowered in {"name", "title", "id", "eid", "slug", "code", "identifier"}:
        return True
    if lowered.endswith("_id") or lowered.endswith("_name"):
        return True
    return any("STRING" in item for item in types) and lowered in {"aliases", "alias"}


def _operators_for_property(name: str, types: list[str]) -> list[str]:
    joined = " ".join(types).upper()
    lowered = name.lower()
    if "LIST" in joined:
        return ["in", "not_in", "is_null", "is_not_null"]
    if "INTEGER" in joined or "FLOAT" in joined or "DATE" in joined:
        return ["eq", "neq", "gt", "gte", "lt", "lte", "is_null", "is_not_null"]
    if "STRING" in joined:
        ops = ["eq", "neq", "contains", "not_contains", "is_null", "is_not_null"]
        if lowered in {"name", "title", "id", "eid"}:
            return ["eq", "neq", "contains", "not_contains"]
        return ops
    return ["eq", "neq", "is_null", "is_not_null"]


def _safe_start_score(count: int | None, lookup_props: list[str]) -> float:
    if count is None or count <= 0:
        return 0.0
    score = 1.0 / count
    if lookup_props:
        score *= 10
    return score


def _top_schema_matches(
    rows: list[tuple[int, dict[str, Any]]], limit: int
) -> list[tuple[int, dict[str, Any]]]:
    return sorted(rows, key=lambda item: item[0], reverse=True)[:limit]


def _extract_handle_refs(value: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"from", "handle", "left", "right"} and isinstance(item, str):
                refs.append(item)
            else:
                refs.extend(_extract_handle_refs(item))
    elif isinstance(value, list):
        for item in value:
            refs.extend(_extract_handle_refs(item))
    return refs


def _compact_tool_args(value: Any) -> Any:
    if isinstance(value, dict):
        keep = {
            "from",
            "handle",
            "left",
            "right",
            "source",
            "var",
            "as",
            "label",
            "text",
            "property",
            "value",
            "relationship_type",
            "direction",
            "target_label",
            "op",
            "distinct",
            "limit",
            "group_by",
            "metrics",
            "select",
            "operands",
            "hops",
            "filters",
        }
        return {str(key): _compact_tool_args(item) for key, item in value.items() if key in keep}
    if isinstance(value, list):
        return [_compact_tool_args(item) for item in value[:12]]
    if isinstance(value, str) and len(value) > 160:
        return value[:157] + "..."
    return value


def _expand_projected_rows(
    base_row: dict[str, Any],
    exploded_fields: list[tuple[str, list[Any]]],
) -> list[dict[str, Any]]:
    rows = [dict(base_row)]
    for alias, values in exploded_fields:
        expanded: list[dict[str, Any]] = []
        for row in rows:
            for value in values:
                next_row = dict(row)
                next_row[alias] = value
                expanded.append(next_row)
        rows = expanded
    return rows


def _ambiguous_relationship_only_constraints(
    constraints: list[dict[str, Any]],
) -> tuple[str, list[str]] | None:
    relationship_only_by_target: dict[tuple[str, str], list[str]] = {}
    for constraint in constraints:
        if constraint.get("property") or constraint.get("value") is not None:
            continue
        target_label = constraint.get("target_label")
        relationship_type = constraint.get("relationship_type")
        if not target_label or not relationship_type:
            continue
        direction = str(constraint.get("direction", "out"))
        key = (str(target_label), direction)
        relationship_only_by_target.setdefault(key, []).append(str(relationship_type))
    for (target_label, _direction), rel_types in relationship_only_by_target.items():
        if len(set(rel_types)) >= 2:
            return target_label, rel_types
    return None


def _bool_arg(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _tokens(value: str) -> list[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return [token.lower() for token in re.split(r"[^A-Za-z0-9]+", spaced) if token]


def _token_variants(tokens: set[str]) -> set[str]:
    variants = set(tokens)
    for token in list(tokens):
        if token.endswith("ies") and len(token) > 4:
            variants.add(token[:-3] + "y")
        if token.endswith("es") and len(token) > 3:
            variants.add(token[:-2])
        if token.endswith("s") and len(token) > 3:
            variants.add(token[:-1])
        if token == "tire":
            variants.add("tyre")
        if token == "tyre":
            variants.add("tire")
    return variants


def _distinctive_entity_search_tokens(value: str) -> set[str]:
    generic = {
        "company",
        "companies",
        "corporation",
        "person",
        "people",
        "individual",
        "individuals",
        "country",
        "countries",
        "industry",
        "industries",
        "manufacturing",
        "manufacture",
        "sector",
        "category",
    }
    tokens = set(_tokens(value))
    distinctive = {token for token in tokens if token not in generic}
    return distinctive or tokens


def _columns(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    return list(rows[0].keys())


def _entity_vars(row: dict[str, Any]) -> list[str]:
    return sorted(key for key, value in row.items() if _is_node_payload(value))


def _handle_entity_vars(rows: list[dict[str, Any]]) -> list[str]:
    found: set[str] = set()
    for row in rows:
        found.update(_entity_vars(row))
    return sorted(found)


def _distinct_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out = []
    for row in rows:
        key = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out


def _preview(
    rows: list[dict[str, Any]], *, focus: str | None, columns: list[str] | None = None
) -> list[Any]:
    if columns:
        return [{column: row.get(column) for column in columns} for row in rows[:10]]
    if focus:
        return [
            row.get(focus, {}).get("properties", {}).get("name")
            or row.get(focus, {}).get("properties", {}).get("id")
            for row in rows[:10]
        ]
    return rows[:10]
