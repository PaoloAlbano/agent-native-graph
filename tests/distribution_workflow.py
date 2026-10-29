"""Run from a copied file outside the checkout against a wheel or HTTP service."""

import argparse
import json
import os
import sys
from pathlib import Path


def exercise(call):
    """Use the public tool contract on a non-Company, multi-label graph."""
    overview = call("schema_overview", {})
    assert {"Device", "Sensor", "Zone", "Unkeyed"} <= {row["label"] for row in overview["labels"]}
    count = call("count_nodes", {"label": "Device", "alias": "devices"})
    assert call("fetch", {"from": count["handle"]})["rows"] == [[25]]
    scan = call("node_scan", {"label": "Device", "as": "device", "limit": 25})
    projection = call(
        "project",
        {
            "from": scan["handle"],
            "select": [
                {"var": "device", "property": "device_key", "alias": "key"},
                {"var": "device", "property": "tags", "alias": "tags"},
                {"var": "device", "property": "installed_on", "alias": "installed"},
                {"var": "device", "property": "reading", "alias": "reading"},
            ],
        },
    )
    rows, offset, page_sizes = [], 0, []
    while True:
        page = call("fetch", {"from": projection["handle"], "offset": offset, "limit": 7})
        assert page["contract_version"] == "ana-fetch-v1"
        assert page["returned_count"] == len(page["rows"])
        assert page["columns"] == ["key", "tags", "installed", "reading"]
        page_sizes.append(len(page["rows"]))
        rows.extend(page["rows"])
        if page["next_offset"] is None:
            break
        assert page["next_offset"] > offset
        offset = page["next_offset"]
    assert page_sizes == [7, 7, 7, 4]
    assert {row[0] for row in rows} == {f"device-{i:02}" for i in range(25)}
    assert all(row[1] == ["lab", "temperature"] and row[2] == "2024-01-02" for row in rows)
    assert sum(row[3] is None for row in rows) == 1
    expanded = call(
        "expand",
        {
            "from": scan["handle"],
            "source": "device",
            "relationship_type": "LOCATED_IN",
            "target_label": "Zone",
            "direction": "out",
            "as": "zone",
            "limit": 100,
            "page_size": 7,
        },
    )
    zones = call(
        "project",
        {
            "from": expanded["handle"],
            "select": [
                {"var": "device", "property": "device_key", "alias": "device"},
                {"var": "zone", "property": "zone_key", "alias": "zone"},
            ],
        },
    )
    linked = call("fetch", {"from": zones["handle"], "limit": 100})["rows"]
    assert len(linked) == 25
    assert set(map(tuple, linked)) == {(f"device-{i:02}", f"zone-{i % 2}") for i in range(25)}
    return {"device_count": 25, "page_sizes": page_sizes, "traversed_rows": len(linked)}


