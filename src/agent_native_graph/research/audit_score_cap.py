"""Replay archived baseline Cypher above the original scoring row cap."""

import argparse
import json
from pathlib import Path

from agent_native_graph.research_common import (
    Neo4jRunner,
    add_neo4j_args,
    read_jsonl,
    result_matches_answer,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_neo4j_args(parser)
    parser.add_argument("--qid", required=True)
    parser.add_argument("--run", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    runner = Neo4jRunner(args.neo4j_uri, args.neo4j_user, args.neo4j_password, args.query_timeout_s)
    report = []
    try:
        for path in args.run:
            matching = [row for row in read_jsonl(path / "run.jsonl") if row["qid"] == args.qid]
            if len(matching) != 1:
                raise ValueError(f"Expected one row for {args.qid} in {path}")
            row = matching[0]
            query = row.get("generated_cypher")
            if not query:
                report.append({"run": str(path), "error": "no_generated_cypher"})
                continue
            execution = runner.execute(query)
            report.append(
                {
                    "run": str(path),
                    "qid": args.qid,
                    "original_error": row.get("error"),
                    "replay_ok": execution.ok,
                    "replay_rows": len(execution.rows),
                    "expected_rows": len(row["expected"]),
                    "replay_exact": execution.ok
                    and result_matches_answer(execution.rows, row["expected"]),
                    "replay_error": execution.error,
                }
            )
    finally:
        runner.close()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
