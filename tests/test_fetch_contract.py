import asyncio
from unittest.mock import MagicMock

import httpx
import pytest

from agent_native_graph.application import neo4j_benchmark
from agent_native_graph.application.agent_loop import _benchmark_fetch_preview
from agent_native_graph.backends.neo4j import backend as backend_module
from agent_native_graph.backends.neo4j.backend import Neo4jGraphBackend


def table_backend(size):
    backend = Neo4jGraphBackend.__new__(Neo4jGraphBackend)
    backend._driver = MagicMock()
    backend.last_fetch = None
    handle = backend._store([{"value": i} for i in range(size)], kind="table", columns=["value"])
    return backend, handle["handle"]


@pytest.mark.parametrize("size", [0, 20, 21, 25, 1001])
def test_fetch_returns_complete_pages_with_a_separate_preview(size):
    backend, handle = table_backend(size)
    rows, offset = [], 0
    while True:
        page = backend.call("fetch", {"from": handle, "limit": 25, "offset": offset})
        assert page["contract_version"] == "ana-fetch-v1"
        assert page["returned_count"] == len(page["rows"])
        assert page["preview"] == page["rows"][:20]
        assert page["preview_truncated"] == (len(page["rows"]) > 20)
        assert page["total_count"] == size and page["offset"] == offset
        assert page["truncated"] == (page["next_offset"] is not None)
        rows.extend(page["rows"])
        if page["next_offset"] is None:
            break
        assert page["next_offset"] == offset + len(page["rows"])
        offset = page["next_offset"]
    assert rows == [[i] for i in range(size)]


def test_default_null_and_out_of_range_pages():
    backend, handle = table_backend(1001)
    for args in ({}, {"limit": None, "offset": None}):
        page = backend.call("fetch", {"from": handle, **args})
        assert len(page["rows"]) == 1000 and page["next_offset"] == 1000
    for offset in (1001, 2000):
        page = backend.call("fetch", {"from": handle, "offset": offset})
        assert page["rows"] == page["preview"] == []
        assert page["returned_count"] == 0 and page["next_offset"] is None
        assert not page["truncated"] and not page["preview_truncated"]


@pytest.mark.parametrize(
    "args",
    [
        {"limit": 0},
        {"limit": -1},
        {"limit": True},
        {"limit": 1.5},
        {"limit": "25"},
        {"offset": -1},
        {"offset": False},
        {"offset": 0.5},
        {"offset": "0"},
    ],
)
def test_invalid_paging_is_rejected_without_changing_last_fetch(args):
    backend, handle = table_backend(25)
    with pytest.raises(ValueError, match="must be an integer"):
        backend.call("fetch", {"from": handle, **args})
    assert backend.last_fetch is None


def test_unknown_handle_is_not_replaced_by_an_empty_page():
    backend, _ = table_backend(25)
    with pytest.raises(ValueError, match="h-missing"):
        backend.call("fetch", {"from": "h-missing"})


@pytest.mark.parametrize(
    "fetch_all,policy,failure",
    [
        (False, None, None),
        (True, None, None),
        (False, "bounded-v1", None),
        (True, "bounded-v1", None),
        (False, "bounded-v1", "cap"),
        (True, "bounded-v1", "cap"),
        (False, "bounded-v1", "no_fetch"),
        (True, "bounded-v1", "no_fetch"),
    ],
)
def test_benchmark_keeps_preview_transcripts_and_complete_scoring(
    monkeypatch, fetch_all, policy, failure
):
    if failure == "cap":
        from agent_native_graph.application.result_policy import BoundedResults

        monkeypatch.setattr(
            neo4j_benchmark, "get_result_policy", lambda name: BoundedResults(max_rows=3)
        )
    backend, handle = table_backend(25)
    monkeypatch.setattr(backend_module, "Neo4jGraphBackend", lambda *a, **kw: backend)
    monkeypatch.setattr(
        neo4j_benchmark,
        "_next_action",
        lambda *a, **kw: (
            {"tool": "done", "args": {}}
            if failure == "no_fetch"
            else {"tool": "fetch", "args": {"from": handle, "limit": 21}}
        ),
    )
    expected = [] if failure else [[i] for i in range(25 if fetch_all or policy else 21)]
    row = neo4j_benchmark._run_agent_task(
        {
            "qid": "test",
            "nl_question": "Return the values",
            "gold_cypher": "RETURN 1",
            "answer_json": expected,
        },
        llm=None,
        schema={},
        neo4j_uri="bolt://example.invalid",
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
        evaluation_fetch_all_pages=fetch_all,
        enable_runner_guardrails=False,
        task_timeout_s=None,
        result_policy=policy,
    )
    if failure:
        assert not row["ok"] and not row["matches_answer_json"]
        assert not row["result_completeness"]["complete"]
        assert row["rows"] == []
        if failure == "cap":
            assert row["result_completeness"]["error"] == "result_row_limit"
        return
    assert row["ok"] and row["matches_answer_json"] and row["rows"] == expected
    result = row["transcript"][0]["result"]
    assert result["rows"] == expected[:20] and result["returned_count"] == len(expected)
    assert not {"contract_version", "preview", "preview_truncated"} & result.keys()
    assert result.get("evaluation_fetch_all_pages", False) == (fetch_all and policy is None)
    if policy:
        assert row["result_completeness"]["complete"]
        assert row["result_completeness"]["scope"] == "stored_handle"
        assert row["result_completeness"]["upstream_completeness"] == "unknown"
    backend._driver.close.assert_called_once()


