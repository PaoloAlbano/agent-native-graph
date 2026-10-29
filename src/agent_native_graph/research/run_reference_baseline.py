"""Run the external Multi-Agent GraphRAG implementation on the ANA Company suite.

This harness reuses the reference project's SinglePassRunner and GraphRAGPipeline
against the already loaded Neo4j graph. It records query rows so both methods
can be scored with the same exact answer_json comparator used by ANA.
"""

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import logging
import math
import os
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from agent_native_graph.application.result_policy import (
    completeness,
    observe_results,
    record_observation,
    result_policy,
)
from agent_native_graph.application.run_config import (
    execution_identity,
    load_profile,
    profile_names,
)
from agent_native_graph.llm_providers.accounting import RequestAccounting, account_requests
from agent_native_graph.llm_providers.execution import (
    Deadline,
    deadline_scope,
    gather_and_settle,
    question_requests,
)
from agent_native_graph.llm_providers.openai_compatible import OpenAICompatibleProvider
from agent_native_graph.llm_providers.settings import LLMCallSettings
from agent_native_graph.research.read_only import execute_read_only_async
from agent_native_graph.research.reference_adapters import (
    REFERENCE_MODES,
    RETRIEVAL_MODES,
    RETRIEVAL_REFERENCE_COMMIT,
    build_profile_runner,
    guarded_graph_class,
    workflow_mode,
)
from agent_native_graph.research.reference_source import reference_source
from agent_native_graph.research_common import (
    normalize_answer_rows,
    parse_answer_json,
    read_jsonl,
    result_matches_answer,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-repo", type=Path, default=Path("../multigraphrag"))
    parser.add_argument(
        "--reference-commit", help="Full Git SHA; export committed source, not the checkout"
    )
    parser.add_argument(
        "--profile",
        choices=profile_names(),
        help="Shared ANA YAML call profile; requires --reference-commit",
    )
    parser.add_argument("--tasks", type=Path, default=Path("data/tasks_company_test.jsonl"))
    parser.add_argument("--graph", type=Path, default=Path("downloads/company_simplekg.json"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=REFERENCE_MODES, required=True)
    parser.add_argument("--model", default="openai/gpt-oss-120b")
    parser.add_argument("--base-url", default="https://openrouter.ai/api/")
    parser.add_argument("--api-key-file", type=Path)
    parser.add_argument("--neo4j-uri", default="bolt://127.0.0.1:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", default="password")
    parser.add_argument("--database", default="neo4j")
    parser.add_argument(
        "--shared-preflight",
        action="store_true",
        help="Verify full graph content and bootstrap the same canonical schema as ANA; new treatment",
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--reasoning", choices=("none", "medium"), default="none")
    parser.add_argument("--max-tokens", type=int, default=16000)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--limit", type=int, default=347)
    parser.add_argument("--query-timeout", type=float, default=30.0)
    parser.add_argument("--task-timeout", type=float, default=240.0)
    parser.add_argument("--max-score-rows", type=int)
    parser.add_argument("--result-policy", choices=("bounded-v1",))
    parser.add_argument("--verify-graph-block", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    return parser.parse_args()


async def _complete_schema(graph_client):
    from multigraphrag.graph.models import RelationshipPattern

    schema = await graph_client.build_schema()
    outcome = await graph_client.run_query(
        "MATCH (a)-[r]->(b) "
        "WITH DISTINCT labels(a) AS starts, type(r) AS rel, labels(b) AS ends "
        "RETURN starts, rel, ends",
        max_rows=1000,
    )
    if not outcome.success or outcome.truncated:
        raise ValueError(f"Cannot discover complete relationship schema: {outcome.error_message}")
    patterns = set()
    for row in outcome.records:
        starts = [label for label in row["starts"] if label != "Entity"] or row["starts"]
        ends = [label for label in row["ends"] if label != "Entity"] or row["ends"]
        for start in starts:
            for end in ends:
                patterns.add((start, row["rel"], end))
    schema.relationships = [
        RelationshipPattern(start_label=start, rel_type=rel, end_label=end)
        for start, rel, end in sorted(patterns)
    ]
    return schema


async def _score_cypher(graph_client, cypher: str | None, expected: list[list], args):
    if not cypher:
        return False, [], "no_cypher"
    result = await execute_read_only_async(
        graph_client._driver, args.database, cypher, args.query_timeout, args.max_score_rows
    )
    policy = result_policy(getattr(args, "result_policy", None))
    if policy:
        record_observation(
            {
                "phase": "scoring",
                **completeness(
                    policy,
                    scope="query",
                    available=len(result["rows"]) if result["ok"] else None,
                    collected=len(result["rows"]),
                    preview=min(len(result["rows"]), policy.preview_rows),
                    complete=result["ok"],
                    error=result["error"],
                ),
            }
        )
    rows = result["rows"]
    return result["ok"] and result_matches_answer(rows, expected), rows, result["error"]


async def _prepare_shared_preflight(args):
    from neo4j import AsyncGraphDatabase

    from agent_native_graph.research.common_preflight import prepare_preflight_async

    async with AsyncGraphDatabase.driver(
        args.neo4j_uri, auth=(args.neo4j_user, args.neo4j_password)
    ) as driver:
        return await prepare_preflight_async(driver, args.database, args.graph)


async def _generate_answer(runner, task, schema_text, mode):
    mode = workflow_mode(mode)
    if mode == "direct":
        generation = await runner.generate(question=task["nl_question"], schema_text=schema_text)
        return SimpleNamespace(cypher=generation.cypher, answer=None, accepted=None, iterations=1)
    if mode == "agentic":
        return await runner.ask(task["nl_question"], schema_text=schema_text)
    return await runner.ask(task["nl_question"], schema_text)


async def _execute_question(task, runner, graph_client, schema_text, expected, args, accounting):
    """Close every owned async request before taking the terminal question snapshot."""
    from multigraphrag.llm.call_log import set_call_context

    result, error = None, None
    deadline = Deadline(args.task_timeout) if args.profile else None
    try:
        with (
            account_requests(accounting),
            set_call_context(qid=task["qid"], domain="company", mode=args.mode),
            deadline_scope(deadline),
        ):
            async with (
                question_requests(),
                asyncio.timeout(args.task_timeout if args.profile else None),
            ):
                for attempt in range(1, 9):
                    try:
                        generation = _generate_answer(runner, task, schema_text, args.mode)
                        result = (
                            await generation
                            if args.profile
                            else await asyncio.wait_for(generation, timeout=args.task_timeout)
                        )
                        error = None
                        break
                    except Exception as exc:
                        error = f"{type(exc).__name__}: {exc}"
                        if not args.profile and "429" in error and attempt < 8:
                            await asyncio.sleep(30)
                            continue
                        break
                if result is not None:
                    if deadline is not None:
                        deadline.remaining()
                    matches, rows, score_error = await _score_cypher(
                        graph_client, result.cypher, expected, args
                    )
                    if deadline is not None:
                        deadline.remaining()
                    return result, matches, rows, error or score_error
                return None, False, [], error or "no_result"
    except Exception as exc:
        return result, False, [], f"{type(exc).__name__}: {exc}"


async def _run(args: argparse.Namespace) -> None:
    if getattr(args, "verify_graph_block", False) and (
        not getattr(args, "shared_preflight", False) or args.resume or args.check_only
    ):
        raise ValueError(
            "--verify-graph-block requires --shared-preflight and does not support --resume/--check-only"
        )
    if getattr(args, "verify_graph_block", False):
        from agent_native_graph.research.graph_integrity import integrity_path

        if any(
            path.exists()
            for path in (args.out, args.out.with_suffix(".meta.json"), integrity_path(args.out))
        ):
            raise FileExistsError(
                "Graph verification requires fresh output, metadata and sidecar paths"
            )
    policy = result_policy(getattr(args, "result_policy", None))
    if policy:
        if not args.profile or not args.reference_commit:
            raise ValueError("--result-policy requires --profile and --reference-commit")
        if args.max_score_rows not in (None, policy.max_rows):
            raise ValueError("bounded-v1 requires --max-score-rows 100000")
    if getattr(args, "mode", None) in RETRIEVAL_MODES and (
        not args.profile or not args.reference_commit
    ):
        raise ValueError("Retrieval-only modes require --profile and --reference-commit")
    if (
        getattr(args, "mode", None) in RETRIEVAL_MODES
        and args.reference_commit != RETRIEVAL_REFERENCE_COMMIT
    ):
        raise ValueError(
            f"Retrieval-only variants are validated only against {RETRIEVAL_REFERENCE_COMMIT}"
        )
    if getattr(args, "shared_preflight", False) and not args.profile:
        raise ValueError("--shared-preflight requires --profile and --reference-commit")
    if args.profile and not args.reference_commit:
        raise ValueError("--profile requires --reference-commit")
    if not args.database.strip():
        raise ValueError("--database must not be blank")
    if args.max_score_rows is None:
        args.max_score_rows = 100000 if args.profile else 10000
    for name in (
        "concurrency",
        "limit",
        "max_tokens",
        "query_timeout",
        "task_timeout",
        "max_score_rows",
    ):
        value = getattr(args, name)
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be positive and finite")
    with reference_source(args.reference_repo.resolve(), args.reference_commit) as provenance:
        await _run_with_reference(args, provenance)


async def _run_with_reference(args: argparse.Namespace, provenance: dict) -> None:
    reference_repo = args.reference_repo.resolve()

    from multigraphrag.agents.query_generator import QueryGeneratorAgent
    from multigraphrag.composition import build_pipeline, build_single_pass_runner
    from multigraphrag.config import (
        AgentModelSettings,
        EvaluationSettings,
        LLMSettings,
        MemgraphSettings,
        Settings,
        WorkflowSettings,
    )
    from multigraphrag.evaluation.cypherbench import load_tasks
    from multigraphrag.llm.call_log import CallLogger, _call_context
    from multigraphrag.llm.factory import build_llm_client

    policy = result_policy(getattr(args, "result_policy", None))
    MemgraphClient = guarded_graph_class(
        timeout=args.query_timeout,
        max_rows=args.max_score_rows,
        **({"policy": policy} if policy else {}),
    )
    profile_settings, profile_hash = load_profile(args.profile) if args.profile else (None, None)
    if profile_settings:
        args.temperature = profile_settings["temperature"]
        args.max_tokens = profile_settings["max_tokens"]
        args.reasoning = "medium" if profile_settings["enable_thinking"] else "none"

    class CountingCallLogger(CallLogger):
        def __init__(self, path: Path) -> None:
            super().__init__(path)
            self.counts: Counter[str] = Counter()

        def log(self, **kwargs) -> None:
            super().log(**kwargs)
            context = _call_context.get()
            if context:
                self.counts[context["qid"]] += 1

    all_tasks = read_jsonl(args.tasks)
    if args.limit < 1 or args.limit > len(all_tasks):
        raise ValueError(f"Limit must be between 1 and {len(all_tasks)}")
    tasks = all_tasks[: args.limit]
    reference_tasks = load_tasks(
        reference_repo / "data/cypherbench", "test", domains=["company"], limit=args.limit
    )
    qids = [task["qid"] for task in tasks]
    if qids != [task.qid for task in reference_tasks] or len(set(qids)) != len(qids):
        raise ValueError("ANA and reference Company task qids differ")
    validate_task_contents(tasks, reference_tasks)
    reference_graph = reference_repo / "data/cypherbench/graphs/simplekg/company_simplekg.json"
    graph_sha = _sha256(args.graph)
    if graph_sha != _sha256(reference_graph):
        raise ValueError("ANA and reference graph dumps differ")

    shared = None
    if getattr(args, "shared_preflight", False):
        shared = await _prepare_shared_preflight(args)
        if shared["graph_sha256"] != graph_sha:
            raise ValueError("Graph input changed after reference input comparison")

    metadata = {
        **provenance,
        "source_repo": "multigraphrag",
        "execution_policy": "read-only-v1",
        "protocol_status": "foundation-only-not-controlled-protocol-compliant",
        "transport": "ana-shared-provider" if args.profile else "reference-legacy",
        "request_accounting_version": 1 if args.profile else None,
        "request_lifecycle": "async-cancellable-v1" if args.profile else "reference-legacy",
        "profile": args.profile,
        "profile_sha256": profile_hash,
        "llm_settings": profile_settings,
        "database": args.database,
        "query_timeout_s": args.query_timeout,
        "task_timeout_s": args.task_timeout,
        "adapter_sha256": _sha256(Path(__file__).with_name("reference_adapters.py")),
        "read_policy_sha256": _sha256(Path(__file__).with_name("read_only.py")),
        "provider_sha256": _sha256(
            Path(__file__).parents[1] / "llm_providers/openai_compatible.py"
        ),
        "harness_sha256": _sha256(Path(__file__)),
        "ana_execution": execution_identity(
            SimpleNamespace(native_tools=False), Path(__file__).resolve().parents[3]
        ),
        "runtime_versions": {
            name: importlib.metadata.version(name)
            for name in ("httpx", "neo4j", "pydantic", "pydantic-settings", "tenacity", "PyYAML")
        },
        "approach": f"multigraphrag_{args.mode}",
        "mode": args.mode,
        "finalization": "retrieval-only-v1"
        if args.mode in RETRIEVAL_MODES
        else ("query-only-v1" if args.mode == "direct" else "reference-interpreter"),
        "benchmark": "cypherbench-company",
        "suite": "full" if args.limit == 347 else f"n{args.limit}",
        "split": "test",
        "model": args.model,
        "temperature": args.temperature,
        "reasoning": args.reasoning,
        "max_tokens": args.max_tokens,
        "concurrency": args.concurrency,
        "limit": args.limit,
        "scoring": "ana_exact_answer_json_on_replayed_cypher",
        "schema_strategy": "shared-canonical-v1"
        if shared is not None
        else "live_full_distinct_relationship_patterns",
        "tasks_sha256": _sha256(args.tasks),
        "graph_sha256": graph_sha,
        "max_score_rows": args.max_score_rows,
        "result_policy": getattr(args, "result_policy", None),
        "verify_graph_block": getattr(args, "verify_graph_block", False),
        "call_logs": [],
    }
    if shared is not None:
        metadata["shared_preflight"] = shared

    if args.check_only:
        settings = Settings(
            _env_file=None,
            memgraph=MemgraphSettings(
                uri=args.neo4j_uri,
                username=args.neo4j_user,
                password=args.neo4j_password,
                database=args.database,
            ),
        )
        async with MemgraphClient(settings.memgraph) as graph_client:
            await graph_client.verify_connectivity()
            schema = await _complete_schema(graph_client) if shared is None else None
            labels = schema.node_labels() if schema is not None else shared["schema"]["labels"]
            rel_types = (
                schema.relationship_types()
                if schema is not None
                else shared["schema"]["relationship_types"]
            )
            if not labels:
                raise ValueError("Neo4j schema is empty; load Company first")
            score_ok, _, score_error = await _score_cypher(
                graph_client, "RETURN 1 AS n", [[1]], args
            )
            if not score_ok or score_error:
                raise ValueError(f"Baseline scoring probe failed: {score_error}")
        print(
            json.dumps(
                {
                    "validated_tasks": len(tasks),
                    "labels": labels,
                    "relationship_types": rel_types,
                    "score_probe": True,
                    **metadata,
                }
            )
        )
        return

    api_key = os.environ.get("API_KEY")
    if not api_key and args.api_key_file:
        api_key = args.api_key_file.read_text(encoding="utf-8").strip()
    if not api_key:
        raise ValueError("Set API_KEY or --api-key-file")

    settings = Settings(
        _env_file=None,
        llm=LLMSettings(
            base_url=args.base_url,
            api_key=api_key,
            model=args.model,
            temperature=args.temperature,
            reasoning_enabled=args.reasoning != "none",
            reasoning_effort="medium" if args.reasoning == "medium" else None,
            max_tokens=args.max_tokens,
            request_timeout=120,
            max_concurrency=args.concurrency,
        ),
        memgraph=MemgraphSettings(
            uri=args.neo4j_uri,
            username=args.neo4j_user,
            password=args.neo4j_password,
            database=args.database,
        ),
        workflow=WorkflowSettings(),
        evaluation=EvaluationSettings(),
        agent_models=AgentModelSettings(),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    metadata_path = args.out.with_suffix(".meta.json")
    if args.resume and args.out.exists() and not metadata_path.exists():
        raise ValueError("Cannot resume: output has no provenance sidecar")
    if args.resume and metadata_path.exists():
        old_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        for key, value in metadata.items():
            if key != "call_logs" and old_metadata.get(key) != value:
                raise ValueError(f"Cannot resume: metadata field {key} differs")
        metadata["call_logs"] = old_metadata.get("call_logs", [])
    existing = read_jsonl(args.out) if args.resume and args.out.exists() else []
    completed = {row["qid"] for row in existing}
    if len(completed) != len(existing) or not completed.issubset(set(qids)):
        raise ValueError("Existing output contains duplicate or unexpected qids")
    if args.out.exists() and not args.resume:
        raise FileExistsError(f"Output already exists: {args.out}")

    calls_path = args.out.with_name(f"{args.out.stem}.calls.{uuid4().hex}.jsonl")
    metadata["call_logs"].append(str(calls_path))
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    block = None
    if getattr(args, "verify_graph_block", False):
        from agent_native_graph.research.graph_integrity import GraphBlock

        block = GraphBlock(args.out, metadata_path, args.graph, shared, qids)
        block.start()
    logger = CountingCallLogger(calls_path)
    semaphore = asyncio.Semaphore(args.concurrency)
    output = args.out.open("a", encoding="utf-8")
    failed = True
    try:
        async with MemgraphClient(settings.memgraph) as graph_client:
            await graph_client.verify_connectivity()
            if shared is not None:
                schema_text = shared["schema_prompt"]
                labels = shared["schema"]["labels"]
            else:
                schema_text = (await _complete_schema(graph_client)).to_cypher_like_prompt()
                labels = await graph_client.get_node_labels()
            if not schema_text.strip() or not labels:
                raise ValueError("Neo4j schema is empty; load Company first")

            async def run_one(task: dict, runner) -> None:
                if task["qid"] in completed:
                    return
                async with semaphore:
                    started = time.perf_counter()
                    accounting = RequestAccounting()
                    expected = normalize_answer_rows(parse_answer_json(task["answer_json"]))
                    cancelled = None
                    try:
                        with observe_results() as observations:
                            result, matches, rows, error = await _execute_question(
                                task, runner, graph_client, schema_text, expected, args, accounting
                            )
                    except asyncio.CancelledError as exc:
                        cancelled = exc
                        result, matches, rows, error = (
                            None,
                            False,
                            [],
                            "CancelledError: Question cancelled",
                        )
                    row = {
                        "approach": f"multigraphrag_{args.mode}",
                        "qid": task["qid"],
                        "nl_question": task["nl_question"],
                        "gold_cypher": task["gold_cypher"],
                        "expected": expected,
                        "generated_cypher": result.cypher if result else None,
                        "answer": result.answer if result else None,
                        "accepted": result.accepted if result else False,
                        "iterations": result.iterations if result else 0,
                        "rows": rows,
                        "ok": result is not None and error is None,
                        "matches_answer_json": matches,
                        "llm_call_count": logger.counts[task["qid"]],
                        "request_accounting": accounting.snapshot() if args.profile else None,
                        "tool_call_count": 0,
                        "error": error,
                        "elapsed_s": time.perf_counter() - started,
                    }
                    if policy:
                        row["result_observations"] = observations
                        final = next(
                            (
                                entry
                                for entry in reversed(observations)
                                if entry["phase"] == "scoring"
                            ),
                            None,
                        )
                        row["result_completeness"] = final or completeness(
                            policy,
                            scope="query",
                            available=None,
                            collected=0,
                            preview=0,
                            complete=False,
                            error=error or "no_final_result",
                        )
                        row["matches_answer_json"] = (
                            matches and row["result_completeness"]["complete"]
                        )
                        row["ok"] = row["ok"] and row["result_completeness"]["complete"]
                    output.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                    output.flush()
                    completed.add(task["qid"])
                    print(f"{args.mode}: {len(completed)}/{len(tasks)}", flush=True)
                    if cancelled is not None:
                        raise cancelled

            async def run_all(runner):
                await gather_and_settle(run_one(task, runner) for task in tasks)

            if args.profile:
                provider = OpenAICompatibleProvider(
                    base_url=args.base_url,
                    model=args.model,
                    api_key_env="API_KEY",
                    api_key_file=args.api_key_file,
                    settings=LLMCallSettings(**profile_settings),
                )
                runner = build_profile_runner(
                    args.mode,
                    settings,
                    graph_client,
                    provider,
                    logger,
                    **({"policy": policy} if policy else {}),
                )
                await run_all(runner)
            elif args.mode == "agentic":
                async with build_pipeline(settings, graph_client, call_logger=logger) as runner:
                    await run_all(runner)
            elif args.mode == "direct":
                client = build_llm_client(
                    settings.llm, agent_name="query_generator", call_logger=logger
                )
                try:
                    runner = QueryGeneratorAgent(client)
                    await run_all(runner)
                finally:
                    await client.aclose()
            else:
                runner, clients = build_single_pass_runner(
                    settings, graph_client, call_logger=logger
                )
                try:
                    await run_all(runner)
                finally:
                    for client in clients:
                        await client.aclose()
        failed = False
    finally:
        output.close()
        logger.close()
        if block is not None:
            await _finish_graph_block(args, block, failed)
    print(json.dumps({"run": str(args.out), "calls": str(calls_path), "completed": len(completed)}))


async def _finish_graph_block(args, block, failed):
    """Run the same content-only postcheck after requests/output settle, including failures."""
    from neo4j import AsyncGraphDatabase

    from agent_native_graph.research.common_preflight import graph_snapshot_async
    from agent_native_graph.research.graph_integrity import GraphIntegrityError

    after, failure = None, None
    try:
        async with AsyncGraphDatabase.driver(
            args.neo4j_uri, auth=(args.neo4j_user, args.neo4j_password)
        ) as driver:
            after = await graph_snapshot_async(driver, block.database)
    except Exception as exc:
        failure = type(exc).__name__
    try:
        report = block.finish(after, run_failed=failed, postcheck_error=failure)
        if not failed and report["status"] != "verified":
            raise GraphIntegrityError("Graph block is not verified; inspect the integrity sidecar")
    except Exception:
        if not failed:
            raise


def validate_task_contents(tasks, reference_tasks):
    """Reject question, gold-query or answer drift even when ordered QIDs match."""
    for task, reference in zip(tasks, reference_tasks, strict=True):
        if (
            reference.graph != "company"
            or task.get("graph", "company") != "company"
            or task["nl_question"] != reference.nl_question
            or task["gold_cypher"] != reference.gold_cypher
            or normalize_answer_rows(parse_answer_json(task["answer_json"]))
            != normalize_answer_rows(parse_answer_json(reference.answer_json))
        ):
            raise ValueError(f"ANA and reference task content differs: {task['qid']}")


def main() -> None:
    args = _parse_args()
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
