import argparse
import json
from pathlib import Path

from agent_native_graph.research_common import (
    Neo4jRunner,
    add_neo4j_args,
    append_jsonl,
    limited_tasks,
    normalize_answer_rows,
    parse_answer_json,
    read_jsonl,
    result_matches_answer,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    add_neo4j_args(parser)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    tasks = limited_tasks(read_jsonl(args.tasks), args.limit)
    if args.out.exists():
        args.out.unlink()

    runner = Neo4jRunner(args.neo4j_uri, args.neo4j_user, args.neo4j_password, args.query_timeout_s)
    summary = {"total": 0, "ok": 0, "matches_answer_json": 0, "errors": 0}
    try:
        for task in tasks:
            expected = normalize_answer_rows(parse_answer_json(task.get("answer_json")))
            execution = runner.execute(str(task["gold_cypher"]))
            matches = execution.ok and result_matches_answer(execution.rows, expected)
            row = {
                "qid": task["qid"],
                "graph": task["graph"],
                "nl_question": task["nl_question"],
                "query": task["gold_cypher"],
                "ok": execution.ok,
                "columns": execution.columns,
                "rows": execution.rows,
                "expected": expected,
                "matches_answer_json": matches,
                "elapsed_s": execution.elapsed_s,
                "error": execution.error,
            }
            append_jsonl(args.out, row)
            summary["total"] += 1
            summary["ok"] += int(execution.ok)
            summary["matches_answer_json"] += int(matches)
            summary["errors"] += int(not execution.ok)
    finally:
        runner.close()

    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
