"""Opt-in pinned-reference integration with real workflows and fake provider/graph.

Run ANA_TEST_REFERENCE=1 uv run --extra reference pytest -q tests/test_reference_workflows.py.
Requires the sibling reference checkout, but makes no network calls or inference.
"""

import asyncio
import hashlib
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from agent_native_graph.llm_providers import openai_compatible
from agent_native_graph.llm_providers.accounting import RequestAccounting
from agent_native_graph.research import run_reference_baseline
from agent_native_graph.research.reference_adapters import (
    build_profile_runner,
    guarded_graph_class,
    profile_client,
)
from agent_native_graph.research.reference_source import reference_source

pytestmark = pytest.mark.skipif(
    os.environ.get("ANA_TEST_REFERENCE") != "1",
    reason="Set ANA_TEST_REFERENCE=1 for pinned reference integration",
)
REFERENCE = Path(
    os.environ.get("ANA_REFERENCE_REPO", str(Path(__file__).resolve().parents[2] / "multigraphrag"))
)
COMMIT = "72fe7105310c85ebe6b1b3b7d4c6152ddb206393"


@pytest.mark.parametrize("concurrency", [1, 2])
def test_failed_reference_batch_drains_active_and_queued_work(concurrency):
    with reference_source(REFERENCE, COMMIT):
        from multigraphrag.llm.base import Prompt
        from multigraphrag.llm.vllm_client import LLMResponseParsingError
        from multigraphrag.schemas import QueryGeneration

        started, active = [], set()

        async def chat(messages, **kwargs):
            index = len(started)
            started.append(index)
            active.add(index)
            try:
                if index == 0:
                    return {"content": "not JSON"}
                await asyncio.Event().wait()
            finally:
                active.discard(index)

        logger = MagicMock()
        client = profile_client(
            SimpleNamespace(_model="fake", achat=chat),
            role="ranker",
            logger=logger,
            concurrency=concurrency,
        )

        async def run():
            with pytest.raises(LLMResponseParsingError):
                # Positional model argument matches the pinned reference API.
                await client.complete_structured_many(
                    [Prompt(system_prompt="S", user_prompt="Q")] * 8, QueryGeneration
                )
            count = logger.log.call_count
            await asyncio.sleep(0)
            assert logger.log.call_count == count

        asyncio.run(run())
        assert not active and len(started) < 8


def test_reference_batch_success_preserves_input_order_and_bound():
    with reference_source(REFERENCE, COMMIT):
        from multigraphrag.llm.base import Prompt

        active, peak = 0, 0

        async def chat(messages, **kwargs):
            nonlocal active, peak
            active += 1
            peak = max(active, peak)
            try:
                await asyncio.sleep(0.001)
                return {"content": messages[-1]["content"]}
            finally:
                active -= 1

        client = profile_client(
            SimpleNamespace(_model="fake", achat=chat),
            role="ranker",
            logger=MagicMock(),
            concurrency=2,
        )
        prompts = [Prompt(system_prompt="S", user_prompt=str(i)) for i in range(5)]
        assert asyncio.run(client.complete_many(prompts)) == [str(i) for i in range(5)]
        assert peak == 2 and active == 0


@pytest.mark.parametrize("phase", ["generation", "scoring"])
def test_question_deadline_includes_final_scoring(monkeypatch, phase):
    with reference_source(REFERENCE, COMMIT):
        stopped = asyncio.Event()

        async def slow(*args, **kwargs):
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        async def fast(*args, **kwargs):
            return SimpleNamespace(cypher="RETURN 1")

        runner = SimpleNamespace(generate=slow if phase == "generation" else fast)
        monkeypatch.setattr(
            run_reference_baseline,
            "_score_cypher",
            slow if phase == "scoring" else AsyncMock(return_value=(True, [[1]], None)),
        )
        args = SimpleNamespace(profile="temp0-none", task_timeout=0.02, mode="direct")
        ledger = RequestAccounting()
        result, matches, rows, error = asyncio.run(
            run_reference_baseline._execute_question(
                {"qid": "test", "nl_question": "Q"}, runner, None, "schema", [[1]], args, ledger
            )
        )
        assert stopped.is_set() and not matches and not rows and "Timeout" in error
        assert ledger.snapshot()["summary"]["requests_settled"]


