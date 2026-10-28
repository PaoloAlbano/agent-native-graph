"""Accounting is observational: preserve payloads, responses, errors and retries."""

import asyncio
import json
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from agent_native_graph.application import neo4j_benchmark
from agent_native_graph.llm_providers import openai_compatible
from agent_native_graph.llm_providers.accounting import (
    RequestAccounting,
    account_requests,
    request_role,
    summarize_ledgers,
)
from agent_native_graph.llm_providers.settings import LLMCallSettings
from agent_native_graph.research.archive_result import _summary


def completion(finish="stop", usage=None, message=None):
    result = {"choices": [{"message": message or {"content": "ok"}, "finish_reason": finish}]}
    if usage is not None:
        result["usage"] = usage
    return result


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("TEST_ACCOUNTING_KEY", "secret-not-for-ledger")

    def make(**settings):
        return openai_compatible.OpenAICompatibleProvider(
            base_url="https://example.invalid",
            model="test/model",
            api_key_env="TEST_ACCOUNTING_KEY",
            api_key_file=None,
            settings=LLMCallSettings(retry_base_s=0, rate_limit_retry_s=0, **settings),
        )

    return make


@pytest.fixture
def transport():
    client_type = httpx.Client

    def install(handler):
        return patch.object(
            openai_compatible.httpx,
            "Client",
            side_effect=lambda **kw: client_type(transport=httpx.MockTransport(handler)),
        )

    return install


def test_single_call_counts_usage_once_and_retains_no_sensitive_payload(provider, transport):
    llm = provider()
    usage = {
        "prompt_tokens": 10,
        "completion_tokens": 2,
        "total_tokens": 12,
        "completion_tokens_details": {"reasoning_tokens": 1},
        "unexpected": "private",
    }
    with transport(lambda req: httpx.Response(200, json=completion(usage=usage))):
        with account_requests() as ledger:
            message = llm.chat([{"role": "user", "content": "private question"}])
    snapshot = ledger.snapshot()
    summary = snapshot["summary"]
    assert summary["logical_calls"] == summary["http_attempts"] == 1
    assert summary["observed_usage_totals"] == {
        "prompt_tokens": 10,
        "completion_tokens": 2,
        "total_tokens": 12,
    }
    assert summary["usage_field_coverage"]["total_tokens"] == 1
    assert summary["observed_token_details_totals"] == {
        "completion_tokens_details.reasoning_tokens": 1
    }
    assert summary["requests_settled"]
    assert message["content"] == "ok"
    assert message["__chat_meta"]["request_accounting"] == snapshot
    assert "private" not in json.dumps(snapshot) and "secret-not-for-ledger" not in json.dumps(
        snapshot
    )
    assert "example.invalid" not in json.dumps(snapshot)


def test_length_fallback_counts_both_generations_without_double_counting(provider, transport):
    sent = []

    def handle(request):
        sent.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=completion(
                "length" if len(sent) == 1 else "stop",
                {"completion_tokens": 7 if len(sent) == 1 else 3},
            ),
        )

    with transport(handle), account_requests() as ledger:
        provider(enable_thinking=True, thinking_effort="medium").chat([])
    summary = ledger.snapshot()["summary"]
    assert summary["logical_calls"] == 1 and summary["http_attempts"] == 2
    assert summary["low_effort_http_attempts"] == 1 and summary["http_retry_attempts"] == 0
    assert summary["observed_completion_responses"] == 2
    assert summary["observed_usage_totals"] == {"completion_tokens": 10}
    assert summary["finish_reasons"] == {"length": 1, "stop": 1}
    assert sent[0]["reasoning_effort"] == "medium" and sent[1]["reasoning_effort"] == "low"
    assert all(p["max_tokens"] == 16000 for p in sent)


def test_fallback_failure_retains_usage_from_every_discarded_initial_response(provider, transport):
    count = 0

    def handle(request):
        nonlocal count
        count += 1
        if count == 2:
            return httpx.Response(429)
        return httpx.Response(
            200, json=completion("stop" if count == 4 else "length", {"total_tokens": count})
        )

    with transport(handle), account_requests() as ledger:
        provider(enable_thinking=True, thinking_effort="medium").chat([])
    summary = ledger.snapshot()["summary"]
    assert summary["http_attempts"] == 4 and summary["logical_calls"] == 1
    assert summary["low_effort_http_attempts"] == 2 and summary["http_retry_attempts"] == 2
    assert summary["observed_usage_totals"] == {"total_tokens": 8}
    assert summary["attempts_with_usage"] == 3 and summary["attempts_without_usage"] == 1
    assert summary["http_status_counts"] == {"200": 3, "429": 1}


@pytest.mark.parametrize("status", [429, 500, 401])
def test_exhausted_http_errors_are_observed_without_changing_existing_retry_policy(
    provider, transport, status
):
    with transport(lambda req: httpx.Response(status)), account_requests() as ledger:
        with pytest.raises(httpx.HTTPStatusError):
            provider(max_attempts=2).chat([])
    summary = ledger.snapshot()["summary"]
    assert summary["http_attempts"] == 2 and summary["failed_logical_calls"] == 1
    assert summary["failed_http_attempts"] == 2 and summary["http_retry_attempts"] == 1
    assert summary["observed_usage_totals"] == {} and summary["usage_field_coverage"] == {}
    assert summary["attempts_without_usage"] == 2 and summary["requests_settled"]