def identity_checks(call):
    """No missing/duplicate business ID may collapse or rebind a graph entity."""
    scan = call("node_scan", {"label": "Probe", "as": "p", "limit": 10})
    assert scan["matched_count"] == 3
    assert len(call("fetch", {"from": scan["handle"]})["rows"]) == 3
    filtered = call(
        "filter",
        {"from": scan["handle"], "var": "p", "property": "id", "op": "eq", "value": "duplicate"},
    )
    assert filtered["matched_count"] == 2
    expanded = call(
        "expand",
        {
            "from": scan["handle"],
            "source": "p",
            "as": "t",
            "relationship_type": "POINTS_TO",
            "target_label": "Endpoint",
            "direction": "out",
        },
    )
    selection = [
        {"var": "p", "property": "marker", "alias": "source"},
        {"var": "t", "property": "marker", "alias": "target"},
    ]
    projected = call("project", {"from": expanded["handle"], "select": selection})
    expected = {("a", "A"), ("b", "B"), ("c", "C")}
    assert set(map(tuple, call("fetch", {"from": projected["handle"]})["rows"])) == expected
    count = call("count_handle", {"from": expanded["handle"], "var": "p", "distinct": True})
    assert call("fetch", {"from": count["handle"]})["rows"] == [[3]]
    target_count = call("count_handle", {"from": expanded["handle"], "var": "t", "distinct": True})
    assert call("fetch", {"from": target_count["handle"]})["rows"] == [[3]]
    optional = call(
        "optional_expand_count",
        {
            "from": scan["handle"],
            "source": "p",
            "relationship_type": "POINTS_TO",
            "target_label": "Endpoint",
            "direction": "out",
            "group_by": [{"var": "p", "property": "marker", "alias": "marker"}],
            "alias": "links",
        },
    )
    assert set(map(tuple, call("fetch", {"from": optional["handle"]})["rows"])) == {
        ("a", 1),
        ("b", 1),
        ("c", 1),
    }
    union = call(
        "entity_set_operation",
        {
            "operands": [
                {"handle": scan["handle"], "var": "p"},
                {"handle": scan["handle"], "var": "p"},
            ],
            "as": "p",
            "op": "union",
        },
    )
    assert union["matched_count"] == 3
    bound = call(
        "pattern_query",
        {
            "from": scan["handle"],
            "start_label": "Probe",
            "start_as": "p",
            "hops": [
                {
                    "relationship_type": "POINTS_TO",
                    "target_label": "Endpoint",
                    "direction": "out",
                    "as": "t",
                }
            ],
            "select": selection,
        },
    )
    assert set(map(tuple, call("fetch", {"from": bound["handle"]})["rows"])) == expected
    twins = call("node_scan", {"label": "Twin", "as": "twin", "limit": 10})
    assert len(call("fetch", {"from": twins["handle"]})["rows"]) == 2
    for label in ("Twin", "UnkeyedTwin"):
        pair = call("node_scan", {"label": label, "as": "twin", "limit": 10})
        assert pair["matched_count"] == 2
        for var in (None, "twin"):
            args = {"from": pair["handle"], "distinct": True}
            if var is not None:
                args["var"] = var
            counted = call("count_handle", args)
            assert call("fetch", {"from": counted["handle"]})["rows"] == [[2]]
        counted = call("count_handle", {"from": pair["handle"], "distinct": False})
        assert call("fetch", {"from": counted["handle"]})["rows"] == [[2]]
    return {
        "opaque_identity": True,
        "missing_id": True,
        "duplicate_ids": True,
        "identical_properties": True,
        "bound_pattern": True,
        "optional_count": True,
        "distinct_rows_with_duplicate_ids": True,
        "distinct_rows_without_ids": True,
    }


