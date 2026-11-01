"""Connection ownership, retry bounds and cancellation with unchanged model payloads."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from unittest.mock import AsyncMock

import httpx
import pytest

from agent_native_graph.application.metrics import classify_failure
from agent_native_graph.llm_providers import openai_compatible as module
from agent_native_graph.llm_providers.accounting import account_requests
from agent_native_graph.llm_providers.settings import LLMCallSettings


def response():
    return {
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        "usage": {"total_tokens": 3},
    }


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("TRANSPORT_TEST_KEY", "test-only")

    def make(**settings):
        return module.OpenAICompatibleProvider(
            base_url="https://example.invalid",
            model="test",
            api_key_env="TRANSPORT_TEST_KEY",
            api_key_file=None,
            settings=LLMCallSettings(**settings),
        )

    return make


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("status", [None, 400, 401, 403, 422, 429, 503])
def test_retry_attempts_have_no_final_sleep_and_use_one_client(
    monkeypatch, provider, asynchronous, status
):
    clients, requests, waits = [], [], []

    def handle(request):
        requests.append(json.loads(request.content))
        if status is None:
            raise httpx.ReadTimeout("test timeout", request=request)
        return httpx.Response(status)

    client_class = httpx.AsyncClient if asynchronous else httpx.Client

    def make(**kwargs):
        client = client_class(transport=httpx.MockTransport(handle), **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(module.httpx, "AsyncClient" if asynchronous else "Client", make)
    monkeypatch.setattr(module.time, "sleep", waits.append)
    async_sleep = AsyncMock(side_effect=waits.append)
    monkeypatch.setattr(module.asyncio, "sleep", async_sleep)
    llm = provider()
    with (
        account_requests() as ledger,
        pytest.raises(httpx.ReadTimeout if status is None else httpx.HTTPStatusError),
    ):
        if asynchronous:
            asyncio.run(llm.achat([], tools=[]))
        else:
            llm.chat([], tools=[])
    transient = status in (None, 429, 503)
    assert len(requests) == (3 if transient else 1)
    assert waits == ([30.0, 30.0] if status == 429 else [2.0, 4.0] if transient else [])
    assert len(clients) == 1 and clients[0].is_closed
    assert all(payload == requests[0] for payload in requests)
    summary = ledger.snapshot()["summary"]
    assert summary["http_attempts"] == len(requests)
    assert summary["http_retry_attempts"] == len(requests) - 1
    assert summary["failed_logical_calls"] == 1 and summary["requests_settled"]


def test_sync_scope_shares_pool_between_workers_and_closes_on_exception(monkeypatch, provider):
    client_class = httpx.Client
    clients = []

    def make(**kwargs):
        client = client_class(
            transport=httpx.MockTransport(lambda req: httpx.Response(200, json=response())),
            **kwargs,
        )
        clients.append(client)
        return client

    monkeypatch.setattr(module.httpx, "Client", make)
    llm = provider()
    with pytest.raises(RuntimeError, match="test failure"):
        with llm:
            with ThreadPoolExecutor(max_workers=3) as pool:
                results = list(pool.map(lambda _: llm.chat([])["content"], range(9)))
            assert results == ["ok"] * 9 and len(clients) == 1
            assert not clients[0].is_closed
            raise RuntimeError("test failure")
    assert clients[0].is_closed
    llm.close()


def test_async_scope_survives_one_cancelled_request_and_closes_pool(monkeypatch, provider):
    client_class = httpx.AsyncClient
    clients = []

    async def scenario():
        started, stopped = asyncio.Event(), asyncio.Event()

        async def handle(request):
            if json.loads(request.content)["messages"]:
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    stopped.set()
            return httpx.Response(200, json=response())

        def make(**kwargs):
            client = client_class(transport=httpx.MockTransport(handle), **kwargs)
            clients.append(client)
            return client

        monkeypatch.setattr(module.httpx, "AsyncClient", make)
        llm = provider()
        with account_requests() as ledger:
            async with llm:
                slow = asyncio.create_task(llm.achat([{"role": "user", "content": "slow"}]))
                await asyncio.wait_for(started.wait(), 1)
                slow.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await slow
                assert stopped.is_set() and not clients[0].is_closed
                answers = await asyncio.gather(llm.achat([]), llm.achat([]))
                assert [a["content"] for a in answers] == ["ok", "ok"]
                assert len(clients) == 1
        assert clients[0].is_closed and ledger.snapshot()["summary"]["requests_settled"]
        await llm.aclose()

    asyncio.run(scenario())


def test_async_pool_closes_when_its_workload_raises(monkeypatch, provider):
    client_class = httpx.AsyncClient
    clients = []

    def make(**kwargs):
        client = client_class(
            transport=httpx.MockTransport(lambda req: httpx.Response(200, json=response())),
            **kwargs,
        )
        clients.append(client)
        return client

    monkeypatch.setattr(module.httpx, "AsyncClient", make)

    async def scenario():
        llm = provider()
        with pytest.raises(ValueError, match="test failure"):
            async with llm:
                assert (await llm.achat([]))["content"] == "ok"
                raise ValueError("test failure")
        assert clients[0].is_closed

    asyncio.run(scenario())


def test_async_pool_cannot_be_used_or_closed_from_another_loop(monkeypatch, provider):
    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        module.httpx,
        "AsyncClient",
        lambda **kwargs: client_class(
            transport=httpx.MockTransport(lambda req: httpx.Response(200, json=response())),
            **kwargs,
        ),
    )
    llm = provider()
    owner = asyncio.new_event_loop()
    try:
        owner.run_until_complete(llm.__aenter__())
        with pytest.raises(RuntimeError, match="owning event loop"):
            asyncio.run(llm.achat([]))
        with pytest.raises(RuntimeError, match="owning event loop"):
            asyncio.run(llm.aclose())
        owner.run_until_complete(llm.aclose())
        assert llm._async_client is None
    finally:
        owner.close()


@pytest.mark.parametrize("field", ["connect_timeout_s", "write_timeout_s", "pool_timeout_s"])
@pytest.mark.parametrize("value", [0, -1, True, float("nan"), float("inf")])
def test_phase_timeouts_are_positive_and_finite(field, value):
    with pytest.raises(ValueError, match=field):
        LLMCallSettings(**{field: value})


def test_phase_timeouts_do_not_enter_model_payload(provider):
    llm = provider(timeout_s=120, connect_timeout_s=5, write_timeout_s=10, pool_timeout_s=3)
    timeout = llm._timeout()
    assert (timeout.read, timeout.connect, timeout.write, timeout.pool) == (120, 5, 10, 3)
    assert llm._payload([], [], "auto", None) == provider()._payload([], [], "auto", None)


def test_settings_preserve_all_existing_positional_arguments():
    settings = LLMCallSettings(
        0.5,
        16000,
        0.9,
        17,
        0.1,
        0.2,
        "END",
        True,
        "medium",
        False,
        "auto",
        120,
        5,
        4,
        45,
        connect_timeout_s=3,
        write_timeout_s=6,
        pool_timeout_s=2,
    )
    assert settings.temperature == 0.5 and settings.max_tokens == 16000
    assert settings.top_p == 0.9 and settings.seed == 17
    assert settings.presence_penalty == 0.1 and settings.frequency_penalty == 0.2
    assert settings.stop == "END" and settings.enable_thinking
    assert settings.thinking_effort == "medium" and not settings.retry_low_effort_on_length
    assert settings.tool_choice == "auto" and settings.timeout_s == 120
    assert settings.max_attempts == 5 and settings.retry_base_s == 4
    assert settings.rate_limit_retry_s == 45
    assert (settings.connect_timeout_s, settings.write_timeout_s, settings.pool_timeout_s) == (
        3,
        6,
        2,
    )


def test_settings_positional_retry_count_does_not_become_connection_timeout():
    settings = LLMCallSettings(
        0.0, 16000, None, None, None, None, None, False, None, True, "auto", 60.0, 5
    )
    assert settings.max_attempts == 5 and settings.connect_timeout_s is None


@pytest.mark.parametrize("asynchronous", [False, True])
def test_phase_timeouts_reach_the_http_request(monkeypatch, provider, asynchronous):
    timeouts = []

    def handle(request):
        timeouts.append(request.extensions["timeout"])
        return httpx.Response(200, json=response())

    client_class = httpx.AsyncClient if asynchronous else httpx.Client
    monkeypatch.setattr(
        module.httpx,
        "AsyncClient" if asynchronous else "Client",
        lambda **kwargs: client_class(transport=httpx.MockTransport(handle), **kwargs),
    )
    llm = provider(timeout_s=120, connect_timeout_s=5, write_timeout_s=10, pool_timeout_s=3)
    if asynchronous:
        asyncio.run(llm.achat([]))
    else:
        llm.chat([])
    assert timeouts == [{"read": 120, "connect": 5, "write": 10, "pool": 3}]


@pytest.mark.parametrize(
    "error,kind",
    [
        ("ReadTimeout: timed out", "llm_timeout"),
        ("ConnectTimeout: timed out", "llm_timeout"),
        ("PoolTimeout: timed out", "llm_timeout"),
        ("HTTPStatusError: 503", "llm_transport_error"),
        ("ConnectError: unavailable", "llm_transport_error"),
        ("ClientError: TransactionTimedOut", "backend_timeout"),
    ],
)
def test_transport_failures_are_distinct_from_graph_timeouts(error, kind):
    assert classify_failure({"matches_answer_json": False, "ok": False, "error": error}) == kind
    assert classify_failure({"matches_answer_json": True, "ok": True, "error": error}) is None


@pytest.mark.parametrize("asynchronous", [False, True])
def test_managed_pool_reuses_a_real_http_connection(monkeypatch, provider, asynchronous):
    ports = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            ports.append(self.client_address[1])
            body = json.dumps(response()).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    llm = provider()
    llm._url = f"http://127.0.0.1:{server.server_port}/v1/chat/completions"
    try:
        if asynchronous:

            async def run():
                async with llm:
                    for _ in range(3):
                        assert (await llm.achat([]))["content"] == "ok"

            asyncio.run(run())
        else:
            with llm:
                for _ in range(3):
                    assert llm.chat([])["content"] == "ok"
        assert len(ports) == 3 and len(set(ports)) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
