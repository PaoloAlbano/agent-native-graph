"""Offline checks for pinned sources, shared LLM payloads and read-only baseline IO."""

import asyncio
import importlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from agent_native_graph.application.run_config import load_profile, profile_names
from agent_native_graph.llm_providers import openai_compatible
from agent_native_graph.llm_providers.settings import LLMCallSettings
from agent_native_graph.research.read_only import execute_read_only_async
from agent_native_graph.research.reference_adapters import profile_client
from agent_native_graph.research.reference_source import reference_source
from agent_native_graph.research.run_reference_baseline import (
    _generate_answer,
    _run,
    _score_cypher,
    validate_task_contents,
)


@pytest.fixture
def reference(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args]).decode().strip()

    git("init", "-q")
    package = tmp_path / "src/multigraphrag"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("VALUE = 'committed'\n")
    (tmp_path / "uv.lock").write_text("version = 1\n")
    git("add", ".")
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture")
    return tmp_path, git("rev-parse", "HEAD")


def test_pinned_export_ignores_dirty_checkout_and_scopes_imports(reference):
    repo, commit = reference
    (repo / "src/multigraphrag/__init__.py").write_text("VALUE = 'dirty'\n")
    old_path = sys.path[:]
    with reference_source(repo, commit) as metadata:
        module = importlib.import_module("multigraphrag")
        assert module.VALUE == "committed"
        exported = Path(module.__file__)
        assert metadata["source_commit"] == commit
        assert metadata["source_mode"] == "pinned-git-export"
        assert "uv.lock" in metadata["source_files"]
        first_hash = metadata["source_sha256"]
    assert sys.path == old_path
    assert "multigraphrag" not in sys.modules
    assert not exported.exists()
    with reference_source(repo, commit) as metadata:
        assert metadata["source_sha256"] == first_hash
    assert "dirty" in (repo / "src/multigraphrag/__init__.py").read_text()


def test_reference_rejects_cached_modules_and_non_full_revision(reference, monkeypatch):
    repo, commit = reference
    with pytest.raises(ValueError, match="40-character"):
        with reference_source(repo, "HEAD"):
            pass
    monkeypatch.setitem(sys.modules, "multigraphrag", SimpleNamespace())
    with pytest.raises(ValueError, match="already imported"):
        with reference_source(repo, commit):
            pass


def async_driver(query_type="r", values=()):
    driver = MagicMock()
    session = driver.session.return_value.__aenter__.return_value
    explain = SimpleNamespace(
        consume=AsyncMock(return_value=SimpleNamespace(query_type=query_type))
    )
    session.run = AsyncMock(return_value=explain)
    manager = MagicMock()
    tx = manager.__aenter__.return_value
    session.begin_transaction = AsyncMock(return_value=manager)
    cursor = MagicMock()
    cursor.keys.return_value = ["value", "value"]
    cursor.__aiter__.return_value = [SimpleNamespace(values=lambda v=v: list(v)) for v in values]
    tx.run = AsyncMock(return_value=cursor)
    tx.rollback = AsyncMock()
    return driver, session, tx


@pytest.mark.parametrize("query_type", ["w", "rw", "s", None])
def test_async_guard_rejects_non_reads(query_type):
    driver, session, tx = async_driver(query_type)
    result = asyncio.run(execute_read_only_async(driver, "company", "CREATE ()", 30))
    assert result["failure_class"] == "non_read_query_rejected"
    session.begin_transaction.assert_not_called()
    tx.run.assert_not_called()


def test_async_guard_keeps_duplicate_columns_parameters_and_timeout():
    driver, session, tx = async_driver(values=[(1, 2), (3, 4)])
    result = asyncio.run(
        execute_read_only_async(driver, "company", "RETURN $x, 2", 7, parameters={"x": 1})
    )
    assert result["ok"] and result["columns"] == ["value", "value"]
    assert result["rows"] == [[1, 2], [3, 4]]
    assert driver.session.call_args.kwargs["database"] == "company"
    assert session.run.call_args.args[0].timeout == 7
    assert session.run.call_args.kwargs["parameters"] == {"x": 1}
    session.begin_transaction.assert_awaited_once_with(timeout=7)
    tx.run.assert_awaited_once_with("RETURN $x, 2", parameters={"x": 1})
    tx.rollback.assert_awaited_once()
    tx.commit.assert_not_called()


