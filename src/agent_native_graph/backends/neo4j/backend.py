import json
import re
from typing import Any

from neo4j import GraphDatabase, Query

from agent_native_graph.application.neo4j_benchmark import main
from agent_native_graph.core.backend import AgentGraphBackend
from agent_native_graph.core.graph_utils import (
    _ambiguous_relationship_only_constraints,
    _as_list,
    _bool_arg,
    _bool_arg_default,
    _columns,
    _constraint_return_properties,
    _cypher_filter_clause,
    _cypher_order_by,
    _cypher_property_expr,
    _dedupe_preserve_order,
    _distinct_projection_vars,
    _distinct_rows,
    _distinct_rows_by_selected_entities,
    _distinctive_entity_search_tokens,
    _entity_vars,
    _expand_projected_rows,
    _handle_entity_vars,
    _handle_var_labels,
    _inferred_type,
    _int_arg,
    _is_node_payload,
    _limit_clause,
    _metric_alias,
    _metric_expr,
    _metric_identity,
    _metric_scalar_value,
    _node_payload,
    _normalize_aggregate_select_to_group_by,
    _normalize_pattern_var_references,
    _optional_count_source_from_group_by,
    _pattern_bound_vars,
    _pattern_var_contexts,
    _pattern_var_labels,
    _predicate,
    _prefer_metric_order_by,
    _preview,
    _primary_label,
    _project_hidden_order_key,
    _project_order_field,
    _project_select_fields,
    _properties_by_label,
    _properties_by_relationship,
    _question_features,
    _relationship_uniqueness_clauses,
    _return_items,
    _row_property,
    _safe_constraint_order_by,
    _safe_cypher_order_by,
    _safe_name,
    _same_target_select_fields,
    _schema_candidates,
    _server_side_entity_branches,
    _shared_role_pattern,
    _strip_project_hidden_order_keys,
    _summarize_row,
    _token_variants,
    _tokens,
    _tool_value,
    _unique_query_var,
    _validate_filter_binding,
    _validate_metric_binding,
)
from agent_native_graph.core.handle_store import HandleStore
from agent_native_graph.core.tooling import call_registered_tool
from agent_native_graph.domain.handles import Handle


