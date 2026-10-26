import argparse
import json
from pathlib import Path

from agent_native_graph.research_common import read_jsonl


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()

    rows = read_jsonl(args.run)
    total = len(rows)
    executable = sum(1 for row in rows if row.get("ok"))
    matches = sum(1 for row in rows if row.get("matches_answer_json"))
    errored = total - executable
    summary = {
        "run": str(args.run),
        "total": total,
        "executable": executable,
        "errored": errored,
        "execution_accuracy": matches / total if total else 0.0,
        "executable_rate": executable / total if total else 0.0,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
