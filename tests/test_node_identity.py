"""Opaque identity is workflow-local; historical property identity remains unchanged."""

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from agent_native_graph.backends.neo4j import backend, identity
from agent_native_graph.core.graph_utils import (
    _distinct_rows,
    _distinct_rows_by_selected_entities,
    _is_node_payload,
    _metric_identity,
    _node_payload,
)
from agent_native_graph.domain.entities import EntityReference, entity_references


class Node(dict):
    labels = ["Device"]

    def __init__(self, key, **properties):
        super().__init__(properties)
        self.element_id = key


class Transaction:
    def __init__(self):
        self.nodes = [
            Node("node-1", id="duplicate"),
            Node("node-2", id="duplicate"),
            Node("node-3"),
        ]
        self.alive = {node.element_id for node in self.nodes}
        self.queries = []
        self.is_closed = False
        self.failure = None

    def run(self, query, **params):
        self.queries.append((query, params))
        if self.failure:
            raise self.failure
        if "RETURN elementId(n) AS key" in query:
            return [{"key": key} for key in params["keys"] if key in self.alive]
        assert query == "MATCH (n:`Device`) RETURN n LIMIT $limit"
        return [{"n": node} for node in self.nodes]

    def rollback(self):
        self.is_closed = True

    def closed(self):
        return self.is_closed


@pytest.fixture
def graph(monkeypatch):
    driver, session, tx = MagicMock(), MagicMock(), Transaction()
    driver.session.return_value = session
    session.begin_transaction.return_value = tx
    monkeypatch.setattr(backend.GraphDatabase, "driver", lambda *a, **kw: driver)
    graph = backend.Neo4jGraphBackend(
        "bolt://example.invalid",
        "reader",
        "test-only",
        {"labels": ["Device"]},
        identity_mode="transaction",
        query_timeout_s=30,
    )
    yield graph, tx, session, driver
    graph.close()


def scan(graph):
    return graph.call("node_scan", {"label": "Device", "as": "d", "limit": 3})


def test_private_identity_never_changes_json_or_properties(graph):
    g, tx, session, _ = graph
    handle = scan(g)
    payloads = [row["d"] for row in g._handle(handle["handle"]).rows]
    assert all(_is_node_payload(p) for p in payloads)
    assert payloads[0]["properties"]["id"] == payloads[1]["properties"]["id"] == "duplicate"
    assert "id" not in payloads[2]["properties"]
    assert len({_metric_identity({"d": p}, "d") for p in payloads}) == 3
    assert all(set(p) == {"labels", "properties"} for p in payloads)
    assert "node-1" not in json.dumps(payloads)
    copied = deepcopy(payloads[0])
    assert copied.reference == payloads[0].reference
    session.begin_transaction.assert_called_once_with(timeout=30)
    scan(g)
    session.begin_transaction.assert_called_once()
    assert all(isinstance(q, str) for q, _ in tx.queries)


def test_distinct_uses_real_entity_identity_not_duplicate_properties(graph):
    g, *_ = graph
    result = scan(g)
    rows = g._handle(result["handle"]).rows
    assert len(_distinct_rows(rows + rows, use_references=True)) == 3
    assert len(_distinct_rows_by_selected_entities(rows + rows, [{"var": "d"}])) == 3
    count = g.call("count_handle", {"from": result["handle"], "var": "d", "distinct": True})
    assert g.call("fetch", {"from": count["handle"]})["rows"] == [[3]]


@pytest.mark.parametrize("var", [None, "d"])
@pytest.mark.parametrize("distinct", [False, True])
def test_count_handle_uses_transaction_identity_with_or_without_a_variable(graph, var, distinct):
    g, *_ = graph
    scanned = scan(g)
    rows = g._handle(scanned["handle"]).rows
    source = g._store(rows + rows, focus="d")
    args = {"from": source["handle"], "distinct": distinct, "alias": "total"}
    if var is not None:
        args["var"] = var
    counted = g.call("count_handle", args)
    assert g.call("fetch", {"from": counted["handle"]})["rows"] == [[3 if distinct else 6]]


def test_distinct_whole_rows_treat_cached_versions_of_the_same_entity_as_one(graph):
    g, *_ = graph
    scanned = scan(g)
    row = g._handle(scanned["handle"]).rows[0]
    changed = deepcopy(row)
    changed["d"]["properties"]["marker"] = "new cached value"
    source = g._store([row, changed], focus="d")
    counted = g.call("count_handle", {"from": source["handle"], "distinct": True})
    assert g.call("fetch", {"from": counted["handle"]})["rows"] == [[1]]


def test_distinct_whole_rows_preserves_legacy_scalar_semantics():
    g = backend.Neo4jGraphBackend.__new__(backend.Neo4jGraphBackend)
    g._driver = MagicMock()
    g.last_fetch = None
    try:
        source = g._store(
            [{"value": {"nested": [1]}}, {"value": {"nested": [1]}}, {"value": {"nested": [2]}}],
            kind="table",
            columns=["value"],
        )
        for distinct, expected in ((False, 3), (True, 2)):
            counted = g.call("count_handle", {"from": source["handle"], "distinct": distinct})
            assert g.call("fetch", {"from": counted["handle"]})["rows"] == [[expected]]
    finally:
        g.close()


