import json
import re
from typing import Any

from agent_native_graph.core.tool_specs import _native_system_prompt, _tool_specs

LIST_ARG_KEYS = {
    "where",
    "filters",
    "hops",
    "select",
    "group_by",
    "metrics",
    "order_by",
    "relationships",
    "operands",
}


def _json_system_prompt(*, enable_planning_tools: bool, schema_entry: str) -> str:
    """Build JSON-mode tool guidance from the same decorator specs used by native calls."""
    tool_lines = []
    for spec in _tool_specs(
        enable_planning_tools=enable_planning_tools,
        schema_entry=schema_entry,
    ):
        function = spec["function"]
        tool_lines.append(
            {
                "name": function["name"],
                "description": function["description"],
                "parameters": function["parameters"],
            }
        )
    return (
        "You are an agent using graph tools. Do not write Cypher.\n"
        "You must answer by composing tool calls over server-side handles.\n"
        "Every response must be a single JSON object with shape "
        '{"tool":"<tool_name>","args":{...}}.\n'
        "Call exactly one tool at a time. Use fetch only when the answer handle is ready.\n"
        "Available tools are generated from the current tool registry:\n"
        f"{json.dumps(tool_lines, ensure_ascii=False)}"
    )


def _task_prompt(question: str, transcript: list[dict[str, Any]]) -> str:
    return json.dumps(
        {
            "question": question,
            "previous_tool_results": transcript[-8:],
            "instruction": "Choose the next tool call. Use fetch when the answer handle is ready.",
        },
        ensure_ascii=False,
    )


def _next_action(
    llm: Any,
    question: str,
    transcript: list[dict[str, Any]],
    *,
    native_tools: bool,
    tool_choice: str,
    enable_planning_tools: bool,
    schema_entry: str,
    enable_runner_guardrails: bool = False,
) -> dict[str, Any]:
    if not native_tools:
        message = llm.chat(
            [
                {
                    "role": "system",
                    "content": _json_system_prompt(
                        enable_planning_tools=enable_planning_tools,
                        schema_entry=schema_entry,
                    ),
                },
                {"role": "user", "content": _task_prompt(question, transcript)},
            ]
        )
        raw = str(message.get("content") or "")
        try:
            action = _parse_action(raw)
        except json.JSONDecodeError:
            if enable_runner_guardrails:
                action = _fallback_action(transcript)
                action["_llm_meta"] = message.get("__chat_meta")
                return action
            raise
        action["args"] = _normalize_tool_args(action.get("args") or {})
        action["_llm_meta"] = message.get("__chat_meta")
        return action

    message = llm.chat(
        [
            {
                "role": "system",
                "content": _native_system_prompt(
                    enable_planning_tools=enable_planning_tools,
                    schema_entry=schema_entry,
                ),
            },
            {"role": "user", "content": _task_prompt(question, transcript)},
        ],
        tools=_tool_specs(enable_planning_tools=enable_planning_tools, schema_entry=schema_entry),
        tool_choice=tool_choice,
    )
    tool_calls = message.get("tool_calls") or []
    if tool_calls:
        call = tool_calls[0]
        function = call.get("function") or {}
        name = str(function.get("name") or "")
        raw_args = function.get("arguments") or "{}"
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args or "{}")
            except json.JSONDecodeError:
                if enable_runner_guardrails:
                    return _fallback_action(transcript)
                raise
        elif isinstance(raw_args, dict):
            args = raw_args
        else:
            raise ValueError(f"Unsupported native tool arguments: {raw_args!r}")
        return {
            "tool": name,
            "args": _normalize_tool_args(_normalize_native_args(args)),
            "_llm_meta": message.get("__chat_meta"),
        }

    content = str(message.get("content") or "").strip()
    if content:
        try:
            action = _parse_action(content)
        except json.JSONDecodeError:
            if enable_runner_guardrails:
                action = _fallback_action(transcript)
                action["_llm_meta"] = message.get("__chat_meta")
                return action
            raise
        action["args"] = _normalize_tool_args(action.get("args") or {})
        action["_llm_meta"] = message.get("__chat_meta")
        return action
    if enable_runner_guardrails:
        action = _fallback_action(transcript)
        action["_llm_meta"] = message.get("__chat_meta")
        return action
    raise ValueError("Model did not return a native tool call or JSON action.")


def _fallback_action(transcript: list[dict[str, Any]]) -> dict[str, Any]:
    handle = _latest_fetchable_handle(transcript)
    if handle is not None:
        return {
            "tool": "fetch",
            "args": {"from": handle, "limit": 1000},
            "auto": True,
            "reason": "fallback_fetch",
        }
    return {"tool": "schema_overview", "args": {}}


