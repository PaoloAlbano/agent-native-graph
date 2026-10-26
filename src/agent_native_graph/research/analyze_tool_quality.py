import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

DEFAULT_RUNS = [
    (
        "defensive_v4",
        "agent_tools_company_gpt_oss_120b_native_tooldesc_v4_defensive_contracts.jsonl",
    ),
    (
        "planning_v5",
        "agent_tools_company_gpt_oss_120b_native_generic_planning_v5.jsonl",
    ),
    (
        "fetch_guard_v6e",
        "agent_tools_company_gpt_oss_120b_native_fetch_guard_conservative_v6e_full.jsonl",
    ),
]

CORE_RESULT_TOOLS = {
    "fetch",
    "project",
    "count_handle",
    "group_count_by_pattern",
    "expand_aggregate",
    "aggregate",
    "compare",
}

PATH_TOOLS = {
    "expand",
    "pattern_query",
    "relationship_query",
    "multi_hop_query",
    "group_count_by_pattern",
    "expand_aggregate",
}


@dataclass(frozen=True)
class RunSpec:
    name: str
    path: Path
    rows: list[dict[str, Any]]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    parser.add_argument("--markdown-out", type=Path, required=True)
    parser.add_argument(
        "--run",
        action="append",
        nargs=2,
        metavar=("NAME", "JSONL"),
        help="Optional run name and JSONL filename/path. Can be repeated.",
    )
    parser.add_argument(
        "--compare",
        action="append",
        nargs=2,
        metavar=("BASELINE_NAME", "CANDIDATE_NAME"),
        help="Optional pair of run names for regression/fix association.",
    )
    args = parser.parse_args()

    specs = _load_specs(args.runs_dir, args.run)
    if not specs:
        raise SystemExit("No run files found.")

    compare_pairs = args.compare or [
        ("defensive_v4", "planning_v5"),
        ("planning_v5", "fetch_guard_v6e"),
    ]
    lines = _build_report(specs, compare_pairs)
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:140]))


def _load_specs(runs_dir: Path, overrides: list[list[str]] | None) -> list[RunSpec]:
    items = (
        [(name, Path(filename)) for name, filename in overrides]
        if overrides
        else [(name, Path(filename)) for name, filename in DEFAULT_RUNS]
    )
    specs: list[RunSpec] = []
    for name, raw_path in items:
        path = raw_path if raw_path.exists() else runs_dir / raw_path
        if not path.exists():
            print(f"Skipping missing run: {path}")
            continue
        specs.append(RunSpec(name=name, path=path, rows=_load(path)))
    return specs


