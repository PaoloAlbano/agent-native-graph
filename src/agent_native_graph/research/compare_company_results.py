"""Build a paired, exact-answer comparison from archived Company runs."""

import argparse
import hashlib
import json
from pathlib import Path

from agent_native_graph.research_common import read_jsonl, result_matches_answer


def _load_run(path: Path) -> tuple[dict, dict[str, dict]]:
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    run_file = path / "run.jsonl"
    digest = hashlib.sha256(run_file.read_bytes()).hexdigest()
    if digest != manifest["run_sha256"]:
        raise ValueError(f"Run SHA-256 differs from manifest: {path}")
    rows = read_jsonl(run_file)
    by_qid = {row["qid"]: row for row in rows}
    if len(by_qid) != len(rows) or len(rows) != manifest["limit"]:
        raise ValueError(f"Incomplete run or duplicate qids: {path}")
    for row in rows:
        actual = result_matches_answer(row["rows"], row["expected"])
        if bool(row["matches_answer_json"]) != actual:
            raise ValueError(f"Stored score disagrees with exact comparator: {row['qid']}")
    return manifest, by_qid


def _validate_profiles(runs: list[tuple[dict, dict[str, dict]]]) -> list[str]:
    first_manifest, first_rows = runs[0]
    required = {"model", "temperature", "reasoning", "max_tokens", "limit", "suite"}
    for manifest, rows in runs[1:]:
        different = {key for key in required if manifest.get(key) != first_manifest.get(key)}
        if different:
            raise ValueError(f"Run profiles differ on {sorted(different)}")
        if set(rows) != set(first_rows):
            raise ValueError("Run qid sets differ")
    return sorted(first_rows)


def _summary(rows: dict[str, dict]) -> dict:
    values = list(rows.values())
    total = len(values)
    return {
        "total": total,
        "correct": sum(bool(row["matches_answer_json"]) for row in values),
        "accuracy": sum(bool(row["matches_answer_json"]) for row in values) / total,
        "executable_rate": sum(bool(row["ok"]) for row in values) / total,
        "average_llm_calls": sum(int(row.get("llm_call_count") or 0) for row in values) / total,
        "average_tool_calls": (
            sum(int(row.get("tool_call_count") or 0) for row in values) / total
            if values[0].get("approach") == "agent_tools_neo4j"
            else None
        ),
        "average_elapsed_s": sum(float(row.get("elapsed_s") or 0) for row in values) / total,
    }


def compare(ana: Path, direct: Path, agentic: Path, gold_validation: Path | None = None) -> dict:
    runs = [_load_run(path) for path in (ana, direct, agentic)]
    baseline_tasks = runs[1][0].get("tasks_sha256")
    baseline_graph = runs[1][0].get("graph_sha256")
    if not baseline_tasks or not baseline_graph:
        raise ValueError("Baseline manifests must include task and graph hashes")
    for manifest, _ in runs:
        if manifest.get("tasks_sha256") != baseline_tasks:
            raise ValueError("Run task files differ")
        if manifest.get("graph_sha256") != baseline_graph:
            raise ValueError("Run graph dumps differ")
    expected_approaches = (
        "agent_tools_neo4j",
        "multigraphrag_direct",
        "multigraphrag_agentic",
    )
    for (manifest, _), expected_approach in zip(runs, expected_approaches, strict=True):
        if manifest.get("approach") != expected_approach:
            raise ValueError(f"Expected {expected_approach}, found {manifest.get('approach')}")
    qids = _validate_profiles(runs)
    labels = ("ANA", "Direct Cypher", "Multi-Agent GraphRAG")
    result = {
        "benchmark": "cypherbench-company",
        "scoring": "ana_exact_answer_json",
        "model": runs[0][0]["model"],
        "temperature": runs[0][0]["temperature"],
        "reasoning": runs[0][0]["reasoning"],
        "qid_count": len(qids),
        "runs": {},
        "paired": {},
    }
    valid_qids = None
    if gold_validation is not None:
        gold_rows = read_jsonl(gold_validation)
        gold_by_qid = {row["qid"]: row for row in gold_rows}
        if len(gold_by_qid) != len(gold_rows) or not set(qids) <= set(gold_by_qid):
            raise ValueError("Gold validation qids do not cover the compared runs")
        valid_qids = {qid for qid in qids if gold_by_qid[qid]["matches_answer_json"]}
        result["gold_reproducible"] = {
            "total": len(valid_qids),
            "excluded_qids": sorted(set(qids) - valid_qids),
        }
    for label, (manifest, rows), path in zip(labels, runs, (ana, direct, agentic), strict=True):
        result["runs"][label] = {
            "path": str(path),
            "run_id": manifest["run_id"],
            "source_commit": manifest.get("source_commit") or manifest.get("git_commit"),
            "concurrency": manifest.get("concurrency"),
            **_summary(rows),
        }
        if valid_qids is not None:
            valid_correct = sum(bool(rows[qid]["matches_answer_json"]) for qid in valid_qids)
            result["runs"][label]["gold_reproducible_correct"] = valid_correct
            result["runs"][label]["gold_reproducible_accuracy"] = valid_correct / len(valid_qids)
    ana_rows = runs[0][1]
    for label, (_, baseline_rows) in zip(labels[1:], runs[1:], strict=True):
        result["paired"][label] = {
            "both_correct": sum(
                bool(ana_rows[qid]["matches_answer_json"])
                and bool(baseline_rows[qid]["matches_answer_json"])
                for qid in qids
            ),
            "ana_only": sum(
                bool(ana_rows[qid]["matches_answer_json"])
                and not bool(baseline_rows[qid]["matches_answer_json"])
                for qid in qids
            ),
            "baseline_only": sum(
                not bool(ana_rows[qid]["matches_answer_json"])
                and bool(baseline_rows[qid]["matches_answer_json"])
                for qid in qids
            ),
            "both_wrong": sum(
                not bool(ana_rows[qid]["matches_answer_json"])
                and not bool(baseline_rows[qid]["matches_answer_json"])
                for qid in qids
            ),
        }
    return result


