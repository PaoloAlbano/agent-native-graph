"""Validate argument errors across tool dispatch and agent execution."""

import asyncio
import copy
import json
from types import SimpleNamespace
from typing import Annotated
from unittest.mock import MagicMock

import httpx
import pytest

from agent_native_graph.application import neo4j_benchmark
from agent_native_graph.backends.neo4j import backend as backend_module
from agent_native_graph.backends.neo4j.backend import Neo4jGraphBackend
from agent_native_graph.core import tooling
from agent_native_graph.core.enums import ToolProfile, ToolStatus
from agent_native_graph.core.tooling import ToolParam, call_registered_tool, registered_tools, tool
from agent_native_graph.tools import load_tool_modules

load_tool_modules()


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch):
    """Keep synthetic definitions local to each test, without changing public catalogs."""
    monkeypatch.setattr(tooling, "_TOOL_REGISTRY", dict(registered_tools()))


@pytest.mark.parametrize("name", sorted(registered_tools()))
def test_every_registered_tool_rejects_unknown_arguments_before_invocation(name):
    backend = MagicMock()
    args = {"unsupported_argument": "must-not-be-discarded"}
    original = copy.deepcopy(args)
    with pytest.raises(ValueError, match="unsupported parameter.*unsupported_argument") as error:
        call_registered_tool(backend, name, args)
    assert "Allowed parameters:" in str(error.value)
    assert "No operation was executed" in str(error.value)
    assert "must-not-be-discarded" not in str(error.value)
    assert args == original
    assert backend.mock_calls == []


@pytest.mark.parametrize("args", [[], "not-an-object", None])
def test_non_object_arguments_are_rejected(args):
    backend = MagicMock()
    with pytest.raises(ValueError, match="arguments must be an object"):
        call_registered_tool(backend, "fetch", args)
    assert backend.mock_calls == []


def test_relationship_filters_cannot_silently_disappear():
    execute = MagicMock()
    args = {
        "source_label": "Asset",
        "relationship_type": "assignedTo",
        "target_label": "Person",
        "relationship_filters": [{"property": "start_year", "op": "lte", "value": 2000}],
    }
    with pytest.raises(ValueError, match="unsupported parameter.*relationship_filters"):
        call_registered_tool(
            SimpleNamespace(_relationship_query=execute), "relationship_query", args
        )
    execute.assert_not_called()
    corrected = {key: value for key, value in args.items() if key != "relationship_filters"}
    corrected["filters"] = [{"var": "rel", **args["relationship_filters"][0]}]
    call_registered_tool(
        SimpleNamespace(_relationship_query=execute), "relationship_query", corrected
    )
    execute.assert_called_once_with(corrected)


@pytest.mark.parametrize("parameter", ["from", "from_"])
def test_declared_public_aliases_and_existing_python_aliases_still_work(parameter):
    execute = MagicMock(return_value={"rows": []})
    assert call_registered_tool(SimpleNamespace(_fetch=execute), "fetch", {parameter: "h1"}) == {
        "rows": []
    }
    execute.assert_called_once_with({"from": "h1"})


@pytest.mark.parametrize("keys", [("from", "from_"), ("from_", "from")])
def test_conflicting_aliases_are_rejected_instead_of_overwriting_each_other(keys):
    execute = MagicMock()
    with pytest.raises(ValueError, match="conflicting arguments"):
        call_registered_tool(
            SimpleNamespace(_fetch=execute), "fetch", dict(zip(keys, ["h1", "h2"], strict=True))
        )
    execute.assert_not_called()


def test_diagnostic_tool_aliases_and_missing_required_arguments():
    execute = MagicMock(return_value={"suggestions": []})
    call_registered_tool(
        SimpleNamespace(_repair_empty_result=execute),
        "repair_empty_result",
        {"tool": "relationship_query", "args": {"filters": []}},
    )
    assert execute.call_args.args[0]["failed_tool"] == "relationship_query"
    execute.reset_mock()
    with pytest.raises(ValueError, match="requires args"):
        call_registered_tool(
            SimpleNamespace(_repair_empty_result=execute),
            "repair_empty_result",
            {"tool": "relationship_query"},
        )
    execute.assert_not_called()


def test_variadic_python_function_does_not_bypass_declared_public_parameters():
    execute = MagicMock(return_value={"ok": True})

    @tool(
        name="test_variadic",
        status=ToolStatus.CORE,
        profile=ToolProfile.READONLY,
        purpose="Test declared arguments.",
        description="Test declared arguments.",
        parameters={"value": {"type": "integer"}},
    )
    def variadic(backend, **values):
        return backend.execute(values)

    backend = SimpleNamespace(execute=execute)
    with pytest.raises(ValueError, match="unsupported parameter.*invented"):
        call_registered_tool(backend, "test_variadic", {"value": 1, "invented": 2})
    execute.assert_not_called()
    assert call_registered_tool(backend, "test_variadic", {"value": 1}) == {"ok": True}
    execute.assert_called_once_with({"value": 1})