@pytest.mark.parametrize(
    "mode,roles",
    [
        ("direct", ["query_generator"]),
        ("single", ["query_generator", "interpreter"]),
        ("agentic", ["query_generator", "query_evaluator", "interpreter"]),
    ],
)
def test_real_reference_workflows_with_shared_adapter(mode, roles):
    with reference_source(REFERENCE, COMMIT):
        from multigraphrag.config import Settings
        from multigraphrag.graph.models import QueryOutcome
        from multigraphrag.llm.call_log import _call_context, set_call_context

        observed_contexts = []

        async def chat(messages, *, response_format):
            observed_contexts.append(_call_context.get()["qid"])
            model = response_format["json_schema"]["name"]
            responses = {
                "QueryGeneration": {"cypher": "RETURN 1 AS n"},
                "EvaluationResult": {"status": "accept", "feedback": "ok"},
                "InterpretedAnswer": {"answer": "1"},
            }
            return {"content": json.dumps(responses[model])}

        async def query(*args, **kwargs):
            return QueryOutcome(success=True, records=[{"n": 1}])

        graph = SimpleNamespace(run_query=query)
        provider = SimpleNamespace(achat=chat, _model="fake/model")
        logger = MagicMock()
        runner = build_profile_runner(mode, Settings(_env_file=None), graph, provider, logger)

        async def execute():
            with set_call_context(qid="test", domain="company", mode=mode):
                if mode == "direct":
                    return await runner.generate(question="Q", schema_text="schema")
                return await runner.ask(question="Q", schema_text="schema")

        result = asyncio.run(execute())
        assert result.cypher == "RETURN 1 AS n"
        assert [call.kwargs["agent"] for call in logger.log.call_args_list] == roles
        assert observed_contexts == ["test"] * len(roles)


def test_real_graph_adapter_caps_preview_not_complete_execution():
    def driver_with_two_rows():
        driver = MagicMock()
        session = driver.session.return_value.__aenter__.return_value
        session.run = AsyncMock(
            return_value=SimpleNamespace(
                consume=AsyncMock(return_value=SimpleNamespace(query_type="r"))
            )
        )
        manager = MagicMock()
        session.begin_transaction = AsyncMock(return_value=manager)
        tx = manager.__aenter__.return_value
        cursor = MagicMock()
        cursor.keys.return_value = ["x", "y"]
        cursor.__aiter__.return_value = [
            SimpleNamespace(values=lambda: [1, 2]),
            SimpleNamespace(values=lambda: [3, 4]),
        ]
        tx.run = AsyncMock(return_value=cursor)
        tx.rollback = AsyncMock()
        return driver

    with reference_source(REFERENCE, COMMIT):
        from multigraphrag.config import MemgraphSettings

        driver = driver_with_two_rows()
        graph_type = guarded_graph_class(timeout=30, max_rows=10)
        graph = graph_type(MemgraphSettings(database="company"), driver=driver)
        outcome = asyncio.run(graph.run_query("RETURN 1", max_rows=1))
        assert outcome.success and outcome.truncated and len(outcome.records) == 1
        driver = driver_with_two_rows()
        graph_type = guarded_graph_class(timeout=30, max_rows=1)
        graph = graph_type(MemgraphSettings(database="company"), driver=driver)
        outcome = asyncio.run(graph.run_query("RETURN 1", max_rows=10))
        assert not outcome.success and not outcome.records
        assert "result_row_limit" in outcome.error_message


