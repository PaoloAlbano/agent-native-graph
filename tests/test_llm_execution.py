"""Cancellable HTTP and deadlines must leave settled metrics and unchanged payloads."""

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import httpx
import pytest

from agent_native_graph.application import neo4j_benchmark
from agent_native_graph.application.run_config import load_profile, profile_names
from agent_native_graph.llm_providers import openai_compatible
from agent_native_graph.llm_providers.accounting import account_requests
from agent_native_graph.llm_providers.execution import (
    Deadline,
    TaskTimeoutError,
    deadline_scope,
    question_requests,
)
from agent_native_graph.llm_providers.settings import LLMCallSettings


def response(finish="stop", usage=None):
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "ok"}, "finish_reason": finish}],
            "usage": usage or {"total_tokens": 3},
        },
    )


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("TEST_EXECUTION_KEY", "test-only")

    def make(settings=None):
        return openai_compatible.OpenAICompatibleProvider(
            base_url="https://example.invalid",
            model="test/model",
            api_key_env="TEST_EXECUTION_KEY",
            api_key_file=None,
            settings=settings or LLMCallSettings(),
        )

    return make


@pytest.fixture
def async_transport(monkeypatch):
    client_type = httpx.AsyncClient
    clients = []

    def install(handle):
        class FakeClient(client_type):
            def __init__(self, **kwargs):
                super().__init__(transport=httpx.MockTransport(handle))
                clients.append(self)

        monkeypatch.setattr(openai_compatible.httpx, "AsyncClient", FakeClient)
        return clients

    return install


@pytest.mark.parametrize("profile", profile_names())
def test_sync_and_async_payloads_and_results_are_identical(
    monkeypatch, provider, async_transport, profile
):
    sent = []

    def handle(request):
        sent.append(json.loads(request.content))
        return response()

    async_transport(handle)
    client_type = httpx.Client
    monkeypatch.setattr(
        openai_compatible.httpx,
        "Client",
        lambda **kw: client_type(transport=httpx.MockTransport(handle)),
    )
    settings, _ = load_profile(profile)
    llm = provider(LLMCallSettings(**settings))
    sync = llm.chat([], tools=[], response_format={"type": "json_object"})
    asynchronous = asyncio.run(llm.achat([], tools=[], response_format={"type": "json_object"}))
    assert sent[0] == sent[1]
    assert sync["content"] == asynchronous["content"] == "ok"
    sync["__chat_meta"].pop("request_accounting")
    asynchronous["__chat_meta"].pop("request_accounting")
    assert sync == asynchronous


def test_async_429_then_length_fallback_preserves_policy(provider, async_transport):
    sent = []

    def handle(request):
        sent.append(json.loads(request.content))
        if len(sent) == 1:
            return httpx.Response(429)
        return response("length" if len(sent) == 2 else "stop")

    clients = async_transport(handle)
    llm = provider(
        LLMCallSettings(enable_thinking=True, thinking_effort="medium", rate_limit_retry_s=0)
    )
    result = asyncio.run(llm.achat([]))
    summary = result["__chat_meta"]["request_accounting"]["summary"]
    assert len(sent) == 3 and sent[0] == sent[1]
    assert sent[2]["reasoning_effort"] == "low"
    assert summary["http_attempts"] == 3 and summary["observed_completion_responses"] == 2
    assert all(client.is_closed for client in clients)


def test_cancelling_http_closes_client_before_snapshot(provider, async_transport):
    started, stopped = asyncio.Event(), asyncio.Event()

    async def handle(request):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    clients = async_transport(handle)
    llm = provider()

    async def run():
        with account_requests() as ledger:
            async with question_requests():
                task = asyncio.create_task(llm.achat([]))
                await asyncio.wait_for(started.wait(), 1)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
        return ledger.snapshot()

    snapshot = asyncio.run(run())
    assert stopped.is_set() and all(client.is_closed for client in clients)
    assert snapshot["summary"]["requests_settled"]
    assert snapshot["attempts"][0]["error_type"] == "CancelledError"
    assert snapshot["summary"]["http_attempts"] == 1


@pytest.mark.parametrize("phase", ["http", "retry_wait", "fallback"])
def test_deadline_interrupts_http_retry_waits_and_fallback(provider, async_transport, phase):
    sent = []

    async def handle(request):
        sent.append(json.loads(request.content))
        if phase == "retry_wait":
            return httpx.Response(429)
        if phase == "fallback" and len(sent) == 1:
            return response("length")
        await asyncio.Event().wait()

    clients = async_transport(handle)
    llm = provider(LLMCallSettings(enable_thinking=True, thinking_effort="medium"))

    async def run():
        with account_requests() as ledger, deadline_scope(Deadline(0.05)):
            with pytest.raises(TaskTimeoutError):
                await llm.achat([])
        return ledger.snapshot()

    started = time.monotonic()
    snapshot = asyncio.run(run())
    assert time.monotonic() - started < 2
    assert len(sent) == (2 if phase == "fallback" else 1)
    assert all(client.is_closed for client in clients)
    assert snapshot["summary"]["requests_settled"]
    assert snapshot["calls"][0]["error_type"] == "TaskTimeoutError"
    if phase == "fallback":
        assert snapshot["summary"]["observed_usage_totals"] == {"total_tokens": 3}


