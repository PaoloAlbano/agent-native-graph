import argparse
import json
import re
import shutil
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_native_graph.application.run_config import (
    config_path,
    file_hash,
    load_config,
    public_config,
    validate_results,
)
from agent_native_graph.research_common import read_jsonl, write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--benchmark", default="cypherbench-company")
    parser.add_argument("--model")
    parser.add_argument("--provider")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--reasoning")
    parser.add_argument("--tool-mode")
    parser.add_argument("--tool-choice")
    parser.add_argument("--max-tokens", type=int)
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--concurrency", type=int)
    parser.add_argument("--notes", default="")
    parser.add_argument("--run-label", help="Unique replica label; defaults to the raw filename")
    parser.add_argument("--delete-source", action="store_true")
    parser.add_argument("--root", type=Path, default=Path("results"))
    parser.add_argument("--tasks-file", type=Path, default=Path("data/tasks_company_test.jsonl"))
    parser.add_argument("--graph-file", type=Path, default=Path("downloads/company_simplekg.json"))
    args = parser.parse_args()

    if args.run.with_suffix(".lock").exists():
        raise ValueError("The run is active or has a stale lock; do not archive it yet")
    rows = read_jsonl(args.run)
    config = load_config(config_path(args.run)) if config_path(args.run).exists() else None
    defaults = {
        "model": None,
        "provider": "openai-compatible",
        "limit": 347,
        "temperature": None,
        "reasoning": "none",
        "tool_mode": "native",
        "tool_choice": "auto",
        "max_tokens": 16000,
        "max_steps": 12,
        "concurrency": None,
    }
    for field, default in defaults.items():
        value = config[field] if config else default
        supplied = getattr(args, field)
        if config and supplied is not None and supplied != value:
            raise ValueError(f"--{field.replace('_', '-')} contradicts the saved run configuration")
        setattr(args, field, value if supplied is None else supplied)
    if not args.model:
        parser.error("Legacy output has no metadata: specify --model and the original profile")
    if len(rows) != args.limit:
        raise SystemExit(
            f"Refusing to archive incomplete run: {args.run} has {len(rows)} rows, "
            f"expected {args.limit}."
        )

    if config:
        validate_results(rows, config)
        args.run_label = args.run_label or config["created_at"]
    else:
        validate_run_rows(rows, args.limit, args.tasks_file)

    run_id = _run_id(args)
    suite = _suite(args.limit)
    root = _archive_root(args.root, args.limit)
    run_dir = root / args.benchmark / suite / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    destination = run_dir / "run.jsonl"
    if destination.exists():
        raise SystemExit(f"Destination already exists: {destination}")
    shutil.copy2(args.run, destination)

    if config:
        _write_json(run_dir / "run-config.json", public_config(config))
    manifest = _manifest(args, run_id, destination, rows, config)
    summary = _summary(rows, run_id)
    failures = [_failure_record(row) for row in rows if not row.get("matches_answer_json")]

    _write_json(run_dir / "manifest.json", manifest)
    _write_json(run_dir / "summary.json", summary)
    write_jsonl(run_dir / "failures.jsonl", failures)

    if args.delete_source:
        args.run.unlink()

    if suite == "full":
        _refresh_index(root / args.benchmark)
    print(json.dumps({"archived": str(run_dir), "accuracy": summary["accuracy"]}, indent=2))


def _run_id(args: argparse.Namespace) -> str:
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    variant = _run_variant(args.run_label or args.run.stem)
    return "_".join(
        [
            date,
            _slug(args.model),
            f"temp{_number_slug(args.temperature)}",
            f"reasoning-{_slug(args.reasoning)}",
            f"tools-{_slug(args.tool_mode)}",
            f"n{args.limit}",
            variant,
        ]
    )


def _run_variant(stem: str) -> str:
    variant = stem
    for prefix in ("agent_tools_first100_", "agent_tools_"):
        if variant.startswith(prefix):
            variant = variant[len(prefix) :]
            break
    return _slug(variant)


def _suite(limit: int) -> str:
    if limit == 347:
        return "full"
    if limit == 100:
        return "first100"
    return f"n{limit}"


def validate_run_rows(rows: list[dict], limit: int, tasks_file: Path) -> None:
    """Reject duplicate/missing QIDs and results from a different task set."""
    qids = [row.get("qid") for row in rows]
    if (
        len(rows) != limit
        or any(not isinstance(qid, str) or not qid for qid in qids)
        or len(set(qids)) != limit
    ):
        raise ValueError("Run must contain exactly the expected number of unique, nonempty QIDs")
    if tasks_file.exists():
        tasks = read_jsonl(tasks_file)[:limit]
        if len(tasks) != limit or {task["qid"] for task in tasks} != set(qids):
            raise ValueError("Run QIDs differ from the selected task set")


def _archive_root(root: Path, limit: int) -> Path:
    if limit != 347 and root == Path("results"):
        return Path(".local-results")
    return root