def _load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _build_report(specs: list[RunSpec], compare_pairs: list[list[str]]) -> list[str]:
    by_name = {spec.name: spec for spec in specs}
    lines: list[str] = [
        "# Agent Tool Quality Analysis",
        "",
        "This report diagnoses the agent-first tool surface using full CypherBench company runs.",
        "The goal is to identify which tools are useful, which correlate with wrong answers, and where the interface should be simplified.",
        "",
        "## Runs",
        "",
        "| run | total | correct | accuracy | success | avg LLM calls | avg tool calls | tool errors |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for spec in specs:
        lines.append(_summary_row(spec))

    lines.extend(
        [
            "",
            "## Most Called Tools",
            "",
            "This is the first pass: if a tool is called constantly, small contract problems become large quality problems.",
            "",
            "| run | top tools by calls | top tools by tasks |",
            "|---|---|---|",
        ]
    )
    for spec in specs:
        metrics = _tool_metrics(spec.rows)
        top_calls = ", ".join(
            f"`{tool}` {item['calls']}"
            for tool, item in sorted(
                metrics.items(), key=lambda pair: pair[1]["calls"], reverse=True
            )[:8]
        )
        top_tasks = ", ".join(
            f"`{tool}` {item['tasks']}"
            for tool, item in sorted(
                metrics.items(), key=lambda pair: pair[1]["tasks"], reverse=True
            )[:8]
        )
        lines.append(f"| `{spec.name}` | {top_calls} | {top_tasks} |")

    lines.extend(
        [
            "",
            "## Per-Tool Accuracy Lift",
            "",
            "Lift compares accuracy on questions where a tool appears against questions where it does not appear in the same run.",
            "A negative lift does not prove the tool is bad: hard questions naturally call more tools. But strong negative lift plus errors/zero rows is a design smell.",
            "",
        ]
    )
    for spec in specs:
        lines.extend(_per_tool_section(spec))

    lines.extend(
        [
            "",
            "## Failure Signals By Tool",
            "",
            "These counters are call-level signals: tool errors, zero matched rows for path-like tools, broad intermediates, truncated results, and final-position frequency.",
            "",
        ]
    )
    for spec in specs:
        lines.extend(_failure_signal_section(spec))

    lines.extend(
        [
            "",
            "## Sequence Smells",
            "",
            "These are common tool sequences in wrong trajectories. They are useful because interface problems often show up as repeated choreography, not just isolated tools.",
            "",
        ]
    )
    for spec in specs:
        lines.extend(_sequence_section(spec))

    lines.extend(
        [
            "",
            "## Regression And Fix Associations",
            "",
            "For each pair, a tool is counted when it appears in a regressed/fixed candidate trajectory.",
            "This helps separate tools that merely exist from tools introduced in trajectories that changed the outcome.",
            "",
        ]
    )
    for left_name, right_name in compare_pairs:
        if left_name in by_name and right_name in by_name:
            lines.extend(_transition_tool_section(by_name[left_name], by_name[right_name]))

    lines.extend(_recommendations(specs))
    return lines


def _summary_row(spec: RunSpec) -> str:
    rows = spec.rows
    total = len(rows)
    correct = sum(_correct(row) for row in rows)
    success = sum(bool(row.get("ok") or row.get("executable")) for row in rows)
    tool_errors = sum(_tool_error_count(row) for row in rows)
    accuracy = correct / total if total else 0.0
    avg_llm = mean(float(row.get("llm_call_count") or 0) for row in rows) if rows else 0.0
    avg_tools = mean(float(row.get("tool_call_count") or 0) for row in rows) if rows else 0.0
    return (
        f"| `{spec.name}` | {total} | {correct} | {accuracy:.2%} | {success} | "
        f"{avg_llm:.2f} | {avg_tools:.2f} | {tool_errors} |"
    )


def _per_tool_section(spec: RunSpec) -> list[str]:
    rows = spec.rows
    total = len(rows)
    total_correct = sum(_correct(row) for row in rows)
    overall_acc = total_correct / total if total else 0.0
    metrics = _tool_metrics(rows)
    lines = [
        f"### `{spec.name}`",
        "",
        "| tool | calls | tasks | acc with tool | acc without tool | lift | avg position | avg calls when used |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for tool, item in sorted(metrics.items(), key=lambda pair: (-pair[1]["tasks"], pair[0])):
        tasks = item["tasks"]
        if not tasks:
            continue
        with_acc = item["correct_tasks"] / tasks
        without_total = total - tasks
        without_correct = total_correct - item["correct_tasks"]
        without_acc = without_correct / without_total if without_total else overall_acc
        lift = with_acc - without_acc
        avg_position = mean(item["positions"]) if item["positions"] else 0.0
        avg_calls_when_used = mean(item["calls_per_task"]) if item["calls_per_task"] else 0.0
        lines.append(
            f"| `{tool}` | {item['calls']} | {tasks} | {with_acc:.2%} | "
            f"{without_acc:.2%} | {lift:+.2%} | {avg_position:.2f} | {avg_calls_when_used:.2f} |"
        )
    lines.append("")
    return lines


def _failure_signal_section(spec: RunSpec) -> list[str]:
    metrics = _tool_metrics(spec.rows)
    lines = [
        f"### `{spec.name}`",
        "",
        "| tool | errors | zero matches | broad matches | truncated | last tool | wrong when last |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for tool, item in sorted(
        metrics.items(),
        key=lambda pair: (
            -(pair[1]["errors"] + pair[1]["zero"] + pair[1]["broad"] + pair[1]["truncated"]),
            pair[0],
        ),
    ):
        if item["calls"] == 0:
            continue
        noisy = item["errors"] + item["zero"] + item["broad"] + item["truncated"] + item["last"]
        if noisy == 0 and item["tasks"] < 10:
            continue
        lines.append(
            f"| `{tool}` | {item['errors']} | {item['zero']} | {item['broad']} | "
            f"{item['truncated']} | {item['last']} | {item['wrong_last']} |"
        )
    lines.append("")
    return lines


def _sequence_section(spec: RunSpec) -> list[str]:
    wrong_bigrams: Counter[str] = Counter()
    correct_bigrams: Counter[str] = Counter()
    wrong_last: Counter[str] = Counter()
    repeated: Counter[str] = Counter()
    for row in spec.rows:
        tools = _tools(row)
        bigrams = [f"{a} -> {b}" for a, b in zip(tools, tools[1:], strict=False)]
        if _correct(row):
            correct_bigrams.update(bigrams)
        else:
            wrong_bigrams.update(bigrams)
            if tools:
                wrong_last[tools[-1]] += 1
        for tool, count in Counter(tools).items():
            if count >= 3:
                repeated[tool] += 1

    lines = [
        f"### `{spec.name}`",
        "",
        "| smell | count | note |",
        "|---|---:|---|",
    ]
    for seq, count in wrong_bigrams.most_common(10):
        contrast = correct_bigrams[seq]
        lines.append(f"| `{seq}` | {count} | correct trajectories also use it {contrast} times |")
    for tool, count in wrong_last.most_common(8):
        lines.append(f"| last tool `{tool}` | {count} | wrong trajectory ended here |")
    for tool, count in repeated.most_common(8):
        lines.append(
            f"| repeated `{tool}` >= 3x | {count} | trajectory likely got stuck or decomposed too much |"
        )
    lines.append("")
    return lines


def _transition_tool_section(left: RunSpec, right: RunSpec) -> list[str]:
    left_by_qid = {str(row["qid"]): row for row in left.rows}
    right_by_qid = {str(row["qid"]): row for row in right.rows}
    shared = sorted(set(left_by_qid) & set(right_by_qid))
    fixed: Counter[str] = Counter()
    regressed: Counter[str] = Counter()
    both_wrong: Counter[str] = Counter()
    for qid in shared:
        left_correct = _correct(left_by_qid[qid])
        right_row = right_by_qid[qid]
        right_correct = _correct(right_row)
        candidate_tools = set(_tools(right_row))
        if left_correct and not right_correct:
            regressed.update(candidate_tools)
        elif not left_correct and right_correct:
            fixed.update(candidate_tools)
        elif not left_correct and not right_correct:
            both_wrong.update(candidate_tools)

    lines = [
        f"### `{left.name}` -> `{right.name}`",
        "",
        "| tool in candidate | fixed | regressed | both wrong | net fixed-regressed |",
        "|---|---:|---:|---:|---:|",
    ]
    all_tools = sorted(set(fixed) | set(regressed) | set(both_wrong))
    for tool in sorted(
        all_tools, key=lambda item: (regressed[item] - fixed[item], both_wrong[item]), reverse=True
    ):
        if fixed[tool] == regressed[tool] == both_wrong[tool] == 0:
            continue
        lines.append(
            f"| `{tool}` | {fixed[tool]} | {regressed[tool]} | {both_wrong[tool]} | "
            f"{fixed[tool] - regressed[tool]:+d} |"
        )
    lines.append("")
    return lines


def _recommendations(specs: list[RunSpec]) -> list[str]:
    latest = specs[-1]
    latest_metrics = _tool_metrics(latest.rows)
    suspicious = _suspicious_tools(latest_metrics)
    useful = _useful_tools(latest_metrics)
    return [
        "",
        "## Tool Design Decisions",
        "",
        "### Keep As Core",
        "",
        "- `schema_inspect`: still necessary as the generic graph-entry point, but it should remain compact and affordance-oriented.",
        "- `entity_resolve`: necessary, but ambiguity handling is a major failure source. It needs better ranked candidates and explicit disambiguation metadata.",
        "- `pattern_query`: useful because it collapses common path traversals, but many wrong runs still use repeated pattern queries. It should become more expressive rather than multiplied.",
        "- `fetch`: required for pagination/finalization. It should stay explicit; auto-fetch looked harmful in `fetch_guard_v6e`.",
        "",
        "### Hide Or Keep Experimental",
        "",
        "- `done`: completion improved but answer quality dropped. Keep it out of default runs until it can verify result shape and semantic intent.",
        "- `draft_tool_plan` and `validate_tool_plan`: they add overhead and did not materially improve full-run quality. Keep them as ablation-only tools.",
        "- `node_scan`: useful for debugging/discovery, but for QA it usually means the model failed to anchor the graph through schema/path affordances.",
        "",
        "### Merge Or Redesign",
        "",
        "- `expand` + `project` + `count_handle`: this chain forces the model to manually compose low-level relational algebra. Replace many of these trajectories with one constrained query tool.",
        "- `entity_set_operation`, `same_target_role_intersection`, `join_handles`, and `filter_same_node`: these overlap around set logic. Merge into a clearer generic set/constraint operator or subsume into the constrained query tool.",
        "- `group_count_by_pattern` should not be a separate mental model from `pattern_query`; counting/grouping is just a result mode over constrained pattern execution.",
        "",
        "### Add One High-Leverage Generic Tool",
        "",
        "Add a generic `constraint_query` style tool, not a vertical/domain tool. Keep the first slice deliberately small: one candidate label, one-hop AND constraints on related-node properties, simple output modes, and pagination.",
        "This is the most promising next move because many failures are not missing facts: they are bad multi-step choreography across otherwise valid generic primitives.",
        "",
        "Proposed capability:",
        "",
        "- Start from a candidate label.",
        "- Apply one or more one-hop relationship constraints with direction and target labels.",
        "- Filter related nodes by simple property predicates such as `name = value`.",
        "- Return `names`, `count`, or `entities`, always with pagination metadata where relevant.",
        "- Validate labels, relationship types, directions, and properties against schema before execution.",
        "- Add OR/NOT, grouped counts, same-entity joins, or multi-hop only as later measured extensions.",
        "",
        "### Current Suspicious Tools In Latest Run",
        "",
        *(f"- `{tool}`: {reason}" for tool, reason in suspicious),
        "",
        "### Current Useful Tools In Latest Run",
        "",
        *(f"- `{tool}`: {reason}" for tool, reason in useful),
    ]


def _suspicious_tools(metrics: dict[str, dict[str, Any]]) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for tool, item in metrics.items():
        if tool == "fetch":
            continue
        tasks = item["tasks"]
        if tasks < 10:
            continue
        with_acc = item["correct_tasks"] / tasks
        signals = item["errors"] + item["zero"] + item["broad"] + item["truncated"]
        if with_acc < 0.50 and signals:
            items.append(
                (
                    tool,
                    f"accuracy when used {with_acc:.1%}, with {signals} noisy call-level signals",
                )
            )
        elif item["wrong_last"] >= 10:
            items.append((tool, f"ended {item['wrong_last']} wrong trajectories"))
    return sorted(items, key=lambda pair: pair[0])


def _useful_tools(metrics: dict[str, dict[str, Any]]) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for tool, item in metrics.items():
        tasks = item["tasks"]
        if tasks < 20:
            continue
        with_acc = item["correct_tasks"] / tasks
        if with_acc >= 0.60 and item["errors"] == 0:
            items.append(
                (tool, f"accuracy when used {with_acc:.1%}, {item['tasks']} tasks, no tool errors")
            )
    return sorted(items, key=lambda pair: pair[0])


def _tool_metrics(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "calls": 0,
            "tasks": 0,
            "correct_tasks": 0,
            "positions": [],
            "calls_per_task": [],
            "errors": 0,
            "zero": 0,
            "broad": 0,
            "truncated": 0,
            "last": 0,
            "wrong_last": 0,
        }
    )
    for row in rows:
        transcript = list(row.get("transcript") or [])
        tools = _tools(row)
        correct = _correct(row)
        per_row_counts = Counter(tools)
        for tool, count in per_row_counts.items():
            item = metrics[tool]
            item["tasks"] += 1
            item["correct_tasks"] += int(correct)
            item["calls_per_task"].append(count)
        for index, step in enumerate(transcript):
            tool = _step_tool(step)
            if not tool:
                continue
            item = metrics[tool]
            item["calls"] += 1
            item["positions"].append(index + 1)
            if _tool_error(step):
                item["errors"] += 1
            matched_count = _matched_count(step)
            if tool in PATH_TOOLS and matched_count == 0:
                item["zero"] += 1
            if matched_count is not None and matched_count >= 1000:
                item["broad"] += 1
            if _truncated(step):
                item["truncated"] += 1
        if tools:
            last = tools[-1]
            metrics[last]["last"] += 1
            if not correct:
                metrics[last]["wrong_last"] += 1
    return metrics


def _correct(row: dict[str, Any]) -> bool:
    return bool(row.get("matches_answer_json"))


def _tools(row: dict[str, Any]) -> list[str]:
    return [tool for step in row.get("transcript", []) if (tool := _step_tool(step))]


def _step_tool(step: dict[str, Any]) -> str | None:
    tool = (step.get("action") or {}).get("tool")
    return str(tool) if tool else None


def _tool_error(step: dict[str, Any]) -> str | None:
    result = step.get("result")
    if isinstance(result, dict) and result.get("status") == "tool_error":
        return str(result.get("error") or "")
    return None


def _tool_error_count(row: dict[str, Any]) -> int:
    explicit = row.get("tool_error_count")
    if explicit is not None:
        return int(explicit)
    return sum(1 for step in row.get("transcript", []) if _tool_error(step))


def _matched_count(step: dict[str, Any]) -> int | None:
    result = step.get("result")
    if not isinstance(result, dict):
        return None
    value = result.get("matched_count")
    return int(value) if isinstance(value, int) else None


def _truncated(step: dict[str, Any]) -> bool:
    result = step.get("result")
    return isinstance(result, dict) and bool(result.get("truncated"))


if __name__ == "__main__":
    main()
