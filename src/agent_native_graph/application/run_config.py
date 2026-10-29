"""Run metadata shared by the benchmark runner and archiver; no execution engine."""

import hashlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import yaml

from agent_native_graph.core.tool_specs import _native_system_prompt, _tool_specs
from agent_native_graph.llm_providers import openai_compatible
from agent_native_graph.llm_providers.settings import LLMCallSettings
from agent_native_graph.research_common import normalize_answer_rows, parse_answer_json

PROFILE_DIR = Path(__file__).resolve().parents[1] / "profiles"


def profile_names() -> list[str]:
    return sorted(path.stem for path in PROFILE_DIR.glob("*.yaml"))


def load_profile(name: str) -> tuple[dict, str]:
    """Read a packaged YAML profile with a small, explicit parameter contract."""
    if name not in profile_names():
        raise ValueError(f"Unknown run profile: {name}")
    payload = (PROFILE_DIR / f"{name}.yaml").read_bytes()
    try:
        settings = yaml.safe_load(payload)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in run profile {name}") from exc
    if not isinstance(settings, dict):
        raise ValueError(f"Profile {name} must be a YAML mapping of LLM call settings")
    try:
        settings = asdict(LLMCallSettings(**settings))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid LLM settings in profile {name}: {exc}") from exc
    return settings, hashlib.sha256(payload).hexdigest()