class Neo4jGraphBackend(AgentGraphBackend):
    _DEFAULT_MAX_INPUT_ROWS = 5000
    _DEFAULT_MAX_SET_OPERAND_ROWS = 10000

    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        schema: dict[str, Any],
        *,
        query_timeout_s: int | None = None,
        schema_entry: str = "overview",
    ) -> None:
        self._driver = GraphDatabase.driver(
            uri, auth=(user, password), connection_timeout=120.0, max_transaction_retry_time=120.0
        )
        self._schema = schema
        self._query_timeout_s = query_timeout_s
        self._schema_entry = schema_entry
        self._handle_store = HandleStore()
        self.last_fetch: list[list[Any]] | None = None

    def _ensure_handle_store(self) -> HandleStore:
        if not hasattr(self, "_handle_store"):
            self._handle_store = HandleStore()
        return self._handle_store

    @property
    def _handles(self) -> dict[str, Handle]:
        return self._ensure_handle_store().handles

    @_handles.setter
    def _handles(self, value: dict[str, Handle]) -> None:
        self._ensure_handle_store().handles = value

    @property
    def _handle_lineage(self) -> dict[str, list[dict[str, Any]]]:
        return self._ensure_handle_store().lineage

    @_handle_lineage.setter
    def _handle_lineage(self, value: dict[str, list[dict[str, Any]]]) -> None:
        self._ensure_handle_store().lineage = value

    @property
    def _counter(self) -> int:
        return self._ensure_handle_store().counter

    @_counter.setter
    def _counter(self, value: int) -> None:
        self._ensure_handle_store().counter = value

    def close(self) -> None:
        self._driver.close()

    def _run(self, session: Any, query: str, **params: Any) -> Any:
        statement: str | Query
        if self._query_timeout_s:
            statement = Query(query, timeout=self._query_timeout_s)
        else:
            statement = query
        return session.run(statement, **params)

    def call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        result = self._call_impl(tool, args)
        self._record_handle_lineage(tool, args, result)
        return result

    def _call_impl(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        registered_result = call_registered_tool(self, tool, args)
        if registered_result is not None:
            return registered_result
        raise ValueError(f"Unknown tool or invalid arguments for tool: {tool}")

    def _schema_inspect(self) -> dict[str, Any]:
        from agent_native_graph.backends.neo4j.schema_runtime import schema_inspect

        return schema_inspect(self)

    def _schema_overview(self) -> dict[str, Any]:
        from agent_native_graph.backends.neo4j.schema_runtime import schema_overview

        return schema_overview(self)

    def _schema_search(self, args: dict[str, Any]) -> dict[str, Any]:
        from agent_native_graph.backends.neo4j.schema_runtime import schema_search

        return schema_search(self, **args)

    def _schema_describe_label(self, args: dict[str, Any]) -> dict[str, Any]:
        from agent_native_graph.backends.neo4j.schema_runtime import schema_describe_label

        return schema_describe_label(self, **args)

    def _schema_describe_relationship(self, args: dict[str, Any]) -> dict[str, Any]:
        from agent_native_graph.backends.neo4j.schema_runtime import schema_describe_relationship

        return schema_describe_relationship(self, **args)

    def _schema_score(self, query_tokens: set[str], values: list[Any]) -> int:
        from agent_native_graph.backends.neo4j.schema_runtime import schema_score

        return schema_score(self, query_tokens, values)

    def _schema_get(self) -> dict[str, Any]:
        from agent_native_graph.backends.neo4j.schema_runtime import schema_get

        return schema_get(self)

    def _schema_affordance(self) -> dict[str, Any]:
        from agent_native_graph.backends.neo4j.schema_runtime import schema_affordance

        return schema_affordance(self)

    def _node_property_affordances(
        self, label: str, props: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        from agent_native_graph.backends.neo4j.schema_runtime import node_property_affordances

        return node_property_affordances(self, label, props)

    def _node_property_samples(self, label: str, prop: str, *, limit: int = 3) -> list[Any]:
        from agent_native_graph.backends.neo4j.schema_runtime import node_property_samples

        return node_property_samples(self, label, prop, limit=limit)

    def _relationship_property_samples(
        self, rel_type: str, prop: str, *, limit: int = 3
    ) -> list[Any]:
        from agent_native_graph.backends.neo4j.schema_runtime import relationship_property_samples

        return relationship_property_samples(self, rel_type, prop, limit=limit)

    def _inspect_paths(self, args: dict[str, Any]) -> dict[str, Any]:
        from agent_native_graph.backends.neo4j.schema_runtime import inspect_paths

        return inspect_paths(self, **args)

    def _summarize_handle(self, args: dict[str, Any]) -> dict[str, Any]:
        handle = self._handle(str(args["from"]))
        sample_limit = _int_arg(args, "sample_limit", 5, min_value=1)
        samples = handle.rows[:sample_limit]
        variables: dict[str, dict[str, Any]] = {}
        for row in handle.rows:
            for key, value in row.items():
                if key == "__rel_ids":
                    continue
                item = variables.setdefault(
                    key,
                    {
                        "name": key,
                        "shape": "unknown",
                        "labels": [],
                        "properties": [],
                        "non_null_count": 0,
                        "sample_values": [],
                    },
                )
                if value is None:
                    continue
                item["non_null_count"] += 1
                if _is_node_payload(value):
                    item["shape"] = "entity"
                    item["labels"] = sorted(set(item["labels"]) | set(value.get("labels", [])))
                    item["properties"] = sorted(
                        set(item["properties"]) | set(value.get("properties", {}).keys())
                    )
                    sample_value = value["properties"].get("name") or value["properties"].get("id")
                else:
                    item["shape"] = "scalar"
                    sample_value = value
                if len(item["sample_values"]) < sample_limit:
                    item["sample_values"].append(sample_value)

        return {
            "handle": handle.id,
            "kind": handle.kind,
            "focus": handle.focus,
            "row_count": len(handle.rows),
            "columns": handle.columns or _columns(handle.rows),
            "variables": list(variables.values()),
            "samples": [_summarize_row(row) for row in samples],
            "next_traversals": self._next_traversals_for_variables(variables),
            "planning_hints": [
                "Use entity variables with shape='entity' for expand/entity_set_operation/count_handle.",
                "Do not use scalar variables with entity_set_operation; combine entity handles before scalar-only project.",
                "Use project only after the handle contains the final entities.",
                "If a later graph operation still needs the entity, use project with keep_entities=true.",
            ],
        }

    def _handle_recap(self, args: dict[str, Any]) -> dict[str, Any]:
        handle = self._handle(str(args["from"]))
        limit = _int_arg(args, "limit", 12, min_value=1)
        lineage = list(getattr(self, "_handle_lineage", {}).get(handle.id, []))[-limit:]
        return {
            "handle": handle.id,
            "kind": handle.kind,
            "focus": handle.focus,
            "row_count": len(handle.rows),
            "entity_variables": _handle_entity_vars(handle.rows),
            "columns": handle.columns or _columns(handle.rows),
            "preview": _preview(handle.rows, focus=handle.focus, columns=handle.columns),
            "lineage": lineage,
            "available_handles": self._available_handle_summaries(),
            "planning_hints": [
                "If this is one branch of an OR/AND question, create the other branch as an entity handle, then call entity_set_operation.",
                "Use the exact handle ids and entity variable names shown here; never invent future handle ids.",
                "Project scalar answer columns only after the final entity_set_operation or graph traversal.",
            ],
        }

    def _repair_empty_result(self, args: dict[str, Any]) -> dict[str, Any]:
        from agent_native_graph.core.diagnostics_runtime import repair_empty_result

        return repair_empty_result(
            self,
            failed_tool=args.get("failed_tool", args.get("tool")),
            failed_args=args.get("failed_args", args.get("args", {})),
            error=args.get("error"),
            reason=args.get("reason"),
        )

    def _draft_tool_plan(self, args: dict[str, Any]) -> dict[str, Any]:
        question = str(args.get("question") or "")
        max_steps = _int_arg(args, "max_steps", 6, min_value=2, max_value=12)
        q_tokens = set(_tokens(question))
        features = _question_features(question)
        candidates = _schema_candidates(self._schema, question)
        recommended_tools: list[str] = []
        plan_outline: list[dict[str, Any]] = [
            {
                "phase": "schema",
                "tool": "schema_overview",
                "why": "Confirm available labels, properties, and relationship directions.",
            }
        ]

        if candidates["named_entity_likely"]:
            recommended_tools.append("entity_resolve")
            plan_outline.append(
                {
                    "phase": "anchor",
                    "tool": "entity_resolve",
                    "why": "Resolve named entities before traversing; avoid broad scans.",
                }
            )

        if features["or"] or features["and"]:
            recommended_tools.append("entity_set_operation")
            plan_outline.append(
                {
                    "phase": "branch",
                    "tool": "entity_set_operation",
                    "why": "Build each branch as entity handles, then union/intersect/difference before projection.",
                }
            )

        if features["grouped_count"]:
            recommended_tools.append("group_handle")
            plan_outline.append(
                {
                    "phase": "aggregate",
                    "tool": "group_handle",
                    "why": "First build the answer handle, then group/count it explicitly.",
                }
            )
        elif features["count"]:
            recommended_tools.append("count_handle")
            plan_outline.append(
                {
                    "phase": "count",
                    "tool": "count_handle",
                    "why": "Count final entity handle with distinct=true unless duplicates are explicitly requested.",
                }
            )
        else:
            recommended_tools.append("pattern_query")
            plan_outline.append(
                {
                    "phase": "query",
                    "tool": "pattern_query",
                    "why": "Use one anchored schema path with filters and projected answer properties.",
                }
            )

        if features["comparison"]:
            recommended_tools.append("compare")
            plan_outline.append(
                {
                    "phase": "compare",
                    "tool": "compare",
                    "why": "Compare resolved entities or branch results on the requested property.",
                }
            )

        if len(candidates["labels"]) >= 2 or features["multi_hop"]:
            recommended_tools.append("inspect_paths")
            plan_outline.insert(
                1,
                {
                    "phase": "path_check",
                    "tool": "inspect_paths",
                    "why": "Check schema path directions before executing multi-hop or reverse-worded traversals.",
                },
            )

        plan_outline.append(
            {
                "phase": "finalize",
                "tool": "project_or_fetch",
                "why": "Project only after final entities are known, then fetch answer rows.",
            }
        )

        risks = []
        if features["or"]:
            risks.append("OR questions should keep each branch as entity rows until after union.")
        if features["grouped_count"]:
            risks.append(
                "Grouped counts should use count_distinct for graph entities unless duplicates matter."
            )
        if features["comparison"]:
            risks.append(
                "Comparison questions need comparable scalar properties such as dates or launch_year."
            )
        if features["superlative"]:
            risks.append("Superlatives need explicit order_by and limit=1.")
        if "all" in q_tokens:
            risks.append(
                "Questions asking for all results still need safe limits and pagination if large."
            )

        return {
            "question": question,
            "features": features,
            "candidate_schema": candidates,
            "recommended_tools": _dedupe_preserve_order(recommended_tools),
            "plan_outline": plan_outline[:max_steps],
            "validation_required": bool(
                features["or"]
                or features["and"]
                or features["grouped_count"]
                or features["comparison"]
                or features["multi_hop"]
            ),
            "risks": risks,
            "planning_hints": [
                "Convert this outline into concrete tool calls before touching broad graph data.",
                "Use validate_tool_plan when the concrete plan has more than one graph query or any set operation.",
                "For OR/AND, project scalar answer columns only after entity_set_operation.",
                "If a branch returns zero rows unexpectedly, call repair_empty_result before continuing.",
            ],
        }

    def _validate_tool_plan(self, args: dict[str, Any]) -> dict[str, Any]:
        plan = _as_list(args.get("plan"))
        warnings: list[dict[str, Any]] = []
        schema_labels = set(self._schema_get()["labels"])
        schema_rels = {row["relationship_type"] for row in self._schema_relationships()}
        broad_tools = {"node_scan", "relationship_query", "pattern_query", "constraint_query"}
        saw_schema = False
        saw_graph_data = False

        for index, raw_step in enumerate(plan):
            if not isinstance(raw_step, dict):
                warnings.append(
                    {
                        "step": index,
                        "severity": "error",
                        "message": "Plan step must be an object with tool and optional args.",
                    }
                )
                continue
            tool = str(raw_step.get("tool") or raw_step.get("name") or "")
            step_args = dict(raw_step.get("args") or {})
            if not tool:
                warnings.append(
                    {"step": index, "severity": "error", "message": "Missing tool name."}
                )
                continue
            if tool in {
                "schema_overview",
                "schema_search",
                "schema_describe_label",
                "schema_describe_relationship",
                "schema_inspect",
            }:
                saw_schema = True
            elif tool not in {
                "draft_tool_plan",
                "validate_tool_plan",
                "repair_empty_result",
                "summarize_handle",
            }:
                saw_graph_data = True

            for key in ("label", "start_label", "source_label", "target_label"):
                if step_args.get(key) and str(step_args[key]) not in schema_labels:
                    warnings.append(
                        {
                            "step": index,
                            "severity": "error",
                            "message": f"Unknown label {step_args[key]!r} in {key}.",
                            "known_labels": sorted(schema_labels),
                        }
                    )

            hops = [hop for hop in _as_list(step_args.get("hops")) if isinstance(hop, dict)]
            for hop_i, hop in enumerate(hops):
                rel = str(hop.get("relationship_type") or "")
                target = str(hop.get("target_label") or "")
                direction = str(hop.get("direction") or "")
                if rel and rel not in schema_rels:
                    warnings.append(
                        {
                            "step": index,
                            "hop": hop_i,
                            "severity": "error",
                            "message": f"Unknown relationship_type {rel!r}.",
                            "known_relationship_types": sorted(schema_rels),
                        }
                    )
                if target and target not in schema_labels:
                    warnings.append(
                        {
                            "step": index,
                            "hop": hop_i,
                            "severity": "error",
                            "message": f"Unknown hop target_label {target!r}.",
                        }
                    )
                if direction and direction not in {"in", "out"}:
                    warnings.append(
                        {
                            "step": index,
                            "hop": hop_i,
                            "severity": "error",
                            "message": "Hop direction must be 'in' or 'out'.",
                        }
                    )

            if tool in {"pattern_query", "multi_hop_query", "constraint_query"}:
                start_label = str(step_args.get("start_label") or "")
                if tool == "constraint_query":
                    find = dict(step_args.get("find") or {})
                    start_label = str(find.get("label") or "")
                    bound_vars = (
                        {str(find.get("as") or start_label.lower())} if start_label else set()
                    )
                else:
                    bound_vars = _pattern_bound_vars(start_label, step_args.get("start_as"), hops)
                for flt in _as_list(step_args.get("filters")):
                    if (
                        isinstance(flt, dict)
                        and flt.get("var")
                        and str(flt["var"]) not in bound_vars
                    ):
                        warnings.append(
                            {
                                "step": index,
                                "severity": "error",
                                "message": f"Filter references unbound variable {flt['var']!r}.",
                                "bound_vars": sorted(bound_vars),
                            }
                        )
                count_var = step_args.get("count_var")
                if count_var and str(count_var) not in bound_vars:
                    warnings.append(
                        {
                            "step": index,
                            "severity": "error",
                            "message": f"count_var {count_var!r} is not bound by the pattern.",
                            "bound_vars": sorted(bound_vars),
                        }
                    )

            if tool == "entity_set_operation":
                operands = _as_list(step_args.get("operands"))
                if len(operands) < 2:
                    warnings.append(
                        {
                            "step": index,
                            "severity": "warning",
                            "message": "entity_set_operation usually needs at least two operands.",
                        }
                    )

            if tool == "node_scan" and not _bool_arg(step_args.get("allow_large")):
                warnings.append(
                    {
                        "step": index,
                        "severity": "warning",
                        "message": "node_scan is a last-resort diagnostic; prefer anchored tools.",
                    }
                )

            if tool in broad_tools and not saw_schema:
                warnings.append(
                    {
                        "step": index,
                        "severity": "warning",
                        "message": "Run schema_overview before broad graph data tools.",
                    }
                )

        has_fetch = any(isinstance(step, dict) and step.get("tool") == "fetch" for step in plan)
        if saw_graph_data and not has_fetch:
            warnings.append(
                {
                    "step": None,
                    "severity": "warning",
                    "message": "Executable plans should end with fetch once the final answer handle is ready.",
                }
            )

        return {
            "valid": not any(item["severity"] == "error" for item in warnings),
            "warnings": warnings,
            "plan_length": len(plan),
            "planning_hints": [
                "Fix all severity=error issues before executing the plan.",
                "Warnings can be acceptable, but broad scans and missing fetch often indicate wasted tool calls.",
                "If validating an outline rather than concrete tool calls, use the warnings to choose safer tools.",
            ],
        }

    def _label_counts(self, labels: list[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        with self._driver.session() as session:
            for label in labels:
                safe_label = _safe_name(label)
                record = self._run(
                    session,
                    f"MATCH (n:`{safe_label}`) RETURN count(n) AS count",
                ).single()
                counts[label] = int(record["count"]) if record else 0
        return counts

    def _schema_relationships(self) -> list[dict[str, str]]:
        return [
            row
            for row in self._schema["label_relationships"]
            if row["source_label"] != "Entity" and row["target_label"] != "Entity"
        ]

    def _next_traversals_for_variables(
        self, variables: dict[str, dict[str, Any]]
    ) -> list[dict[str, Any]]:
        rels = self._schema_relationships()
        out: list[dict[str, Any]] = []
        for var_name, info in variables.items():
            if info.get("shape") != "entity":
                continue
            for label in info.get("labels", []):
                if label == "Entity":
                    continue
                for rel in rels:
                    if rel["source_label"] == label:
                        out.append(
                            {
                                "var": var_name,
                                "label": label,
                                "relationship_type": rel["relationship_type"],
                                "direction": "out",
                                "target_label": rel["target_label"],
                            }
                        )
                    if rel["target_label"] == label:
                        out.append(
                            {
                                "var": var_name,
                                "label": label,
                                "relationship_type": rel["relationship_type"],
                                "direction": "in",
                                "target_label": rel["source_label"],
                            }
                        )
        return out[:30]

    def _entity_resolve(self, args: dict[str, Any]) -> dict[str, Any]:
        label = _safe_name(str(args["label"]))
        text = str(args["text"])
        var = str(args.get("as") or label.lower())
        limit = _int_arg(args, "limit", 5, min_value=1)
        if limit > 10 and not _bool_arg(args.get("allow_large")):
            limit = 10
        raw_context_terms = args.get("context_terms") or []
        if isinstance(raw_context_terms, str):
            raw_context_terms = [raw_context_terms]
        context_terms = [
            str(term).strip().lower() for term in raw_context_terms if str(term).strip()
        ]
        search_terms = sorted(_token_variants(_distinctive_entity_search_tokens(text)))
        query = (
            f"MATCH (n:`{label}`) "
            "WITH n, "
            "CASE "
            "WHEN n.name = $text THEN 0 "
            "WHEN toLower(toString(n.name)) = toLower($text) THEN 1 "
            "WHEN toLower(toString(n.name)) CONTAINS toLower($text) THEN 2 "
            "WHEN any(alias IN coalesce(n.aliases, []) WHERE toLower(toString(alias)) CONTAINS toLower($text)) THEN 3 "
            "ELSE 99 END AS score "
            "WITH n, score, "
            "CASE "
            "WHEN size($context_terms) = 0 THEN 0 "
            "WHEN all(term IN $context_terms WHERE "
            "toLower(toString(n.name)) CONTAINS term "
            "OR any(alias IN coalesce(n.aliases, []) WHERE toLower(toString(alias)) CONTAINS term) "
            "OR toLower(toString(coalesce(n.description, ''))) CONTAINS term"
            ") THEN 0 "
            "WHEN any(term IN $context_terms WHERE "
            "toLower(toString(n.name)) CONTAINS term "
            "OR any(alias IN coalesce(n.aliases, []) WHERE toLower(toString(alias)) CONTAINS term) "
            "OR toLower(toString(coalesce(n.description, ''))) CONTAINS term"
            ") THEN 1 "
            "ELSE 2 END AS context_score "
            "WHERE score < 99 "
            "WITH min(context_score) AS best_context_score, "
            "collect({n: n, score: score, context_score: context_score}) AS hits "
            "UNWIND hits AS hit "
            "WITH hit, best_context_score "
            "WHERE hit.context_score = best_context_score "
            "WITH min(hit.score) AS best_score, collect(hit) AS hits "
            "UNWIND hits AS hit "
            "WITH hit "
            "WHERE hit.score = best_score "
            "RETURN hit.n AS n ORDER BY hit.context_score, hit.score, hit.n.name LIMIT $limit"
        )
        candidates_query = (
            f"MATCH (n:`{label}`) "
            "WITH n, "
            "CASE "
            "WHEN n.name = $text THEN 0 "
            "WHEN toLower(toString(n.name)) = toLower($text) THEN 1 "
            "WHEN toLower(toString(n.name)) CONTAINS toLower($text) THEN 2 "
            "WHEN toLower($text) CONTAINS toLower(toString(n.name)) THEN 2 "
            "WHEN any(alias IN coalesce(n.aliases, []) WHERE toLower(toString(alias)) CONTAINS toLower($text)) THEN 3 "
            "WHEN any(alias IN coalesce(n.aliases, []) WHERE toLower($text) CONTAINS toLower(toString(alias))) THEN 3 "
            "ELSE 99 END AS score "
            "WITH n, score, "
            "CASE "
            "WHEN any(term IN $search_terms WHERE "
            "toLower(toString(n.name)) CONTAINS term "
            "OR any(alias IN coalesce(n.aliases, []) WHERE toLower(toString(alias)) CONTAINS term) "
            "OR toLower(toString(coalesce(n.description, ''))) CONTAINS term"
            ") THEN 4 "
            "ELSE 99 END AS token_score "
            "WITH n, score, token_score, "
            "CASE "
            "WHEN size($context_terms) = 0 THEN 0 "
            "WHEN all(term IN $context_terms WHERE "
            "toLower(toString(n.name)) CONTAINS term "
            "OR any(alias IN coalesce(n.aliases, []) WHERE toLower(toString(alias)) CONTAINS term) "
            "OR toLower(toString(coalesce(n.description, ''))) CONTAINS term"
            ") THEN 0 "
            "WHEN any(term IN $context_terms WHERE "
            "toLower(toString(n.name)) CONTAINS term "
            "OR any(alias IN coalesce(n.aliases, []) WHERE toLower(toString(alias)) CONTAINS term) "
            "OR toLower(toString(coalesce(n.description, ''))) CONTAINS term"
            ") THEN 1 "
            "ELSE 2 END AS context_score "
            "WITH n, CASE WHEN score < token_score THEN score ELSE token_score END AS score, context_score "
            "WHERE score < 99 "
            "RETURN n, score, context_score ORDER BY context_score, score, n.name LIMIT $candidate_limit"
        )
        rows = []
        candidates: list[dict[str, Any]] = []
        with self._driver.session() as session:
            for record in self._run(
                session,
                query,
                text=text,
                context_terms=context_terms,
                limit=limit,
            ):
                rows.append({var: _node_payload(record["n"]), "__rel_ids": []})
            for record in self._run(
                session,
                candidates_query,
                text=text,
                context_terms=context_terms,
                candidate_limit=max(limit, 8),
                search_terms=search_terms,
            ):
                node = _node_payload(record["n"])
                props = node.get("properties", {})
                candidates.append(
                    {
                        "name": props.get("name") or props.get("id"),
                        "labels": node.get("labels", []),
                        "score": record["score"],
                        "context_score": record["context_score"],
                        "properties": {
                            key: props[key]
                            for key in ("name", "aliases", "description")
                            if key in props
                        },
                    }
                )
        result = self._store(rows, focus=var)
        if context_terms:
            result["context_terms"] = context_terms
        selected_names = set(result.get("preview") or [])
        alternatives = [
            candidate for candidate in candidates if candidate.get("name") not in selected_names
        ]
        if alternatives:
            result["alternative_candidates"] = alternatives[:5]
            result["candidate_hint"] = (
                "If a traversal from the selected candidate returns zero rows, "
                "retry entity_resolve with context_terms from the original question "
                "or resolve a more exact candidate from alternative_candidates."
            )
        if len(rows) > 1:
            result["ambiguity_hint"] = (
                "Multiple candidates matched. If the question includes a country, "
                "parenthetical, or other qualifier, pass it in context_terms."
            )
        return result

    def _node_search(self, args: dict[str, Any]) -> dict[str, Any]:
        label = _safe_name(str(args["label"]))
        prop = _safe_name(str(args.get("property", "name")))
        value = args["value"]
        var = str(args.get("as") or label.lower())
        limit = _int_arg(args, "limit", 1000, min_value=1)
        query = f"MATCH (n:`{label}` {{{prop}: $value}}) RETURN n LIMIT $limit"
        rows = []
        with self._driver.session() as session:
            for record in self._run(session, query, value=value, limit=limit):
                rows.append({var: _node_payload(record["n"]), "__rel_ids": []})
        return self._store(rows, focus=var)

    def _value_search(self, args: dict[str, Any]) -> dict[str, Any]:
        label = _safe_name(str(args["label"]))
        prop = _safe_name(str(args["property"]))
        text = str(args["text"])
        var = str(args.get("as") or label.lower())
        limit = _int_arg(args, "limit", 20, min_value=1, max_value=100)
        match_mode = str(args.get("match_mode") or "auto").lower()
        keep_entities = _bool_arg(args.get("keep_entities", True))
        if match_mode not in {"auto", "exact", "iexact", "contains", "prefix", "suffix"}:
            raise ValueError(
                "value_search match_mode must be one of: auto, exact, iexact, "
                "contains, prefix, suffix."
            )

        query = (
            f"MATCH (n:`{label}`) "
            f"WHERE n.`{prop}` IS NOT NULL "
            f"WITH n, n.`{prop}` AS value, toLower(toString(n.`{prop}`)) AS lowered, "
            "toLower($text) AS needle "
            "WITH n, value, "
            "CASE "
            "WHEN $match_mode IN ['auto', 'exact'] AND toString(value) = $text THEN 0 "
            "WHEN $match_mode IN ['auto', 'iexact'] AND lowered = needle THEN 1 "
            "WHEN $match_mode IN ['auto', 'contains'] AND lowered CONTAINS needle THEN 2 "
            "WHEN $match_mode = 'prefix' AND lowered STARTS WITH needle THEN 3 "
            "WHEN $match_mode = 'suffix' AND lowered ENDS WITH needle THEN 4 "
            "ELSE 99 END AS score "
            "WHERE score < 99 "
            "RETURN n, value, score "
            "ORDER BY score, toString(value) "
            "LIMIT $limit"
        )
        rows: list[dict[str, Any]] = []
        with self._driver.session() as session:
            for record in self._run(
                session,
                query,
                text=text,
                match_mode=match_mode,
                limit=limit,
            ):
                value = record["value"]
                if keep_entities:
                    rows.append(
                        {
                            var: _node_payload(record["n"]),
                            "value": value,
                            "match_score": int(record["score"]),
                            "__rel_ids": [],
                        }
                    )
                else:
                    rows.append({"value": value, "match_score": int(record["score"])})

        result = self._store(
            rows,
            focus=var if keep_entities else None,
            kind="rows" if keep_entities else "table",
            columns=["value", "match_score"],
        )
        result["matched_property"] = {"label": label, "property": prop, "text": text}
        result["planning_hints"] = [
            "Use the returned value exactly in a later filter when you need a property value.",
            "If keep_entities=true, the returned handle can also be used directly by expand.",
            "Use entity_resolve instead when resolving a specific named company/person/place node.",
        ]
        return result

    def _node_scan(self, args: dict[str, Any]) -> dict[str, Any]:
        label = _safe_name(str(args["label"]))
        var = str(args.get("as") or label.lower())
        limit = _int_arg(args, "limit", 50000, min_value=1)
        if limit > 5000 and not args.get("allow_large"):
            raise ValueError(
                "node_scan is capped at 5000 unless allow_large=true. "
                "Use count_nodes, entity_resolve, relationship_query, multi_hop_query, "
                "or expand_aggregate instead."
            )
        query = f"MATCH (n:`{label}`) RETURN n LIMIT $limit"
        rows = []
        with self._driver.session() as session:
            for record in self._run(session, query, limit=limit):
                rows.append({var: _node_payload(record["n"]), "__rel_ids": []})
        return self._store(rows, focus=var)

    def _count_nodes(self, args: dict[str, Any]) -> dict[str, Any]:
        label = _safe_name(str(args["label"]))
        alias = _safe_name(str(args.get("alias") or f"{label.lower()}_count"))
        query = f"MATCH (n:`{label}`) RETURN count(n) AS `{alias}`"
        with self._driver.session() as session:
            record = self._run(session, query).single()
        rows = [{alias: int(record[alias]) if record else 0}]
        return self._store(rows, kind="table", columns=[alias])

    def _count_handle(self, args: dict[str, Any]) -> dict[str, Any]:
        handle = self._handle(str(args["from"]))
        var = args.get("var")
        alias = str(args.get("alias") or "count")
        distinct = bool(args.get("distinct", False))
        server_side_count = self._server_side_entity_set_count(handle, var=var, distinct=distinct)
        if server_side_count is not None:
            return self._store([{alias: server_side_count}], kind="table", columns=[alias])
        if var:
            values = [
                row[str(var)]["properties"].get("id")
                for row in handle.rows
                if str(var) in row and isinstance(row[str(var)], dict)
            ]
            count = len(set(values)) if distinct else len(values)
        else:
            keys = {
                json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
                for row in handle.rows
            }
            count = len(keys) if distinct else len(handle.rows)
        return self._store([{alias: count}], kind="table", columns=[alias])

    def _server_side_entity_set_count(
        self,
        handle: Handle,
        *,
        var: Any,
        distinct: bool,
    ) -> int | None:
        if not distinct or not var:
            return None
        metadata = handle.metadata.get("server_side_entity_set")
        if not isinstance(metadata, dict):
            return None
        if str(metadata.get("var") or "") != str(var):
            return None
        if metadata.get("op") != "union":
            return None
        branches = [branch for branch in metadata.get("branches", []) if isinstance(branch, dict)]
        if len(branches) < 2:
            return None

        query_parts: list[str] = []
        params: dict[str, Any] = {}
        for index, branch in enumerate(branches):
            query, branch_params = self._scoped_entity_branch_query(branch, index)
            query_parts.append(query)
            params.update(branch_params)
        query = (
            "CALL () { "
            + " UNION ".join(query_parts)
            + " } RETURN count(DISTINCT entity_id) AS `count`"
        )
        with self._driver.session() as session:
            records = self._run(session, query, **params)
            record = records.single() if hasattr(records, "single") else next(iter(records), None)
        return int(record["count"]) if record else 0

    def _scoped_entity_branch_query(
        self,
        branch: dict[str, Any],
        index: int,
    ) -> tuple[str, dict[str, Any]]:
        query = str(branch["query"])
        params = dict(branch.get("params") or {})
        renamed: dict[str, Any] = {}
        for key, value in params.items():
            scoped_key = f"b{index}_{key}"
            query = re.sub(rf"\${re.escape(str(key))}\b", f"${scoped_key}", query)
            renamed[scoped_key] = value
        return query, renamed

    def _combined_server_side_entity_metadata(
        self,
        *,
        op: str,
        left: Handle,
        right: Handle,
        left_var: str,
        right_var: str,
        out_var: str,
    ) -> dict[str, Any] | None:
        if op != "union":
            return None
        left_branches, left_label = _server_side_entity_branches(left, left_var)
        right_branches, right_label = _server_side_entity_branches(right, right_var)
        if not left_branches or not right_branches or left_label != right_label:
            return None
        return {
            "server_side_entity_set": {
                "op": "union",
                "branches": [*left_branches, *right_branches],
                "var": out_var,
                "label": left_label,
            }
        }

    def _expand(self, args: dict[str, Any]) -> dict[str, Any]:
        source_handle = self._handle(str(args["from"]))
        source_var = str(args["source"])
        rel_type = _safe_name(str(args["relationship_type"]))
        if rel_type not in set(self._schema["relationship_types"]):
            raise ValueError(
                f"Unknown relationship_type {rel_type!r}. "
                f"Supported: {self._schema['relationship_types']}"
            )
        target_label = _safe_name(str(args["target_label"]))
        target_var = str(args.get("as") or target_label.lower())
        direction = str(args.get("direction", "out"))
        limit = _int_arg(args, "limit", 10000, min_value=1)
        page_size = _int_arg(args, "page_size", 2000, min_value=1)

        input_rows = [
            {
                "row_index": index,
                "source_id": row[source_var]["properties"]["id"],
                "rel_ids": list(row.get("__rel_ids", [])),
            }
            for index, row in enumerate(source_handle.rows)
            if source_var in row
        ]
        if not input_rows:
            return self._store([], focus=target_var)
        self._guard_large_handle_input(
            source_handle,
            tool="expand",
            var=source_var,
            args=args,
            alternatives=[
                "start from a more selective entity_resolve/node_search handle",
                "use pattern_query or constraint_query with filters pushed into the pattern",
                "use expand_aggregate/optional_expand_count for grouped count questions",
                "use same_target_role_intersection for same-target multi-role questions",
            ],
        )

        if direction == "out":
            pattern = f"(s)-[r:`{rel_type}`]->(t:`{target_label}`)"
        elif direction == "in":
            pattern = f"(s)<-[r:`{rel_type}`]-(t:`{target_label}`)"
        elif direction == "both":
            pattern = f"(s)-[r:`{rel_type}`]-(t:`{target_label}`)"
        else:
            raise ValueError(f"Unsupported direction: {direction}")

        query = (
            "UNWIND $rows AS row "
            "MATCH (s {id: row.source_id}) "
            f"MATCH {pattern} "
            "WHERE NOT elementId(r) IN row.rel_ids "
            "RETURN row.row_index AS row_index, elementId(r) AS rel_id, t LIMIT $limit"
        )
        output: list[dict[str, Any]] = []
        pages = 0
        remaining = limit
        with self._driver.session() as session:
            for page_start in range(0, len(input_rows), page_size):
                if remaining <= 0:
                    break
                pages += 1
                page = input_rows[page_start : page_start + page_size]
                for record in self._run(session, query, rows=page, limit=remaining):
                    base = dict(source_handle.rows[record["row_index"]])
                    base["__rel_ids"] = [*base.get("__rel_ids", []), record["rel_id"]]
                    base[target_var] = _node_payload(record["t"])
                    output.append(base)
                    remaining -= 1
                    if remaining <= 0:
                        break
        source_ids = sorted({row["source_id"] for row in input_rows})
        count_query = (
            "UNWIND $source_ids AS source_id "
            "MATCH (s {id: source_id}) "
            f"MATCH {pattern} "
            "RETURN t.id AS entity_id"
        )
        metadata = {
            "server_side_entity_query": {
                "query": count_query,
                "params": {"source_ids": source_ids},
                "var": target_var,
                "label": target_label,
            }
        }
        result = self._store(output, focus=target_var, metadata=metadata)
        result["pages"] = pages
        result["page_size"] = page_size
        result["input_count"] = len(input_rows)
        result["limited"] = remaining <= 0
        return result

    def _expand_aggregate(self, args: dict[str, Any]) -> dict[str, Any]:
        source_handle = self._handle(str(args["from"]))
        source_var = str(args["source"])
        rel_type = _safe_name(str(args["relationship_type"]))
        if rel_type not in set(self._schema["relationship_types"]):
            raise ValueError(
                f"Unknown relationship_type {rel_type!r}. "
                f"Supported: {self._schema['relationship_types']}"
            )
        target_label = _safe_name(str(args["target_label"]))
        target_var = str(args.get("as") or target_label.lower())
        direction = str(args.get("direction", "out"))
        limit = _int_arg(args, "limit", 1000, min_value=1)
        source_nodes = [row[source_var] for row in source_handle.rows if source_var in row]
        source_ids = [node["properties"]["id"] for node in source_nodes]
        if not source_ids:
            return self._store([], kind="table", columns=[])
        source_label = _safe_name(
            str(args.get("source_label") or _primary_label(source_nodes[0].get("labels", [])))
        )
        if direction == "out":
            pattern = f"({source_var})-[r:`{rel_type}`]->({target_var}:`{target_label}`)"
        elif direction == "in":
            pattern = f"({source_var})<-[r:`{rel_type}`]-({target_var}:`{target_label}`)"
        else:
            raise ValueError(f"Unsupported direction: {direction}")

        group_by = list(args.get("group_by") or [])
        metrics = list(args.get("metrics") or [])
        return_exprs = []
        group_exprs = []
        for item in group_by:
            alias = _safe_name(str(item["alias"]))
            expr = _cypher_property_expr(
                str(item["var"]), str(item["property"]), item.get("value_type")
            )
            return_exprs.append(f"{expr} AS `{alias}`")
            group_exprs.append(f"`{alias}`")
        for metric in metrics:
            return_exprs.append(_metric_expr(metric))
        if not return_exprs:
            raise ValueError("expand_aggregate requires group_by and/or metrics")
        query = (
            f"MATCH ({source_var}:`{source_label}`) "
            f"WHERE {source_var}.id IN $source_ids "
            f"MATCH {pattern} "
            f"RETURN {', '.join(return_exprs)} "
            "LIMIT $limit"
        )
        output: list[dict[str, Any]] = []
        with self._driver.session() as session:
            for record in self._run(session, query, source_ids=source_ids, limit=limit):
                output.append({key: _tool_value(record[key]) for key in record.keys()})
        return self._store(output, kind="table", columns=_columns(output))

    def _optional_expand_count(self, args: dict[str, Any]) -> dict[str, Any]:
        source_handle = self._handle(str(args["from"]))
        source_var = str(args["source"])
        rel_type = _safe_name(str(args["relationship_type"]))
        if rel_type not in set(self._schema["relationship_types"]):
            raise ValueError(
                f"Unknown relationship_type {rel_type!r}. "
                f"Supported: {self._schema['relationship_types']}"
            )
        target_label = _safe_name(str(args["target_label"]))
        direction = str(args.get("direction", "out"))
        alias = str(args.get("alias") or "count")
        distinct = _bool_arg_default(args.get("distinct"), True)
        exclude_traversed_relationships = _bool_arg_default(
            args.get("exclude_traversed_relationships"), False
        )
        limit = _int_arg(args, "limit", 0, min_value=1) if args.get("limit") is not None else None
        group_by = [
            item
            for item in _as_list(args.get("group_by"))
            if isinstance(item, dict) and item.get("var") and item.get("property")
        ]
        if not group_by:
            group_by = [{"var": source_var, "property": "name", "alias": "name"}]

        input_rows = []
        seen_source_ids: set[Any] = set()
        for index, row in enumerate(source_handle.rows):
            if source_var not in row or not _is_node_payload(row[source_var]):
                continue
            source_id = row[source_var]["properties"]["id"]
            if source_id in seen_source_ids:
                continue
            seen_source_ids.add(source_id)
            input_rows.append(
                {
                    "row_index": index,
                    "source_id": source_id,
                    "rel_ids": list(row.get("__rel_ids", [])),
                }
            )
        if not input_rows:
            columns = [str(item.get("alias") or item["property"]) for item in group_by]
            return self._store([], kind="table", columns=[*columns, alias])
        if direction == "out":
            pattern = f"(s)-[r:`{rel_type}`]->(t:`{target_label}`)"
        elif direction == "in":
            pattern = f"(s)<-[r:`{rel_type}`]-(t:`{target_label}`)"
        else:
            raise ValueError(f"Unsupported optional_expand_count direction: {direction}")

        count_expr = "count(DISTINCT t)" if distinct else "count(t)"
        params = {"rows": input_rows}
        query = f"UNWIND $rows AS row MATCH (s {{id: row.source_id}}) OPTIONAL MATCH {pattern} "
        if exclude_traversed_relationships:
            query += "WHERE r IS NULL OR NOT elementId(r) IN row.rel_ids "
        query += f"RETURN row.row_index AS row_index, {count_expr} AS related_count "
        query += _limit_clause(args, params)
        counts_by_index: dict[int, int] = {row["row_index"]: 0 for row in input_rows}
        with self._driver.session() as session:
            for record in self._run(session, query, **params):
                counts_by_index[int(record["row_index"])] = int(record["related_count"] or 0)

        output: list[dict[str, Any]] = []
        for input_row in input_rows if limit is None else input_rows[:limit]:
            source_row = source_handle.rows[input_row["row_index"]]
            out: dict[str, Any] = {}
            for item in group_by:
                out[str(item.get("alias") or item["property"])] = _row_property(
                    source_row, str(item["var"]), str(item["property"])
                )
            out[alias] = counts_by_index.get(input_row["row_index"], 0)
            output.append(out)
        columns = [str(item.get("alias") or item["property"]) for item in group_by]
        result = self._store(output, kind="table", columns=[*columns, alias])
        result["finalization_hint"] = (
            "This is already a left-preserving aggregate table. If these columns "
            "match the requested answer, call fetch on this handle next. Do not "
            "call expand, project, or group_handle again unless the question asks "
            "for additional columns."
        )
        result["columns"] = [*columns, alias]
        return result

    def _optional_count_by_pattern(self, args: dict[str, Any]) -> dict[str, Any]:
        args = dict(args)
        start_label = _safe_name(str(args["start_label"]))
        current_var = str(args.get("start_as") or start_label.lower())
        hops = list(args.get("hops") or [])
        if not hops:
            raise ValueError("optional_count_by_pattern requires at least one source-building hop")
        if not isinstance(args.get("optional_relationship"), dict):
            raise ValueError(
                "optional_count_by_pattern requires optional_relationship with "
                "relationship_type, direction, and target_label. Use this tool only "
                "for OPTIONAL MATCH + count semantics where source rows with zero "
                "related targets must still appear. If you only need a normal path "
                "traversal, use pattern_query. If you already have the source handle, "
                "use optional_expand_count."
            )
        optional_rel = dict(args["optional_relationship"])
        params: dict[str, Any] = {}
        query_parts = [f"MATCH ({current_var}:`{start_label}`)"]

        source_handle_id = args.get("from")
        if source_handle_id:
            source_handle = self._handle(str(source_handle_id))
            source_ids = [
                row[current_var]["properties"]["id"]
                for row in source_handle.rows
                if current_var in row
            ]
            params["source_ids"] = source_ids
            query_parts.append(f"WHERE {current_var}.id IN $source_ids")

        relationship_filters: list[dict[str, Any]] = []
        for index, hop in enumerate(hops):
            rel_type = _safe_name(str(hop["relationship_type"]))
            if rel_type not in set(self._schema["relationship_types"]):
                raise ValueError(
                    f"Unknown relationship_type {rel_type!r}. "
                    f"Supported: {self._schema['relationship_types']}"
                )
            target_label = _safe_name(str(hop["target_label"]))
            target_var = str(hop.get("as") or target_label.lower())
            direction = str(hop.get("direction", "out"))
            rel_var = str(hop.get("rel_as") or f"r{index}")
            if direction == "out":
                pattern = (
                    f"({current_var})-[{rel_var}:`{rel_type}`]->({target_var}:`{target_label}`)"
                )
            elif direction == "in":
                pattern = (
                    f"({current_var})<-[{rel_var}:`{rel_type}`]-({target_var}:`{target_label}`)"
                )
            else:
                raise ValueError(
                    f"Unsupported optional_count_by_pattern hop direction: {direction}"
                )
            query_parts.append(f"MATCH {pattern}")
            for rel_filter in _as_list(hop.get("relationship_filters")):
                if not isinstance(rel_filter, dict):
                    continue
                normalized_filter = dict(rel_filter)
                normalized_filter.setdefault("var", rel_var)
                relationship_filters.append(normalized_filter)
            current_var = target_var

        contexts = _pattern_var_contexts(start_label, args.get("start_as"), hops)
        group_by = [
            item
            for item in _as_list(args.get("group_by"))
            if isinstance(item, dict) and item.get("var") and item.get("property")
        ]
        source_var = str(
            args.get("source")
            or _optional_count_source_from_group_by(group_by, contexts)
            or current_var
        )
        if source_var not in contexts or contexts[source_var].get("kind") != "node":
            raise ValueError(
                "optional_count_by_pattern source must be a node variable produced by "
                f"start_as/hops. Got {source_var!r}; available: {sorted(contexts)}"
            )

        args["filters"] = [*list(args.get("filters") or []), *relationship_filters]
        args = _normalize_pattern_var_references(args, contexts)
        where_parts: list[str] = []
        for index, flt in enumerate(list(args.get("filters") or [])):
            _validate_filter_binding(flt, set(contexts))
            flt = self._normalize_filter_for_context(
                flt,
                contexts=contexts,
                context="optional_count_by_pattern.filters",
            )
            clause, clause_params = _cypher_filter_clause(flt, index)
            where_parts.append(clause)
            params.update(clause_params)
        self._validate_projection_context_properties(
            args,
            contexts,
            context="optional_count_by_pattern",
        )
        if where_parts:
            query_parts.append("WHERE " + " AND ".join(where_parts))

        if not group_by:
            group_by = [{"var": source_var, "property": "name", "alias": "name"}]
        with_vars = [source_var]
        for item in group_by:
            var = str(item["var"])
            if var not in contexts:
                raise ValueError(
                    f"optional_count_by_pattern group_by var {var!r} is not bound. "
                    f"Available variables: {sorted(contexts)}. Use one of the "
                    "available variables in group_by, or add a prior hop that binds "
                    f"{var!r} before grouping. If you need to count an optional target, "
                    "put that variable in optional_relationship.as instead of group_by."
                )
            if contexts[var].get("kind") == "node" and var not in with_vars:
                with_vars.append(var)

        optional_rel_type = _safe_name(str(optional_rel["relationship_type"]))
        if optional_rel_type not in set(self._schema["relationship_types"]):
            raise ValueError(
                f"Unknown optional relationship_type {optional_rel_type!r}. "
                f"Supported: {self._schema['relationship_types']}"
            )
        optional_target_label = _safe_name(str(optional_rel["target_label"]))
        optional_target_var = str(optional_rel.get("as") or optional_target_label.lower())
        optional_rel_var = str(optional_rel.get("rel_as") or "optional_rel")
        optional_direction = str(optional_rel.get("direction", "out"))
        if optional_direction == "out":
            optional_pattern = (
                f"({source_var})-[{optional_rel_var}:`{optional_rel_type}`]->"
                f"({optional_target_var}:`{optional_target_label}`)"
            )
        elif optional_direction == "in":
            optional_pattern = (
                f"({source_var})<-[{optional_rel_var}:`{optional_rel_type}`]-"
                f"({optional_target_var}:`{optional_target_label}`)"
            )
        else:
            raise ValueError(
                f"Unsupported optional_count_by_pattern optional direction: {optional_direction}"
            )

        optional_contexts = {
            **contexts,
            optional_rel_var: {
                "kind": "relationship",
                "relationship_type": optional_rel_type,
            },
            optional_target_var: {"kind": "node", "label": optional_target_label},
        }
        optional_filter_parts: list[str] = []
        filter_offset = len(params)
        for offset, flt in enumerate(_as_list(optional_rel.get("relationship_filters"))):
            if not isinstance(flt, dict):
                continue
            normalized_filter = dict(flt)
            normalized_filter.setdefault("var", optional_rel_var)
            normalized_filter = self._normalize_filter_for_context(
                normalized_filter,
                contexts=optional_contexts,
                context="optional_count_by_pattern.optional_relationship.relationship_filters",
            )
            clause, clause_params = _cypher_filter_clause(normalized_filter, filter_offset + offset)
            optional_filter_parts.append(clause)
            params.update(clause_params)

        alias = _safe_name(str(args.get("alias") or _metric_alias(args) or "count"))
        count_expr = (
            f"count(DISTINCT {optional_target_var})"
            if args.get("distinct") is not False
            else f"count({optional_target_var})"
        )
        return_items = [
            f"{_cypher_property_expr(str(item['var']), str(item['property']), item.get('value_type'))} AS `{_safe_name(str(item.get('alias') or item['property']))}`"
            for item in group_by
        ]
        return_items.append(f"{count_expr} AS `{alias}`")

        query = " ".join(query_parts)
        query += f" WITH DISTINCT {', '.join(with_vars)}"
        query += f" OPTIONAL MATCH {optional_pattern}"
        if optional_filter_parts:
            query += (
                " WHERE "
                + f"{optional_rel_var} IS NULL OR ("
                + " AND ".join(optional_filter_parts)
                + ")"
            )
        query += f" RETURN {', '.join(return_items)}"
        order_by = _safe_cypher_order_by(
            {
                "order_by": args.get("order_by"),
                "group_by": group_by,
                "metrics": [{"op": "count", "var": optional_target_var, "alias": alias}],
            }
        )
        if order_by:
            query += f" ORDER BY {order_by}"
        query += _limit_clause(args, params)

        output: list[dict[str, Any]] = []
        with self._driver.session() as session:
            for record in self._run(session, query, **params):
                output.append({key: _tool_value(record[key]) for key in record.keys()})
        columns = [str(item.get("alias") or item["property"]) for item in group_by]
        result = self._store(output, kind="table", columns=[*columns, alias])
        result["finalization_hint"] = (
            "This is already a left-preserving optional aggregate table. If these "
            "columns match the requested answer, call fetch on this handle next."
        )
        result["columns"] = [*columns, alias]
        return result

    def _relationship_query(self, args: dict[str, Any]) -> dict[str, Any]:
        if "target_label" not in args:
            raise ValueError("relationship_query requires target_label")
        source_label = _safe_name(str(args["source_label"]))
        target_label = _safe_name(str(args["target_label"]))
        source_var = str(args.get("source_as") or source_label.lower())
        target_var = str(args.get("target_as") or target_label.lower())
        rel_type = _safe_name(str(args["relationship_type"]))
        rel_var = str(args.get("rel_as") or args.get("relationship_as") or "rel")
        if rel_type not in set(self._schema["relationship_types"]):
            raise ValueError(
                f"Unknown relationship_type {rel_type!r}. "
                f"Supported: {self._schema['relationship_types']}"
            )
        direction = str(args.get("direction", "out"))
        if direction == "out":
            pattern = f"({source_var}:`{source_label}`)-[{rel_var}:`{rel_type}`]->({target_var}:`{target_label}`)"
        elif direction == "in":
            pattern = f"({source_var}:`{source_label}`)<-[{rel_var}:`{rel_type}`]-({target_var}:`{target_label}`)"
        else:
            raise ValueError(f"Unsupported relationship_query direction: {direction}")
        contexts = {
            source_var: {"kind": "node", "label": source_label},
            target_var: {"kind": "node", "label": target_label},
            rel_var: {"kind": "relationship", "relationship_type": rel_type},
        }
        args = _normalize_pattern_var_references(dict(args), contexts)
        where_parts: list[str] = []
        params: dict[str, Any] = {}
        for index, flt in enumerate(list(args.get("filters") or [])):
            _validate_filter_binding(flt, set(contexts))
            flt = self._normalize_filter_for_context(
                flt,
                contexts=contexts,
                context="relationship_query.filters",
            )
            clause, clause_params = _cypher_filter_clause(flt, index)
            where_parts.append(clause)
            params.update(clause_params)
        self._validate_projection_context_properties(args, contexts, context="relationship_query")
        group_by = list(args.get("group_by") or [])
        metrics = list(args.get("metrics") or [])
        select = list(args.get("select") or [])
        return_items = _return_items({"group_by": group_by, "metrics": metrics, "select": select})
        if not return_items:
            return_items = [f"{source_var} AS source", f"{target_var} AS target"]
        distinct_kw = "DISTINCT " if _bool_arg(args.get("distinct")) else ""
        query = f"MATCH {pattern}"
        if where_parts:
            query += " WHERE " + " AND ".join(where_parts)
        query += f" RETURN {distinct_kw}{', '.join(return_items)}"
        order_by = _cypher_order_by(list(args.get("order_by") or []))
        if order_by:
            query += f" ORDER BY {order_by}"
        query += _limit_clause(args, params)
        output: list[dict[str, Any]] = []
        with self._driver.session() as session:
            for record in self._run(session, query, **params):
                output.append({key: _tool_value(record[key]) for key in record.keys()})
        return self._store(output, kind="table", columns=_columns(output))

    def _multi_hop_query(self, args: dict[str, Any]) -> dict[str, Any]:
        args = dict(args)
        start_label = _safe_name(str(args["start_label"]))
        current_var = str(args.get("start_as") or start_label.lower())
        hops = list(args.get("hops") or [])
        if not hops:
            raise ValueError("multi_hop_query requires at least one hop")
        params: dict[str, Any] = {}
        query_parts = [f"MATCH ({current_var}:`{start_label}`)"]

        source_handle_id = args.get("from")
        if source_handle_id:
            source_handle = self._handle(str(source_handle_id))
            self._guard_large_handle_input(
                source_handle,
                tool="pattern_query",
                var=current_var,
                args=args,
                alternatives=[
                    "push the filter into pattern_query instead of starting from a broad handle",
                    "use constraint_query for one entity type satisfying multiple relationship constraints",
                    "use expand_aggregate/group_handle for grouped counts",
                    "use top_entities_by_property for earliest/latest/youngest questions",
                ],
            )
            source_ids = [
                row[current_var]["properties"]["id"]
                for row in source_handle.rows
                if current_var in row
            ]
            params["source_ids"] = source_ids
            query_parts.append(f"WHERE {current_var}.id IN $source_ids")

        relationship_filters: list[dict[str, Any]] = []
        relationship_vars: list[str] = []
        for index, hop in enumerate(hops):
            rel_type = _safe_name(str(hop["relationship_type"]))
            if rel_type not in set(self._schema["relationship_types"]):
                raise ValueError(
                    f"Unknown relationship_type {rel_type!r}. "
                    f"Supported: {self._schema['relationship_types']}"
                )
            target_label = _safe_name(str(hop["target_label"]))
            target_var = str(hop.get("as") or target_label.lower())
            direction = str(hop.get("direction", "out"))
            rel_var = str(hop.get("rel_as") or f"r{index}")
            if direction == "out":
                pattern = (
                    f"({current_var})-[{rel_var}:`{rel_type}`]->({target_var}:`{target_label}`)"
                )
            elif direction == "in":
                pattern = (
                    f"({current_var})<-[{rel_var}:`{rel_type}`]-({target_var}:`{target_label}`)"
                )
            else:
                raise ValueError(f"Unsupported multi_hop_query direction: {direction}")
            query_parts.append(f"MATCH {pattern}")
            relationship_vars.append(rel_var)
            for rel_filter in _as_list(hop.get("relationship_filters")):
                if not isinstance(rel_filter, dict):
                    continue
                normalized_filter = dict(rel_filter)
                normalized_filter.setdefault("var", rel_var)
                relationship_filters.append(normalized_filter)
            current_var = target_var

        contexts = _pattern_var_contexts(start_label, args.get("start_as"), hops)
        args["filters"] = [*list(args.get("filters") or []), *relationship_filters]
        args = _normalize_pattern_var_references(args, contexts)
        where_parts: list[str] = []
        where_parts.extend(_relationship_uniqueness_clauses(relationship_vars))
        for index, flt in enumerate(list(args.get("filters") or [])):
            _validate_filter_binding(flt, set(contexts))
            flt = self._normalize_filter_for_context(
                flt,
                contexts=contexts,
                context="pattern_query.filters",
            )
            clause, clause_params = _cypher_filter_clause(flt, index)
            where_parts.append(clause)
            params.update(clause_params)
        self._validate_projection_context_properties(args, contexts, context="pattern_query")
        if where_parts:
            query_parts.append("WHERE " + " AND ".join(where_parts))

        default_focus: str | None = None
        return_items = _return_items(args)
        if not return_items:
            default_focus = current_var
            return_items = [f"{current_var} AS {current_var}"]
        distinct_kw = "DISTINCT " if _bool_arg(args.get("distinct")) else ""
        query = " ".join(query_parts)
        distinct_entity_vars = _distinct_projection_vars(args)
        if distinct_entity_vars:
            query += f" WITH DISTINCT {', '.join(distinct_entity_vars)}"
            distinct_kw = ""
        query += f" RETURN {distinct_kw}{', '.join(return_items)}"
        count_query = None
        if default_focus:
            count_query = " ".join(query_parts) + f" RETURN {default_focus}.id AS entity_id"
        order_by = _safe_cypher_order_by(args)
        if order_by:
            query += f" ORDER BY {order_by}"
        query += _limit_clause(args, params)
        output: list[dict[str, Any]] = []
        with self._driver.session() as session:
            for record in self._run(session, query, **params):
                if default_focus:
                    output.append(
                        {default_focus: _tool_value(record[default_focus]), "__rel_ids": []}
                    )
                else:
                    output.append({key: _tool_value(record[key]) for key in record.keys()})
        if default_focus:
            metadata = {
                "server_side_entity_query": {
                    "query": count_query,
                    "params": dict(params),
                    "var": default_focus,
                    "label": contexts[default_focus]["label"],
                }
            }
            return self._store(output, focus=default_focus, metadata=metadata)
        return self._store(output, kind="table", columns=_columns(output))

    def _pattern_query(self, args: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(args)
        normalized.setdefault("distinct", True)
        if not normalized.get("hops"):
            if (
                not normalized.get("select")
                and not normalized.get("group_by")
                and not normalized.get("metrics")
            ):
                start_var = str(
                    normalized.get("start_as") or str(normalized["start_label"]).lower()
                )
                normalized["select"] = [{"var": start_var, "property": "name", "alias": "name"}]
            return self._single_node_pattern_query(normalized)
        if (
            not normalized.get("select")
            and not normalized.get("group_by")
            and not normalized.get("metrics")
        ):
            hops = list(normalized.get("hops") or [])
            if hops:
                # Keep multi-hop pattern_query composable for agents: follow-up tools
                # need the final entity payload, not only its display name.
                normalized.pop("select", None)
        return self._multi_hop_query(normalized)

    def _top_entities_by_property(self, args: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(args)
        start_label = str(normalized["start_label"])
        hops = list(normalized.get("hops") or [])
        if normalized.get("target"):
            target_var = str(normalized["target"])
        elif hops:
            target_var = str(hops[-1].get("as") or str(hops[-1]["target_label"]).lower())
        else:
            target_var = str(normalized.get("start_as") or start_label.lower())

        prop = _safe_name(str(normalized["property"]))
        order = str(normalized.get("order") or "desc").lower()
        if order not in {"asc", "desc"}:
            raise ValueError("top_entities_by_property order must be 'asc' or 'desc'")

        contexts = _pattern_var_contexts(start_label, normalized.get("start_as"), hops)
        if target_var not in contexts:
            raise ValueError(
                f"top_entities_by_property target {target_var!r} is not bound by the pattern. "
                f"Bound variables: {sorted(contexts)}. Set target to the node variable whose "
                "property should be ranked."
            )
        if contexts[target_var].get("kind") != "node":
            raise ValueError(
                f"top_entities_by_property target {target_var!r} must be a node variable, "
                "not a relationship variable."
            )
        target_label = contexts[target_var]["label"]
        try:
            self._validate_context_property(
                var=target_var,
                contexts=contexts,
                prop=prop,
                op="eq",
                context="top_entities_by_property.property",
            )
        except ValueError as exc:
            candidates = self._property_owner_candidates(prop, contexts)
            if candidates:
                raise ValueError(
                    f"top_entities_by_property cannot rank {target_var}.{prop}: "
                    f"{prop!r} is not a property of label {target_label!r}. "
                    f"Variables in this pattern that have this property: {candidates}. "
                    "Set target to one of those variables, or choose a property that "
                    "belongs to the requested target."
                ) from exc
            raise

        hidden_rank_alias = "__rank_value"
        select = list(normalized.get("select") or [])
        if not select:
            select = [
                {
                    "var": target_var,
                    "property": "name",
                    "alias": str(normalized.get("name_alias") or "name"),
                }
            ]
        has_rank_projection = any(
            isinstance(item, dict)
            and str(item.get("var")) == target_var
            and str(item.get("property")) == prop
            for item in select
        )
        if has_rank_projection:
            rank_alias = next(
                str(item.get("alias") or item.get("property"))
                for item in select
                if isinstance(item, dict)
                and str(item.get("var")) == target_var
                and str(item.get("property")) == prop
            )
            hidden_rank_alias = ""
        else:
            rank_alias = hidden_rank_alias
            select.append({"var": target_var, "property": prop, "alias": rank_alias})
        if _bool_arg(normalized.get("include_property")) and not has_rank_projection:
            rank_alias = str(normalized.get("property_alias") or prop)
            select[-1]["alias"] = rank_alias
            hidden_rank_alias = ""
        normalized["select"] = select
        hidden_tie_alias = "__rank_tie_id"
        select.append({"var": target_var, "property": "id", "alias": hidden_tie_alias})
        normalized["order_by"] = [
            {"field": rank_alias, "direction": order},
            {"field": hidden_tie_alias, "direction": "asc"},
        ]
        normalized["limit"] = _int_arg(normalized, "limit", 1, min_value=1)
        normalized["distinct"] = _bool_arg_default(normalized.get("distinct"), True)

        result = self._pattern_query(normalized)
        handle = self._handle(str(result["handle"]))
        if hidden_rank_alias or hidden_tie_alias:
            for row in handle.rows:
                if hidden_rank_alias:
                    row.pop(hidden_rank_alias, None)
                row.pop(hidden_tie_alias, None)
            if hidden_rank_alias:
                handle.columns = [
                    column for column in handle.columns if column != hidden_rank_alias
                ]
            handle.columns = [column for column in handle.columns if column != hidden_tie_alias]
            result["preview"] = _preview(handle.rows, focus=handle.focus, columns=handle.columns)
        result["ranking"] = {
            "target": target_var,
            "property": prop,
            "order": order,
            "limit": normalized["limit"],
        }
        result["finalization_hint"] = (
            "This handle is already ranked by the requested property. If the "
            "selected columns match the question, call fetch on this handle next."
        )
        return result

    def _property_owner_candidates(
        self, prop: str, contexts: dict[str, dict[str, str]]
    ) -> list[dict[str, str]]:
        label_props = _properties_by_label(self._schema.get("node_properties", []))
        candidates: list[dict[str, str]] = []
        for var, context in contexts.items():
            if context.get("kind") != "node":
                continue
            label = context["label"]
            known_props = {item["name"] for item in label_props.get(label, [])}
            if prop in known_props:
                candidates.append({"var": var, "label": label})
        return candidates

    def _constraint_query(self, args: dict[str, Any]) -> dict[str, Any]:
        find = dict(args.get("find") or {})
        if not find.get("label"):
            raise ValueError("constraint_query requires find.label")
        find_label = _safe_name(str(find["label"]))
        find_var = str(find.get("as") or find_label.lower())
        constraints = [item for item in _as_list(args.get("where")) if isinstance(item, dict)]
        if not constraints:
            raise ValueError("constraint_query requires at least one where constraint")

        schema_labels = set(self._schema_get()["labels"])
        if find_label not in schema_labels:
            raise ValueError(
                f"Unknown find.label {find_label!r}; known labels: {sorted(schema_labels)}"
            )

        ambiguous_same_target = _ambiguous_relationship_only_constraints(constraints)
        if ambiguous_same_target:
            target_label, rel_types = ambiguous_same_target
            raise ValueError(
                "constraint_query cannot express whether repeated relationship-only "
                f"constraints to target_label={target_label!r} must share the same "
                "target entity. For ordinary wording like 'has both role A and "
                "role B a company', assume the roles share the same target unless "
                "the user explicitly says different targets. Repair this by "
                "calling same_target_role_intersection with source_label=find.label, "
                f"target_label={target_label!r}, and relationships={rel_types}. "
                "Do not call constraint_query again for this question."
            )

        limit = _int_arg(args, "limit", 1000, min_value=1)
        offset = _int_arg(args, "offset", 0, min_value=0)
        distinct = _bool_arg_default(args.get("distinct"), True)
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        query_parts = [f"MATCH ({find_var}:`{find_label}`)"]
        where_parts: list[str] = []
        used_vars = {find_var}

        for index, constraint in enumerate(constraints):
            rel_type = _safe_name(str(constraint["relationship_type"]))
            direction = str(constraint.get("direction", "out"))
            target_label = _safe_name(str(constraint["target_label"]))
            if target_label not in schema_labels:
                raise ValueError(
                    f"Unknown target_label {target_label!r}; known labels: {sorted(schema_labels)}"
                )
            self._validate_relationship_pattern(
                source_label=find_label,
                relationship_type=rel_type,
                direction=direction,
                target_label=target_label,
            )
            target_var = str(constraint.get("target_as") or target_label.lower())
            target_var = _unique_query_var(target_var, used_vars)
            used_vars.add(target_var)
            rel_var = f"cq_r{index}"
            if direction == "out":
                pattern = f"({find_var})-[{rel_var}:`{rel_type}`]->({target_var}:`{target_label}`)"
            elif direction == "in":
                pattern = f"({find_var})<-[{rel_var}:`{rel_type}`]-({target_var}:`{target_label}`)"
            else:
                raise ValueError("constraint_query direction must be 'out' or 'in'")
            query_parts.append(f"MATCH {pattern}")
            if constraint.get("property"):
                filter_spec = self._normalize_filter_for_label(
                    {
                        "var": target_var,
                        "property": constraint["property"],
                        "op": constraint.get("op", "eq"),
                        "value": constraint.get("value"),
                        "value_type": constraint.get("value_type"),
                    },
                    var=target_var,
                    label=target_label,
                    context="constraint_query.where",
                )
                clause, clause_params = _cypher_filter_clause(filter_spec, index)
                where_parts.append(clause)
                params.update(clause_params)

        if where_parts:
            query_parts.append("WHERE " + " AND ".join(where_parts))

        return_mode = str(args.get("return_mode") or "names")
        distinct_kw = "DISTINCT " if distinct else ""
        if return_mode == "entities":
            return_expr = f"{distinct_kw}{find_var} AS {find_var}"
            columns: list[str] | None = None
            focus = find_var
            kind = "rows"
        elif return_mode == "names":
            prop = _safe_name(str(args.get("return_property") or "name"))
            alias = _safe_name(str(args.get("alias") or prop))
            return_items = [f"{distinct_kw}{find_var}.`{prop}` AS `{alias}`"]
            columns = [alias]
            for extra in _constraint_return_properties(args):
                extra_prop = _safe_name(str(extra["property"]))
                extra_alias = _safe_name(str(extra.get("alias") or extra_prop))
                return_items.append(f"{find_var}.`{extra_prop}` AS `{extra_alias}`")
                columns.append(extra_alias)
            return_expr = ", ".join(return_items)
            focus = None
            kind = "table"
        elif return_mode == "count":
            alias = _safe_name(str(args.get("alias") or f"{find_var}_count"))
            count_expr = f"count(DISTINCT {find_var})" if distinct else f"count({find_var})"
            return_expr = f"{count_expr} AS `{alias}`"
            columns = [alias]
            focus = None
            kind = "table"
        else:
            raise ValueError("constraint_query return_mode must be one of: entities, names, count")

        base_query = " ".join(query_parts)
        query = base_query
        query += f" RETURN {return_expr}"
        if return_mode != "count":
            order_by = _safe_constraint_order_by(args, find_var, return_mode)
            if order_by:
                query += f" ORDER BY {order_by}"
            query += " SKIP $offset LIMIT $limit"

        output: list[dict[str, Any]] = []
        with self._driver.session() as session:
            for record in self._run(session, query, **params):
                if return_mode == "entities":
                    output.append({find_var: _tool_value(record[find_var]), "__rel_ids": []})
                else:
                    output.append({key: _tool_value(record[key]) for key in record.keys()})
        metadata = None
        if return_mode == "entities":
            count_params = {
                key: value for key, value in params.items() if key not in {"limit", "offset"}
            }
            metadata = {
                "server_side_entity_query": {
                    "query": f"{base_query} RETURN {find_var}.id AS entity_id",
                    "params": count_params,
                    "var": find_var,
                    "label": find_label,
                }
            }
        result = self._store(output, focus=focus, kind=kind, columns=columns, metadata=metadata)
        if return_mode == "entities" and len(output) >= limit and not args.get("allow_large"):
            result["large_result_hint"] = (
                "constraint_query returned at least the requested limit and may be capped. "
                "If the question asks for a count or grouped count, prefer return_mode='count', "
                "group_handle, expand_aggregate, optional_expand_count, or set_count_by_patterns "
                "instead of materializing a large entity handle."
            )
        return result

    def _validate_relationship_pattern(
        self,
        *,
        source_label: str,
        relationship_type: str,
        direction: str,
        target_label: str,
    ) -> None:
        if relationship_type not in set(self._schema["relationship_types"]):
            raise ValueError(
                f"Unknown relationship_type {relationship_type!r}. "
                f"Supported: {self._schema['relationship_types']}"
            )
        if direction == "out":
            expected_source = source_label
            expected_target = target_label
        elif direction == "in":
            expected_source = target_label
            expected_target = source_label
        else:
            raise ValueError("direction must be 'out' or 'in'")
        if not any(
            row["source_label"] == expected_source
            and row["relationship_type"] == relationship_type
            and row["target_label"] == expected_target
            for row in self._schema_relationships()
        ):
            raise ValueError(
                "Relationship pattern is not in schema: "
                f"(:{expected_source})-[:{relationship_type}]->(:{expected_target}). "
                "Use schema_inspect or inspect_paths to choose the valid direction and labels."
            )

    def _single_node_pattern_query(self, args: dict[str, Any]) -> dict[str, Any]:
        start_label = _safe_name(str(args["start_label"]))
        current_var = str(args.get("start_as") or start_label.lower())
        params: dict[str, Any] = {}
        query_parts = [f"MATCH ({current_var}:`{start_label}`)"]

        source_handle_id = args.get("from")
        if source_handle_id:
            source_handle = self._handle(str(source_handle_id))
            self._guard_large_handle_input(
                source_handle,
                tool="pattern_query",
                var=current_var,
                args=args,
                alternatives=[
                    "push the filter into pattern_query instead of starting from a broad handle",
                    "use node_search/entity_resolve for named entities",
                    "use count_handle or group_handle if the handle is already the desired entity set",
                ],
            )
            source_ids = [
                row[current_var]["properties"]["id"]
                for row in source_handle.rows
                if current_var in row
            ]
            params["source_ids"] = source_ids
            query_parts.append(f"WHERE {current_var}.id IN $source_ids")

        where_parts: list[str] = []
        for index, flt in enumerate(_as_list(args.get("filters"))):
            _validate_filter_binding(flt, {current_var})
            flt = self._normalize_filter_for_label(
                flt,
                var=str(flt.get("var") or current_var),
                label=start_label,
                context="pattern_query.filters",
            )
            clause, clause_params = _cypher_filter_clause(flt, index)
            where_parts.append(clause)
            params.update(clause_params)
        if where_parts:
            query_parts.append(
                ("AND " if source_handle_id else "WHERE ") + " AND ".join(where_parts)
            )

        return_items = _return_items(args)
        if not return_items:
            return_items = [f"{current_var} AS {current_var}"]
        distinct_kw = "DISTINCT " if _bool_arg(args.get("distinct")) else ""
        query = " ".join(query_parts)
        distinct_entity_vars = _distinct_projection_vars(args)
        if distinct_entity_vars:
            query += f" WITH DISTINCT {', '.join(distinct_entity_vars)}"
            distinct_kw = ""
        query += f" RETURN {distinct_kw}{', '.join(return_items)}"
        order_by = _safe_cypher_order_by(args)
        if order_by:
            query += f" ORDER BY {order_by}"
        query += _limit_clause(args, params)
        output: list[dict[str, Any]] = []
        with self._driver.session() as session:
            for record in self._run(session, query, **params):
                output.append({key: _tool_value(record[key]) for key in record.keys()})
        return self._store(output, kind="table", columns=_columns(output))

    def _group_count_by_pattern(self, args: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(args)
        if "count_var" not in normalized:
            metrics = _as_list(normalized.get("metrics"))
            if metrics and isinstance(metrics[0], dict) and metrics[0].get("var"):
                normalized["count_var"] = metrics[0]["var"]
        count_var = str(normalized.pop("count_var"))
        alias = str(normalized.pop("alias", f"{count_var}_count"))
        distinct = _bool_arg(normalized.pop("distinct", True))
        _validate_metric_binding(
            count_var,
            _pattern_bound_vars(
                str(normalized["start_label"]),
                normalized.get("start_as"),
                _as_list(normalized.get("hops")),
            ),
        )
        self._validate_projection_properties(
            normalized,
            _pattern_var_labels(
                str(normalized["start_label"]),
                normalized.get("start_as"),
                _as_list(normalized.get("hops")),
            ),
            context="group_count_by_pattern",
        )
        normalized["metrics"] = [
            {
                "op": "count_distinct" if distinct else "count",
                "var": count_var,
                "alias": alias,
            }
        ]
        normalized["order_by"] = _prefer_metric_order_by(normalized, alias)
        normalized.pop("select", None)
        return self._multi_hop_query(normalized)

    def _entity_set_operation(self, args: dict[str, Any]) -> dict[str, Any]:
        operands = _as_list(args.get("operands"))
        if len(operands) < 2:
            raise ValueError("entity_set_operation requires at least two operands")
        op = str(args["op"])
        if op not in {"union", "intersect", "difference"}:
            raise ValueError("entity_set_operation op must be one of: union, intersect, difference")
        self._validate_entity_set_operands(operands)
        self._guard_large_entity_set_operands(args, operands)
        out_var = str(args.get("as") or operands[0].get("var") or "entity")
        current_handle = str(operands[0]["handle"])
        current_var = str(operands[0]["var"])
        result: dict[str, Any] | None = None
        for operand in operands[1:]:
            result = self._combine(
                {
                    "left": current_handle,
                    "right": str(operand["handle"]),
                    "op": op,
                    "left_var": current_var,
                    "right_var": str(operand["var"]),
                    "as": out_var,
                }
            )
            current_handle = str(result["handle"])
            current_var = out_var
        assert result is not None
        result["set_operation_hint"] = (
            "This handle is the combined entity set. If the question asks 'how many', "
            f"call count_handle with from={result['handle']!r}, var={out_var!r}, "
            "distinct=true. If it asks for names or properties, call project on this "
            "handle with distinct=false unless the user explicitly asks for unique "
            "scalar values. Fetch only after count_handle/project if scalar answer "
            "rows are needed."
        )
        self._handle(str(result["handle"])).metadata["entity_set_operation"] = True
        return result

    def _set_count_by_patterns(self, args: dict[str, Any]) -> dict[str, Any]:
        op = str(args.get("op") or "union")
        if op != "union":
            raise ValueError("set_count_by_patterns currently supports op='union' only")
        branches = [branch for branch in _as_list(args.get("branches")) if isinstance(branch, dict)]
        if len(branches) < 2:
            raise ValueError("set_count_by_patterns requires at least two branches")
        alias = _safe_name(str(args.get("alias") or "count"))
        branch_queries: list[str] = []
        params: dict[str, Any] = {}
        return_labels: set[str] = set()
        filter_index = 0
        for branch_index, branch in enumerate(branches):
            query, branch_params, return_label, filter_index = self._set_count_branch_query(
                branch,
                branch_index=branch_index,
                filter_index=filter_index,
            )
            branch_queries.append(query)
            params.update(branch_params)
            return_labels.add(return_label)
        if len(return_labels) > 1:
            raise ValueError(
                "set_count_by_patterns branches must return the same entity label/type. "
                f"Got: {sorted(return_labels)}"
            )
        query = (
            "CALL () { "
            + " UNION ".join(branch_queries)
            + f" }} RETURN count(DISTINCT entity_id) AS `{alias}`"
        )
        with self._driver.session() as session:
            records = self._run(session, query, **params)
            record = records.single() if hasattr(records, "single") else next(iter(records), None)
        rows = [{alias: int(record[alias]) if record else 0}]
        result = self._store(rows, kind="table", columns=[alias])
        result["finalization_hint"] = (
            "This is already a server-side set count. If this count matches the "
            "question, call fetch on this handle next."
        )
        return result

    def _set_count_branch_query(
        self,
        branch: dict[str, Any],
        *,
        branch_index: int,
        filter_index: int,
    ) -> tuple[str, dict[str, Any], str, int]:
        start_label = _safe_name(str(branch["start_label"]))
        current_var = str(branch.get("start_as") or start_label.lower())
        hops = [hop for hop in _as_list(branch.get("hops")) if isinstance(hop, dict)]
        return_var = str(branch["return_var"])
        query_parts = [f"MATCH ({current_var}:`{start_label}`)"]
        relationship_filters: list[dict[str, Any]] = []
        relationship_vars: list[str] = []
        for index, hop in enumerate(hops):
            rel_type = _safe_name(str(hop["relationship_type"]))
            if rel_type not in set(self._schema["relationship_types"]):
                raise ValueError(
                    f"Unknown relationship_type {rel_type!r}. "
                    f"Supported: {self._schema['relationship_types']}"
                )
            target_label = _safe_name(str(hop["target_label"]))
            target_var = str(hop.get("as") or target_label.lower())
            direction = str(hop.get("direction", "out"))
            rel_var = str(hop.get("rel_as") or f"b{branch_index}_r{index}")
            if direction == "out":
                pattern = (
                    f"({current_var})-[{rel_var}:`{rel_type}`]->({target_var}:`{target_label}`)"
                )
            elif direction == "in":
                pattern = (
                    f"({current_var})<-[{rel_var}:`{rel_type}`]-({target_var}:`{target_label}`)"
                )
            else:
                raise ValueError(f"Unsupported set_count_by_patterns hop direction: {direction}")
            query_parts.append(f"MATCH {pattern}")
            relationship_vars.append(rel_var)
            for rel_filter in _as_list(hop.get("relationship_filters")):
                if not isinstance(rel_filter, dict):
                    continue
                normalized_filter = dict(rel_filter)
                normalized_filter.setdefault("var", rel_var)
                relationship_filters.append(normalized_filter)
            current_var = target_var
        contexts = _pattern_var_contexts(start_label, branch.get("start_as"), hops)
        if return_var not in contexts or contexts[return_var].get("kind") != "node":
            raise ValueError(
                f"set_count_by_patterns return_var {return_var!r} is not a node "
                f"variable in branch {branch_index}. Available variables: {sorted(contexts)}"
            )
        branch = _normalize_pattern_var_references(
            {**branch, "filters": [*_as_list(branch.get("filters")), *relationship_filters]},
            contexts,
        )
        where_parts = _relationship_uniqueness_clauses(relationship_vars)
        params: dict[str, Any] = {}
        for flt in _as_list(branch.get("filters")):
            if not isinstance(flt, dict):
                continue
            _validate_filter_binding(flt, set(contexts))
            flt = self._normalize_filter_for_context(
                flt,
                contexts=contexts,
                context="set_count_by_patterns.filters",
            )
            if (
                contexts.get(str(flt.get("var") or ""), {}).get("kind") == "node"
                and str(flt.get("property") or "") == "name"
                and str(flt.get("op") or "eq") == "eq"
                and isinstance(flt.get("value"), str)
            ):
                flt = {**flt, "op": "eq_ci"}
            clause, clause_params = _cypher_filter_clause(flt, filter_index)
            where_parts.append(clause)
            params.update(clause_params)
            filter_index += 1
        if where_parts:
            query_parts.append("WHERE " + " AND ".join(where_parts))
        query_parts.append(f"RETURN {return_var}.id AS entity_id")
        return " ".join(query_parts), params, contexts[return_var]["label"], filter_index

    def _validate_entity_set_operands(self, operands: list[Any]) -> None:
        labels_by_operand: list[set[str]] = []
        for operand in operands:
            if not isinstance(operand, dict):
                raise ValueError(
                    "entity_set_operation operands must be objects with handle and var"
                )
            handle = self._handle(str(operand["handle"]))
            var = str(operand["var"])
            entity_vars = _handle_entity_vars(handle.rows)
            labels: set[str] = set()
            saw_var = False
            for row in handle.rows:
                if var not in row:
                    continue
                saw_var = True
                value = row[var]
                if not _is_node_payload(value):
                    raise ValueError(
                        "entity_set_operation requires entity rows; operands must be entity handles. "
                        f"Handle {handle.id} variable {var!r} is scalar/table-shaped; "
                        f"Available entity variables: {entity_vars}. "
                        "Use one of those entity variables, or rerun the branch without "
                        "scalar select/project before combining. If you must project before "
                        "combining, project with keep_entities=true."
                    )
                labels.update(label for label in value.get("labels", []) if label != "Entity")
            if not saw_var and handle.rows:
                raise ValueError(
                    f"entity_set_operation variable {var!r} is not present in handle {handle.id}. "
                    f"Available variables: {_columns(handle.rows)}. "
                    f"Available entity variables: {entity_vars}. "
                    "Use an entity variable for entity_set_operation. If no entity "
                    "variables are available, rerun the branch without scalar select/project "
                    "before combining, or project with keep_entities=true earlier."
                )
            labels_by_operand.append(labels)
        non_empty = [labels for labels in labels_by_operand if labels]
        if len(non_empty) > 1:
            common = set.intersection(*non_empty)
            if not common:
                raise ValueError(
                    "entity_set_operation operands should represent the same entity label/type. "
                    f"Observed labels: {[sorted(labels) for labels in labels_by_operand]}. "
                    "For OR/AND, make each branch return the same entity variable type before combining."
                )

    def _validate_filter_property(
        self,
        *,
        var: str,
        label: str,
        prop: str,
        op: str,
        context: str,
    ) -> str | None:
        if not prop:
            return None
        label_props = _properties_by_label(self._schema.get("node_properties", []))
        known_props = {item["name"]: item for item in label_props.get(label, [])}
        if prop in known_props:
            inferred = _inferred_type(known_props[prop]["types"])
            if inferred.startswith("list") and op in {"contains", "not_contains"}:
                raise ValueError(
                    f"{context}: property {label}.{prop} is {inferred}; use op='in' or "
                    "op='not_in' with the scalar member value instead of contains/not_contains."
                )
            return inferred
        relationship_types = set(self._schema.get("relationship_types", []))
        if prop in relationship_types:
            suggestions = [
                {
                    "relationship_type": row["relationship_type"],
                    "direction": "out" if row["source_label"] == label else "in",
                    "target_label": row["target_label"]
                    if row["source_label"] == label
                    else row["source_label"],
                }
                for row in self._schema_relationships()
                if row["relationship_type"] == prop
                and (row["source_label"] == label or row["target_label"] == label)
            ]
            raise ValueError(
                f"{context}: relationship {prop!r} was used as property filter on "
                f"variable {var!r} with label {label!r}. Use a hop instead. "
                f"Suggested hops: {suggestions}"
            )
        raise ValueError(
            f"{context}: unknown property {prop!r} for label {label!r}. "
            f"Known properties: {sorted(known_props)}"
        )

    def _normalize_filter_for_label(
        self,
        flt: dict[str, Any],
        *,
        var: str,
        label: str,
        context: str,
    ) -> dict[str, Any]:
        normalized = dict(flt)
        prop = str(normalized.get("property") or "")
        op = str(normalized.get("op") or "eq")
        inferred = self._validate_filter_property(
            var=var,
            label=label,
            prop=prop,
            op=op,
            context=context,
        )
        if inferred and inferred.startswith("list"):
            if op == "eq":
                normalized["op"] = "in"
            elif op == "neq":
                normalized["op"] = "not_in"
        return normalized

    def _validate_projection_properties(
        self,
        args: dict[str, Any],
        var_labels: dict[str, str],
        *,
        context: str,
    ) -> None:
        for section in ("select", "group_by", "order_by"):
            for item in _as_list(args.get(section)):
                if not isinstance(item, dict) or not item.get("var") or not item.get("property"):
                    continue
                var = str(item["var"])
                if var not in var_labels:
                    continue
                self._validate_filter_property(
                    var=var,
                    label=var_labels[var],
                    prop=str(item["property"]),
                    op="eq",
                    context=f"{context}.{section}",
                )

    def _validate_context_property(
        self,
        *,
        var: str,
        contexts: dict[str, dict[str, str]],
        prop: str,
        op: str,
        context: str,
    ) -> str | None:
        if not prop or var not in contexts:
            return None
        var_context = contexts[var]
        if var_context["kind"] == "node":
            return self._validate_filter_property(
                var=var,
                label=var_context["label"],
                prop=prop,
                op=op,
                context=context,
            )

        rel_type = var_context["relationship_type"]
        rel_props = _properties_by_relationship(self._schema.get("relationship_properties", []))
        known_props = {item["name"]: item for item in rel_props.get(rel_type, [])}
        if prop not in known_props:
            raise ValueError(
                f"{context}: unknown relationship property {prop!r} for relationship "
                f"type {rel_type!r}. Known properties: {sorted(known_props)}"
            )
        inferred = _inferred_type(known_props[prop]["types"])
        if inferred.startswith("list") and op in {"contains", "not_contains"}:
            raise ValueError(
                f"{context}: relationship property {rel_type}.{prop} is {inferred}; "
                "use op='in' or op='not_in' with the scalar member value instead."
            )
        return inferred

    def _normalize_filter_for_context(
        self,
        flt: dict[str, Any],
        *,
        contexts: dict[str, dict[str, str]],
        context: str,
    ) -> dict[str, Any]:
        normalized = dict(flt)
        var = str(normalized.get("var") or "")
        op = str(normalized.get("op") or "eq")
        inferred = self._validate_context_property(
            var=var,
            contexts=contexts,
            prop=str(normalized.get("property") or ""),
            op=op,
            context=context,
        )
        if inferred and inferred.startswith("list"):
            if op == "eq":
                normalized["op"] = "in"
            elif op == "neq":
                normalized["op"] = "not_in"
        return normalized

    def _validate_projection_context_properties(
        self,
        args: dict[str, Any],
        contexts: dict[str, dict[str, str]],
        *,
        context: str,
    ) -> None:
        for section in ("select", "group_by", "order_by"):
            for item in _as_list(args.get(section)):
                if not isinstance(item, dict) or not item.get("var") or not item.get("property"):
                    continue
                self._validate_context_property(
                    var=str(item["var"]),
                    contexts=contexts,
                    prop=str(item["property"]),
                    op="eq",
                    context=f"{context}.{section}",
                )

    def _filter(self, args: dict[str, Any]) -> dict[str, Any]:
        handle = self._handle(str(args["from"]))
        var = str(args["var"])
        prop = str(args["property"])
        flt = dict(args)
        labels = _handle_var_labels(handle, var)
        if len(labels) == 1:
            flt = self._normalize_filter_for_label(
                flt,
                var=var,
                label=next(iter(labels)),
                context="filter",
            )
        op = str(flt["op"])
        value = _coerce_filter_value(flt.get("value"), flt.get("value_type"))
        if handle.rows and not any(var in row for row in handle.rows):
            raise ValueError(
                f"filter variable {var!r} is not present in handle {handle.id}. "
                f"Available columns/variables: {_columns(handle.rows)}"
            )
        rows = [row for row in handle.rows if _predicate(_row_property(row, var, prop), op, value)]
        return self._store(rows, focus=handle.focus)

    def _filter_same_node(self, args: dict[str, Any]) -> dict[str, Any]:
        handle = self._handle(str(args["from"]))
        left_var = str(args["left_var"])
        right_var = str(args["right_var"])
        rows = [
            row
            for row in handle.rows
            if left_var in row
            and right_var in row
            and row[left_var]["properties"].get("id") == row[right_var]["properties"].get("id")
        ]
        return self._store(rows, focus=handle.focus)

    def _join_handles(self, args: dict[str, Any]) -> dict[str, Any]:
        left = self._handle(str(args["left"]))
        right = self._handle(str(args["right"]))
        left_var = str(args.get("left_var") or left.focus)
        right_var = str(args.get("right_var") or right.focus)
        out_var = str(args.get("as") or left_var)
        op = str(args.get("op", "inner"))
        left_labels = _handle_var_labels(left, left_var)
        right_labels = _handle_var_labels(right, right_var)
        if left_labels and right_labels and not (left_labels & right_labels):
            raise ValueError(
                "join_handles joins by graph node identity, so both variables must "
                f"represent the same label/type. {left.id}.{left_var} has "
                f"{sorted(left_labels)}, while {right.id}.{right_var} has "
                f"{sorted(right_labels)}. Use expand/pattern_query to traverse "
                "relationships between different labels."
            )
        right_by_id = {
            row[right_var]["properties"]["id"]: row
            for row in right.rows
            if right_var in row and isinstance(row[right_var], dict)
        }
        rows: list[dict[str, Any]] = []
        for row in left.rows:
            if left_var not in row or not isinstance(row[left_var], dict):
                continue
            item_id = row[left_var]["properties"].get("id")
            matched = item_id in right_by_id
            if op == "inner" and matched:
                merged = dict(row)
                merged[out_var] = row[left_var]
                rows.append(merged)
            elif op == "left_semi" and matched:
                rows.append({out_var: row[left_var]})
            elif op == "left_anti" and not matched:
                rows.append({out_var: row[left_var]})
        if op not in {"inner", "left_semi", "left_anti"}:
            raise ValueError(f"Unsupported join_handles op: {op}")
        return self._store(rows, focus=out_var)

    def _same_target_role_intersection(self, args: dict[str, Any]) -> dict[str, Any]:
        source_label = _safe_name(str(args["source_label"]))
        target_label = _safe_name(str(args["target_label"]))
        source_var = str(args.get("source_as") or source_label.lower())
        target_var = str(args.get("target_as") or target_label.lower())
        relationships = list(args.get("relationships") or [])
        if len(relationships) < 2:
            raise ValueError("same_target_role_intersection requires at least two relationships")
        limit = _int_arg(args, "limit", 1000, min_value=1)
        distinct = _bool_arg_default(args.get("distinct"), True)

        match_parts = [f"MATCH ({source_var}:`{source_label}`)"]
        for index, rel in enumerate(relationships):
            rel_type = _safe_name(str(rel["relationship_type"]))
            if rel_type not in set(self._schema["relationship_types"]):
                raise ValueError(
                    f"Unknown relationship_type {rel_type!r}. "
                    f"Supported: {self._schema['relationship_types']}"
                )
            direction = str(rel.get("direction", "in"))
            rel_var = f"r{index}"
            if direction == "in":
                pattern = (
                    f"({source_var})<-[{rel_var}:`{rel_type}`]-({target_var}:`{target_label}`)"
                )
            elif direction == "out":
                pattern = (
                    f"({source_var})-[{rel_var}:`{rel_type}`]->({target_var}:`{target_label}`)"
                )
            else:
                raise ValueError(f"Unsupported direction for role intersection: {direction}")
            match_parts.append(f"MATCH {pattern}")

        where_parts: list[str] = []
        params: dict[str, Any] = {"limit": limit}
        normalized_filters: list[dict[str, Any]] = []
        for index, flt in enumerate(list(args.get("filters") or [])):
            contexts = {
                source_var: {"kind": "node", "label": source_label},
                target_var: {"kind": "node", "label": target_label},
            }
            flt = self._normalize_filter_for_context(
                flt,
                contexts=contexts,
                context="same_target_role_intersection.filters",
            )
            normalized_filters.append(flt)
            clause, clause_params = _cypher_filter_clause(flt, index)
            where_parts.append(clause)
            params.update(clause_params)
        rel_types = [str(rel.get("relationship_type")) for rel in relationships]
        repeated_same_relationship = len(set(rel_types)) < len(rel_types)
        target_multi_value_filters = [
            flt
            for flt in normalized_filters
            if str(flt.get("var")) == target_var
            and str(flt.get("op")) in {"in", "contains_any"}
            and isinstance(flt.get("value"), list)
            and len(flt.get("value") or []) >= 2
        ]
        if repeated_same_relationship and target_multi_value_filters:
            raise ValueError(
                "same_target_role_intersection requires all repeated roles to point to the same target entity. "
                f"A filter like {target_var}.name IN [...] does not mean the source is connected to all listed targets. "
                "For common-neighbor questions over multiple named targets, resolve each target separately, "
                "expand each target to the requested source entity type, then use entity_set_operation op='intersect' "
                "on those source entity handles."
            )

        select = list(args.get("select") or [])
        keep_entities = _bool_arg(args.get("keep_entities", False))
        order_by = [order for order in _as_list(args.get("order_by")) if isinstance(order, dict)]
        selectable_fields = _same_target_select_fields(select)
        hidden_order_items: list[tuple[int, str, str, Any]] = []
        if select:
            return_items = [
                f"{_cypher_property_expr(str(item['var']), str(item['property']), item.get('value_type'))} AS `{_safe_name(str(item.get('alias') or item['property']))}`"
                for item in select
            ]
            for index, order in enumerate(order_by):
                if order.get("field") or not order.get("var") or not order.get("property"):
                    continue
                field = selectable_fields.get((str(order["var"]), str(order["property"])))
                if field:
                    continue
                alias = _project_hidden_order_key(index)
                hidden_order_items.append(
                    (
                        index,
                        alias,
                        str(order["var"]),
                        str(order["property"]),
                    )
                )
                return_items.append(
                    f"{_cypher_property_expr(str(order['var']), str(order['property']), order.get('value_type'))} AS `{alias}`"
                )
            if keep_entities:
                return_items = [
                    f"{source_var} AS {source_var}",
                    f"{target_var} AS {target_var}",
                    *return_items,
                ]
        else:
            return_items = [f"{source_var} AS source", f"{target_var} AS target"]
        distinct_kw = "DISTINCT " if distinct else ""
        query = " ".join(match_parts)
        if where_parts:
            query += " WHERE " + " AND ".join(where_parts)
        query += f" RETURN {distinct_kw}{', '.join(return_items)} LIMIT $limit"

        output: list[dict[str, Any]] = []
        with self._driver.session() as session:
            for record in self._run(session, query, **params):
                if select:
                    row: dict[str, Any] = {}
                    if keep_entities:
                        row[source_var] = _tool_value(record[source_var])
                        row[target_var] = _tool_value(record[target_var])
                    exploded_fields: list[tuple[str, list[Any]]] = []
                    for item in select:
                        alias = _safe_name(str(item.get("alias") or item["property"]))
                        value = _tool_value(record[alias])
                        if _bool_arg(item.get("explode")):
                            if value is None:
                                values = []
                            else:
                                values = list(value) if isinstance(value, list) else [value]
                            exploded_fields.append((alias, values))
                        else:
                            row[alias] = value
                    for _index, alias, _var, _property in hidden_order_items:
                        row[alias] = _tool_value(record[alias])
                    if keep_entities:
                        row["__rel_ids"] = []
                    output.extend(_expand_projected_rows(row, exploded_fields))
                else:
                    output.append(
                        {
                            source_var: _node_payload(record["source"]),
                            target_var: _node_payload(record["target"]),
                            "__rel_ids": [],
                        }
                    )
        if select and order_by:
            for index, order in reversed(list(enumerate(order_by))):
                field = (
                    str(order["field"])
                    if order.get("field")
                    else selectable_fields.get((str(order.get("var")), str(order.get("property"))))
                    or _project_hidden_order_key(index)
                )
                reverse = str(order.get("direction", "asc")).lower() == "desc"
                output.sort(
                    key=lambda item: (item.get(field) is None, item.get(field)), reverse=reverse
                )
            output = [_strip_project_hidden_order_keys(row) for row in output]
        if select and not keep_entities:
            if distinct:
                output = _distinct_rows(output)
            result = self._store(output, kind="table", columns=_columns(output))
            result["finalization_hint"] = True
            return result
        if select and keep_entities and distinct:
            output = _distinct_rows(output)
        selected_entity_vars = sorted(
            {
                str(item.get("var"))
                for item in select
                if isinstance(item, dict) and str(item.get("var")) in {source_var, target_var}
            }
        )
        result_focus = (
            selected_entity_vars[0]
            if select and keep_entities and len(selected_entity_vars) == 1
            else source_var
        )
        metadata = None
        if select and keep_entities:
            metadata = {
                "entity_projection_distinct_default": True,
                "preferred_fetch_columns": [
                    _safe_name(str(item.get("alias") or item["property"]))
                    for item in select
                    if isinstance(item, dict) and item.get("property")
                ],
            }
        result = self._store(output, focus=result_focus, metadata=metadata)
        if select and not keep_entities:
            result["finalization_hint"] = True
        if select and keep_entities:
            result["continuation_hint"] = (
                "Selected scalar columns were kept together with source/target entities. "
                "Use filter, entity_set_operation, expand, or project on this handle before "
                "fetching if more graph work is needed."
            )
        return result

    def _shared_role_aggregate(self, args: dict[str, Any]) -> dict[str, Any]:
        args = _normalize_aggregate_select_to_group_by(args)
        seed_label = _safe_name(str(args["seed_label"]))
        shared_label = _safe_name(str(args["shared_label"]))
        peer_label = _safe_name(str(args["peer_label"]))
        seed_var = _safe_name(str(args.get("seed_as") or "seed"))
        shared_var = _safe_name(str(args.get("shared_as") or "shared"))
        peer_var = _safe_name(str(args.get("peer_as") or "peer"))
        seed_rel = dict(args["seed_relationship"])
        peer_rel = dict(args["peer_relationship"])
        seed_rel_type = _safe_name(str(seed_rel["relationship_type"]))
        peer_rel_type = _safe_name(str(peer_rel["relationship_type"]))
        if seed_rel_type not in set(self._schema["relationship_types"]):
            raise ValueError(
                f"Unknown seed relationship_type {seed_rel_type!r}. "
                f"Supported: {self._schema['relationship_types']}"
            )
        if peer_rel_type not in set(self._schema["relationship_types"]):
            raise ValueError(
                f"Unknown peer relationship_type {peer_rel_type!r}. "
                f"Supported: {self._schema['relationship_types']}"
            )

        seed_handle = None
        seed_from = args.get("seed_from")
        if seed_from:
            seed_handle = self._handle(str(seed_from))
            seed_var = self._resolve_seed_var_from_handle(seed_handle, seed_var)

        seed_pattern = _shared_role_pattern(
            left_var=seed_var,
            left_label=seed_label,
            rel_var="seed_rel",
            rel_type=seed_rel_type,
            right_var=shared_var,
            right_label=shared_label,
            direction=str(seed_rel.get("direction", "out")),
        )
        peer_pattern = _shared_role_pattern(
            left_var=peer_var,
            left_label=peer_label,
            rel_var="peer_rel",
            rel_type=peer_rel_type,
            right_var=shared_var,
            right_label=shared_label,
            direction=str(peer_rel.get("direction", "out")),
        )

        contexts = {
            seed_var: {"kind": "node", "label": seed_label},
            shared_var: {"kind": "node", "label": shared_label},
            peer_var: {"kind": "node", "label": peer_label},
            "seed_rel": {"kind": "relationship", "relationship_type": seed_rel_type},
            "peer_rel": {"kind": "relationship", "relationship_type": peer_rel_type},
        }
        context_by_filter_section = {
            "seed_filters": "shared_role_aggregate.seed_filters",
            "shared_filters": "shared_role_aggregate.shared_filters",
            "peer_filters": "shared_role_aggregate.peer_filters",
        }
        params: dict[str, Any] = {"limit": _int_arg(args, "limit", 1000, min_value=1)}
        where_parts: list[str] = []
        if seed_handle is not None:
            seed_ids = [
                row[seed_var]["properties"]["id"]
                for row in seed_handle.rows
                if _is_node_payload(row.get(seed_var))
            ]
            if not seed_ids:
                raise ValueError(
                    f"shared_role_aggregate seed_from handle {seed_handle.id} does not contain "
                    f"entity variable {seed_var!r}. Available entity variables: "
                    f"{_handle_entity_vars(seed_handle.rows)}"
                )
            params["seed_ids"] = seed_ids
            where_parts.append(f"{seed_var}.id IN $seed_ids")
        filter_index = 0
        for section in ("seed_filters", "shared_filters", "peer_filters"):
            for flt in _as_list(args.get(section)):
                if not isinstance(flt, dict):
                    continue
                flt = self._normalize_filter_for_context(
                    flt,
                    contexts=contexts,
                    context=context_by_filter_section[section],
                )
                clause, clause_params = _cypher_filter_clause(flt, filter_index)
                where_parts.append(clause)
                params.update(clause_params)
                filter_index += 1
        if _bool_arg(args.get("exclude_seed", True)) and seed_label == peer_label:
            where_parts.append(f"{seed_var}.id <> {peer_var}.id")

        self._validate_projection_context_properties(
            args, contexts, context="shared_role_aggregate"
        )

        return_items = _return_items(args)
        if not return_items:
            select = _as_list(args.get("select"))
            if select:
                return_items = _return_items({"select": select})
            else:
                return_items = [f"{peer_var} AS peer", f"{shared_var} AS shared"]
        query = f"MATCH {seed_pattern} MATCH {peer_pattern}"
        if where_parts:
            query += " WHERE " + " AND ".join(where_parts)
        distinct_kw = ""
        distinct_entity_vars = _distinct_projection_vars(args)
        if distinct_entity_vars:
            query += f" WITH DISTINCT {', '.join(distinct_entity_vars)}"
        elif not _as_list(args.get("metrics")) and _bool_arg(args.get("distinct", True)):
            distinct_kw = "DISTINCT "
        query += f" RETURN {distinct_kw}{', '.join(return_items)}"
        order_by = _safe_cypher_order_by(args)
        if order_by:
            query += f" ORDER BY {order_by}"
        query += " LIMIT $limit"

        output: list[dict[str, Any]] = []
        table_output = bool(
            _as_list(args.get("select"))
            or _as_list(args.get("group_by"))
            or _as_list(args.get("metrics"))
        )
        with self._driver.session() as session:
            for record in self._run(session, query, **params):
                if table_output:
                    output.append({key: _tool_value(record[key]) for key in record.keys()})
                else:
                    output.append(
                        {
                            peer_var: _node_payload(record["peer"]),
                            shared_var: _node_payload(record["shared"]),
                            "__rel_ids": [],
                        }
                    )
        if table_output:
            return self._store(output, kind="table", columns=_columns(output))
        return self._store(output, focus=peer_var)

    def _combine(self, args: dict[str, Any]) -> dict[str, Any]:
        left = self._handle(str(args["left"]))
        right = self._handle(str(args["right"]))
        op = str(args["op"])
        left_var = str(args.get("left_var") or left.focus)
        right_var = str(args.get("right_var") or right.focus)
        out_var = str(args.get("as") or left_var)
        left_by_id = {
            row[left_var]["properties"]["id"]: row
            for row in left.rows
            if _is_node_payload(row.get(left_var))
        }
        right_by_id = {
            row[right_var]["properties"]["id"]: row
            for row in right.rows
            if _is_node_payload(row.get(right_var))
        }
        if not left_by_id and any(left_var in row for row in left.rows):
            raise ValueError(
                f"combine/entity_set_operation requires entity rows for {left_var!r}; "
                "received scalar/table rows. Use project/fetch for scalar answers or "
                "combine handles before projecting properties."
            )
        if not right_by_id and any(right_var in row for row in right.rows):
            raise ValueError(
                f"combine/entity_set_operation requires entity rows for {right_var!r}; "
                "received scalar/table rows. Use project/fetch for scalar answers or "
                "combine handles before projecting properties."
            )
        if op == "union":
            ids = set(left_by_id) | set(right_by_id)
        elif op == "intersect":
            ids = set(left_by_id) & set(right_by_id)
        elif op == "difference":
            ids = set(left_by_id) - set(right_by_id)
        else:
            raise ValueError(f"Unsupported combine op: {op}")
        rows = []
        for item_id in ids:
            if item_id in left_by_id:
                payload = left_by_id[item_id][left_var]
            else:
                payload = right_by_id[item_id][right_var]
            rows.append({out_var: payload})
        metadata = self._combined_server_side_entity_metadata(
            op=op,
            left=left,
            right=right,
            left_var=left_var,
            right_var=right_var,
            out_var=out_var,
        )
        return self._store(rows, focus=out_var, metadata=metadata)

    def _aggregate(self, args: dict[str, Any]) -> dict[str, Any]:
        handle = self._handle(str(args["from"]))
        group_by = list(args.get("group_by") or [])
        metrics = list(args.get("metrics") or [])
        groups: dict[tuple[Any, ...], dict[str, Any]] = {}
        distinct_sets: dict[tuple[Any, ...], dict[str, set[Any]]] = {}
        metric_values: dict[tuple[Any, ...], dict[str, list[Any]]] = {}
        for row in handle.rows:
            key_values = tuple(
                _row_property(row, item["var"], item["property"]) for item in group_by
            )
            out = groups.setdefault(
                key_values,
                {item["alias"]: value for item, value in zip(group_by, key_values, strict=True)},
            )
            metric_sets = distinct_sets.setdefault(key_values, {})
            scalar_values = metric_values.setdefault(key_values, {})
            for metric in metrics:
                alias = metric["alias"]
                if metric["op"] == "count_distinct":
                    identity = _metric_identity(row, str(metric["var"]))
                    if identity is not None:
                        metric_sets.setdefault(alias, set()).add(identity)
                elif metric["op"] == "count":
                    out[alias] = int(out.get(alias, 0)) + 1
                elif metric["op"] in {"max", "min", "sum", "avg"}:
                    value = _metric_scalar_value(row, str(metric["var"]), metric.get("property"))
                    if value is not None:
                        scalar_values.setdefault(alias, []).append(value)
                else:
                    raise ValueError(f"Unsupported metric op: {metric['op']}")
        for key, out in groups.items():
            for alias, values in distinct_sets.get(key, {}).items():
                out[alias] = len(values)
            for metric in metrics:
                alias = metric["alias"]
                values = metric_values.get(key, {}).get(alias, [])
                if not values:
                    continue
                if metric["op"] == "max":
                    out[alias] = max(values)
                elif metric["op"] == "min":
                    out[alias] = min(values)
                elif metric["op"] == "sum":
                    out[alias] = sum(values)
                elif metric["op"] == "avg":
                    out[alias] = sum(values) / len(values)
        return self._store(
            list(groups.values()), kind="table", columns=_columns(list(groups.values()))
        )

    def _project(self, args: dict[str, Any]) -> dict[str, Any]:
        if _as_list(args.get("group_by")) or _as_list(args.get("metrics")):
            return self._aggregate(args)
        handle = self._handle(str(args["from"]))
        select = list(args.get("select") or [])
        order_by = [order for order in _as_list(args.get("order_by")) if isinstance(order, dict)]
        keep_entities = _bool_arg(args.get("keep_entities"))
        distinct_requested = _bool_arg(args.get("distinct"))
        distinct_scope = str(args.get("distinct_scope") or "").lower()
        entity_distinct = distinct_scope == "entity" or (
            handle.metadata.get("entity_projection_distinct_default") and distinct_scope != "scalar"
        )
        source_rows = (
            _distinct_rows_by_selected_entities(handle.rows, select)
            if entity_distinct
            else handle.rows
        )
        rows = []
        for row in source_rows:
            out: dict[str, Any] = {}
            if keep_entities:
                out.update(
                    {
                        key: value
                        for key, value in row.items()
                        if key != "__rel_ids" and _is_node_payload(value)
                    }
                )
            exploded_fields: list[tuple[str, list[Any]]] = []
            for item in select:
                alias = item.get("alias") or f"{item['var']}.{item['property']}"
                value = _row_property(row, item["var"], item["property"])
                if _bool_arg(item.get("explode")):
                    if value is None:
                        values = []
                    else:
                        values = list(value) if isinstance(value, list) else [value]
                    exploded_fields.append((str(alias), values))
                else:
                    out[alias] = value
            for index, order in enumerate(order_by):
                if order.get("field") or not order.get("var") or not order.get("property"):
                    continue
                out[_project_hidden_order_key(index)] = _row_property(
                    row,
                    str(order["var"]),
                    str(order["property"]),
                )
            rows.extend(_expand_projected_rows(out, exploded_fields))
        selectable_fields = _project_select_fields(select)
        for index, order in reversed(list(enumerate(order_by))):
            field = _project_order_field(order, selectable_fields) or _project_hidden_order_key(
                index
            )
            if not field:
                continue
            reverse = str(order.get("direction", "asc")).lower() == "desc"
            rows.sort(key=lambda item: (item.get(field) is None, item.get(field)), reverse=reverse)
        rows = [_strip_project_hidden_order_keys(row) for row in rows]
        scalar_distinct = distinct_requested and not (
            (handle.metadata.get("entity_set_operation") or entity_distinct)
            and str(args.get("distinct_scope") or "entity").lower() != "scalar"
        )
        if scalar_distinct:
            rows = _distinct_rows(rows)
        if args.get("limit") is not None:
            rows = rows[: int(args["limit"])]
        columns = [item.get("alias") or f"{item['var']}.{item['property']}" for item in select]
        result = self._store(rows, kind="table", columns=[str(column) for column in columns])
        if keep_entities:
            result["continuation_hint"] = (
                "This projection preserved entity variables for later graph work. "
                "Do not call project again with the same arguments. If the selected "
                "columns are already the final answer, call fetch; otherwise call a "
                "different graph, set, or aggregate tool next."
            )
        return result

    def _compare(self, args: dict[str, Any]) -> dict[str, Any]:
        left = self._first_row(str(args["left"]))
        right = self._first_row(str(args["right"]))
        left_var = str(args["left_var"])
        right_var = str(args["right_var"])
        prop = str(args["property"])
        op = str(args["op"])
        alias = str(args.get("alias") or "answer")
        self._validate_compare_operand(
            row=left,
            var=left_var,
            prop=prop,
            handle_id=str(args["left"]),
            side="left",
        )
        self._validate_compare_operand(
            row=right,
            var=right_var,
            prop=prop,
            handle_id=str(args["right"]),
            side="right",
        )
        left_value = _row_property(left, left_var, prop)
        right_value = _row_property(right, right_var, prop)
        if left_value is None or right_value is None:
            raise ValueError(
                f"Cannot compare missing values for property {prop!r}: "
                f"left={left_value!r}, right={right_value!r}"
            )

        if op == "argmax":
            chosen = left[left_var] if left_value >= right_value else right[right_var]
            rows = [{alias: chosen["properties"].get("name") or chosen["properties"].get("id")}]
        elif op == "argmin":
            chosen = left[left_var] if left_value <= right_value else right[right_var]
            rows = [{alias: chosen["properties"].get("name") or chosen["properties"].get("id")}]
        elif op in {"eq", "neq", "gt", "gte", "lt", "lte"}:
            rows = [{alias: _predicate(left_value, op, right_value)}]
        elif op == "difference":
            rows = [{alias: left_value - right_value}]
        else:
            raise ValueError(f"Unsupported compare op: {op}")
        return self._store(rows, kind="table", columns=[alias])

    def _scalar_compute(self, args: dict[str, Any]) -> dict[str, Any]:
        inputs = [item for item in _as_list(args.get("inputs")) if isinstance(item, dict)]
        op = str(args.get("op") or "")
        alias = str(args.get("alias") or "answer")
        if not inputs:
            raise ValueError(
                "scalar_compute requires at least one input with handle and column. "
                "Project scalar values first, then call scalar_compute."
            )
        if op not in {
            "difference",
            "absolute_difference",
            "sum",
            "min",
            "max",
            "avg",
            "argmin",
            "argmax",
        }:
            raise ValueError(
                "Unsupported scalar_compute op. Supported: difference, "
                "absolute_difference, sum, min, max, avg, argmin, argmax."
            )

        values: list[dict[str, Any]] = []
        for index, item in enumerate(inputs):
            handle_id = str(item.get("handle") or "")
            column = str(item.get("column") or "")
            row_index = _int_arg(item, "row_index", 0, min_value=0)
            if not handle_id or not column:
                raise ValueError(f"scalar_compute input {index} must include handle and column.")
            handle = self._handle(handle_id)
            if row_index >= len(handle.rows):
                raise ValueError(
                    f"scalar_compute input {index} row_index={row_index} is out of "
                    f"range for handle {handle_id} with {len(handle.rows)} rows."
                )
            row = handle.rows[row_index]
            if column not in row:
                raise ValueError(
                    f"scalar_compute input {index} column {column!r} is not present "
                    f"in handle {handle_id}. Available columns: {sorted(row.keys())}."
                )
            value = row[column]
            if not isinstance(value, int | float):
                raise ValueError(
                    f"scalar_compute input {index} column {column!r} must be numeric, "
                    f"got {type(value).__name__}: {value!r}."
                )
            values.append(
                {
                    "handle": handle_id,
                    "column": column,
                    "alias": item.get("alias") or column,
                    "value": value,
                }
            )

        numeric_values = [item["value"] for item in values]
        if op in {"difference", "absolute_difference"} and len(numeric_values) != 2:
            raise ValueError(f"scalar_compute op {op!r} requires exactly two numeric inputs.")
        if op in {"argmin", "argmax"} and not values:
            raise ValueError(f"scalar_compute op {op!r} requires at least one input.")

        if op == "difference":
            answer = numeric_values[0] - numeric_values[1]
        elif op == "absolute_difference":
            answer = abs(numeric_values[0] - numeric_values[1])
        elif op == "sum":
            answer = sum(numeric_values)
        elif op == "min":
            answer = min(numeric_values)
        elif op == "max":
            answer = max(numeric_values)
        elif op == "avg":
            answer = sum(numeric_values) / len(numeric_values)
        elif op == "argmin":
            answer = min(values, key=lambda item: item["value"])["alias"]
        else:
            answer = max(values, key=lambda item: item["value"])["alias"]

        result = self._store([{alias: answer}], kind="table", columns=[alias])
        result["scalar_compute"] = {"op": op, "inputs": values}
        result["finalization_hint"] = "This scalar result is ready to fetch as the final answer."
        return result

    def _validate_compare_operand(
        self,
        *,
        row: dict[str, Any],
        var: str,
        prop: str,
        handle_id: str,
        side: str,
    ) -> None:
        if var not in row:
            entity_vars = _entity_vars(row)
            raise ValueError(
                f"compare {side} operand variable {var!r} is not present in handle {handle_id}. "
                f"Available entity variables: {entity_vars}; all columns: {_columns([row])}. "
                "Compare entity handles directly, or if you used project before compare, "
                "rerun project with keep_entities=true."
            )
        if not _is_node_payload(row[var]):
            raise ValueError(
                f"compare {side} operand variable {var!r} in handle {handle_id} is scalar/table-shaped, "
                "but compare requires an entity variable. Use the original entity handle or "
                "project with keep_entities=true before compare."
            )
        if prop not in row[var].get("properties", {}):
            raise ValueError(
                f"compare {side} operand entity {var!r} in handle {handle_id} does not have "
                f"property {prop!r}. Available properties: {sorted(row[var].get('properties', {}))}"
            )

    def _fetch(self, args: dict[str, Any]) -> dict[str, Any]:
        handle = self._handle(str(args["from"]))
        limit = _int_arg(args, "limit", 1000, min_value=1)
        offset = _int_arg(args, "offset", 0, min_value=0)
        handle_rows = handle.rows
        if (
            handle.focus
            and handle.metadata.get("entity_projection_distinct_default")
            and handle.kind != "table"
        ):
            handle_rows = _distinct_rows_by_selected_entities(
                handle.rows,
                [{"var": handle.focus, "property": "id"}],
            )
        rows = handle_rows[offset : offset + limit]
        if handle.kind == "table":
            columns = handle.columns or _columns(rows)
            data = [[row.get(column) for column in columns] for row in rows]
        elif handle.metadata.get("preferred_fetch_columns"):
            columns = list(handle.metadata["preferred_fetch_columns"])
            data = [[row.get(column) for column in columns] for row in rows]
        else:
            focus = handle.focus
            columns = [f"{focus}.name"] if focus else ["value"]
            data = [
                [row[focus]["properties"].get("name") if focus and focus in row else row]
                for row in rows
            ]
        self.last_fetch = data
        result = {
            "columns": columns,
            "rows": data[:20],
            "returned_count": len(data),
            "offset": offset,
            "limit": limit,
            "total_count": len(handle_rows),
            "next_offset": offset + len(data) if offset + len(data) < len(handle_rows) else None,
            "truncated": offset + len(data) < len(handle_rows),
        }
        if result["truncated"]:
            result["pagination_hint"] = (
                "This fetch returned only one page. If the final answer requires all rows, "
                "call fetch again with next_offset. If the question asks for a count or "
                "grouped summary, use count_handle or group_handle instead of paging raw rows."
            )
        return result

    def _store(
        self,
        rows: list[dict[str, Any]],
        *,
        focus: str | None = None,
        kind: str = "rows",
        columns: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._ensure_handle_store().store(
            rows,
            focus=focus,
            kind=kind,
            columns=columns,
            metadata=metadata,
        )

    def _guard_large_handle_input(
        self,
        handle: Handle,
        *,
        tool: str,
        var: str,
        args: dict[str, Any],
        alternatives: list[str],
    ) -> None:
        max_input_rows = _int_arg(
            args,
            "max_input_rows",
            self._DEFAULT_MAX_INPUT_ROWS,
            min_value=1,
        )
        if len(handle.rows) <= max_input_rows or args.get("allow_large"):
            return
        entity_vars = _handle_entity_vars(handle.rows)
        raise ValueError(
            f"{tool} would consume a large handle: {handle.id} has {len(handle.rows)} "
            f"rows, max_input_rows={max_input_rows}, requested var={var!r}. "
            f"Available entity variables: {entity_vars}. This plan can generate a very "
            "large backend query. Use one of these safer alternatives: "
            + "; ".join(alternatives)
            + ". Set allow_large=true only when the user explicitly needs the full broad traversal."
        )

    def _guard_large_entity_set_operands(
        self,
        args: dict[str, Any],
        operands: list[Any],
    ) -> None:
        max_operand_rows = _int_arg(
            args,
            "max_operand_rows",
            self._DEFAULT_MAX_SET_OPERAND_ROWS,
            min_value=1,
        )
        if args.get("allow_large"):
            return
        large_operands: list[str] = []
        for operand in operands:
            if not isinstance(operand, dict) or "handle" not in operand:
                continue
            handle = self._handle(str(operand["handle"]))
            if len(handle.rows) > max_operand_rows:
                large_operands.append(f"{handle.id}:{len(handle.rows)}")
        if not large_operands:
            return
        raise ValueError(
            "entity_set_operation would combine very large materialized handles "
            f"({', '.join(large_operands)}), max_operand_rows={max_operand_rows}. "
            "For count-only OR questions, use set_count_by_patterns. For grouped "
            "answers, push filters into pattern_query/constraint_query and aggregate "
            "server-side before materializing rows. Set allow_large=true only when "
            "the user explicitly needs the full combined entity set."
        )

    def _resolve_seed_var_from_handle(self, seed_handle: Handle, seed_var: str) -> str:
        if any(_is_node_payload(row.get(seed_var)) for row in seed_handle.rows):
            return seed_var
        entity_vars = _handle_entity_vars(seed_handle.rows)
        if len(entity_vars) == 1:
            return str(entity_vars[0])
        return seed_var

    def _handle(self, handle_id: str) -> Handle:
        return self._ensure_handle_store().get(handle_id)

    def _first_row(self, handle_id: str) -> dict[str, Any]:
        return self._ensure_handle_store().first_row(handle_id)

    def _record_handle_lineage(
        self,
        tool: str,
        args: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        self._ensure_handle_store().record_lineage(tool, args, result)

    def _available_handle_summaries(self) -> list[dict[str, Any]]:
        return self._ensure_handle_store().available_summaries()

    def _handle_summary(self, handle_id: str) -> dict[str, Any]:
        return self._ensure_handle_store().summary(handle_id)


def _coerce_filter_value(value: Any, value_type: Any) -> Any:
    normalized_type = str(value_type or "").lower()
    if value is None:
        return None
    if normalized_type == "integer":
        return int(value)
    return value


if __name__ == "__main__":
    main()
