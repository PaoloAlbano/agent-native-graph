import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import httpx
import pytest

from agent_native_graph.application.sessions import (
    BackendSessions,
    SessionCapacityError,
    SessionConfig,
    SessionNotFound,
)
from agent_native_graph.core.backend import AgentGraphBackend


def memory_factory(created):
    """An engine-neutral test adapter using only the common contract and store."""

    def factory(store):
        backend = MagicMock(spec=AgentGraphBackend)

        def call(tool, args):
            if tool in {"make", "count_nodes"}:
                return store.store([{"value": args["value"]}], kind="table", columns=["value"])
            if tool == "fetch":
                return {"rows": store.get(args["from"]).rows}
            raise ValueError("unknown test tool")

        backend.call.side_effect = call
        created.append((backend, store))
        return backend

    return factory


def test_sessions_isolate_handles_even_after_each_has_created_its_first_handle():
    created = []
    sessions = BackendSessions(memory_factory(created))
    a, b = sessions.create(), sessions.create()
    ha = sessions.call(a, "make", {"value": "A"})["handle"]
    hb = sessions.call(b, "make", {"value": "B"})["handle"]
    assert ha != hb
    assert sessions.call(a, "fetch", {"from": ha})["rows"] == [{"value": "A"}]
    with pytest.raises(ValueError, match="Unknown handle"):
        sessions.call(b, "fetch", {"from": ha})
    sessions.delete(a)
    assert not created[0][1].handles
    assert sessions.call(b, "fetch", {"from": hb})["rows"] == [{"value": "B"}]
    with pytest.raises(SessionNotFound):
        sessions.call(a, "fetch", {"from": ha})
    sessions.close()
    sessions.close()
    for backend, store in created:
        backend.close.assert_called_once()
        assert not store.handles


def test_idle_expiry_releases_capacity_and_closes_backend():
    now, created = [0.0], []
    sessions = BackendSessions(memory_factory(created), SessionConfig(1, 10), clock=lambda: now[0])
    token = sessions.create()
    with pytest.raises(SessionCapacityError):
        sessions.create()
    now[0] = 11
    with pytest.raises(SessionNotFound):
        sessions.call(token, "make", {"value": 1})
    created[0][0].close.assert_called_once()
    sessions.create()
    sessions.close()


def test_factory_failure_does_not_leak_capacity():
    created = []
    good = memory_factory(created)
    factory = MagicMock(side_effect=[RuntimeError("failed"), good])

    def create(store):
        result = factory(store)
        return result(store)

    sessions = BackendSessions(create, SessionConfig(max_sessions=1))
    with pytest.raises(RuntimeError, match="failed"):
        sessions.create()
    sessions.create()
    sessions.close()


def test_shutdown_attempts_all_backends_after_close_error():
    created = []
    sessions = BackendSessions(memory_factory(created))
    sessions.create()
    sessions.create()
    created[0][0].close.side_effect = RuntimeError("close failed")
    with pytest.raises(ExceptionGroup):
        sessions.close()
    for backend, _ in created:
        backend.close.assert_called_once()
    with pytest.raises(RuntimeError, match="closed"):
        sessions.create()


def test_shutdown_waits_for_inflight_session_creation():
    started, release = threading.Event(), threading.Event()
    created = []

    def factory(store):
        started.set()
        assert release.wait(5)
        return memory_factory(created)(store)

    sessions = BackendSessions(factory)
    with ThreadPoolExecutor(2) as pool:
        creation = pool.submit(sessions.create)
        assert started.wait(5)
        closing = pool.submit(sessions.close)
        try:
            with pytest.raises(TimeoutError):
                closing.result(timeout=0.05)
        finally:
            release.set()
        closing.result(timeout=5)
        try:
            token = creation.result(timeout=5)
        except RuntimeError as exc:
            assert "closed" in str(exc)
        else:
            with pytest.raises(SessionNotFound):
                sessions.call(token, "make", {"value": 1})
    created[0][0].close.assert_called_once()


def test_active_workflow_does_not_expire_and_same_session_calls_are_serialized():
    created, now = [], [0.0]
    sessions = BackendSessions(memory_factory(created), SessionConfig(2, 10), clock=lambda: now[0])
    token = sessions.create()
    other = sessions.create()
    entered, release = threading.Event(), threading.Event()
    second_entered = threading.Event()

    def slow(tool, args):
        if args.get("first"):
            entered.set()
            assert release.wait(5)
        else:
            second_entered.set()
        return {}

    created[0][0].call.side_effect = slow
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(sessions.call, token, "test", {"first": True})
        assert entered.wait(5)
        second = pool.submit(sessions.call, token, "test", {})
        now[0] = 20
        try:
            with pytest.raises(SessionNotFound):
                sessions.call(other, "make", {"value": 1})
            assert not second_entered.wait(0.05)
            created[0][0].close.assert_not_called()
        finally:
            release.set()
        first.result(timeout=5)
        second.result(timeout=5)
    assert second_entered.is_set()
    sessions.close()