def test_decorator_annotations_remain_the_source_of_allowed_parameter_names():
    @tool(
        name="test_alias",
        status=ToolStatus.CORE,
        profile=ToolProfile.READONLY,
        purpose="Test aliases.",
        description="Test aliases.",
    )
    def annotated(backend, source: Annotated[str, ToolParam("Source handle.", alias="from")]):
        return {"source": source}

    assert call_registered_tool(None, "test_alias", {"from": "h1"}) == {"source": "h1"}
    with pytest.raises(ValueError, match="unsupported parameter.*backend"):
        call_registered_tool(None, "test_alias", {"from": "h1", "backend": "replacement"})


def test_http_returns_argument_error_and_keeps_session_usable(demo_auth, demo_headers):
    pytest.importorskip("fastapi")
    from agent_native_graph.interfaces.service import create_app

    backend = Neo4jGraphBackend.__new__(Neo4jGraphBackend)
    backend._driver = MagicMock()
    backend._schema_overview = MagicMock(return_value={"labels": []})

    def factory(store):
        backend._handle_store = store
        return backend

    app = create_app(backend_factory=factory, auth=demo_auth)

    async def requests():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test", headers=demo_headers
            ) as client:
                opened = await client.post("/sessions")
                assert opened.status_code == 201
                headers = {"X-ANA-Session": opened.json()["session_id"]}
                response = await client.post(
                    "/tools/call",
                    headers=headers,
                    json={"tool": "schema_overview", "args": {"invented": "do-not-echo"}},
                )
                assert response.status_code == 400
                assert "unsupported parameter(s): 'invented'" in response.json()["detail"]
                assert "do-not-echo" not in response.json()["detail"]
                backend._schema_overview.assert_not_called()
                backend._driver.session.assert_not_called()
                corrected = await client.post(
                    "/tools/call",
                    headers=headers,
                    json={"tool": "schema_overview", "args": {}},
                )
                assert corrected.status_code == 200
                assert corrected.json()["result"] == {"labels": []}
                backend._schema_overview.assert_called_once_with()

    asyncio.run(requests())
    backend._driver.close.assert_called_once()


@pytest.mark.parametrize("policy", [None, "bounded-v1"])
def test_native_agent_receives_error_and_chooses_its_own_corrected_call(monkeypatch, policy):
    backend = Neo4jGraphBackend.__new__(Neo4jGraphBackend)
    backend._driver = MagicMock()
    backend.last_fetch = None
    execute = MagicMock(
        side_effect=lambda args: backend._store([{"name": "Alex"}], kind="table", columns=["name"])
    )
    monkeypatch.setattr(backend, "_relationship_query", execute)
    monkeypatch.setattr(backend_module, "Neo4jGraphBackend", lambda *a, **kw: backend)
    base = {"source_label": "Asset", "relationship_type": "assignedTo", "target_label": "Person"}
    actions = [
        (
            "relationship_query",
            {
                **base,
                "relationship_filters": [{"property": "start_year", "op": "lte", "value": 2000}],
            },
        ),
        (
            "relationship_query",
            {
                **base,
                "filters": [{"var": "rel", "property": "start_year", "op": "lte", "value": 2000}],
            },
        ),
        ("fetch", {"from": "h1"}),
    ]
    requests = []

    class ScriptedModel:
        def chat(self, messages, **kwargs):
            index = len(requests)
            requests.append(copy.deepcopy(messages))
            if index == 1:
                previous = json.loads(messages[-1]["content"])["previous_tool_results"]
                assert previous[-1]["result"]["status"] == "tool_error"
                assert "relationship_filters" in previous[-1]["result"]["error"]
                assert "Allowed parameters:" in previous[-1]["result"]["error"]
                execute.assert_not_called()
            name, args = actions[index]
            return {"tool_calls": [{"function": {"name": name, "arguments": json.dumps(args)}}]}

    row = neo4j_benchmark._run_agent_task(
        {
            "qid": "argument-recovery",
            "nl_question": "Who was assigned in 2000?",
            "gold_cypher": "RETURN 'Alex'",
            "answer_json": [["Alex"]],
        },
        llm=ScriptedModel(),
        schema={},
        neo4j_uri="bolt://example.invalid",
        neo4j_user="test",
        neo4j_password="test",
        neo4j_query_timeout_s=30,
        max_steps=3,
        native_tools=True,
        tool_choice="auto",
        enable_planning_tools=False,
        schema_entry="overview",
        wrapper_planning=False,
        auto_fetch_on_done=False,
        evaluation_fetch_all_pages=False,
        enable_runner_guardrails=False,
        task_timeout_s=None,
        result_policy=policy,
    )
    assert row["ok"] and row["matches_answer_json"]
    assert row["llm_call_count"] == 3 and row["tool_error_count"] == 1
    assert len(row["transcript"]) == 3 and row["error"] is None
    execute.assert_called_once_with(actions[1][1])
    backend._driver.close.assert_called_once()
