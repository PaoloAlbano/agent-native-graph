import argparse
import json
from pathlib import Path
from typing import Any

from agent_native_graph.research_common import write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--from-hf", action="store_true")
    parser.add_argument("--graph", default="company")
    parser.add_argument("--split", default="test")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    if args.from_hf:
        rows = _load_from_hf(args.split)
    elif args.source_dir:
        rows = _load_from_source_dir(args.source_dir, args.split)
    else:
        raise SystemExit("Provide either --source-dir or --from-hf.")

    filtered = [
        _normalize_task(row)
        for row in rows
        if str(row.get("graph", "")).lower() == args.graph.lower()
    ]
    write_jsonl(args.out, filtered)
    print(
        json.dumps(
            {
                "out": str(args.out),
                "split": args.split,
                "graph": args.graph,
                "rows": len(filtered),
            },
            sort_keys=True,
        )
    )


def _load_from_hf(split: str) -> list[dict[str, Any]]:
    try:
        from datasets import load_dataset  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit(
            "`datasets` is not installed. Clone the HF dataset locally and use --source-dir, "
            "or install datasets in this investigation environment."
        ) from exc
    dataset = load_dataset("megagonlabs/cypherbench", split=split)
    return [dict(row) for row in dataset]


def _load_from_source_dir(source_dir: Path, split: str) -> list[dict[str, Any]]:
    candidates = sorted(source_dir.rglob(f"*{split}*.parquet"))
    if not candidates:
        candidates = sorted(source_dir.rglob(f"*{split}*.jsonl"))
    if not candidates:
        candidates = sorted(source_dir.rglob(f"*{split}*.json"))
    if not candidates:
        raise SystemExit(f"No files matching split={split!r} found under {source_dir}.")

    rows: list[dict[str, Any]] = []
    for path in candidates:
        if path.suffix == ".parquet":
            import pandas as pd

            rows.extend(pd.read_parquet(path).to_dict(orient="records"))
        elif path.suffix == ".jsonl":
            with path.open("r", encoding="utf-8") as handle:
                rows.extend(json.loads(line) for line in handle if line.strip())
        elif path.suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                rows.extend(dict(item) for item in payload)
            elif isinstance(payload, dict) and split in payload:
                rows.extend(dict(item) for item in payload[split])
    return rows


def _normalize_task(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "qid": row.get("qid"),
        "graph": row.get("graph"),
        "gold_cypher": row.get("gold_cypher"),
        "nl_question": row.get("nl_question"),
        "answer_json": row.get("answer_json"),
        "from_template": row.get("from_template"),
    }


if __name__ == "__main__":
    main()
