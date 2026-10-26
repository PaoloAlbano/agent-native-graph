"""Run the external Multi-Agent GraphRAG implementation on the ANA Company suite.

This harness reuses the reference project's SinglePassRunner and GraphRAGPipeline
against the already loaded Neo4j graph. It records query rows so both methods
can be scored with the same exact answer_json comparator used by ANA.
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from agent_native_graph.research_common import (
    normalize_answer_rows,
    normalize_result_rows,
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
    parser.add_argument("--tasks", type=Path, default=Path("data/tasks_company_test.jsonl"))
    parser.add_argument("--graph", type=Path, default=Path("downloads/company_simplekg.json"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=("direct", "single", "agentic"), required=True)
    parser.add_argument("--model", default="openai/gpt-oss-120b")
    parser.add_argument("--base-url", default="https://openrouter.ai/api/")
    parser.add_argument("--api-key-file", type=Path)
    parser.add_argument("--neo4j-uri", default="bolt://127.0.0.1:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", default="password")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--reasoning", choices=("none", "medium"), default="none")
    parser.add_argument("--max-tokens", type=int, default=16000)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--limit", type=int, default=347)
    parser.add_argument("--query-timeout", type=float, default=30.0)
    parser.add_argument("--task-timeout", type=float, default=240.0)
    parser.add_argument("--max-score-rows", type=int, default=10000)
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
    import neo4j

    if not cypher:
        return False, [], "no_cypher"
    try:
        async with graph_client._driver.session(
            database=graph_client._settings.database, default_access_mode=neo4j.READ_ACCESS
        ) as session:
            result = await session.run(neo4j.Query(cypher, timeout=args.query_timeout))
            keys = list(result.keys())
            records = []
            async for record in result:
                if len(records) >= args.max_score_rows:
                    return False, [], "score_row_limit"
                records.append({key: record.get(key) for key in keys})
        rows = normalize_result_rows(records)
        return result_matches_answer(rows, expected), rows, None
    except Exception as exc:  # A generated query can fail independently of the agent run.
        return False, [], f"score_query_error: {type(exc).__name__}: {exc}"


async def _run(args: argparse.Namespace) -> None:
    reference_repo = args.reference_repo.resolve()
    sys.path.insert(0, str(reference_repo / "src"))

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
    from multigraphrag.graph.memgraph_client import MemgraphClient
    from multigraphrag.llm.call_log import CallLogger, _call_context, set_call_context
    from multigraphrag.llm.factory import build_llm_client

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
    reference_graph = reference_repo / "data/cypherbench/graphs/simplekg/company_simplekg.json"
    if _sha256(args.graph) != _sha256(reference_graph):
        raise ValueError("ANA and reference graph dumps differ")

    source_commit = subprocess.check_output(
        ["git", "-C", str(reference_repo), "rev-parse", "HEAD"], text=True
    ).strip()
    source_repo = subprocess.check_output(
        ["git", "-C", str(reference_repo), "remote", "get-url", "origin"], text=True
    ).strip()
    metadata = {
        "source_repo": source_repo,
        "source_commit": source_commit,
        "approach": f"multigraphrag_{args.mode}",
        "mode": args.mode,
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
        "schema_strategy": "live_full_distinct_relationship_patterns",
        "tasks_sha256": _sha256(args.tasks),
        "graph_sha256": _sha256(args.graph),
        "max_score_rows": args.max_score_rows,
        "call_logs": [],
    }

    if args.check_only:
        settings = Settings(
            _env_file=None,
            memgraph=MemgraphSettings(
                uri=args.neo4j_uri,
                username=args.neo4j_user,
                password=args.neo4j_password,
            ),
        )
        async with MemgraphClient(settings.memgraph) as graph_client:
            await graph_client.verify_connectivity()
            schema = await _complete_schema(graph_client)
            labels = schema.node_labels()
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
                    "relationship_types": schema.relationship_types(),
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
        ),
        workflow=WorkflowSettings(),
        evaluation=EvaluationSettings(),
        agent_models=AgentModelSettings(),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    metadata_path = args.out.with_suffix(".meta.json")
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

    calls_path = args.out.with_name(f"{args.out.stem}.calls.{int(time.time())}.jsonl")
    metadata["call_logs"].append(str(calls_path))
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    logger = CountingCallLogger(calls_path)
    semaphore = asyncio.Semaphore(args.concurrency)
    output = args.out.open("a", encoding="utf-8")
    try:
        async with MemgraphClient(settings.memgraph) as graph_client:
            await graph_client.verify_connectivity()
            schema_text = (await _complete_schema(graph_client)).to_cypher_like_prompt()
            if not schema_text.strip() or not (await graph_client.get_node_labels()):
                raise ValueError("Neo4j schema is empty; load Company first")

            async def run_one(task: dict, runner) -> None:
                if task["qid"] in completed:
                    return
                async with semaphore:
                    started = time.perf_counter()
                    result = None
                    error = None
                    for attempt in range(1, 9):
                        try:
                            with set_call_context(
                                qid=task["qid"], domain="company", mode=args.mode
                            ):
                                if args.mode == "direct":
                                    generation = await asyncio.wait_for(
                                        runner.generate(
                                            question=task["nl_question"], schema_text=schema_text
                                        ),
                                        timeout=args.task_timeout,
                                    )
                                    result = SimpleNamespace(
                                        cypher=generation.cypher,
                                        answer=None,
                                        accepted=None,
                                        iterations=1,
                                    )
                                elif args.mode == "agentic":
                                    result = await asyncio.wait_for(
                                        runner.ask(task["nl_question"], schema_text=schema_text),
                                        timeout=args.task_timeout,
                                    )
                                else:
                                    result = await asyncio.wait_for(
                                        runner.ask(task["nl_question"], schema_text),
                                        timeout=args.task_timeout,
                                    )
                            error = None
                            break
                        except Exception as exc:
                            error = f"{type(exc).__name__}: {exc}"
                            if "429" in error and attempt < 8:
                                await asyncio.sleep(30)
                                continue
                            break
                    expected = normalize_answer_rows(parse_answer_json(task["answer_json"]))
                    if result is not None:
                        matches, rows, score_error = await _score_cypher(
                            graph_client, result.cypher, expected, args
                        )
                    else:
                        matches, rows, score_error = False, [], "no_result"
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
                        "ok": result is not None and score_error is None,
                        "matches_answer_json": matches,
                        "llm_call_count": logger.counts[task["qid"]],
                        "tool_call_count": 0,
                        "error": error or score_error,
                        "elapsed_s": time.perf_counter() - started,
                    }
                    output.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                    output.flush()
                    completed.add(task["qid"])
                    print(f"{args.mode}: {len(completed)}/{len(tasks)}", flush=True)

            if args.mode == "agentic":
                async with build_pipeline(settings, graph_client, call_logger=logger) as runner:
                    await asyncio.gather(*(run_one(task, runner) for task in tasks))
            elif args.mode == "direct":
                client = build_llm_client(
                    settings.llm, agent_name="query_generator", call_logger=logger
                )
                try:
                    runner = QueryGeneratorAgent(client)
                    await asyncio.gather(*(run_one(task, runner) for task in tasks))
                finally:
                    await client.aclose()
            else:
                runner, clients = build_single_pass_runner(
                    settings, graph_client, call_logger=logger
                )
                try:
                    await asyncio.gather(*(run_one(task, runner) for task in tasks))
                finally:
                    for client in clients:
                        await client.aclose()
    finally:
        output.close()
        logger.close()
    print(json.dumps({"run": str(args.out), "calls": str(calls_path), "completed": len(completed)}))


def main() -> None:
    args = _parse_args()
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