def _guarded_action(
    question: str,
    transcript: list[dict[str, Any]],
    action: dict[str, Any],
) -> dict[str, Any]:
    if _latest_result_has_finalization_hint(transcript):
        handle = _latest_fetchable_handle(transcript)
        if handle is not None and action.get("tool") != "fetch":
            return {
                "tool": "fetch",
                "args": {"from": handle, "limit": 1000},
                "auto": True,
                "reason": "finalization_hint_guard",
                "blocked_action": action,
            }

    if action.get("tool") == "schema_overview" and _tool_was_called(transcript, "schema_overview"):
        handle = _latest_fetchable_handle(transcript)
        if handle is not None:
            return {
                "tool": "fetch",
                "args": {"from": handle, "limit": 1000},
                "auto": True,
                "reason": "duplicate_schema_overview_guard",
                "blocked_action": action,
            }
        return {
            "tool": "schema_search",
            "args": {"query": question, "limit": 8},
            "auto": True,
            "reason": "duplicate_schema_overview_guard",
            "blocked_action": action,
        }

    return action


def _latest_result_has_finalization_hint(transcript: list[dict[str, Any]]) -> bool:
    for step in reversed(transcript):
        result = step.get("result") or {}
        if not isinstance(result, dict):
            continue
        if result.get("status") == "tool_error":
            continue
        return bool(result.get("finalization_hint"))
    return False


def _evaluation_fetch_all_pages(
    backend: Any,
    action: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    if not result.get("truncated"):
        return result
    args = dict(action.get("args") or {})
    handle = args.get("from")
    total_count = int(result.get("total_count") or 0)
    if not handle or total_count <= int(result.get("returned_count") or 0):
        return result
    full_result = backend.call(
        "fetch",
        {
            "from": handle,
            "offset": 0,
            "limit": total_count,
        },
    )
    full_result["evaluation_fetch_all_pages"] = True
    full_result["model_requested_limit"] = args.get("limit")
    return full_result


def _tool_was_called(transcript: list[dict[str, Any]], tool: str) -> bool:
    return any((step.get("action") or {}).get("tool") == tool for step in transcript)


def _normalize_native_args(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize_native_args(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_native_args(item) for item in value]
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                return _normalize_native_args(json.loads(stripped))
            except json.JSONDecodeError:
                return value
    return value


def _normalize_tool_args(args: Any) -> dict[str, Any]:
    if not isinstance(args, dict):
        return {}
    normalized = dict(args)
    for key in LIST_ARG_KEYS:
        if key in normalized:
            normalized[key] = _normalize_list_arg(normalized[key])
    return normalized


def _normalize_list_arg(value: Any) -> list[Any]:
    value = _normalize_native_args(value)
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [_normalize_native_args(item) for item in value]
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                return _normalize_list_arg(json.loads(stripped))
            except json.JSONDecodeError:
                return []
    return []


def _latest_fetchable_handle(transcript: list[dict[str, Any]]) -> str | None:
    diagnostic_tools = {
        "schema_overview",
        "schema_search",
        "schema_describe_label",
        "schema_describe_relationship",
        "schema_inspect",
        "schema_get",
        "schema_affordance",
        "draft_tool_plan",
        "validate_tool_plan",
        "inspect_paths",
        "summarize_handle",
        "repair_empty_result",
    }
    final_answer_tools = {
        "group_handle",
        "aggregate",
        "compare",
        "count_handle",
        "count_nodes",
        "expand_aggregate",
        "constraint_query",
        "filter",
        "project",
        "relationship_query",
        "shared_role_aggregate",
        "scalar_compute",
    }
    for step in reversed(transcript):
        action = step.get("action") or {}
        tool = action.get("tool")
        if tool in diagnostic_tools:
            continue
        result = step.get("result") or {}
        if not isinstance(result, dict):
            continue
        handle = result.get("handle")
        if not handle:
            continue
        # Auto-fetch is deliberately conservative: exploratory entity handles
        # such as node_scan/expand are usually intermediate, while table-shaped
        # or explicitly projecting/counting tools are much more likely final.
        if result.get("kind") == "table" or tool in final_answer_tools:
            return str(handle)
    return None


def _parse_action(raw: str) -> dict[str, Any]:
    stripped = raw.strip()
    match = re.search(r"```(?:json)?\s*(.*?)```", stripped, flags=re.DOTALL)
    if match:
        stripped = match.group(1).strip()
    return json.loads(stripped)
