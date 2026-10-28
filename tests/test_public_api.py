import asyncio
import os
import subprocess
import sys
from unittest.mock import MagicMock

import httpx
import pytest

from agent_native_graph import AgentGraphBackend, connect_neo4j, get_tool_specs
from agent_native_graph.backends.neo4j import backend, introspection
from agent_native_graph.core.tool_specs import SCHEMA_ENTRY_MODES, _tool_specs


@pytest.fixture
def connection(monkeypatch):
    driver = MagicMock()
    connect = MagicMock(return_value=driver)
    discover = MagicMock(return_value={"labels": ["Device"]})
    monkeypatch.setattr(backend.GraphDatabase, "driver", connect)
    monkeypatch.setattr(introspection, "introspect_schema", discover)
    return driver, connect, discover


def test_factory_discovers_schema_and_context_closes_once(connection):
    driver, connect, discover = connection
    with connect_neo4j("bolt://example.invalid", "reader", "test-only") as graph:
        assert isinstance(graph, AgentGraphBackend)
        assert graph.tool_specs() == get_tool_specs()
        assert graph._schema == {"labels": ["Device"]}
    discover.assert_called_once_with(
        "bolt://example.invalid", "reader", "test-only", query_timeout_s=30
    )
    assert connect.call_args.kwargs["auth"] == ("reader", "test-only")
    graph.close()
    driver.close.assert_called_once()
    with pytest.raises(RuntimeError, match="closed"):
        graph.call("schema_overview", {})


def test_context_closes_on_exception_without_suppressing_it(connection):
    driver, _, _ = connection
    with pytest.raises(RuntimeError, match="workflow failed"):
        with connect_neo4j("bolt://example.invalid", "reader", "test-only"):
            raise RuntimeError("workflow failed")
    driver.close.assert_called_once()


def test_schema_override_avoids_discovery_and_uses_client_mode(connection):
    driver, _, discover = connection
    with connect_neo4j(
        "bolt://example.invalid",
        "reader",
        "test-only",
        schema={"labels": []},
        query_timeout_s=None,
        schema_entry="targeted_first",
    ) as graph:
        assert graph._query_timeout_s is None
        assert graph.tool_specs() == get_tool_specs(schema_entry="targeted_first")
    discover.assert_not_called()
    driver.close.assert_called_once()


@pytest.mark.parametrize("timeout", [0, -1, True, 1.5, "30"])
def test_invalid_factory_configuration_fails_before_io(connection, timeout):
    _, connect, discover = connection
    with pytest.raises(ValueError, match="query_timeout_s"):
        connect_neo4j("bolt://example.invalid", "reader", "test-only", query_timeout_s=timeout)
    discover.assert_not_called()
    connect.assert_not_called()


def test_invalid_mode_and_failed_discovery_do_not_create_backend(connection):
    _, connect, discover = connection
    with pytest.raises(ValueError, match="schema entry"):
        connect_neo4j("bolt://example.invalid", "reader", "test-only", schema_entry="unknown")
    discover.assert_not_called()
    discover.side_effect = RuntimeError("discovery failed")
    with pytest.raises(RuntimeError, match="discovery failed"):
        connect_neo4j("bolt://example.invalid", "reader", "test-only")
    connect.assert_not_called()


@pytest.mark.parametrize("mode", SCHEMA_ENTRY_MODES)
@pytest.mark.parametrize("planning", [False, True])
def test_public_catalog_is_exactly_the_effective_native_payload(mode, planning):
    assert get_tool_specs(enable_planning_tools=planning, schema_entry=mode) == _tool_specs(
        enable_planning_tools=planning, schema_entry=mode
    )


def test_public_catalog_returns_independent_schemas():
    specs = get_tool_specs()
    label = next(s for s in specs if s["function"]["name"] == "count_nodes")
    label["function"]["parameters"]["properties"]["label"]["description"] = "edited"
    original = next(s for s in get_tool_specs() if s["function"]["name"] == "count_nodes")
    assert original["function"]["parameters"]["properties"]["label"]["description"] != "edited"
    with pytest.raises(ValueError, match="boolean"):
        get_tool_specs(enable_planning_tools="false")


def test_import_and_catalog_require_no_research_provider_or_dataset(tmp_path):
    code = """
import sys
from agent_native_graph import connect_neo4j, get_tool_specs
assert len(get_tool_specs()) == 35
assert not any(n.startswith((
    'agent_native_graph.application', 'agent_native_graph.research',
    'agent_native_graph.llm_providers',
)) for n in sys.modules)
"""
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"API_KEY", "API_KEY_FILE", "ANA_SCHEMA_JSON"}
    }
    subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path, env=env, check=True, capture_output=True
    )


def test_http_native_catalog_needs_no_backend(monkeypatch, demo_auth, demo_headers):
    pytest.importorskip("fastapi")
    from agent_native_graph.interfaces import service

    factory = MagicMock(side_effect=AssertionError("no database required"))
    monkeypatch.setenv("ANA_SCHEMA_ENTRY", "targeted_first")

    async def requests():
        transport = httpx.ASGITransport(
            app=service.create_app(backend_factory=factory, auth=demo_auth)
        )
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", headers=demo_headers
        ) as client:
            for planning in (False, True):
                response = await client.get(
                    "/tools/specs", params={"enable_planning_tools": str(planning).lower()}
                )
                assert response.status_code == 200
                assert response.json()["tools"] == get_tool_specs(
                    enable_planning_tools=planning, schema_entry="targeted_first"
                )
            metadata = (await client.get("/tools")).json()
            assert metadata["tools"] and "function" not in metadata["tools"][0]

    asyncio.run(requests())
    factory.assert_not_called()
