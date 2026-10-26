"""Summarize paired failures from three complete archived runs."""

import argparse
import json
from collections import Counter
from pathlib import Path

from agent_native_graph.research_common import read_jsonl


def _load(path: Path) -> dict[str, dict]:
    rows = read_jsonl(path / "run.jsonl")
    result = {row["qid"]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"Duplicate QIDs in {path}")
    return result


def _reason(row: dict) -> str:
    if not row["ok"]:
        return str(row.get("failure_class") or "execution_error")
    actual = row["rows"]
    expected = row["expected"]
    if not actual and expected:
        return "empty_result"
    if len(actual) != len(expected):
        return "cardinality_mismatch"
    return "value_or_order_mismatch"


def _tools(row: dict) -> list[str]:
    return [
        str(step["action"]["tool"])
        for step in row.get("transcript", [])
        if isinstance(step, dict)
        and isinstance(step.get("action"), dict)
        and step["action"].get("tool")
    ]


def audit(ana_path: Path, direct_path: Path, agentic_path: Path) -> dict:
    ana, direct, agentic = (_load(path) for path in (ana_path, direct_path, agentic_path))
    if set(ana) != set(direct) or set(ana) != set(agentic):
        raise ValueError("Runs have different QID sets")
    failures = [row for row in ana.values() if not row["matches_answer_json"]]
    reasons = Counter(_reason(row) for row in failures)
    tool_presence = Counter(tool for row in failures for tool in set(_tools(row)))
    baseline_only = {}
    for name, other in (("direct", direct), ("agentic", agentic)):
        baseline_only[name] = [
            {
                "qid": row["qid"],
                "question": row["nl_question"],
                "reason": _reason(row),
                "tools": _tools(row),
                "expected_rows": len(row["expected"]),
                "actual_rows": len(row["rows"]),
            }
            for row in failures
            if other[row["qid"]]["matches_answer_json"]
        ]
    return {
        "total": len(ana),
        "ana_failures": len(failures),
        "ana_failure_reasons": dict(reasons),
        "tools_present_in_failures": dict(tool_presence.most_common()),
        "baseline_only": baseline_only,
    }


def _markdown(report: dict) -> str:
    lines = [
        "# Paired Failure Audit",
        "",
        "Counts are descriptive, not causal: harder questions can invoke more tools.",
        "",
        f"ANA failures: {report['ana_failures']}/{report['total']}.",
        "",
        "| Failure reason | Count |",
        "|---|---:|",
    ]
    lines.extend(
        f"| {reason} | {count} |" for reason, count in report["ana_failure_reasons"].items()
    )
    lines.extend(["", "## Baseline-Only Cases", ""])
    for method, cases in report["baseline_only"].items():
        lines.extend([f"### {method}: {len(cases)}", ""])
        for case in cases:
            lines.append(
                f"- `{case['qid']}` {case['question']} "
                f"({case['reason']}; {case['actual_rows']}/{case['expected_rows']} rows; "
                f"tools: {', '.join(case['tools'])})"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ana", type=Path, required=True)
    parser.add_argument("--direct", type=Path, required=True)
    parser.add_argument("--agentic", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.ana, args.direct, args.agentic)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.with_suffix(".json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    args.out.with_suffix(".md").write_text(_markdown(report), encoding="utf-8")
    print(json.dumps({"ana_failures": report["ana_failures"], "out": str(args.out)}))


if __name__ == "__main__":
    main()
