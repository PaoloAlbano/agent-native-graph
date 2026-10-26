"""Compare two complete runs of the same method and model profile."""

import argparse
import hashlib
import json
from pathlib import Path

from agent_native_graph.research_common import read_jsonl


def _load(path: Path) -> tuple[dict, dict[str, dict]]:
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    run_file = path / "run.jsonl"
    if hashlib.sha256(run_file.read_bytes()).hexdigest() != manifest["run_sha256"]:
        raise ValueError(f"Run checksum differs from manifest: {path}")
    rows = read_jsonl(run_file)
    by_qid = {row["qid"]: row for row in rows}
    if len(by_qid) != len(rows) or len(rows) != manifest["limit"]:
        raise ValueError(f"Incomplete or duplicate-QID run: {path}")
    return manifest, by_qid


def compare(first_path: Path, second_path: Path, *, allow_concurrency_diff: bool = False) -> dict:
    first_manifest, first = _load(first_path)
    second_manifest, second = _load(second_path)
    required = (
        "approach",
        "model",
        "temperature",
        "reasoning",
        "max_tokens",
        "concurrency",
        "limit",
        "tasks_sha256",
        "graph_sha256",
    )
    differences = [key for key in required if first_manifest.get(key) != second_manifest.get(key)]
    if allow_concurrency_diff:
        differences = [key for key in differences if key != "concurrency"]
    if differences or set(first) != set(second):
        raise ValueError(f"Runs differ in profile/QIDs: {differences}")
    fixed = []
    regressed = []
    both_correct = 0
    both_wrong = 0
    for qid in first:
        before = bool(first[qid]["matches_answer_json"])
        after = bool(second[qid]["matches_answer_json"])
        if before and after:
            both_correct += 1
        elif before:
            regressed.append(qid)
        elif after:
            fixed.append(qid)
        else:
            both_wrong += 1
    return {
        "first": str(first_path),
        "second": str(second_path),
        "approach": first_manifest["approach"],
        "model": first_manifest["model"],
        "total": len(first),
        "first_correct": both_correct + len(regressed),
        "second_correct": both_correct + len(fixed),
        "both_correct": both_correct,
        "both_wrong": both_wrong,
        "fixed_qids": fixed,
        "regressed_qids": regressed,
        "answer_outcome_disagreement": len(fixed) + len(regressed),
        "same_concurrency": first_manifest.get("concurrency") == second_manifest.get("concurrency"),
        "first_concurrency": first_manifest.get("concurrency"),
        "second_concurrency": second_manifest.get("concurrency"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--allow-concurrency-diff", action="store_true")
    args = parser.parse_args()
    report = compare(args.first, args.second, allow_concurrency_diff=args.allow_concurrency_diff)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {key: value for key, value in report.items() if not key.endswith("qids")}, indent=2
        )
    )


if __name__ == "__main__":
    main()
