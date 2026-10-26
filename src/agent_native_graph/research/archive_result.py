import argparse
import hashlib
import json
import re
import shutil
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_native_graph.research_common import read_jsonl, write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--benchmark", default="cypherbench-company")
    parser.add_argument("--model", required=True)
    parser.add_argument("--provider", default="openai-compatible")
    parser.add_argument("--limit", type=int, default=347)
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--reasoning", default="none")
    parser.add_argument("--tool-mode", default="native")
    parser.add_argument("--tool-choice", default="auto")
    parser.add_argument("--max-tokens", type=int, default=16000)
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--concurrency", type=int)
    parser.add_argument("--notes", default="")
    parser.add_argument("--delete-source", action="store_true")
    parser.add_argument("--root", type=Path, default=Path("results"))
    parser.add_argument("--tasks-file", type=Path, default=Path("data/tasks_company_test.jsonl"))
    parser.add_argument("--graph-file", type=Path, default=Path("downloads/company_simplekg.json"))
    args = parser.parse_args()

    rows = read_jsonl(args.run)
    if len(rows) != args.limit:
        raise SystemExit(
            f"Refusing to archive incomplete run: {args.run} has {len(rows)} rows, "
            f"expected {args.limit}."
        )

    run_id = _run_id(args)
    suite = _suite(args.limit)
    root = _archive_root(args.root, args.limit)
    run_dir = root / args.benchmark / suite / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    destination = run_dir / "run.jsonl"
    if destination.exists():
        raise SystemExit(f"Destination already exists: {destination}")
    shutil.copy2(args.run, destination)

    manifest = _manifest(args, run_id, destination, rows)
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
    variant = _run_variant(args.run.stem)
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


def _archive_root(root: Path, limit: int) -> Path:
    if limit != 347 and root == Path("results"):
        return Path(".local-results")
    return root


def _manifest(
    args: argparse.Namespace,
    run_id: str,
    destination: Path,
    rows: list[dict[str, Any]],
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
        "source_file": str(args.run),
        "run_file": "run.jsonl",
        "run_sha256": _sha256(destination),
        "tasks_sha256": _sha256(args.tasks_file) if args.tasks_file.exists() else None,
        "graph_sha256": _sha256(args.graph_file) if args.graph_file.exists() else None,
        "git_commit": _git_commit(),
        "notes": args.notes,
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
    for manifest_path in sorted(benchmark_dir.glob("**/manifest.json")):
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
