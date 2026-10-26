"""Validate and archive a complete reference baseline run."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from agent_native_graph.research_common import read_jsonl, write_jsonl

DEFAULT_ARCHIVE_ROOT = Path(".local-results/baselines/multigraphrag/cypherbench-company")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _validate_rows(rows: list[dict], tasks: list[dict], metadata: dict) -> None:
    expected_qids = [task["qid"] for task in tasks[: metadata["limit"]]]
    actual_qids = [row.get("qid") for row in rows]
    if len(rows) != metadata["limit"]:
        raise ValueError(f"Incomplete run: {len(rows)} rows; expected {metadata['limit']}")
    if len(set(actual_qids)) != len(actual_qids) or set(actual_qids) != set(expected_qids):
        raise ValueError("Run qids differ from the declared Company suite")
    if any(row.get("approach") != metadata["approach"] for row in rows):
        raise ValueError("Run approach differs from metadata")


def archive(run: Path, root: Path, tasks_path: Path, graph_path: Path) -> Path:
    metadata_path = run.with_suffix(".meta.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if Path(metadata["source_repo"]).is_absolute():
        metadata["source_repo"] = subprocess.check_output(
            ["git", "-C", metadata["source_repo"], "remote", "get-url", "origin"],
            text=True,
        ).strip()
    tasks = read_jsonl(tasks_path)
    rows = read_jsonl(run)
    if metadata["tasks_sha256"] != _sha256(tasks_path):
        raise ValueError("Task file changed after the baseline run")
    if metadata["graph_sha256"] != _sha256(graph_path):
        raise ValueError("Graph dump changed after the baseline run")
    _validate_rows(rows, tasks, metadata)
    for source in metadata.get("call_logs", []):
        if not Path(source).exists():
            raise FileNotFoundError(source)

    run_id = "_".join(
        [
            datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
            _slug(metadata["model"]),
            metadata["mode"],
            f"temp{metadata['temperature']:g}",
            f"reasoning-{metadata['reasoning']}",
            f"n{metadata['limit']}",
        ]
    )
    destination = root / metadata["suite"] / "runs" / run_id
    if destination.exists():
        raise FileExistsError(destination)
    destination.mkdir(parents=True)
    shutil.copy2(run, destination / "run.jsonl")
    call_files = []
    for index, source in enumerate(metadata.get("call_logs", []), start=1):
        source_path = Path(source)
        target = f"calls-{index}.jsonl"
        shutil.copy2(source_path, destination / target)
        call_files.append(target)

    total = len(rows)
    correct = sum(bool(row["matches_answer_json"]) for row in rows)
    executable = sum(bool(row["ok"]) for row in rows)
    failures = [row for row in rows if not row["matches_answer_json"]]
    error_classes = Counter(str(row["error"]).split(":", 1)[0] for row in rows if row.get("error"))
    summary = {
        "run_id": run_id,
        "total": total,
        "correct": correct,
        "accuracy": correct / total,
        "executable": executable,
        "executable_rate": executable / total,
        "average_llm_calls": sum(int(row.get("llm_call_count") or 0) for row in rows) / total,
        "average_elapsed_s": sum(float(row.get("elapsed_s") or 0) for row in rows) / total,
        "error_classes": dict(error_classes),
    }
    manifest = {
        **metadata,
        "run_id": run_id,
        "run_file": "run.jsonl",
        "run_sha256": _sha256(destination / "run.jsonl"),
        "call_logs": call_files,
        "archived_at": datetime.now(UTC).isoformat(),
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (destination / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_jsonl(destination / "failures.jsonl", failures)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, default=Path("data/tasks_company_test.jsonl"))
    parser.add_argument("--graph", type=Path, default=Path("downloads/company_simplekg.json"))
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ARCHIVE_ROOT,
    )
    args = parser.parse_args()
    destination = archive(args.run, args.root, args.tasks, args.graph)
    print(destination)


if __name__ == "__main__":
    main()