def test_async_row_cap_never_scores_partial_rows():
    driver, _, tx = async_driver(values=[(1, 2), (3, 4)])
    result = asyncio.run(execute_read_only_async(driver, "neo4j", "RETURN 1", 30, 1))
    assert result["rows"] == [] and result["failure_class"] == "result_row_limit"
    tx.rollback.assert_awaited_once()


def test_async_cancellation_rolls_back_and_propagates():
    driver, _, tx = async_driver()
    tx.run.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(execute_read_only_async(driver, "neo4j", "RETURN 1", 30))
    tx.rollback.assert_awaited_once()


@pytest.mark.parametrize("timeout,rows", [(0, 2), (float("inf"), 2), (1, 0), (1, True)])
def test_invalid_bounds_never_contact_database(timeout, rows):
    driver = MagicMock()
    result = asyncio.run(execute_read_only_async(driver, "neo4j", "RETURN 1", timeout, rows))
    assert not result["ok"]
    driver.session.assert_not_called()


def test_final_scoring_uses_same_guard_and_full_rows():
    driver, _, _ = async_driver(values=[(1, 2), (3, 4)])
    args = SimpleNamespace(database="company", query_timeout=30, max_score_rows=10)
    graph = SimpleNamespace(_driver=driver)
    match, rows, error = asyncio.run(_score_cypher(graph, "RETURN 1", [[3, 4], [1, 2]], args))
    assert match and error is None and len(rows) == 2


@pytest.mark.parametrize("name", profile_names())
def test_structured_baseline_and_native_ana_share_profile_payload(monkeypatch, name):
    monkeypatch.setenv("TEST_LLM_KEY", "test-only")
    values, _ = load_profile(name)
    provider = openai_compatible.OpenAICompatibleProvider(
        base_url="https://example.invalid",
        model="test/model",
        api_key_env="TEST_LLM_KEY",
        api_key_file=None,
        settings=LLMCallSettings(**values),
    )
    sent = []

    def handle(request):
        sent.append(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]}
        )

    client_type = httpx.Client
    with patch.object(
        openai_compatible.httpx,
        "Client",
        side_effect=lambda **kw: client_type(transport=httpx.MockTransport(handle)),
    ):
        provider.chat([], tools=[])
        provider.chat([], response_format={"type": "json_object"})
    native, baseline = sent
    assert native.pop("tools") == [] and native.pop("tool_choice") == "auto"
    assert baseline.pop("response_format") == {"type": "json_object"}
    assert native == baseline
    assert baseline["max_tokens"] == 16000


def test_profile_requires_frozen_source_before_io():
    with pytest.raises(ValueError, match="requires --reference-commit"):
        asyncio.run(_run(SimpleNamespace(profile="temp0-none", reference_commit=None)))


@pytest.mark.parametrize(
    "shared,resume,check", [(False, False, False), (True, True, False), (True, False, True)]
)
def test_block_verification_requires_fresh_shared_run_before_io(shared, resume, check):
    with pytest.raises(ValueError, match="does not support --resume/--check-only"):
        asyncio.run(
            _run(
                SimpleNamespace(
                    verify_graph_block=True,
                    shared_preflight=shared,
                    resume=resume,
                    check_only=check,
                )
            )
        )


@pytest.mark.parametrize("mode", ["single_retrieval", "agentic_retrieval"])
@pytest.mark.parametrize("profile,pin", [(None, None), (None, "a" * 40), ("temp0-none", None)])
def test_retrieval_variants_require_profile_and_pin_before_io(mode, profile, pin):
    with pytest.raises(ValueError, match="Retrieval-only modes require"):
        asyncio.run(_run(SimpleNamespace(mode=mode, profile=profile, reference_commit=pin)))


def test_unknown_reference_mode_is_rejected_before_importing_reference():
    from agent_native_graph.research.reference_adapters import build_profile_runner

    with pytest.raises(ValueError, match="Unknown reference mode"):
        build_profile_runner("typo", None, None, None, None)


