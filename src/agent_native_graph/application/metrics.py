from collections import Counter
from typing import Any


def _summarize_llm_metrics(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    finish_reasons = Counter(
        str(item.get("finish_reason")) for item in metrics if item.get("finish_reason") is not None
    )
    initial_finish_reasons = Counter(
        str(item.get("initial_finish_reason"))
        for item in metrics
        if item.get("initial_finish_reason") is not None
    )
    usage_totals: Counter[str] = Counter()
    initial_usage_totals: Counter[str] = Counter()
    completion_detail_totals: Counter[str] = Counter()
    prompt_detail_totals: Counter[str] = Counter()
    for item in metrics:
        _add_usage_totals(usage_totals, item.get("usage"))
        _add_usage_totals(initial_usage_totals, item.get("initial_usage"))
        usage = item.get("usage") if isinstance(item.get("usage"), dict) else {}
        _add_usage_totals(
            completion_detail_totals,
            usage.get("completion_tokens_details") if isinstance(usage, dict) else {},
        )
        _add_usage_totals(
            prompt_detail_totals,
            usage.get("prompt_tokens_details") if isinstance(usage, dict) else {},
        )
    return {
        "finish_reasons": dict(finish_reasons),
        "initial_finish_reasons": dict(initial_finish_reasons),
        "low_effort_retry_count": sum(1 for item in metrics if item.get("low_effort_retry")),
        "rate_limit_retries": sum(int(item.get("rate_limit_retries") or 0) for item in metrics),
        "http_retries": sum(int(item.get("http_retries") or 0) for item in metrics),
        "request_attempts": sum(int(item.get("request_attempts") or 0) for item in metrics),
        "usage_totals": dict(usage_totals),
        "initial_usage_totals": dict(initial_usage_totals),
        "completion_tokens_details_totals": dict(completion_detail_totals),
        "prompt_tokens_details_totals": dict(prompt_detail_totals),
    }


def _add_usage_totals(target: Counter[str], usage: Any) -> None:
    if not isinstance(usage, dict):
        return
    for key, value in usage.items():
        if isinstance(value, int | float):
            target[str(key)] += value


def _summarize_tool_metrics(transcript: list[dict[str, Any]]) -> dict[str, Any]:
    tool_counts: Counter[str] = Counter()
    dirty_schema_args = 0
    duplicate_schema_overview_calls = 0
    repeated_targeted_schema_calls = 0
    seen_targeted_schema: set[tuple[str, Any]] = set()
    schema_tools = {
        "schema_overview",
        "schema_search",
        "schema_describe_label",
        "schema_describe_relationship",
    }
    for step in transcript:
        action = step.get("action") or {}
        if not isinstance(action, dict):
            continue
        tool = str(action.get("tool") or "")
        if not tool:
            continue
        tool_counts[tool] += 1
        args = action.get("args") if isinstance(action.get("args"), dict) else {}
        if tool == "schema_overview":
            if tool_counts[tool] > 1:
                duplicate_schema_overview_calls += 1
            if args:
                dirty_schema_args += 1
        elif tool == "schema_search":
            key = (tool, args.get("query"))
            if key in seen_targeted_schema:
                repeated_targeted_schema_calls += 1
            seen_targeted_schema.add(key)
            if set(args) - {"query", "limit"}:
                dirty_schema_args += 1
        elif tool == "schema_describe_label":
            key = (tool, args.get("label"))
            if key in seen_targeted_schema:
                repeated_targeted_schema_calls += 1
            seen_targeted_schema.add(key)
            if set(args) - {"label"}:
                dirty_schema_args += 1
        elif tool == "schema_describe_relationship":
            key = (tool, args.get("relationship_type"))
            if key in seen_targeted_schema:
                repeated_targeted_schema_calls += 1
            seen_targeted_schema.add(key)
            if set(args) - {"relationship_type"}:
                dirty_schema_args += 1
    return {
        "tool_counts": dict(tool_counts),
        "schema_tool_calls": sum(tool_counts.get(tool, 0) for tool in schema_tools),
        "duplicate_schema_overview_calls": duplicate_schema_overview_calls,
        "repeated_targeted_schema_calls": repeated_targeted_schema_calls,
        "dirty_schema_args": dirty_schema_args,
    }


def classify_failure(row: dict[str, Any]) -> str | None:
    """Classify benchmark failures without changing execution behavior."""
    if row.get("matches_answer_json"):
        return None
    error = str(row.get("error") or "")
    transcript = row.get("transcript") or []
    tool_errors: list[str] = []
    for step in transcript:
        result = step.get("result") if isinstance(step, dict) else None
        if isinstance(result, dict) and result.get("status") == "tool_error":
            tool_errors.append(str(result.get("error") or ""))
    combined = "\n".join([error, *tool_errors]).lower()
    if "jsondecodeerror" in combined:
        return "json_decode"
    if "transactiontimedout" in combined or "timeout" in combined:
        return "backend_timeout"
    if "unknown handle" in combined:
        return "unknown_handle"
    if "not bound" in combined or "unbound" in combined:
        return "unbound_variable"
    if "must be numeric" in combined or "unsupported scalar_compute" in combined:
        return "scalar_compute_error"
    if not row.get("ok"):
        return "no_final_fetch_or_max_steps"
    return "semantic_mismatch"


def _update_summary(summary: dict[str, Any], row: dict[str, Any]) -> None:
    summary["total"] += 1
    summary["tool_success"] += int(bool(row["ok"]))
    summary["matches_answer_json"] += int(bool(row["matches_answer_json"]))
    summary["tool_calls"] += int(row["tool_call_count"])
    summary["llm_calls"] += int(row["llm_call_count"])
    llm_summary = row.get("llm_metric_summary") or {}
    summary["llm_low_effort_retries"] = summary.get("llm_low_effort_retries", 0) + int(
        llm_summary.get("low_effort_retry_count") or 0
    )
    summary["llm_initial_length_finishes"] = summary.get("llm_initial_length_finishes", 0) + int(
        llm_summary.get("initial_finish_reasons", {}).get("length") or 0
    )
    summary["llm_final_length_finishes"] = summary.get("llm_final_length_finishes", 0) + int(
        llm_summary.get("finish_reasons", {}).get("length") or 0
    )
    summary["llm_rate_limit_retries"] = summary.get("llm_rate_limit_retries", 0) + int(
        llm_summary.get("rate_limit_retries") or 0
    )
    usage_totals = llm_summary.get("usage_totals") or {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        summary[f"llm_{key}"] = summary.get(f"llm_{key}", 0) + int(usage_totals.get(key) or 0)
    tool_summary = row.get("tool_metric_summary") or {}
    summary["dirty_schema_args"] = summary.get("dirty_schema_args", 0) + int(
        tool_summary.get("dirty_schema_args") or 0
    )
    summary["duplicate_schema_overview_calls"] = summary.get(
        "duplicate_schema_overview_calls", 0
    ) + int(tool_summary.get("duplicate_schema_overview_calls") or 0)
    summary["repeated_targeted_schema_calls"] = summary.get(
        "repeated_targeted_schema_calls", 0
    ) + int(tool_summary.get("repeated_targeted_schema_calls") or 0)
    failure_class = row.get("failure_class")
    if failure_class:
        key = f"failure_{failure_class}"
        summary[key] = summary.get(key, 0) + 1