def _manifest(
    args: argparse.Namespace,
    run_id: str,
    destination: Path,
    rows: list[dict[str, Any]],
    config: dict | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "benchmark": args.benchmark,
        "split": "test",
        "category": "company",
        "approach": rows[0].get("approach") if rows else "agent_tools_neo4j",
        "model": args.model,
        "provider": args.provider,
        "temperature": args.temperature,
        "reasoning": args.reasoning,
        "tool_mode": args.tool_mode,
        "tool_choice": args.tool_choice,
        "max_tokens": args.max_tokens,
        "max_steps": args.max_steps,
        "concurrency": args.concurrency,
        "limit": args.limit,
        "suite": _suite(args.limit),
        "source_file": args.run.name if config else str(args.run),
        "run_file": "run.jsonl",
        "run_sha256": file_hash(destination),
        "tasks_sha256": config["inputs"]["tasks"]["sha256"]
        if config
        else file_hash(args.tasks_file)
        if args.tasks_file.exists()
        else None,
        "graph_sha256": config["inputs"]["graph"]["sha256"]
        if config
        else file_hash(args.graph_file)
        if args.graph_file.exists()
        else None,
        "git_commit": config["git_commit"] if config else _git_commit(),
        "notes": args.notes,
        **(
            {
                "configuration_sha256": config["configuration_sha256"],
                "run_profile": config["profile"],
                "profile_sha256": config.get("profile_sha256"),
                "run_config_sha256": file_hash(destination.parent / "run-config.json"),
            }
            if config
            else {}
        ),
    }


def _summary(rows: list[dict[str, Any]], run_id: str) -> dict[str, Any]:
    total = len(rows)
    ok = sum(bool(row.get("ok")) for row in rows)
    matches = sum(bool(row.get("matches_answer_json")) for row in rows)
    llm_calls = sum(int(row.get("llm_call_count") or 0) for row in rows)
    tool_calls = sum(int(row.get("tool_call_count") or 0) for row in rows)
    tool_errors = sum(int(row.get("tool_error_count") or 0) for row in rows)
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    failure_classes: Counter[str] = Counter()
    tools: Counter[str] = Counter()
    for row in rows:
        if row.get("failure_class"):
            failure_classes[str(row["failure_class"])] += 1
        for metric in row.get("llm_call_metrics") or []:
            usage = metric.get("usage") or {}
            prompt_tokens += int(usage.get("prompt_tokens") or metric.get("prompt_tokens") or 0)
            completion_tokens += int(
                usage.get("completion_tokens") or metric.get("completion_tokens") or 0
            )
            total_tokens += int(usage.get("total_tokens") or metric.get("total_tokens") or 0)
        for step in row.get("transcript") or []:
            action = step.get("action") or {}
            if action.get("tool"):
                tools[str(action["tool"])] += 1
    return {
        "run_id": run_id,
        "total": total,
        "ok": ok,
        "matches": matches,
        "accuracy": matches / total if total else 0.0,
        "executable_rate": ok / total if total else 0.0,
        "avg_llm_calls": llm_calls / total if total else 0.0,
        "avg_tool_calls": tool_calls / total if total else 0.0,
        "tool_errors": tool_errors,
        "llm_prompt_tokens": prompt_tokens,
        "llm_completion_tokens": completion_tokens,
        "llm_total_tokens": total_tokens,
        "failure_classes": dict(sorted(failure_classes.items())),
        "failure_total": sum(failure_classes.values()),
        "top_tools": tools.most_common(20),
    }


def _failure_record(row: dict[str, Any]) -> dict[str, Any]:
    failure = dict(row)
    failure["failure_category"] = row.get("failure_class") or "unknown"
    return failure


def _refresh_index(benchmark_dir: Path) -> None:
    records = []
    for manifest_path in sorted(benchmark_dir.glob("full/runs/*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        summary_path = manifest_path.with_name("summary.json")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        suite = manifest.get("suite") or _suite(int(manifest["limit"]))
        if suite != "full":
            continue
        records.append(
            {
                "run_id": manifest["run_id"],
                "suite": suite,
                "model": manifest["model"],
                "temperature": manifest["temperature"],
                "reasoning": manifest["reasoning"],
                "limit": manifest["limit"],
                "accuracy": summary["accuracy"],
                "executable_rate": summary["executable_rate"],
                "avg_tool_calls": summary["avg_tool_calls"],
                "avg_llm_calls": summary["avg_llm_calls"],
                "path": str(manifest_path.parent.relative_to(benchmark_dir)),
            }
        )
    _write_json(benchmark_dir / "index.json", records)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return None


def _slug(value: Any) -> str:
    text = str(value).lower().replace("/", "-")
    return re.sub(r"[^a-z0-9._-]+", "-", text).strip("-")


def _number_slug(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value:g}".replace(".", "p")


if __name__ == "__main__":
    main()