def test_bounded_policy_caps_candidates_but_not_schema_and_records_full_scoring():
    from agent_native_graph.application.result_policy import (
        BoundedResults,
        CandidatePreviewGraph,
        observe_results,
    )

    with reference_source(REFERENCE, COMMIT):
        from multigraphrag.config import MemgraphSettings

        driver = MagicMock()
        session = driver.session.return_value.__aenter__.return_value
        session.run = AsyncMock(
            return_value=SimpleNamespace(
                consume=AsyncMock(return_value=SimpleNamespace(query_type="r"))
            )
        )
        manager = MagicMock()
        session.begin_transaction = AsyncMock(return_value=manager)
        tx = manager.__aenter__.return_value

        async def query(*args, **kwargs):
            cursor = MagicMock()
            cursor.keys.return_value = ["n"]
            cursor.__aiter__.return_value = [
                SimpleNamespace(values=lambda i=i: [i]) for i in range(25)
            ]
            return cursor

        tx.run = query
        tx.rollback = AsyncMock()
        graph_type = guarded_graph_class(timeout=30, max_rows=100000, policy=BoundedResults())
        graph = graph_type(MemgraphSettings(database="neo4j"), driver=driver)

        async def execute():
            with observe_results() as observations:
                candidate = await CandidatePreviewGraph(graph).run_query("RETURN 1", max_rows=200)
                schema = await graph.run_query("RETURN 1", max_rows=1000)
                result = await run_reference_baseline._score_cypher(
                    graph,
                    "RETURN 1",
                    [[i] for i in range(25)],
                    SimpleNamespace(
                        database="neo4j",
                        query_timeout=30,
                        max_score_rows=100000,
                        result_policy="bounded-v1",
                    ),
                )
            return candidate, schema, result, observations

        candidate, schema, result, observations = asyncio.run(execute())
        assert len(candidate.records) == 20 and candidate.truncated
        assert len(schema.records) == 25 and not schema.truncated
        assert result == (True, [[i] for i in range(25)], None)
        assert [o["phase"] for o in observations] == ["candidate", "introspection", "scoring"]
        assert all(o["collected_count"] == 25 and o["complete"] for o in observations)
        assert observations[0]["preview_count"] == 20 and observations[0]["preview_truncated"]


