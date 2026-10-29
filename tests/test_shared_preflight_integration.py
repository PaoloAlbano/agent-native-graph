"""Opt-in wiring tests; no network, graph server, model provider or raw dump needed."""

import asyncio
import hashlib
import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_native_graph.application import agent_loop, neo4j_benchmark, run_config
from agent_native_graph.research import common_preflight, run_reference_baseline


def artifact(graph):
    schema = common_preflight.canonical_schema(
        {
            "labels": ["Asset"],
            "relationship_types": [],
            "node_properties": [],
            "relationship_properties": [],
            "label_relationships": [],
        }
    )
    text = json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {
        "version": "shared-preflight-v1",
        "database": "benchmark",
        "graph_sha256": hashlib.sha256(graph.read_bytes()).hexdigest(),
        "snapshot": {"nodes": {"count": 1, "sha256": "n"}, "edges": {"count": 0, "sha256": "e"}},
        "schema": schema,
        "schema_sha256": common_preflight.schema_digest(schema),
        "schema_prompt": text,
        "schema_prompt_sha256": hashlib.sha256(text.encode()).hexdigest(),
    }


def test_task_prompt_preserves_legacy_bytes_and_adds_only_explicit_bootstrap():
    transcript = [{"action": {"tool": "schema_overview"}, "result": {}}]
    expected = json.dumps(
        {
            "question": "Q",
            "previous_tool_results": transcript,
            "instruction": "Choose the next tool call. Use fetch when the answer handle is ready.",
        },
        ensure_ascii=False,
    )
    assert agent_loop._task_prompt("Q", transcript) == expected
    result = json.loads(agent_loop._task_prompt("Q", transcript, '{"labels":["Asset"]}'))
    assert result.pop("schema_bootstrap") == '{"labels":["Asset"]}'
    assert result == json.loads(expected)


def test_both_preflight_adapters_pass_identical_inputs_and_named_database(tmp_path, monkeypatch):
    import neo4j

    graph = tmp_path / "graph.json"
    graph.write_text("{}")
    expected = artifact(graph)
    sync_driver, async_driver = MagicMock(), MagicMock()
    sync_driver.__enter__.return_value = sync_driver
    async_driver.__aenter__.return_value = async_driver
    monkeypatch.setattr(neo4j.GraphDatabase, "driver", MagicMock(return_value=sync_driver))
    monkeypatch.setattr(neo4j.AsyncGraphDatabase, "driver", MagicMock(return_value=async_driver))
    sync = MagicMock(return_value=expected)
    asynchronous = AsyncMock(return_value=expected)
    monkeypatch.setattr(common_preflight, "prepare_preflight", sync)
    monkeypatch.setattr(common_preflight, "prepare_preflight_async", asynchronous)
    args = SimpleNamespace(
        neo4j_uri="bolt://unused",
        neo4j_user="test",
        neo4j_password="test",
        database="benchmark",
        graph_file=graph,
        graph=graph,
    )
    assert neo4j_benchmark._prepare_shared_preflight(args) == asyncio.run(
        run_reference_baseline._prepare_shared_preflight(args)
    )
    assert sync.call_args.args == (sync_driver, "benchmark", graph)
    assert asynchronous.call_args.args == (async_driver, "benchmark", graph)


