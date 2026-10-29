"""Preview truncation, stored-handle paging and graph coverage are different facts."""

import asyncio
from unittest.mock import MagicMock

import pytest

from agent_native_graph.application.result_policy import (
    BoundedResults,
    CandidatePreviewGraph,
    candidate_result,
    collect_handle,
    observe_results,
    record_observation,
    result_policy,
)
from agent_native_graph.backends.neo4j.backend import Neo4jGraphBackend


def table(size):
    graph = Neo4jGraphBackend.__new__(Neo4jGraphBackend)
    graph._driver = MagicMock()
    graph.last_fetch = None
    handle = graph._store([{"x": i} for i in range(size)], kind="table", columns=["x"])["handle"]
    return graph, handle


@pytest.mark.parametrize("size,offset", [(0, 0), (25, 0), (25, 10), (25, 24), (25, 25)])
def test_collection_restarts_at_zero_without_claiming_graph_completeness(size, offset):
    graph, handle = table(size)
    args = {"from": handle, "offset": offset, "limit": 2}
    page = graph.call("fetch", args)
    final = collect_handle(graph, {"args": args}, page, BoundedResults())
    assert graph.last_fetch == [[i] for i in range(size)]
    assert final["result_completeness"] == {
        "policy": "bounded-v1",
        "scope": "stored_handle",
        "status": "complete",
        "available_count": size,
        "collected_count": size,
        "preview_count": min(size, 20),
        "preview_truncated": size > 20,
        "complete": True,
        "upstream_completeness": "unknown",
        "error": None,
    }


def test_row_cap_never_leaves_a_partial_last_fetch():
    graph, handle = table(4)
    args = {"from": handle, "limit": 2}
    page = graph.call("fetch", args)
    with pytest.raises(ValueError, match="result_row_limit"):
        collect_handle(graph, {"args": args}, page, BoundedResults(max_rows=3))
    assert graph.last_fetch is None


@pytest.mark.parametrize(
    "change", ["total_count", "returned_count", "offset", "next_offset", "truncated"]
)
def test_invalid_pagination_is_not_scored(change):
    graph, handle = table(25)
    args = {"from": handle, "limit": 2}
    page = graph.call("fetch", args)
    page[change] = -1
    with pytest.raises(ValueError):
        collect_handle(graph, {"args": args}, page, BoundedResults())
    assert graph.last_fetch is None


@pytest.mark.parametrize("failure", ["exception", "changed", "short", "columns"])
def test_second_fetch_must_prove_complete_unchanged_coverage(failure):
    graph, handle = table(25)
    args = {"from": handle, "limit": 2}
    page = graph.call("fetch", args)
    original = graph.call

    def changed(*a, **kw):
        result = original(*a, **kw)
        if failure == "exception":
            raise ValueError("test failure after fetching")
        if failure == "changed":
            result["total_count"] += 1
        elif failure == "short":
            result["rows"].pop()
        else:
            result["columns"] = ["different"]
        return result

    graph.call = changed
    with pytest.raises(ValueError):
        collect_handle(graph, {"args": args}, page, BoundedResults())
    assert graph.last_fetch is None


def test_observations_and_candidate_scopes_are_isolated_for_concurrent_questions():
    class Graph:
        schema = "delegated schema"

        async def run_query(self, label):
            await asyncio.sleep(0)
            assert candidate_result()
            record_observation({"label": label})

    async def question(label):
        with observe_results() as entries:
            proxy = CandidatePreviewGraph(Graph())
            assert proxy.schema == "delegated schema"
            await proxy.run_query(label)
            assert not candidate_result()
        return entries

    async def run():
        return await asyncio.gather(question("a"), question("b"))

    assert asyncio.run(run()) == [[{"label": "a"}], [{"label": "b"}]]
    assert not candidate_result()
    record_observation({"label": "outside"})


def test_default_is_unchanged_and_unknown_policy_is_rejected():
    assert result_policy(None) is None
    with pytest.raises(ValueError):
        result_policy("unknown")
