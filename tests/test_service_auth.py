import asyncio
import json
from unittest.mock import MagicMock

import httpx
import pytest

from agent_native_graph.application.auth import (
    ApiKeyAuth,
    ApiKeyClient,
    AuthenticationError,
    AuthNotConfigured,
    Principal,
)
from agent_native_graph.core.enums import ToolProfile


def test_auth_file_snapshot_and_secret_redaction(tmp_path, monkeypatch):
    key = "test-only-secret-" * 3
    path = tmp_path / "auth.config.json"
    path.write_text(json.dumps({"clients": [{"id": "reader", "api_key": key}]}))
    monkeypatch.setenv("ANA_AUTH_FILE", str(path))
    auth = ApiKeyAuth.from_env()
    path.unlink()
    assert auth.authenticate("Bearer " + key) == Principal("reader")
    assert key not in repr(ApiKeyClient("reader", key))
    for credential in (None, "Basic " + key, "Bearer wrong", "Bearer "):
        with pytest.raises(AuthenticationError) as error:
            auth.authenticate(credential)
        assert key not in str(error.value)
    assert Principal("reader").permits("readonly")
    assert not Principal("reader").permits("readwrite")
    assert Principal("writer", ToolProfile.READWRITE).permits("readonly")
    assert Principal("writer", ToolProfile.READWRITE).permits("readwrite")


@pytest.mark.parametrize(
    "contents",
    [
        "not JSON",
        "[]",
        "{}",
        '{"clients": [null]}',
        '{"clients": [{"id": "x", "api_key": "short"}]}',
        '{"clients": [{"id": "x", "api_key": "abcdefghijklmnopqrstuvwxyz123456", "profile": "admin"}]}',
    ],
)
def test_invalid_auth_files_fail_closed(tmp_path, monkeypatch, contents):
    path = tmp_path / "auth.config.json"
    path.write_text(contents)
    monkeypatch.setenv("ANA_AUTH_FILE", str(path))
    with pytest.raises(ValueError, match="Invalid ANA_AUTH_FILE"):
        ApiKeyAuth.from_env()


def test_missing_configuration_has_no_anonymous_fallback(monkeypatch):
    monkeypatch.delenv("ANA_AUTH_FILE", raising=False)
    with pytest.raises(AuthNotConfigured):
        ApiKeyAuth.from_env().authenticate(None)
    with pytest.raises(ValueError, match="ids must be unique"):
        ApiKeyAuth((ApiKeyClient("same", "a" * 32), ApiKeyClient("same", "b" * 32)))
    with pytest.raises(ValueError, match="keys must be unique"):
        ApiKeyAuth((ApiKeyClient("a", "a" * 32), ApiKeyClient("b", "a" * 32)))


def test_http_auth_owner_and_tool_permissions(monkeypatch):
    pytest.importorskip("fastapi")
    from agent_native_graph.interfaces import service

    contracts = service.get_tool_contract()
    for item in contracts:
        if item["name"] == "count_nodes":
            item["profile"] = "readwrite"
    monkeypatch.setattr(service, "get_tool_contract", lambda status=None: contracts)
    backends = []

    def factory(store):
        backend = MagicMock()
        backend.call.return_value = {"ok": True}
        backends.append(backend)
        return backend

    auth = ApiKeyAuth(
        (ApiKeyClient("reader", "r" * 32), ApiKeyClient("writer", "w" * 32, ToolProfile.READWRITE))
    )
    app = service.create_app(backend_factory=factory, auth=auth)
    reader = {"Authorization": "Bearer " + "r" * 32}
    writer = {"Authorization": "Bearer " + "w" * 32}

    async def requests():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test"
            ) as client:
                assert (await client.get("/health")).status_code == 200
                for route, method in (
                    ("/tools", "GET"),
                    ("/tools/specs", "GET"),
                    ("/sessions", "POST"),
                    ("/sessions/current", "DELETE"),
                    ("/tools/call", "POST"),
                ):
                    response = await client.request(
                        method,
                        route,
                        json={"tool": "fetch", "args": {}} if route == "/tools/call" else None,
                    )
                    assert response.status_code == 401
                    assert response.headers["www-authenticate"] == "Bearer"
                assert not backends
                assert (
                    await client.post("/sessions", headers={"Authorization": "Bearer wrong"})
                ).status_code == 401
                for route in ("/tools", "/tools/specs"):
                    data = (await client.get(route, headers=reader)).json()["tools"]
                    names = {
                        item.get("name", item.get("function", {}).get("name")) for item in data
                    }
                    assert "count_nodes" not in names and "fetch" in names
                    data = (await client.get(route, headers=writer)).json()["tools"]
                    assert any(
                        item.get("name", item.get("function", {}).get("name")) == "count_nodes"
                        for item in data
                    )
                token = (await client.post("/sessions", headers=reader)).json()["session_id"]
                owned = {**reader, "X-ANA-Session": token}
                stolen = {**writer, "X-ANA-Session": token}
                payload = {"tool": "fetch", "args": {}}
                assert (
                    await client.post("/tools/call", headers=stolen, json=payload)
                ).status_code == 404
                assert (await client.delete("/sessions/current", headers=stolen)).status_code == 404
                backends[0].call.assert_not_called()
                assert (
                    await client.post("/tools/call", headers=owned, json=payload)
                ).status_code == 200
                for name in ("count_nodes", "_query", "unknown"):
                    response = await client.post(
                        "/tools/call?profile=readwrite",
                        headers=owned,
                        json={"tool": name, "args": {"profile": "readwrite"}},
                    )
                    assert response.status_code == 403
                writer_token = (await client.post("/sessions", headers=writer)).json()["session_id"]
                assert (
                    await client.post(
                        "/tools/call",
                        headers={**writer, "X-ANA-Session": writer_token},
                        json={"tool": "count_nodes", "args": {}},
                    )
                ).status_code == 200
                assert (await client.delete("/sessions/current", headers=owned)).status_code == 204

    asyncio.run(requests())


def test_unconfigured_http_is_closed_but_health_is_public():
    pytest.importorskip("fastapi")
    from agent_native_graph.interfaces.service import create_app

    factory = MagicMock()
    app = create_app(backend_factory=factory, auth=ApiKeyAuth())

    async def requests():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            assert (await client.get("/health")).status_code == 200
            assert (await client.get("/tools/specs")).status_code == 503
            assert (await client.post("/sessions")).status_code == 503

    asyncio.run(requests())
    factory.assert_not_called()
