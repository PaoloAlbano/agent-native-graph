"""Engine-neutral ANA schema, planning, handles and local row operations."""

import json
from abc import abstractmethod
from typing import Any

from agent_native_graph.core.backend import AgentGraphBackend
from agent_native_graph.core.graph_utils import (
    _as_list,
    _bool_arg,
    _columns,
    _dedupe_preserve_order,
    _distinct_rows,
    _distinct_rows_by_selected_entities,
    _entity_vars,
    _expand_projected_rows,
    _handle_entity_vars,
    _handle_var_labels,
    _inferred_type,
    _int_arg,
    _is_node_payload,
    _metric_identity,
    _metric_scalar_value,
    _pattern_bound_vars,
    _predicate,
    _preview,
    _project_hidden_order_key,
    _project_order_field,
    _project_select_fields,
    _properties_by_label,
    _properties_by_relationship,
    _question_features,
    _row_property,
    _schema_candidates,
    _strip_project_hidden_order_keys,
    _summarize_row,
    _tokens,
    _validate_membership_operand,
)
from agent_native_graph.core.handle_store import HandleStore
from agent_native_graph.domain.entities import entity_identity
from agent_native_graph.domain.handles import Handle


class SharedGraphBackend(AgentGraphBackend):
    """Shared runtime; concrete engines implement graph reads and sampling hooks."""

    _DEFAULT_MAX_INPUT_ROWS = 5000
    _DEFAULT_MAX_SET_OPERAND_ROWS = 10000
    _identity = None

    @abstractmethod
    def _label_counts(self, labels):
        """Return counts for the requested labels from this workflow's graph."""

    @abstractmethod
    def _node_property_samples(self, label, prop, *, limit=3):
        """Sample node values through the concrete engine."""

    @abstractmethod
    def _relationship_property_samples(self, rel_type, prop, *, limit=3):
        """Sample relationship values through the concrete engine."""

    def _entity_key(self, value):
        return entity_identity(value)

    def _server_side_entity_set_count(self, handle, *, var, distinct):
        return None

    def _combined_server_side_entity_metadata(
        self, *, op, left, right, left_var, right_var, out_var
    ):
        return None

    def close(self):
        self._ensure_handle_store().clear()

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

    def _schema_inspect(self) -> dict[str, Any]:
        from agent_native_graph.core.schema_runtime import schema_inspect

        return schema_inspect(self)

    def _schema_overview(self) -> dict[str, Any]:
        from agent_native_graph.core.schema_runtime import schema_overview

        return schema_overview(self)

    def _schema_search(self, args: dict[str, Any]) -> dict[str, Any]:
        from agent_native_graph.core.schema_runtime import schema_search

        return schema_search(self, **args)

    def _schema_describe_label(self, args: dict[str, Any]) -> dict[str, Any]:
        from agent_native_graph.core.schema_runtime import schema_describe_label

        return schema_describe_label(self, **args)

    def _schema_describe_relationship(self, args: dict[str, Any]) -> dict[str, Any]:
        from agent_native_graph.core.schema_runtime import schema_describe_relationship

        return schema_describe_relationship(self, **args)

    def _schema_score(self, query_tokens: set[str], values: list[Any]) -> int:
        from agent_native_graph.core.schema_runtime import schema_score

        return schema_score(self, query_tokens, values)

    def _schema_get(self) -> dict[str, Any]:
        from agent_native_graph.core.schema_runtime import schema_get

        return schema_get(self)

    def _schema_affordance(self) -> dict[str, Any]:
        from agent_native_graph.core.schema_runtime import schema_affordance

        return schema_affordance(self)

    def _node_property_affordances(
        self, label: str, props: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        from agent_native_graph.core.schema_runtime import node_property_affordances

        return node_property_affordances(self, label, props)

    def _inspect_paths(self, args: dict[str, Any]) -> dict[str, Any]:
        from agent_native_graph.core.schema_runtime import inspect_paths

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
                self._entity_key(row[str(var)])
                for row in handle.rows
                if str(var) in row and isinstance(row[str(var)], dict)
            ]
            count = len(set(values)) if distinct else len(values)
        elif distinct and getattr(self, "_identity", None) is not None:
            count = len(_distinct_rows(handle.rows, use_references=True))
        else:
            keys = {
                json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
                for row in handle.rows
            }
            count = len(keys) if distinct else len(handle.rows)
        return self._store([{alias: count}], kind="table", columns=[alias])

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
        _validate_membership_operand(op, flt.get("value"))
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
            and self._entity_key(row[left_var]) == self._entity_key(row[right_var])
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
            self._entity_key(row[right_var]): row
            for row in right.rows
            if right_var in row and isinstance(row[right_var], dict)
        }
        rows: list[dict[str, Any]] = []
        for row in left.rows:
            if left_var not in row or not isinstance(row[left_var], dict):
                continue
            item_id = self._entity_key(row[left_var])
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

    def _combine(self, args: dict[str, Any]) -> dict[str, Any]:
        left = self._handle(str(args["left"]))
        right = self._handle(str(args["right"]))
        op = str(args["op"])
        left_var = str(args.get("left_var") or left.focus)
        right_var = str(args.get("right_var") or right.focus)
        out_var = str(args.get("as") or left_var)
        left_by_id = {
            self._entity_key(row[left_var]): row
            for row in left.rows
            if _is_node_payload(row.get(left_var))
        }
        right_by_id = {
            self._entity_key(row[right_var]): row
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
            rows = _distinct_rows(rows, use_references=getattr(self, "_identity", None) is not None)
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
        """Return a complete stored-handle page with a separate bounded preview."""
        paging = {}
        for name, default, minimum in (("limit", 1000, 1), ("offset", 0, 0)):
            value = args.get(name)
            value = default if value is None else value
            if type(value) is not int or value < minimum:
                raise ValueError(f"fetch {name} must be an integer >= {minimum}")
            paging[name] = value
        handle = self._handle(str(args["from"]))
        limit, offset = paging["limit"], paging["offset"]
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
            "contract_version": "ana-fetch-v1",
            "columns": columns,
            "rows": data,
            "preview": data[:20],
            "preview_truncated": len(data) > 20,
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