@pytest.mark.parametrize(
    "mode,termination,shared",
    [
        ("direct", "success", False),
        ("single", "success", False),
        ("agentic", "success", False),
        ("direct", "timeout", False),
        ("direct", "cancel", False),
        ("direct", "success", True),
        ("single", "success", True),
        ("agentic", "success", True),
        ("single_retrieval", "success", False),
        ("agentic_retrieval", "success", False),
        ("single_retrieval", "success", True),
        ("agentic_retrieval", "success", True),
        ("single_retrieval", "timeout", True),
        ("agentic_retrieval", "cancel", True),
        ("single_retrieval", "bounded", True),
        ("agentic_retrieval", "bounded", True),
        ("single_retrieval", "block_stable", True),
        ("agentic_retrieval", "block_changed", True),
        ("single_retrieval", "block_post_error", True),
        ("agentic_retrieval", "block_cancel", True),
        ("direct", "mismatch", True),
    ],
)
def test_harness_records_pinned_profile_run_without_network(
    tmp_path, monkeypatch, mode, termination, shared
):
    """Exercise import lifetime, task checks, runner selection and on-disk provenance."""
    block_case = termination.removeprefix("block_") if termination.startswith("block_") else None
    if block_case:
        termination = "cancel" if block_case == "cancel" else "success"
    bounded = termination == "bounded"
    if bounded:
        termination = "success"
    output = tmp_path / "run.jsonl"
    task = {
        "qid": "offline-question",
        "graph": "company",
        "nl_question": "Return one",
        "gold_cypher": "RETURN 1 AS n",
        "answer_json": "[[1]]",
    }
    task_file = tmp_path / "tasks.jsonl"
    task_file.write_text(json.dumps(task) + "\n")
    graph_file = tmp_path / "graph.json"
    graph_file.write_text("{}")
    graph_sha = hashlib.sha256(graph_file.read_bytes()).hexdigest()

    @contextmanager
    def pinned_with_fake_tasks(*args):
        # Exercise the real import boundary without requiring ignored dataset downloads.
        with reference_source(*args) as provenance:
            from multigraphrag.evaluation import cypherbench

            monkeypatch.setattr(
                cypherbench, "load_tasks", lambda *a, **kw: [SimpleNamespace(**task)]
            )
            yield provenance

    monkeypatch.setattr(run_reference_baseline, "reference_source", pinned_with_fake_tasks)
    monkeypatch.setenv("API_KEY", "test-not-a-real-key")
    monkeypatch.setattr(
        "sys.argv",
        [
            "baseline-run",
            "--mode",
            mode,
            "--reference-repo",
            str(REFERENCE),
            "--reference-commit",
            COMMIT,
            "--profile",
            "temp0-none",
            "--limit",
            "1",
            "--out",
            str(output),
            "--tasks",
            str(task_file),
            "--graph",
            str(graph_file),
        ],
    )
    args = run_reference_baseline._parse_args()
    args.result_policy = "bounded-v1" if bounded else None
    args.verify_graph_block = bool(block_case)
    args.shared_preflight = shared
    canonical = {
        "labels": ["Asset"],
        "relationship_types": [],
        "node_properties": [],
        "relationship_properties": [],
        "label_relationships": [],
    }
    bootstrap = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    evidence = {
        "version": "shared-preflight-v1",
        "database": "neo4j",
        "schema": canonical,
        "schema_prompt": bootstrap,
        "schema_sha256": "shared-hash",
        "schema_prompt_sha256": "shared-hash",
        "snapshot": {
            "nodes": {"count": 1, "sha256": "a" * 64},
            "edges": {"count": 0, "sha256": "b" * 64},
        },
        "graph_sha256": graph_sha,
    }
    prepare = AsyncMock(return_value=evidence)
    if termination == "mismatch":
        prepare.side_effect = ValueError("Graph content mismatch")
    monkeypatch.setattr(run_reference_baseline, "_prepare_shared_preflight", prepare)
    if termination == "timeout":
        args.task_timeout = 0.05
    # File identities and final scoring have separate tests; no large dump or DB IO here.
    monkeypatch.setattr(run_reference_baseline, "_sha256", lambda path: graph_sha)
    if block_case:
        import copy

        import neo4j

        from agent_native_graph.research import common_preflight

        after = copy.deepcopy(evidence["snapshot"])
        if block_case == "changed":
            after["edges"]["sha256"] = "c" * 64
        scan = AsyncMock(return_value=after)
        if block_case == "post_error":
            scan.side_effect = RuntimeError("private endpoint must not be retained")
        monkeypatch.setattr(common_preflight, "graph_snapshot_async", scan)
        monkeypatch.setattr(neo4j.AsyncGraphDatabase, "driver", MagicMock())

    async def score(*args):
        if bounded:
            from agent_native_graph.application.result_policy import (
                BoundedResults,
                completeness,
                record_observation,
            )

            record_observation(
                {
                    "phase": "scoring",
                    **completeness(
                        BoundedResults(),
                        scope="query",
                        available=1,
                        collected=1,
                        preview=1,
                        complete=True,
                    ),
                }
            )
        return True, [[1]], None

    monkeypatch.setattr(run_reference_baseline, "_score_cypher", score)
    schema = SimpleNamespace(to_cypher_like_prompt=lambda: "(:Company)")
    monkeypatch.setattr(run_reference_baseline, "_complete_schema", AsyncMock(return_value=schema))

    class Graph:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            pass

        async def verify_connectivity(self):
            pass

        async def get_node_labels(self):
            return ["Company"]

        async def run_query(self, *args, **kwargs):
            from multigraphrag.graph.models import QueryOutcome

            return QueryOutcome(success=True, records=[{"n": 1}])

    monkeypatch.setattr(
        run_reference_baseline, "guarded_graph_class", lambda **kw: lambda settings: Graph()
    )
    responses = {
        "QueryGeneration": {"cypher": "RETURN 1 AS n"},
        "EvaluationResult": {"status": "accept", "feedback": "ok"},
        "InterpretedAnswer": {"answer": "1"},
    }
    client_type = httpx.AsyncClient
    payloads = []

    started, stopped = asyncio.Event(), asyncio.Event()

    async def handle(request):
        if termination != "success":
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
        payload = json.loads(request.content)
        payloads.append(payload)
        response = responses[payload["response_format"]["json_schema"]["name"]]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(response)}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
            },
        )

    class FakeAsyncClient(client_type):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(handle))

    monkeypatch.setattr(openai_compatible.httpx, "AsyncClient", FakeAsyncClient)

    async def execute():
        run = asyncio.create_task(run_reference_baseline._run(args))
        if termination == "mismatch":
            with pytest.raises(ValueError, match="Graph content mismatch"):
                await run
        elif termination == "cancel":
            await asyncio.wait_for(started.wait(), 2)
            run.cancel()
            with pytest.raises(asyncio.CancelledError):
                await run
        elif block_case in ("changed", "post_error"):
            from agent_native_graph.research.graph_integrity import GraphIntegrityError

            with pytest.raises(GraphIntegrityError):
                await run
        else:
            await run

    asyncio.run(execute())
    if termination == "mismatch":
        assert not output.exists() and not output.with_suffix(".meta.json").exists()
        assert not payloads
        return
    metadata = json.loads(output.with_suffix(".meta.json").read_text())
    row = json.loads(output.read_text())
    if block_case:
        report = json.loads(output.with_suffix(".integrity.json").read_text())
        assert report["status"] == (
            "verified"
            if block_case == "stable"
            else "invalid"
            if block_case == "changed"
            else "incomplete"
        )
        assert "private endpoint" not in json.dumps(report)
        scan.assert_awaited_once()
        assert scan.call_args.args[1] == "neo4j"
    if termination != "success":
        assert not row["ok"] and not row["matches_answer_json"] and stopped.is_set()
        assert ("CancelledError" if termination == "cancel" else "Timeout") in row["error"]
        assert row["request_accounting"]["summary"]["http_attempts"] == 1
        assert row["request_accounting"]["summary"]["requests_settled"]
        assert row["llm_call_count"] == 1
        return
    assert metadata["source_mode"] == "pinned-git-export"
    assert metadata["transport"] == "ana-shared-provider"
    assert metadata["llm_settings"]["max_tokens"] == 16000
    if shared:
        assert metadata["shared_preflight"] == evidence
        assert metadata["schema_strategy"] == "shared-canonical-v1"
        generator = next(
            p for p in payloads if p["response_format"]["json_schema"]["name"] == "QueryGeneration"
        )
        assert bootstrap in generator["messages"][-1]["content"]
        run_reference_baseline._complete_schema.assert_not_called()
    else:
        assert "shared_preflight" not in metadata
    assert metadata["execution_policy"] == "read-only-v1"
    if bounded:
        assert metadata["result_policy"] == "bounded-v1"
        assert (
            row["result_completeness"]["complete"]
            and row["result_completeness"]["scope"] == "query"
        )
    assert (
        row["ok"]
        and row["llm_call_count"]
        == {
            "direct": 1,
            "single": 2,
            "agentic": 3,
            "single_retrieval": 1,
            "agentic_retrieval": 2,
        }[mode]
    )
    if mode.endswith("_retrieval"):
        assert metadata["finalization"] == "retrieval-only-v1"
        assert row["approach"] == f"multigraphrag_{mode}" and row["answer"] is None
        assert "interpreter" not in row["request_accounting"]["summary"]["roles"]
    accounting = row["request_accounting"]["summary"]
    assert accounting["logical_calls"] == accounting["http_attempts"] == row["llm_call_count"]
    assert accounting["observed_usage_totals"]["total_tokens"] == 11 * row["llm_call_count"]
    assert accounting["roles"]["query_generator"] == 1
    assert accounting["requests_settled"]
    assert len(metadata["call_logs"]) == 1
    assert "multigraphrag" not in sys.modules
    assert "test-not-a-real-key" not in output.with_suffix(".meta.json").read_text()
    original_calls = Path(metadata["call_logs"][0]).read_bytes()
    args.resume = True
    if block_case:
        with pytest.raises(ValueError, match="does not support --resume"):
            asyncio.run(run_reference_baseline._run(args))
        return
    asyncio.run(run_reference_baseline._run(args))
    resumed = json.loads(output.with_suffix(".meta.json").read_text())
    assert len(set(resumed["call_logs"])) == 2
    assert Path(metadata["call_logs"][0]).read_bytes() == original_calls
    assert json.loads(output.read_text()) == row
    args.result_policy = None if bounded else "bounded-v1"
    with pytest.raises(ValueError, match="metadata field result_policy differs"):
        asyncio.run(run_reference_baseline._run(args))
    args.result_policy = "bounded-v1" if bounded else None
    args.database = "changed"
    with pytest.raises(ValueError, match="metadata field database differs"):
        asyncio.run(run_reference_baseline._run(args))
    args.database = "neo4j"
    output.with_suffix(".meta.json").unlink()
    with pytest.raises(ValueError, match="no provenance sidecar"):
        asyncio.run(run_reference_baseline._run(args))