def _markdown(result: dict) -> str:
    lines = [
        "# CypherBench Company Comparison",
        "",
        f"Model: `{result['model']}`. Temperature: {result['temperature']:g}. "
        f"Reasoning: `{result['reasoning']}`. Questions: {result['qid_count']}.",
        "",
        "Primary metric: exact row-wise match against CypherBench `answer_json` "
        "using the same ANA comparator for every method.",
        "",
        "| Method | Correct | Accuracy | Executable | Avg LLM calls | Avg tool calls | Avg seconds |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label, run in result["runs"].items():
        tool_calls = (
            f"{run['average_tool_calls']:.2f}" if run["average_tool_calls"] is not None else "n/a"
        )
        lines.append(
            f"| {label} | {run['correct']}/{run['total']} | {run['accuracy']:.1%} | "
            f"{run['executable_rate']:.1%} | {run['average_llm_calls']:.2f} | "
            f"{tool_calls} | {run['average_elapsed_s']:.2f} |"
        )
    concurrency = {label: run["concurrency"] for label, run in result["runs"].items()}
    lines.extend(
        [
            "",
            "Run concurrency: "
            + ", ".join(f"{label}={value}" for label, value in concurrency.items())
            + ". Different values mean this is not an identical-load comparison.",
        ]
    )
    if "gold_reproducible" in result:
        count = result["gold_reproducible"]["total"]
        lines.extend(["", f"Gold reproducible subset: {count} questions.", ""])
        for label, run in result["runs"].items():
            lines.append(
                f"- {label}: {run['gold_reproducible_correct']}/{count} "
                f"({run['gold_reproducible_accuracy']:.1%})"
            )
    lines.extend(
        [
            "",
            "## Paired Outcomes",
            "",
            "| Baseline | Both correct | ANA only | Baseline only | Both wrong |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for label, paired in result["paired"].items():
        lines.append(
            f"| {label} | {paired['both_correct']} | {paired['ana_only']} | "
            f"{paired['baseline_only']} | {paired['both_wrong']} |"
        )
    lines.extend(
        [
            "",
            "The baseline's generated Cypher is replayed for scoring. Agent-facing query "
            "results retain the reference implementation's own row bound. "
            "See each run manifest for source commits and scoring limits.",
            "",
        ]
    )
    return "\n".join(lines)


def _output_paths(out: Path) -> tuple[Path, Path]:
    stem = out.with_suffix("") if out.suffix in {".json", ".md"} else out
    return Path(f"{stem}.json"), Path(f"{stem}.md")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ana", type=Path, required=True)
    parser.add_argument("--direct", type=Path, required=True)
    parser.add_argument("--agentic", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--gold-validation",
        type=Path,
        default=Path("results/cypherbench-company/gold-validation.jsonl"),
    )
    args = parser.parse_args()
    result = compare(args.ana, args.direct, args.agentic, args.gold_validation)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    json_path, markdown_path = _output_paths(args.out)
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(result), encoding="utf-8")
    print(markdown_path)


if __name__ == "__main__":
    main()