def finalization():
    """Run the distributed benchmark against real Neo4j, scripting only model decisions."""
    from unittest.mock import patch

    from agent_native_graph.application import neo4j_benchmark

    package = Path(neo4j_benchmark.__file__).resolve()
    expected_root = Path(os.getenv("ANA_TEST_PACKAGE_ROOT", sys.prefix)).resolve()
    assert package.is_relative_to(expected_root), package
    assert not any(os.environ.get(key) for key in ("API_KEY", "API_KEY_FILE"))
    for policy in (None, "bounded-v1"):
        for ending in ("done", "max_steps", "fetch", "done_then_fetch"):

            def decision(_llm, _question, transcript, *, ending=ending, **kwargs):
                if not transcript:
                    return {"tool": "count_nodes", "args": {"label": "Device", "alias": "devices"}}
                if ending == "fetch" or len(transcript) == 2:
                    return {"tool": "fetch", "args": {"from": transcript[0]["result"]["handle"]}}
                return {"tool": "done", "args": {}}

            with patch.object(neo4j_benchmark, "_next_action", side_effect=decision):
                row = neo4j_benchmark._run_agent_task(
                    {
                        "qid": "distribution-finalization",
                        "nl_question": "Count devices",
                        "gold_cypher": "MATCH (n:Device) RETURN count(n)",
                        "answer_json": [[25]],
                    },
                    llm=None,
                    schema={},
                    neo4j_uri=os.environ["ANA_TEST_GRAPH_URI"],
                    neo4j_user="neo4j",
                    neo4j_password="ana-disposable-test",
                    database="neo4j",
                    neo4j_query_timeout_s=30,
                    max_steps=1
                    if ending == "max_steps"
                    else 3
                    if ending == "done_then_fetch"
                    else 2,
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
            expected = policy is None or ending in ("fetch", "done_then_fetch")
            assert row["ok"] == row["matches_answer_json"] == expected
            assert row["rows"] == ([[25]] if expected else [])
            if policy:
                assert not any(step["action"].get("auto") for step in row["transcript"])
                assert row["result_completeness"]["complete"] == expected
    return {
        "packaged_runner": True,
        "explicit_fetch_required": True,
        "recovery_with_explicit_fetch": True,
        "legacy_fallbacks_preserved": True,
    }


def identity_library():
    from neo4j import GraphDatabase

    from agent_native_graph import connect_neo4j

    uri = os.environ["ANA_TEST_GRAPH_URI"]
    options = {
        "database": "neo4j",
        "identity_mode": "transaction",
        "workflow_timeout_s": 120,
        "query_timeout_s": 120,
    }
    with connect_neo4j(uri, "neo4j", "ana-disposable-test", **options) as graph:
        report = identity_checks(graph.call)
        bound = graph.call("node_scan", {"label": "Probe", "as": "p", "limit": 10})
        with GraphDatabase.driver(uri, auth=("neo4j", "ana-disposable-test")) as writer:
            with writer.session(database="neo4j") as session:
                session.run("MATCH (n:Probe {marker: 'a'}) SET n.id = 'changed'").consume()
        expanded = graph.call(
            "expand",
            {
                "from": bound["handle"],
                "source": "p",
                "as": "t",
                "relationship_type": "POINTS_TO",
                "target_label": "Endpoint",
                "direction": "out",
            },
        )
        assert expanded["matched_count"] == 3
        tombstone = graph.call("node_scan", {"label": "Tombstone", "as": "n", "limit": 1})
        with GraphDatabase.driver(uri, auth=("neo4j", "ana-disposable-test")) as writer:
            with writer.session(database="neo4j") as session:
                session.run("MATCH (n:Probe {marker: 'a'}) SET n.id = 'duplicate'").consume()
                session.run("MATCH (n:Tombstone) DELETE n").consume()
                session.run("CREATE (:Tombstone {id: 'replaceable', marker: 'new'})").consume()
        try:
            graph.call("fetch", {"from": tombstone["handle"]})
        except ValueError as exc:
            assert "create a new workflow" in str(exc)
        else:
            raise AssertionError("Deleted node was silently replaced")
        try:
            graph.call("count_nodes", {"label": "Probe"})
        except ValueError as exc:
            assert "invalid" in str(exc)
        else:
            raise AssertionError("Invalid transaction was silently reopened")
    return report | {"changed_property_id": True, "deleted_node_invalidates": True}


def library():
    """Assert wheel provenance, workflow isolation and cleanup on success/failure."""
    import agent_native_graph
    from agent_native_graph import connect_neo4j, get_tool_specs

    package = Path(agent_native_graph.__file__).resolve()
    assert package.is_relative_to(Path(sys.prefix).resolve()), package
    assert not Path("src").exists() and not Path("data").exists()
    assert not Path("downloads").exists()
    assert not any(key in os.environ for key in ("API_KEY", "API_KEY_FILE", "ANA_SCHEMA_JSON"))
    assert get_tool_specs()
    uri = os.environ["ANA_TEST_GRAPH_URI"]
    with connect_neo4j(uri, "neo4j", "ana-disposable-test", database="neo4j") as first:
        report = exercise(first.call)
        handle = first.call("count_nodes", {"label": "Device"})["handle"]
        with connect_neo4j(uri, "neo4j", "ana-disposable-test", database="neo4j") as second:
            second.call("count_nodes", {"label": "Device"})
            try:
                second.call("fetch", {"from": handle})
            except ValueError as exc:
                assert "Unknown handle" in str(exc)
            else:
                raise AssertionError("Handle leaked across workflows")
        # Scalar access is valid without id; traversal still requires an id.
        unkeyed = first.call("node_scan", {"label": "Unkeyed", "as": "u", "limit": 1})
        assert first.call("count_nodes", {"label": "Unkeyed"})["matched_count"] == 1
        try:
            first.call(
                "expand",
                {
                    "from": unkeyed["handle"],
                    "source": "u",
                    "relationship_type": "LOCATED_IN",
                    "target_label": "Zone",
                    "direction": "out",
                },
            )
        except KeyError as exc:
            assert exc.args == ("id",)
        else:
            raise AssertionError("Revisit the documented id limitation")
    try:
        first.call("schema_overview", {})
    except RuntimeError as exc:
        assert "closed" in str(exc)
    else:
        raise AssertionError("Closed workflow accepted a call")
    try:
        with connect_neo4j(uri, "neo4j", "ana-disposable-test", database="neo4j") as failed:
            raise LookupError("intentional client failure")
    except LookupError:
        try:
            failed.call("schema_overview", {})
        except RuntimeError as exc:
            assert "closed" in str(exc)
        else:
            raise AssertionError("Exception path did not close the workflow")
    assert not any(name.startswith("agent_native_graph.llm_providers") for name in sys.modules)
    assert not any(name.startswith("agent_native_graph.research") for name in sys.modules)
    return report | {"wheel_import": True, "isolated_workflows": True, "close_on_error": True}


def http(transaction=False):
    """Exercise the shipped container through real HTTP, not an ASGI fake."""
    import httpx

    from agent_native_graph import get_tool_specs

    config = json.loads(Path(os.environ["ANA_TEST_AUTH_FILE"]).read_text())
    credentials = [{"Authorization": "Bearer " + item["api_key"]} for item in config["clients"]]
    with httpx.Client(base_url=os.environ["ANA_TEST_SERVICE_URL"], timeout=60) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/tools/specs").status_code == 401
        assert (
            client.get("/tools/specs", headers=credentials[0]).json()["tools"] == get_tool_specs()
        )
        tokens = []
        for headers in credentials:
            response = client.post("/sessions", headers=headers)
            response.raise_for_status()
            tokens.append(response.json()["session_id"])
        headers = [
            cred | {"X-ANA-Session": token} for cred, token in zip(credentials, tokens, strict=True)
        ]

        def call(tool, args):
            response = client.post(
                "/tools/call", headers=headers[0], json={"tool": tool, "args": args}
            )
            response.raise_for_status()
            return response.json()["result"]

        if transaction:
            report = identity_checks(call)
            for session_headers in headers:
                assert (
                    client.delete("/sessions/current", headers=session_headers).status_code == 204
                )
            return report
        first_handle = call("count_nodes", {"label": "Device"})["handle"]
        second_count = client.post(
            "/tools/call",
            headers=headers[1],
            json={"tool": "count_nodes", "args": {"label": "Device"}},
        )
        second_count.raise_for_status()
        assert first_handle != second_count.json()["result"]["handle"]
        foreign_first = client.post(
            "/tools/call",
            headers=headers[1],
            json={"tool": "fetch", "args": {"from": first_handle}},
        )
        assert foreign_first.status_code == 400 and "Unknown handle" in foreign_first.text
        report = exercise(call)
        assert client.post("/sessions", headers=credentials[0]).status_code == 429
        handle = call("count_nodes", {"label": "Device"})["handle"]
        payload = {"tool": "fetch", "args": {"from": handle}}
        foreign = client.post("/tools/call", headers=headers[1], json=payload)
        assert foreign.status_code == 400 and "Unknown handle" in foreign.text
        stolen = credentials[1] | {"X-ANA-Session": tokens[0]}
        assert client.post("/tools/call", headers=stolen, json=payload).status_code == 404
        assert client.delete("/sessions/current", headers=stolen).status_code == 404
        assert call("fetch", {"from": handle})["rows"] == [[25]]
        invalid = client.post(
            "/tools/call", headers=headers[0], json={"tool": "fetch", "args": {"from": "missing"}}
        )
        assert invalid.status_code == 400
        for session_headers in headers:
            assert client.delete("/sessions/current", headers=session_headers).status_code == 204
            assert (
                client.post("/tools/call", headers=session_headers, json=payload).status_code == 404
            )
        fresh = client.post("/sessions", headers=credentials[0])
        fresh.raise_for_status()
        assert (
            client.delete(
                "/sessions/current",
                headers=credentials[0] | {"X-ANA-Session": fresh.json()["session_id"]},
            ).status_code
            == 204
        )
    return report | {
        "authenticated_http": True,
        "isolated_sessions": True,
        "capacity_released": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=("library", "http", "identity", "identity-http", "finalization")
    )
    args = parser.parse_args()
    runners = {
        "library": library,
        "http": http,
        "identity": identity_library,
        "identity-http": lambda: http(transaction=True),
        "finalization": finalization,
    }
    print(json.dumps(runners[args.mode](), sort_keys=True))
