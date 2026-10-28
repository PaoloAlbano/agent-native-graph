import importlib.util
from pathlib import Path

import httpx
import pytest


def load_example():
    path = Path(__file__).resolve().parents[1] / "examples/http_workflow.py"
    spec = importlib.util.spec_from_file_location("http_workflow", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("fail_fetch", [False, True])
def test_example_paginates_and_closes_even_on_failure(fail_fetch):
    example = load_example()
    calls = []
    emitted = []

    def handle(request):
        import json

        calls.append((request.method, request.url.path))
        assert request.headers["Authorization"] == "Bearer test-only"
        if request.url.path == "/tools/specs":
            return httpx.Response(
                200,
                json={
                    "tools": [
                        {"function": {"name": name}}
                        for name in ("schema_overview", "node_scan", "fetch")
                    ]
                },
            )
        if request.url.path == "/sessions":
            return httpx.Response(201, json={"session_id": "opaque-session"})
        assert request.headers["X-ANA-Session"] == "opaque-session"
        assert "opaque-session" not in str(request.url)
        if request.method == "DELETE":
            return httpx.Response(204)
        payload = json.loads(request.content)
        tool, args = payload["tool"], payload["args"]
        if tool == "schema_overview":
            result = {"labels": [{"label": "ExampleEntity"}]}
        elif tool == "node_scan":
            assert args == {"label": "ExampleEntity", "limit": 25}
            result = {"handle": "example-handle"}
        else:
            if fail_fetch:
                return httpx.Response(400, json={"detail": "example failure"})
            offset = args["offset"]
            end = min(offset + args["limit"], 25)
            result = {
                "contract_version": "ana-fetch-v1",
                "columns": ["value"],
                "rows": [[i] for i in range(offset, end)],
                "next_offset": end if end < 25 else None,
            }
        return httpx.Response(200, json={"tool": tool, "result": result})

    with httpx.Client(
        base_url="http://test",
        headers={"Authorization": "Bearer test-only"},
        transport=httpx.MockTransport(handle),
    ) as client:
        if fail_fetch:
            with pytest.raises(httpx.HTTPStatusError):
                example.run_demo(client, emit=emitted.append)
        else:
            result = example.run_demo(client, emit=emitted.append)
            assert result["pages"] == 3 and result["rows"] == 25
            assert [len(page["rows"]) for page in emitted[:-1]] == [10, 10, 5]
    assert calls[-1] == ("DELETE", "/sessions/current")


def test_example_closes_an_empty_graph_workflow():
    example = load_example()
    requests = []

    def handle(request):
        requests.append(request)
        if request.url.path == "/tools/specs":
            return httpx.Response(
                200,
                json={
                    "tools": [
                        {"function": {"name": n}} for n in ("schema_overview", "node_scan", "fetch")
                    ]
                },
            )
        if request.url.path == "/sessions":
            return httpx.Response(201, json={"session_id": "s"})
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json={"result": {"labels": []}})

    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(handle)) as client:
        assert example.run_demo(client, emit=lambda _: None)["rows"] == 0
    assert requests[-1].method == "DELETE"