def test_identity_joins_filters_and_sets_do_not_match_duplicate_business_ids(graph):
    g, *_ = graph
    scanned = scan(g)
    nodes = [row["d"] for row in g._handle(scanned["handle"]).rows]
    left = g._store([{"a": nodes[0]}], focus="a")["handle"]
    right = g._store([{"b": nodes[1]}], focus="b")["handle"]
    joined = g.call(
        "join_handles",
        {"left": left, "right": right, "left_var": "a", "right_var": "b", "op": "inner"},
    )
    assert joined["matched_count"] == 0
    both = g._store([{"a": nodes[0], "b": nodes[1]}], focus="a")["handle"]
    filtered = g.call("filter_same_node", {"from": both, "left_var": "a", "right_var": "b"})
    assert filtered["matched_count"] == 0
    union = g.call(
        "entity_set_operation",
        {"op": "union", "operands": [{"handle": left, "var": "a"}, {"handle": right, "var": "b"}]},
    )
    assert union["matched_count"] == 2


def test_identity_settings_are_validated_and_environment_is_snapshotted(monkeypatch):
    from agent_native_graph.backends.neo4j.config import Neo4jConfig

    monkeypatch.setenv("ANA_NEO4J_IDENTITY_MODE", "transaction")
    monkeypatch.setenv("ANA_NEO4J_WORKFLOW_TIMEOUT_S", "37")
    config = Neo4jConfig.from_env()
    monkeypatch.setenv("ANA_NEO4J_IDENTITY_MODE", "property")
    assert config.identity_mode == "transaction" and config.workflow_timeout_s == 37
    with pytest.raises(ValueError, match="identity_mode"):
        Neo4jConfig(identity_mode="guess")
    with pytest.raises(ValueError, match="workflow_timeout_s"):
        Neo4jConfig(workflow_timeout_s=0)


def test_deletion_invalidates_even_cached_fetch_and_never_rebinds(graph):
    g, tx, session, _ = graph
    handle = scan(g)["handle"]
    tx.alive.remove("node-1")
    with pytest.raises(identity.StaleWorkflowError, match="deleted"):
        g.call("fetch", {"from": handle})
    assert not g._handles and tx.closed()
    session.close.assert_called_once()
    tx.alive.add("node-1")
    with pytest.raises(identity.StaleWorkflowError, match="invalid"):
        scan(g)
    session.begin_transaction.assert_called_once()


def test_timeout_is_terminal_and_does_not_open_another_transaction(graph, monkeypatch):
    g, tx, _, _ = graph
    monkeypatch.setattr(identity.time, "monotonic", lambda: 1)
    handle = scan(g)["handle"]
    monkeypatch.setattr(identity.time, "monotonic", lambda: 32)
    with pytest.raises(identity.StaleWorkflowError, match="timed out"):
        g.call("fetch", {"from": handle})
    assert tx.closed() and not g._handles


def test_metadata_only_handles_do_not_bypass_deleted_ancestor_validation(graph):
    g, tx, *_ = graph
    scan(g)
    scalar = g._store([{"count": 3}], kind="table", columns=["count"])
    tx.alive.remove("node-2")
    with pytest.raises(identity.StaleWorkflowError, match="deleted"):
        g.call("fetch", {"from": scalar["handle"]})


def test_explicit_close_is_idempotent_and_cannot_reopen_identity(graph):
    g, tx, session, driver = graph
    scan(g)
    g.close()
    g.close()
    assert tx.closed() and not g._handles and not g._identity.keys
    driver.close.assert_called_once()
    session.close.assert_called_once()
    with pytest.raises(identity.StaleWorkflowError):
        with g._identity.queries():
            pass


@pytest.mark.parametrize("failure", [Neo4jError("failed"), ServiceUnavailable("failed")])
def test_transaction_error_invalidates_but_argument_errors_do_not(graph, failure):
    g, tx, *_ = graph
    scan(g)
    with pytest.raises(ValueError, match="requires"):
        g.call("expand", {})
    assert not tx.closed()
    tx.failure = failure
    with pytest.raises(identity.StaleWorkflowError, match="transaction failed"):
        scan(g)
    assert tx.closed() and not g._handles


def test_foreign_reference_is_rejected(graph):
    g, *_ = graph
    other = identity.TransactionIdentity(MagicMock(), "neo4j", 30, lambda: None)
    other.transaction = MagicMock()
    with entity_references(other.reference):
        payload = _node_payload(Node("node-1"))
    handle = g._store([{"d": payload}], focus="d")
    with pytest.raises(ValueError, match="another workflow"):
        g.call("fetch", {"from": handle["handle"]})


def test_legacy_payload_bytes_and_property_identity_remain_unchanged():
    node = Node("internal-key", id="business-id")
    payload = _node_payload(node)
    assert type(payload) is dict
    assert _metric_identity({"d": payload}, "d") == "business-id"
    assert payload == {"labels": ["Device"], "properties": {"id": "business-id"}}
    assert not _is_node_payload(_node_payload(Node("no-id")))


def test_reference_decoding_scope_is_nested_and_always_restored():
    node = Node("same-element", marker="visible")
    with entity_references(lambda n: EntityReference("outer", n.element_id)):
        outer = _node_payload(node)
        with pytest.raises(LookupError):
            with entity_references(lambda n: EntityReference("inner", n.element_id)):
                assert _node_payload(node).reference.owner == "inner"
                raise LookupError("abort inner call")
        assert _node_payload(node).reference == outer.reference
    assert type(_node_payload(node)) is dict


def test_tool_and_prompt_hashes_match_the_frozen_archived_treatment():
    from agent_native_graph.application.run_config import execution_identity

    root = Path(__file__).resolve().parents[1]
    archived = next(
        (root / "results/cypherbench-company/full/runs").glob(
            "*gpt-oss-20b_temp0_reasoning-none*/run-config.json"
        )
    )
    expected = json.loads(archived.read_text())["identity"]
    actual = execution_identity(
        SimpleNamespace(native_tools=True, enable_planning_tools=False, schema_entry="overview"),
        root,
    )
    assert actual["tools_sha256"] == expected["tools_sha256"]
    assert actual["system_prompt_sha256"] == expected["system_prompt_sha256"]