@pytest.mark.parametrize(
    "mode", ["direct", "single", "agentic", "single_retrieval", "agentic_retrieval"]
)
def test_dispatch_passes_only_question_and_schema_not_gold_fields(mode):
    runner = SimpleNamespace(generate=AsyncMock(), ask=AsyncMock())
    task = {
        "qid": "private-qid",
        "nl_question": "Visible question",
        "gold_cypher": "HIDDEN_GOLD_SENTINEL",
        "answer_json": "HIDDEN_ANSWER_SENTINEL",
    }
    asyncio.run(_generate_answer(runner, task, "Visible schema", mode))
    if mode == "direct":
        runner.generate.assert_awaited_once_with(
            question="Visible question", schema_text="Visible schema"
        )
        runner.ask.assert_not_called()
    elif mode.startswith("agentic"):
        runner.ask.assert_awaited_once_with("Visible question", schema_text="Visible schema")
        runner.generate.assert_not_called()
    else:
        runner.ask.assert_awaited_once_with("Visible question", "Visible schema")
        runner.generate.assert_not_called()


@pytest.mark.parametrize("mode", ["single_retrieval", "agentic_retrieval"])
def test_unvalidated_reference_revision_is_rejected_for_retrieval_variants(mode):
    with pytest.raises(ValueError, match="validated only against"):
        asyncio.run(
            _run(SimpleNamespace(mode=mode, profile="temp0-none", reference_commit="a" * 40))
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("nl_question", "different question"),
        ("gold_cypher", "RETURN 2"),
        ("answer_json", "[[2]]"),
        ("graph", "other"),
    ],
)
def test_full_task_validation_detects_drift_with_same_qid(field, value):
    task = {
        "qid": "same",
        "graph": "company",
        "nl_question": "Q",
        "gold_cypher": "RETURN 1",
        "answer_json": "[[1]]",
    }
    reference = SimpleNamespace(**task)
    task[field] = value
    with pytest.raises(ValueError, match="content differs"):
        validate_task_contents([task], [reference])


def test_pinned_export_rejects_symlinks(reference):
    repo, _ = reference
    (repo / "src/multigraphrag/link.py").symlink_to("/tmp/outside.py")
    subprocess.check_call(["git", "-C", str(repo), "add", "."])
    subprocess.check_call(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "link",
        ]
    )
    commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"]).decode().strip()
    with pytest.raises(ValueError, match="Unsafe"):
        with reference_source(repo, commit):
            pass


def test_profile_client_logs_native_reference_interface(monkeypatch):
    # A minimal reference contract avoids requiring the external project's dependencies.
    class Base:
        pass

    class Structured:
        @staticmethod
        def _parse_structured(content, model):
            return model(json.loads(content))

    monkeypatch.setitem(sys.modules, "multigraphrag.llm.base", SimpleNamespace(LLMClient=Base))
    monkeypatch.setitem(
        sys.modules, "multigraphrag.llm.vllm_client", SimpleNamespace(VllmClient=Structured)
    )
    provider = SimpleNamespace(
        _model="test/model", achat=AsyncMock(return_value={"content": '{"n": 1}'})
    )
    logger = MagicMock()

    class Model(dict):
        @classmethod
        def model_json_schema(cls):
            return {"type": "object"}

    client = profile_client(provider, role="query_generator", logger=logger, concurrency=3)
    result = asyncio.run(
        client.complete_structured(system_prompt="S", user_prompt="Q", response_model=Model)
    )
    assert result == {"n": 1} and client.max_concurrency == 3
    assert provider.achat.call_args.kwargs["response_format"]["json_schema"]["strict"] is True
    assert logger.log.call_args.kwargs["agent"] == "query_generator"
    assert logger.log.call_args.kwargs["error"] is None
    provider.achat.side_effect = RuntimeError("failure")
    with pytest.raises(RuntimeError):
        asyncio.run(client.complete(system_prompt="S", user_prompt="Q"))
    assert logger.log.call_args.kwargs["error"] == "RuntimeError"