@pytest.fixture
def diagnostic(tmp_path, monkeypatch):
    tasks, schema, graph = (
        tmp_path / name for name in ("tasks.jsonl", "schema.json", "graph.json")
    )
    task = {
        "qid": "q",
        "graph": "company",
        "nl_question": "Q",
        "gold_cypher": "GOLD_DO_NOT_SEND",
        "answer_json": "[[1]]",
    }
    tasks.write_text(json.dumps(task) + "\n")
    schema.write_text('{"extra_examples": "LOCAL_FILE_MUST_NOT_ENTER_SHARED_BOOTSTRAP"}')
    graph.write_text("{}")
    out = tmp_path / "run.jsonl"
    argv = [
        "benchmark-neo4j",
        "--tasks",
        str(tasks),
        "--schema-json",
        str(schema),
        "--graph-file",
        str(graph),
        "--out",
        str(out),
        "--limit",
        "1",
        "--native-tools",
        "--shared-preflight",
        "--database",
        "benchmark",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    return task, argv, graph, out


def test_ana_shared_mode_saves_evidence_and_uses_live_schema(diagnostic, monkeypatch):
    task, _, graph, out = diagnostic
    expected = artifact(graph)
    monkeypatch.setattr(neo4j_benchmark, "_prepare_shared_preflight", lambda args: expected)
    execute = MagicMock()
    monkeypatch.setattr(neo4j_benchmark, "_execute", execute)
    neo4j_benchmark.main()
    args, _, schema = execute.call_args.args
    assert schema == expected["schema"] and args.shared_preflight_artifact == expected
    config = run_config.load_config(out.with_suffix(".config.json"))
    assert config["schema_source"] == "shared-live-preflight-v1"
    assert config["shared_preflight"] == expected
    assert "LOCAL_FILE_MUST_NOT" not in config["shared_preflight"]["schema_prompt"]
    assert "GOLD_DO_NOT_SEND" not in config["shared_preflight"]["schema_prompt"]


def test_mismatched_graph_prevents_config_or_inference(diagnostic, monkeypatch):
    _, _, _, out = diagnostic

    def mismatch(args):
        raise ValueError("Graph content mismatch")

    monkeypatch.setattr(neo4j_benchmark, "_prepare_shared_preflight", mismatch)
    execute = MagicMock()
    monkeypatch.setattr(neo4j_benchmark, "_execute", execute)
    with pytest.raises(ValueError, match="Graph content mismatch"):
        neo4j_benchmark.main()
    execute.assert_not_called()
    assert not out.exists() and not out.with_suffix(".config.json").exists()


def test_graph_file_change_after_preflight_prevents_inference(diagnostic, monkeypatch):
    _, _, graph, out = diagnostic
    expected = artifact(graph)

    def prepare(args):
        graph.write_text('{"changed":true}')
        return expected

    monkeypatch.setattr(neo4j_benchmark, "_prepare_shared_preflight", prepare)
    execute = MagicMock()
    monkeypatch.setattr(neo4j_benchmark, "_execute", execute)
    with pytest.raises(ValueError, match="Graph input changed"):
        neo4j_benchmark.main()
    execute.assert_not_called()
    assert not out.with_suffix(".config.json").exists()


def test_check_only_does_not_accidentally_scan_live_graph(diagnostic, monkeypatch):
    _, argv, _, _ = diagnostic
    monkeypatch.setattr(sys, "argv", [*argv, "--check-only"])
    preflight = MagicMock()
    monkeypatch.setattr(neo4j_benchmark, "_prepare_shared_preflight", preflight)
    with pytest.raises(SystemExit):
        neo4j_benchmark.main()
    preflight.assert_not_called()


def test_resume_rejects_changed_shared_schema(diagnostic, monkeypatch):
    _, argv, graph, _ = diagnostic
    expected = artifact(graph)
    monkeypatch.setattr(neo4j_benchmark, "_prepare_shared_preflight", lambda args: expected)
    execute = MagicMock()
    monkeypatch.setattr(neo4j_benchmark, "_execute", execute)
    neo4j_benchmark.main()
    monkeypatch.setattr(sys, "argv", [*argv, "--resume"])
    expected["schema"]["labels"].append("Changed")
    with pytest.raises(ValueError, match="changed"):
        neo4j_benchmark.main()
    assert execute.call_count == 1


def test_native_shared_mode_uses_same_bootstrap_and_named_db(tmp_path, monkeypatch):
    from agent_native_graph.backends.neo4j import backend as backend_module

    graph = tmp_path / "graph.json"
    graph.write_text("{}")
    evidence = artifact(graph)
    backend = SimpleNamespace(last_fetch=None, close=MagicMock())

    def call(tool, args):
        backend.last_fetch = [[1]]
        return {"rows": [[1]], "returned_count": 1}

    backend.call = call
    factory = MagicMock(return_value=backend)
    monkeypatch.setattr(backend_module, "Neo4jGraphBackend", factory)
    llm = SimpleNamespace(
        chat=MagicMock(
            return_value={
                "tool_calls": [{"function": {"name": "fetch", "arguments": '{"from":"h1"}'}}]
            }
        )
    )
    row = neo4j_benchmark._run_agent_task(
        {"qid": "q", "nl_question": "Q", "gold_cypher": "GOLD_DO_NOT_SEND", "answer_json": "[[1]]"},
        llm=llm,
        schema=evidence["schema"],
        schema_bootstrap=evidence["schema_prompt"],
        database="benchmark",
        neo4j_uri="bolt://unused",
        neo4j_user="test",
        neo4j_password="test",
        neo4j_query_timeout_s=30,
        max_steps=1,
        native_tools=True,
        tool_choice="auto",
        enable_planning_tools=False,
        schema_entry="overview",
        wrapper_planning=False,
        auto_fetch_on_done=False,
        evaluation_fetch_all_pages=False,
        enable_runner_guardrails=False,
        task_timeout_s=None,
    )
    assert row["ok"] and row["matches_answer_json"]
    assert factory.call_args.kwargs["database"] == "benchmark"
    user = json.loads(llm.chat.call_args.args[0][-1]["content"])
    assert user["schema_bootstrap"] == evidence["schema_prompt"]
    assert "GOLD_DO_NOT_SEND" not in json.dumps(llm.chat.call_args.args)