def test_question_failure_cancels_active_siblings_but_not_other_questions(
    provider, async_transport
):
    started, stopped = asyncio.Event(), asyncio.Event()

    async def handle(request):
        messages = json.loads(request.content)["messages"]
        if messages:
            return response()
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    clients = async_transport(handle)
    llm = provider()

    async def failing_question():
        with account_requests() as ledger:
            with pytest.raises(ValueError):
                async with question_requests():
                    asyncio.create_task(llm.achat([]))
                    await started.wait()
                    raise ValueError("structured parse failure")
        return ledger.snapshot()

    async def successful_question():
        await started.wait()
        with account_requests() as ledger:
            async with question_requests():
                await llm.achat([{"role": "user", "content": "other question"}])
        return ledger.snapshot()

    async def run():
        return await asyncio.wait_for(asyncio.gather(failing_question(), successful_question()), 2)

    failed, succeeded = asyncio.run(run())
    assert stopped.is_set() and all(client.is_closed for client in clients)
    assert failed["summary"]["failed_logical_calls"] == 1 and failed["summary"]["requests_settled"]
    assert succeeded["summary"]["failed_logical_calls"] == 0


def test_expired_deadline_sends_no_request(provider, async_transport):
    sent = []
    async_transport(lambda request: sent.append(request))
    deadline = Deadline(0.001)
    time.sleep(0.002)

    async def run():
        with account_requests() as ledger, deadline_scope(deadline):
            with pytest.raises(TaskTimeoutError):
                await provider().achat([])
        return ledger.snapshot()

    assert asyncio.run(run())["summary"]["http_attempts"] == 0
    assert not sent


@pytest.mark.parametrize("termination", ["cancel", "deadline"])
def test_real_local_http_connection_closes_on_termination(provider, monkeypatch, termination):
    """Exercise HTTPX/httpcore cancellation on a socket, not only a mock handler."""
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")

    async def run():
        started, disconnected = asyncio.Event(), asyncio.Event()

        async def serve(reader, writer):
            try:
                headers = await reader.readuntil(b"\r\n\r\n")
                length = next(
                    int(line.split(b":", 1)[1])
                    for line in headers.split(b"\r\n")
                    if line.lower().startswith(b"content-length:")
                )
                await reader.readexactly(length)
                started.set()
                await reader.read()
            finally:
                disconnected.set()
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(serve, "127.0.0.1", 0)
        llm = provider()
        llm._url = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}/v1/chat/completions"
        try:
            async with server:
                with (
                    account_requests() as ledger,
                    deadline_scope(Deadline(0.5) if termination == "deadline" else None),
                ):
                    task = asyncio.create_task(llm.achat([]))
                    await asyncio.wait_for(started.wait(), timeout=2)
                    if termination == "cancel":
                        task.cancel()
                    with pytest.raises(
                        asyncio.CancelledError if termination == "cancel" else TaskTimeoutError
                    ):
                        await task
                    await asyncio.wait_for(disconnected.wait(), timeout=1)
                return ledger.snapshot()
        finally:
            server.close()
            await server.wait_closed()

    snapshot = asyncio.run(run())
    assert snapshot["summary"]["requests_settled"]
    assert snapshot["summary"]["http_attempts"] == 1


def test_ana_worker_deadlines_are_independent_at_concurrency_two(
    monkeypatch, provider, async_transport
):
    from agent_native_graph.backends.neo4j import backend as backend_module

    backends = []

    def backend(*args, **kwargs):
        instance = SimpleNamespace(last_fetch=None, closed=False)

        def call(tool, args):
            instance.last_fetch = [[1]]
            return {"rows": [[1]], "returned_count": 1}

        instance.call = call
        instance.close = lambda: setattr(instance, "closed", True)
        backends.append(instance)
        return instance

    monkeypatch.setattr(backend_module, "Neo4jGraphBackend", backend)

    async def handle(request):
        await asyncio.sleep(0.15)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {"name": "fetch", "arguments": '{"from":"h1"}'},
                                }
                            ]
                        },
                    }
                ]
            },
        )

    clients = async_transport(handle)
    llm = provider()

    def run(timeout):
        return neo4j_benchmark._run_agent_task(
            {
                "qid": str(timeout),
                "nl_question": "Q",
                "gold_cypher": "RETURN 1",
                "answer_json": "[[1]]",
            },
            llm=llm,
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
            evaluation_fetch_all_pages=False,
            enable_runner_guardrails=False,
            task_timeout_s=timeout,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        early = executor.submit(run, 0.05)
        late = executor.submit(run, 2)
        expired, success = early.result(), late.result()
    assert expired["failure_class"] == "task_timeout" and not expired["ok"]
    assert success["ok"] and success["matches_answer_json"]
    assert all(
        row["request_accounting"]["summary"]["requests_settled"] for row in (expired, success)
    )
    assert all(client.is_closed for client in clients) and all(b.closed for b in backends)


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan"), True])
def test_invalid_deadlines_are_rejected(value):
    with pytest.raises(ValueError):
        Deadline(value)
