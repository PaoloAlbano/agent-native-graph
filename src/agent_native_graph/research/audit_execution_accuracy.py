"""Audit archived runs against live gold-query results without calling an LLM.

This is a CypherBench-style secondary metric. It compares denotations, not
generated Cypher text; ANA has no generated Cypher to submit to the original
CypherBench evaluator.
"""

import argparse
import hashlib
import json
from pathlib import Path

from agent_native_graph.research.execution_equivalence import execution_equivalent
from agent_native_graph.research_common import read_jsonl


def audit(gold_path: Path, run_paths: list[Path]) -> dict:
    gold_rows = read_jsonl(gold_path)
    gold = {row["qid"]: row for row in gold_rows}
    if len(gold) != len(gold_rows):
        raise ValueError("Duplicate QID in gold results")
    report = {"gold_path": str(gold_path), "gold_count": len(gold), "runs": []}
    for path in run_paths:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        run_file = path / "run.jsonl"
        if hashlib.sha256(run_file.read_bytes()).hexdigest() != manifest["run_sha256"]:
            raise ValueError(f"Run checksum differs from manifest: {path}")
        rows = read_jsonl(run_file)
        if len(rows) != len(gold) or {row["qid"] for row in rows} != set(gold):
            raise ValueError(f"Incomplete or unpaired run: {path}")
        changed = []
        official_style_correct = 0
        exact_correct = 0
        for row in rows:
            target = gold[row["qid"]]
            if row["gold_cypher"] != target["query"] or row["expected"] != target["expected"]:
                raise ValueError(f"Gold task differs from archived run: {row['qid']}")
            order_matters = "order by" in row["gold_cypher"].lower()
            equivalent = bool(row["ok"] and target["ok"]) and execution_equivalent(
                row["rows"], target["rows"], order_matters=order_matters
            )
            exact = bool(row["matches_answer_json"])
            official_style_correct += equivalent
            exact_correct += exact
            if equivalent != exact:
                changed.append(
                    {
                        "qid": row["qid"],
                        "question": row["nl_question"],
                        "exact_answer_json": exact,
                        "execution_equivalent": equivalent,
                        "gold_reproduces_answer_json": target["matches_answer_json"],
                        "order_matters": order_matters,
                    }
                )
        report["runs"].append(
            {
                "path": str(path),
                "model": manifest["model"],
                "approach": manifest["approach"],
                "exact_correct": exact_correct,
                "execution_equivalent_correct": official_style_correct,
                "changed": changed,
            }
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--run", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.gold, args.run)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "runs": len(report["runs"])}, sort_keys=True))


if __name__ == "__main__":
    main()