def test_timeout_then_success_and_unknown_usage(provider, transport):
    count = 0

    def handle(request):
        nonlocal count
        count += 1
        if count == 1:
            raise httpx.ReadTimeout("private endpoint must not enter ledger", request=request)
        return httpx.Response(200, json=completion())

    with transport(handle), account_requests() as ledger:
        provider().chat([])
    snapshot = ledger.snapshot()
    assert snapshot["summary"]["http_attempts"] == 2
    assert snapshot["summary"]["observed_usage_totals"] == {}
    assert snapshot["attempts"][0]["error_type"] == "ReadTimeout"
    assert "private endpoint" not in json.dumps(snapshot)


def test_malformed_response_is_counted_before_provider_raises(provider, transport):
    with (
        transport(lambda req: httpx.Response(200, content=b"not json")),
        account_requests() as ledger,
    ):
        with pytest.raises(json.JSONDecodeError):
            provider().chat([])
    assert ledger.snapshot()["summary"]["http_attempts"] == 1
    assert ledger.snapshot()["summary"]["failed_logical_calls"] == 1


def test_role_context_propagates_to_worker_threads_and_questions_stay_isolated(provider, transport):
    llm = provider()

    async def question():
        with account_requests() as ledger:

            async def role(name):
                with request_role(name):
                    await asyncio.to_thread(llm.chat, [])

            await asyncio.gather(role("generator"), role("evaluator"))
        return ledger.snapshot()

    async def run():
        return await asyncio.gather(question(), question())

    with transport(lambda req: httpx.Response(200, json=completion())):
        first, second = asyncio.run(run())
    assert (
        first["summary"]["roles"] == second["summary"]["roles"] == {"generator": 1, "evaluator": 1}
    )
    assert {c["id"] for c in first["calls"]}.isdisjoint(c["id"] for c in second["calls"])


def test_snapshot_reports_pending_work_and_does_not_mutate_after_capture():
    ledger = RequestAccounting()
    call = ledger.start_call("model")
    ledger.start_attempt(call, "initial")
    snapshot = ledger.snapshot()
    assert not snapshot["summary"]["requests_settled"]
    assert snapshot["summary"]["pending_http_attempts"] == 1
    ledger.update(call, status="ok")
    assert snapshot["calls"][0]["status"] == "pending"


def test_cancelled_await_does_not_claim_blocking_http_has_finished(provider, transport):
    started, release = Event(), Event()

    def handle(request):
        started.set()
        if not release.wait(timeout=3):
            raise RuntimeError("test did not release worker")
        return httpx.Response(200, json=completion())

    llm = provider()

    async def run():
        with account_requests() as ledger:
            task = asyncio.create_task(asyncio.to_thread(llm.chat, []))
            try:
                assert await asyncio.to_thread(started.wait, 2)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                pending = ledger.snapshot()
            finally:
                release.set()

            async def settled():
                while not ledger.snapshot()["summary"]["requests_settled"]:
                    await asyncio.sleep(0.001)

            await asyncio.wait_for(settled(), timeout=2)
        return pending, ledger.snapshot()

    with transport(handle):
        pending, final = asyncio.run(run())
    assert pending["summary"]["pending_http_attempts"] == 1
    assert not pending["summary"]["requests_settled"]
    assert final["summary"]["requests_settled"]


def test_legacy_and_new_archival_summaries_remain_distinguishable(provider, transport):
    assert summarize_ledgers([None, None]) is None
    with (
        transport(lambda req: httpx.Response(200, json=completion(usage={"total_tokens": 0}))),
        account_requests() as ledger,
    ):
        provider().chat([])
    summary = summarize_ledgers([ledger.snapshot(), None])
    assert summary["instrumented_items"] == summary["uninstrumented_items"] == 1
    assert summary["observed_usage_totals"] == {"total_tokens": 0}
    assert summary["usage_field_coverage"] == {"total_tokens": 1}
    old = _summary([{"ok": True}], "old")
    assert "request_accounting" not in old
    new = _summary([{"ok": True, "request_accounting": ledger.snapshot()}], "new")
    assert new["request_accounting"]["http_attempts"] == 1


def test_native_task_keeps_failed_request_accounting_even_without_chat_metadata(
    monkeypatch, provider, transport
):
    from agent_native_graph.backends.neo4j import backend as backend_module

    backend = SimpleNamespace(last_fetch=None, close=lambda: None)
    monkeypatch.setattr(backend_module, "Neo4jGraphBackend", lambda *args, **kw: backend)
    with transport(lambda req: httpx.Response(429)):
        row = neo4j_benchmark._run_agent_task(
            {"qid": "test", "nl_question": "Q", "answer_json": "[]", "gold_cypher": "RETURN 1"},
            llm=provider(max_attempts=2),
            schema={},
            neo4j_uri="bolt://unused",
            neo4j_user="test",
            neo4j_password="test",
            neo4j_query_timeout_s=30,
            max_steps=12,
            native_tools=True,
            tool_choice="auto",
            enable_planning_tools=False,
            schema_entry="overview",
            wrapper_planning=False,
            auto_fetch_on_done=False,
            evaluation_fetch_all_pages=True,
            enable_runner_guardrails=False,
            task_timeout_s=None,
        )
    assert not row["ok"] and row["llm_call_metrics"] == []
    assert row["request_accounting"]["summary"]["failed_logical_calls"] == 1
    assert row["request_accounting"]["summary"]["http_attempts"] == 2