def test_different_sessions_execute_independently_and_shutdown_drains_active_calls():
    created = []
    sessions = BackendSessions(memory_factory(created))
    a, b = sessions.create(), sessions.create()
    started, release = threading.Event(), threading.Event()

    def slow(tool, args):
        started.set()
        assert release.wait(5)
        return {}

    created[0][0].call.side_effect = slow
    with ThreadPoolExecutor(3) as pool:
        call = pool.submit(sessions.call, a, "test", {})
        assert started.wait(5)
        try:
            other = pool.submit(sessions.call, b, "make", {"value": "B"})
            assert other.result(timeout=2)["handle"]
            closing = pool.submit(sessions.close)
            with pytest.raises(TimeoutError):
                closing.result(timeout=0.05)
        finally:
            release.set()
        call.result(timeout=5)
        closing.result(timeout=5)
    for backend, store in created:
        backend.close.assert_called_once()
        assert not store.handles


def test_http_creation_errors_are_sanitized_and_capacity_is_reusable(demo_auth, demo_headers):
    pytest.importorskip("fastapi")
    from agent_native_graph.interfaces.service import create_app

    created = []
    factory = MagicMock(
        side_effect=[RuntimeError("secret connection details"), memory_factory(created)]
    )

    def connect(store):
        return factory(store)(store)

    app = create_app(backend_factory=connect, session_config=SessionConfig(1, 60), auth=demo_auth)

    async def requests():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test", headers=demo_headers
            ) as client:
                assert (await client.get("/health")).status_code == 200
                factory.assert_not_called()
                failure = await client.post("/sessions")
                assert failure.status_code == 503 and "secret" not in failure.text
                success = await client.post("/sessions")
                assert success.status_code == 201
                assert success.headers["cache-control"] == "no-store"

    asyncio.run(requests())
    created[0][0].close.assert_called_once()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_sessions": 0},
        {"max_sessions": True},
        {"idle_timeout_s": 0},
        {"idle_timeout_s": float("nan")},
        {"idle_timeout_s": True},
    ],
)
def test_invalid_session_configuration(kwargs):
    with pytest.raises(ValueError):
        SessionConfig(**kwargs)


def test_http_sessions_are_app_local_and_shutdown_closes_remaining_backends(
    demo_auth, demo_headers
):
    pytest.importorskip("fastapi")
    from agent_native_graph.interfaces.service import create_app

    created = []
    app = create_app(
        backend_factory=memory_factory(created), session_config=SessionConfig(2, 60), auth=demo_auth
    )
    other = create_app(backend_factory=memory_factory([]), auth=demo_auth)

    async def requests():
        async with app.router.lifespan_context(app), other.router.lifespan_context(other):
            async with (
                httpx.AsyncClient(
                    transport=httpx.ASGITransport(app), base_url="http://test", headers=demo_headers
                ) as client,
                httpx.AsyncClient(
                    transport=httpx.ASGITransport(other),
                    base_url="http://other",
                    headers=demo_headers,
                ) as peer,
            ):
                missing = await client.post(
                    "/tools/call", json={"tool": "make", "args": {"value": 1}}
                )
                assert missing.status_code == 401
                a = (await client.post("/sessions")).json()["session_id"]
                b = (await client.post("/sessions")).json()["session_id"]
                assert (await client.post("/sessions")).status_code == 429

                async def call(token, tool, args):
                    return await client.post(
                        "/tools/call",
                        headers={"X-ANA-Session": token},
                        json={"tool": tool, "args": args},
                    )

                ha = (await call(a, "count_nodes", {"value": "A"})).json()["result"]["handle"]
                hb = (await call(b, "count_nodes", {"value": "B"})).json()["result"]["handle"]
                assert ha != hb
                assert (await call(b, "fetch", {"from": ha})).status_code == 400
                assert (await call(a, "fetch", {"from": ha})).status_code == 200
                foreign = await peer.post(
                    "/tools/call",
                    headers={"X-ANA-Session": a},
                    json={"tool": "fetch", "args": {"from": ha}},
                )
                assert foreign.status_code == 404
                assert (
                    await client.delete("/sessions/current", headers={"X-ANA-Session": a})
                ).status_code == 204
                assert (await call(a, "fetch", {"from": ha})).status_code == 404
        for backend, store in created:
            backend.close.assert_called_once()
            assert not store.handles

    asyncio.run(requests())