def llm_settings_for_run(args) -> LLMCallSettings:
    """Profiles own call settings; direct diagnostic CLI retains its environment defaults."""
    if getattr(args, "llm_settings", None) is not None:
        return args.llm_settings
    return LLMCallSettings(
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        enable_thinking=args.enable_thinking,
        thinking_effort=args.thinking_effort,
        tool_choice=args.tool_choice,
        timeout_s=openai_compatible.LLM_HTTP_TIMEOUT_S,
        max_attempts=openai_compatible.LLM_HTTP_MAX_ATTEMPTS,
        retry_base_s=openai_compatible.LLM_HTTP_RETRY_BASE_S,
        rate_limit_retry_s=openai_compatible.LLM_RATE_LIMIT_RETRY_S,
    )


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def file_hash(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def config_path(output: Path) -> Path:
    return output.with_suffix(".config.json")


def apply_profile(args) -> None:
    if not args.profile:
        return
    if (
        args.limit not in (None, 347)
        or args.max_steps != 12
        or args.neo4j_query_timeout_s != 30
        or args.task_timeout_s is not None
    ):
        raise ValueError(
            "Company runs require 347 cases, 12 steps, query timeout 30s and no task timeout; omit --profile for diagnostics"
        )
    if args.schema_entry != "overview" or any(
        (
            args.enable_planning_tools,
            args.wrapper_planning,
            args.auto_fetch_on_done,
            args.enable_runner_guardrails,
        )
    ):
        raise ValueError("Company runs use overview and no runner interventions")
    settings, args.profile_sha256 = load_profile(args.profile)
    args.llm_settings = LLMCallSettings(**settings)
    for name in ("temperature", "max_tokens", "enable_thinking", "thinking_effort", "tool_choice"):
        setattr(args, name, getattr(args.llm_settings, name))
    args.limit, args.native_tools, args.evaluation_fetch_all_pages = 347, True, True


def new_output(directory: Path, model: str, profile: str | None) -> Path:
    label = re.sub(r"[^a-zA-Z0-9._-]+", "-", model)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return directory / f"{label}_{profile or 'custom'}_{stamp}.jsonl"


def task_signature(tasks: list[dict]) -> str:
    return digest(
        sorted(
            [
                [
                    t["qid"],
                    t["nl_question"],
                    t["gold_cypher"],
                    normalize_answer_rows(parse_answer_json(t["answer_json"])),
                ]
                for t in tasks
            ]
        )
    )


def result_signature(rows: list[dict]) -> str:
    return digest(
        sorted([[r["qid"], r["nl_question"], r["gold_cypher"], r["expected"]] for r in rows])
    )


def validate_results(rows: list[dict], config: dict) -> None:
    qids = [r.get("qid") for r in rows]
    if (
        len(rows) != config["limit"]
        or any(not isinstance(qid, str) or not qid for qid in qids)
        or len(set(qids)) != len(qids)
    ):
        raise ValueError("Results must contain all expected unique QIDs")
    if result_signature(rows) != config["task_signature_sha256"]:
        raise ValueError(
            "Result questions, gold queries or expected answers differ from the saved tasks"
        )


def load_config(path: Path) -> dict:
    config = json.loads(path.read_text())
    if config.get("version") != 2 or config.get("configuration_sha256") != digest(
        {k: v for k, v in config.items() if k != "configuration_sha256"}
    ):
        raise ValueError("Invalid run configuration; do not edit saved metadata")
    return config


def public_config(config: dict) -> dict:
    public = {k: v for k, v in config.items() if k not in {"inputs", "runtime_identity"}}
    public["input_hashes"] = {name: entry["sha256"] for name, entry in config["inputs"].items()}
    return public


def execution_identity(args, root: Path) -> dict:
    """Record effective contracts and code, not just the checkout's commit label."""
    return {
        "source_tree_sha256": digest(
            {
                str(p.relative_to(root)): file_hash(p)
                for p in sorted((root / "src/agent_native_graph").rglob("*.py"))
            }
        ),
        "uv_lock_sha256": file_hash(root / "uv.lock"),
        "pyproject_sha256": file_hash(root / "pyproject.toml"),
        "tools_sha256": digest(
            _tool_specs(
                enable_planning_tools=args.enable_planning_tools, schema_entry=args.schema_entry
            )
        )
        if args.native_tools
        else None,
        "system_prompt_sha256": digest(
            _native_system_prompt(
                enable_planning_tools=args.enable_planning_tools, schema_entry=args.schema_entry
            )
        )
        if args.native_tools
        else None,
        "python": platform.python_version(),
        "libraries": {
            name: importlib.metadata.version(name) for name in ("httpx", "neo4j", "PyYAML")
        },
    }


def save_config(args, tasks: list[dict], root: Path) -> dict:
    """Save actual runner settings once; resume must match without reconstructing history."""
    path = config_path(args.out)
    if args.resume and not path.exists():
        raise ValueError("Cannot resume without original run metadata; start a new run")
    previous = load_config(path) if args.resume else None
    inputs = {
        name: {"path": str(p.resolve()), "sha256": file_hash(p) if p.exists() else None}
        for name, p in {
            "tasks": args.tasks,
            "schema": args.schema_json,
            "graph": args.graph_file,
        }.items()
    }
    if args.profile and (
        len(tasks) != 347
        or not inputs["graph"]["sha256"]
        or any(t.get("graph") != "company" for t in tasks)
    ):
        raise ValueError("A Company profile requires the full Company tasks and a local graph dump")
    qids = [t["qid"] for t in tasks]
    if (
        not qids
        or any(not isinstance(qid, str) or not qid for qid in qids)
        or len(set(qids)) != len(qids)
    ):
        raise ValueError("Tasks must have unique QIDs")
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    config = {
        "version": 2,
        "created_at": previous["created_at"] if previous else datetime.now(UTC).isoformat(),
        "model": args.model,
        "provider": args.provider_tag,
        "profile": args.profile,
        "profile_sha256": getattr(args, "profile_sha256", None),
        "llm_settings": asdict(llm_settings_for_run(args)),
        "temperature": args.temperature,
        "reasoning": (args.thinking_effort or "enabled") if args.enable_thinking else "none",
        "concurrency": args.concurrency,
        "limit": len(tasks),
        "max_tokens": args.max_tokens,
        "max_steps": args.max_steps,
        "tool_mode": "native" if args.native_tools else "json",
        "tool_choice": args.tool_choice,
        "options": {
            name: getattr(args, name)
            for name in (
                "neo4j_query_timeout_s",
                "enable_thinking",
                "thinking_effort",
                "schema_entry",
                "enable_planning_tools",
                "wrapper_planning",
                "auto_fetch_on_done",
                "evaluation_fetch_all_pages",
                "enable_runner_guardrails",
            )
        },
        "task_timeout_s": args.task_timeout_s,
        "inputs": inputs,
        "task_signature_sha256": task_signature(tasks),
        "git_commit": commit,
        "runtime_identity": digest(
            [openai_compatible.chat_completions_url(args.base_url), args.neo4j_uri]
        ),
        "identity": execution_identity(args, root),
    }
    shared = getattr(args, "shared_preflight_artifact", None)
    if shared is not None:
        if shared["graph_sha256"] != inputs["graph"]["sha256"]:
            raise ValueError("Graph input changed after shared preflight; no inference started")
        config["schema_source"] = "shared-live-preflight-v1"
        config["shared_preflight"] = shared
    config["configuration_sha256"] = digest(config)
    if previous:
        # A docs-only commit is harmless if executable sources and treatment match.
        def comparable(c):
            return {k: v for k, v in c.items() if k not in {"git_commit", "configuration_sha256"}}

        if comparable(previous) != comparable(config):
            raise ValueError(
                "Run settings, inputs, runtime or executable code changed; start a new run"
            )
        return previous
    with path.open("x") as stream:
        stream.write(json.dumps(config, indent=2, sort_keys=True) + "\n")
    return config


@contextmanager
def run_lock(output: Path):
    """One local writer; a hard kill leaves a lock to inspect before resuming."""
    output.parent.mkdir(parents=True, exist_ok=True)
    path = output.with_suffix(".lock")
    with path.open("x") as stream:
        stream.write(str(os.getpid()))
    try:
        yield
    finally:
        path.unlink()