@pytest.mark.parametrize("policy", [None, "bounded-v1"])
@pytest.mark.parametrize("ending", ["done", "max_steps", "explicit_fetch", "done_then_fetch"])
def test_bounded_policy_never_finalizes_an_intermediate_handle_automatically(
    monkeypatch, policy, ending
):
    backend, handle = table_backend(1)
    original_call = backend.call
    calls = []

    def call(tool, args):
        calls.append(tool)
        if tool == "node_scan":
            return {"handle": handle, "kind": "table", "matched_count": 1}
        return original_call(tool, args)

    monkeypatch.setattr(backend, "call", call)
    monkeypatch.setattr(backend_module, "Neo4jGraphBackend", lambda *a, **kw: backend)
    planned = [
        {"tool": "node_scan", "args": {}},
        {"tool": "fetch", "args": {"from": handle}}
        if ending == "explicit_fetch"
        else {"tool": "done", "args": {}},
    ]
    if ending == "done_then_fetch":
        planned.append({"tool": "fetch", "args": {"from": handle}})
    actions = iter(planned)
    monkeypatch.setattr(neo4j_benchmark, "_next_action", lambda *a, **kw: next(actions))
    row = neo4j_benchmark._run_agent_task(
        {
            "qid": "finalization",
            "nl_question": "Return the value",
            "gold_cypher": "RETURN 0",
            "answer_json": [[0]],
        },
        llm=None,
        schema={},
        neo4j_uri="bolt://example.invalid",
        neo4j_user="test",
        neo4j_password="test",
        neo4j_query_timeout_s=30,
        max_steps=1 if ending == "max_steps" else len(planned),
        native_tools=True,
        tool_choice="auto",
        enable_planning_tools=False,
        schema_entry="overview",
        wrapper_planning=False,
        auto_fetch_on_done=ending == "max_steps",
        evaluation_fetch_all_pages=False,
        enable_runner_guardrails=False,
        task_timeout_s=None,
        result_policy=policy,
    )
    should_fetch = policy is None or ending in ("explicit_fetch", "done_then_fetch")
    assert ("fetch" in calls) == should_fetch
    assert row["ok"] == row["matches_answer_json"] == should_fetch
    assert row["rows"] == ([[0]] if should_fetch else [])
    if policy:
        assert row["result_completeness"]["complete"] == should_fetch
        assert not any(step["action"].get("auto") for step in row["transcript"])
        if ending == "done_then_fetch":
            assert [step["action"]["tool"] for step in row["transcript"]] == [
                "node_scan",
                "done",
                "fetch",
            ]
            assert row["transcript"][1]["result"]["status"] == "tool_error"


def test_entity_deduplication_happens_before_page_offsets():
    backend, _ = table_backend(0)
    a = {"shape": "entity", "labels": ["Device"], "properties": {"id": "a", "name": "A"}}
    b = {"shape": "entity", "labels": ["Device"], "properties": {"id": "b", "name": "B"}}
    handle = backend._store(
        [{"device": a}, {"device": a}, {"device": b}],
        focus="device",
        metadata={"entity_projection_distinct_default": True},
    )
    first = backend.call("fetch", {"from": handle["handle"], "limit": 1})
    second = backend.call(
        "fetch", {"from": handle["handle"], "limit": 1, "offset": first["next_offset"]}
    )
    assert first["rows"] == [["A"]] and second["rows"] == [["B"]]
    assert first["total_count"] == second["total_count"] == 2
    assert second["next_offset"] is None


def test_preview_adapter_does_not_mutate_the_public_page():
    backend, handle = table_backend(25)
    page = backend.call("fetch", {"from": handle})
    preview = _benchmark_fetch_preview(page)
    assert len(page["rows"]) == 25 and page["contract_version"] == "ana-fetch-v1"
    assert preview == {
        "columns": ["value"],
        "rows": [[i] for i in range(20)],
        "returned_count": 25,
        "offset": 0,
        "limit": 1000,
        "total_count": 25,
        "next_offset": None,
        "truncated": False,
    }


def test_http_fetch_delivers_all_rows_and_reports_invalid_paging(
    monkeypatch, demo_auth, demo_headers
):
    pytest.importorskip("fastapi")
    from agent_native_graph.interfaces import service

    state = {}

    def factory(store):
        backend, _ = table_backend(0)
        backend._handle_store = store
        state["handle"] = backend._store(
            [{"value": i} for i in range(25)], kind="table", columns=["value"]
        )["handle"]
        return backend

    async def request_pages():
        app = service.create_app(backend_factory=factory, auth=demo_auth)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", headers=demo_headers
        ) as client:
            session = (await client.post("/sessions")).json()["session_id"]
            client.headers["X-ANA-Session"] = session
            handle = state["handle"]
            response = await client.post(
                "/tools/call", json={"tool": "fetch", "args": {"from": handle, "limit": 25}}
            )
            assert response.status_code == 200
            page = response.json()["result"]
            assert page["contract_version"] == "ana-fetch-v1"
            assert page["rows"] == [[i] for i in range(25)]
            assert len(page["preview"]) == 20 and page["preview_truncated"]
            assert page["returned_count"] == 25 and page["next_offset"] is None
            invalid = await client.post(
                "/tools/call", json={"tool": "fetch", "args": {"from": handle, "offset": -1}}
            )
            assert invalid.status_code == 400 and "offset" in invalid.json()["detail"]
        app.state.sessions.close()

    asyncio.run(request_pages())
