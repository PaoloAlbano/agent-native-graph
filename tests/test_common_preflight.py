"""Shared preflight tests: all database traffic is fake."""

import asyncio
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from neo4j import READ_ACCESS, Query
from neo4j.time import Date

from agent_native_graph.research import common_preflight as preflight
from agent_native_graph.research.load_simplekg_neo4j import load_simplekg


class AsyncRows:
    def __init__(self, rows):
        self.rows = iter(rows)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.rows)
        except StopIteration:
            raise StopAsyncIteration from None


class Session:
    def __init__(self, driver):
        self.driver = driver

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def run(self, query):
        assert isinstance(query, Query)
        assert query.timeout == self.driver.timeout
        self.driver.queries.append(query.text)
        return copy.deepcopy(self.driver.rows[query.text])


class AsyncSession(Session):
    async def run(self, query):
        return AsyncRows(super().run(query))


class Driver:
    def __init__(self, rows, *, asynchronous=False, timeout=17):
        self.rows = rows
        self.asynchronous = asynchronous
        self.timeout = timeout
        self.queries = []
        self.options = []

    def session(self, **kwargs):
        self.options.append(kwargs)
        return (AsyncSession if self.asynchronous else Session)(self)


def invoke(rows, graph, asynchronous=False, **kwargs):
    driver = Driver(rows, asynchronous=asynchronous)
    function = preflight.prepare_preflight_async if asynchronous else preflight.prepare_preflight
    result = function(driver, "benchmark", graph, query_timeout_s=17, **kwargs)
    if asynchronous:
        result = asyncio.run(result)
    assert driver.options == [
        {"database": "benchmark", "default_access_mode": READ_ACCESS, "fetch_size": 2000}
    ]
    assert driver.queries == [preflight._NODES, preflight._EDGES, *preflight._METADATA.values()]
    return result


@pytest.fixture
def fixture(tmp_path):
    graph = tmp_path / "graph.json"
    graph.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "secret-a",
                        "labels": ["Person", "Mixed:Case"],
                        "properties": {
                            "name": "private-name",
                            "date_birth": "2001-02-03",
                            "scores": [1, 2],
                            "gone": None,
                        },
                    },
                    {"id": "secret-b", "labels": ["Person"]},
                    {"id": "secret-c"},
                ],
                "edges": [
                    {
                        "source": "secret-a",
                        "target": "secret-b",
                        "type": "HAS`ROLE:in",
                        "properties": {"when": "private-edge", "gone": None},
                    }
                ],
            }
        )
    )
    loaded = load_simplekg(graph)
    nodes = [
        {
            "labels": sorted(set(["Entity", *node["labels"]])),
            "props": {key: value for key, value in node["properties"].items() if value is not None},
        }
        for node in loaded["nodes"]
    ]
    edges = [
        {
            "source": edge["source_id"],
            "target": edge["target_id"],
            "type": edge["type"],
            "props": {key: value for key, value in edge["properties"].items() if value is not None},
        }
        for edge in loaded["edges"]
    ]
    node_properties = []
    for node in nodes:
        for name in node["props"]:
            node_properties.append(
                {
                    "nodeType": "ignored spelling",
                    "nodeLabels": node["labels"],
                    "propertyName": name,
                    "propertyTypes": {"date_birth": ["Date"], "scores": ["LongArray"]}.get(
                        name, ["String"]
                    ),
                    "mandatory": True,
                }
            )
    rel_type = ":`HAS``ROLE:in`"
    metadata = {
        "labels": [
            {"label": label}
            for label in sorted({label for node in nodes for label in node["labels"]})
        ],
        "relationship_types": [{"relationshipType": "HAS`ROLE:in"}],
        "node_properties": node_properties,
        "relationship_properties": [
            {
                "relType": rel_type,
                "propertyName": key,
                "propertyTypes": ["String"],
                "mandatory": True,
            }
            for key in edges[0]["props"]
        ],
        "label_relationships": [
            {"source_label": source, "relationship_type": edges[0]["type"], "target_label": target}
            for source in nodes[0]["labels"]
            for target in nodes[1]["labels"]
        ],
    }
    rows = {preflight._NODES: nodes, preflight._EDGES: edges}
    rows.update({query: metadata[key] for key, query in preflight._METADATA.items()})
    return graph, rows


@pytest.mark.parametrize("asynchronous", [False, True])
def test_content_only_postcheck_reuses_full_fingerprint_without_schema_queries(
    fixture, asynchronous
):
    graph, rows = fixture
    driver = Driver(rows, asynchronous=asynchronous)
    if asynchronous:
        actual = asyncio.run(
            preflight.graph_snapshot_async(driver, "benchmark", query_timeout_s=17)
        )
    else:
        actual = preflight.graph_snapshot(driver, "benchmark", query_timeout_s=17)
    assert actual == preflight.expected_snapshot(graph)
    assert driver.queries == [preflight._NODES, preflight._EDGES]
    assert driver.options == [
        {"database": "benchmark", "default_access_mode": READ_ACCESS, "fetch_size": 2000}
    ]


def test_sync_async_identical_and_value_free(fixture):
    graph, rows = fixture
    result = invoke(rows, graph)
    assert result == invoke(rows, graph, True)
    assert set(result) == {
        "version",
        "database",
        "graph_sha256",
        "snapshot",
        "schema",
        "schema_sha256",
        "schema_prompt",
        "schema_prompt_sha256",
    }
    assert result["version"] == "shared-preflight-v1"
    assert result["snapshot"] == preflight.expected_snapshot(graph)
    assert result["graph_sha256"] == hashlib.sha256(graph.read_bytes()).hexdigest()
    assert result["schema_sha256"] == result["schema_prompt_sha256"]
    assert result["schema_sha256"] == hashlib.sha256(result["schema_prompt"].encode()).hexdigest()
    assert json.loads(result["schema_prompt"]) == result["schema"]
    for secret in ("private-name", "secret-a", "private-edge", "2001-02-03"):
        assert secret not in result["schema_prompt"]
    assert "Mixed_Case" in result["schema"]["labels"]  # Loader's label normalization.
    assert "LongArray" in result["schema_prompt"]
    assert "Date" in result["schema_prompt"]


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize(
    "mutation",
    [
        "property",
        "rewire",
        "missing_node",
        "extra_node",
        "duplicate_node",
        "missing_edge",
        "duplicate_edge",
        "edge_property",
        "label",
    ],
)
def test_content_mismatch_before_metadata(fixture, asynchronous, mutation):
    graph, rows = fixture
    if mutation == "property":
        rows[preflight._NODES][0]["props"]["name"] = "changed"
    elif mutation == "rewire":
        rows[preflight._EDGES][0]["target"] = "secret-c"
    elif mutation == "missing_node":
        rows[preflight._NODES].pop()
    elif mutation in ("extra_node", "duplicate_node"):
        rows[preflight._NODES].append(copy.deepcopy(rows[preflight._NODES][0]))
        if mutation == "extra_node":
            rows[preflight._NODES][-1]["props"]["id"] = "new"
    elif mutation == "missing_edge":
        rows[preflight._EDGES].clear()
    elif mutation == "duplicate_edge":
        rows[preflight._EDGES] *= 2
    elif mutation == "edge_property":
        rows[preflight._EDGES][0]["props"]["when"] = "changed"
    else:
        rows[preflight._NODES][0]["labels"].append("Other")
    driver = Driver(rows, asynchronous=asynchronous)
    with pytest.raises(ValueError, match="Graph content mismatch"):
        if asynchronous:
            asyncio.run(
                preflight.prepare_preflight_async(driver, "benchmark", graph, query_timeout_s=17)
            )
        else:
            preflight.prepare_preflight(driver, "benchmark", graph, query_timeout_s=17)
    assert driver.queries == [preflight._NODES, preflight._EDGES]


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("collection", list(preflight._METADATA))
def test_truncated_metadata_fails_closed(fixture, asynchronous, collection):
    graph, rows = fixture
    rows[preflight._METADATA[collection]] = []
    with pytest.raises(ValueError):
        invoke(rows, graph, asynchronous)


@pytest.mark.parametrize("asynchronous", [False, True])
def test_malformed_metadata(fixture, asynchronous):
    graph, rows = fixture
    del rows[preflight._METADATA["node_properties"]][0]["mandatory"]
    with pytest.raises(ValueError):
        invoke(rows, graph, asynchronous)


def test_order_duplicates_stable(fixture):
    graph, rows = fixture
    expected = invoke(rows, graph)
    for query in rows:
        rows[query].reverse()
        if query in preflight._METADATA.values():
            rows[query] *= 2
    assert invoke(rows, graph) == expected
    assert invoke(rows, graph, True) == expected


def test_canonical_punctuation_typeless_unknown():
    raw = {key: [] for key in preflight._METADATA}
    raw["labels"] = ["lower:Case", "a`b", "lower:Case", "Empty"]
    raw["relationship_types"] = ["a`b:REL"]
    raw["node_properties"] = [
        {
            "nodeType": ":anything",
            "nodeLabels": ["lower:Case", "a`b"],
            "propertyName": "x",
            "propertyTypes": ["List<Date>", "String", "String"],
            "mandatory": False,
        },
        {
            "nodeType": "",
            "nodeLabels": [],
            "propertyName": "unknown",
            "propertyTypes": None,
            "mandatory": None,
        },
        {
            "nodeType": ":Empty",
            "nodeLabels": ["Empty"],
            "propertyName": None,
            "propertyTypes": [],
            "mandatory": None,
        },
    ]
    raw["relationship_properties"] = [
        {
            "relType": ":`a``b:REL`",
            "propertyName": "t",
            "propertyTypes": ["LocalDateTime", "DurationArray"],
            "mandatory": None,
        }
    ]
    schema = preflight.canonical_schema(raw)
    assert "lower:Case" in schema["labels"]
    assert any(row["nodeType"] == ":`a``b`:`lower:Case`" for row in schema["node_properties"])
    assert any(
        row["nodeType"] == "" and row["mandatory"] is None and row["propertyTypes"] == []
        for row in schema["node_properties"]
    )
    assert preflight.canonical_schema(schema) == schema
    assert preflight.schema_digest(raw) == preflight.schema_digest(schema)
    changed = copy.deepcopy(schema)
    changed["node_properties"][0]["mandatory"] = True
    assert preflight.schema_digest(changed) != preflight.schema_digest(schema)


def test_empty_graph(tmp_path):
    graph = tmp_path / "empty.json"
    graph.write_text('{"nodes": [], "edges": []}')
    rows = {
        query: [] for query in [preflight._NODES, preflight._EDGES, *preflight._METADATA.values()]
    }
    result = invoke(rows, graph)
    assert result == invoke(rows, graph, True)
    assert result["schema"] == {key: [] for key in preflight._METADATA}


@pytest.mark.parametrize(
    "database,timeout",
    [(None, 1), ("", 1), ("  ", 1), ("x", 0), ("x", -1), ("x", float("nan")), ("x", True)],
)
def test_invalid_options_before_session(fixture, database, timeout):
    graph, rows = fixture
    driver = Driver(rows)
    with pytest.raises(ValueError):
        preflight.prepare_preflight(driver, database, graph, query_timeout_s=timeout)
    assert not driver.options


def test_date_null_fingerprint(fixture):
    graph, rows = fixture
    assert rows[preflight._NODES][0]["props"]["date_birth"] == Date(2001, 2, 3)
    assert "gone" not in rows[preflight._NODES][0]["props"]
    assert preflight.fingerprint([[Date(2001, 2, 3), None]]) == preflight.fingerprint(
        [["2001-02-03", None]]
    )
    assert preflight.fingerprint([1, 1]) != preflight.fingerprint([1])


@pytest.mark.parametrize("change", ["missing", "bad_list", "bad_bool", "conflict", "escaping"])
def test_canonical_malformed(fixture, change):
    graph, rows = fixture
    schema = invoke(rows, graph)["schema"]
    if change == "missing":
        del schema["labels"]
    elif change == "bad_list":
        schema["node_properties"][0]["propertyTypes"] = "String"
    elif change == "bad_bool":
        schema["node_properties"][0]["mandatory"] = "false"
    elif change == "conflict":
        schema["node_properties"].append(dict(schema["node_properties"][0], mandatory=False))
    else:
        schema["relationship_properties"][0]["relType"] = ":`bad`escape`"
    with pytest.raises(ValueError):
        preflight.canonical_schema(schema)


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("change", ["bytes", "identity"])
def test_graph_changes_during_expected_snapshot(fixture, monkeypatch, asynchronous, change):
    graph, rows = fixture
    if change == "bytes":
        loader = preflight.load_simplekg

        def changing_loader(path):
            normalized = loader(path)
            path.write_bytes(path.read_bytes() + b" ")
            return normalized

        monkeypatch.setattr(preflight, "load_simplekg", changing_loader)
    else:
        # Equal bytes do not hide a detected identity/mtime change.
        original_stat = Path.stat
        calls = 0

        def changed_stat(path, **kwargs):
            nonlocal calls
            stat = original_stat(path, **kwargs)
            if path != graph:
                return stat
            calls += 1
            return SimpleNamespace(
                st_dev=stat.st_dev,
                st_ino=stat.st_ino,
                st_size=stat.st_size,
                st_mtime_ns=stat.st_mtime_ns + calls,
                st_ctime_ns=stat.st_ctime_ns,
            )

        monkeypatch.setattr(Path, "stat", changed_stat)
    driver = Driver(rows, asynchronous=asynchronous)
    with pytest.raises(ValueError, match="Graph file changed"):
        if asynchronous:
            asyncio.run(
                preflight.prepare_preflight_async(driver, "benchmark", graph, query_timeout_s=17)
            )
        else:
            preflight.prepare_preflight(driver, "benchmark", graph, query_timeout_s=17)
    assert driver.options == []
    assert driver.queries == []


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize(
    "reference", ["node_label", "rel_type", "endpoint_source", "endpoint_target", "endpoint_type"]
)
def test_unknown_schema_references(fixture, asynchronous, reference):
    graph, rows = fixture
    if reference == "node_label":
        row = rows[preflight._METADATA["node_properties"]][0]
        row["nodeLabels"] = [*row["nodeLabels"], "Unknown:Label`"]
    elif reference == "rel_type":
        rows[preflight._METADATA["relationship_properties"]][0]["relType"] = ":`Unknown``:REL`"
    else:
        key = {
            "endpoint_source": "source_label",
            "endpoint_target": "target_label",
            "endpoint_type": "relationship_type",
        }[reference]
        rows[preflight._METADATA["label_relationships"]][0][key] = "Unknown:identifier`"
    raw = {key: copy.deepcopy(rows[query]) for key, query in preflight._METADATA.items()}
    raw["labels"] = [row["label"] for row in raw["labels"]]
    raw["relationship_types"] = [row["relationshipType"] for row in raw["relationship_types"]]
    with pytest.raises(ValueError, match="references unknown schema"):
        preflight.canonical_schema(raw)
    with pytest.raises(ValueError, match="references unknown schema"):
        invoke(rows, graph, asynchronous)


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("kind", ["node", "relationship"])
@pytest.mark.parametrize("mandatory", [True, False, None])
def test_mandatory_against_live_values(fixture, asynchronous, kind, mandatory):
    graph, rows = fixture
    payload = json.loads(graph.read_text())
    if kind == "node":
        payload["nodes"].append(
            {"id": "secret-d", "labels": ["Person"], "properties": {"optional": "value"}}
        )
        rows[preflight._NODES].append(
            {
                "labels": ["Entity", "Person"],
                "props": {"id": "secret-d", "eid": "secret-d", "optional": "value"},
            }
        )
        rows[preflight._METADATA["node_properties"]].append(
            {
                "nodeType": ":`Entity`:`Person`",
                "nodeLabels": ["Entity", "Person"],
                "propertyName": "optional",
                "propertyTypes": ["String"],
                "mandatory": mandatory,
            }
        )
    else:
        payload["edges"].append(
            {
                "id": "edge-without-when",
                "source": "secret-a",
                "target": "secret-c",
                "type": "HAS`ROLE:in",
            }
        )
        rows[preflight._EDGES].append(
            {
                "source": "secret-a",
                "target": "secret-c",
                "type": "HAS`ROLE:in",
                "props": {"id": "edge-without-when"},
            }
        )
        for row in rows[preflight._METADATA["relationship_properties"]]:
            if row["propertyName"] == "when":
                row["mandatory"] = mandatory
    graph.write_text(json.dumps(payload))
    if mandatory is True:
        with pytest.raises(ValueError, match="Mandatory property absent"):
            invoke(rows, graph, asynchronous)
    else:
        result = invoke(rows, graph, asynchronous)
        assert result == invoke(rows, graph, not asynchronous)


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize(
    "property_name,declared",
    [("name", ["Long"]), ("scores", ["StringArray"]), ("when", ["Boolean"])],
)
def test_reliably_known_type_contradictions(fixture, asynchronous, property_name, declared):
    graph, rows = fixture
    collection = "relationship_properties" if property_name == "when" else "node_properties"
    for row in rows[preflight._METADATA[collection]]:
        if row["propertyName"] == property_name:
            row["propertyTypes"] = declared
    with pytest.raises(ValueError, match="Property types contradict"):
        invoke(rows, graph, asynchronous)


@pytest.mark.parametrize(
    "declared", [[], None, ["UnrecognizedType"], ["String", "UnrecognizedType"]]
)
def test_unknown_types_are_not_guessed(fixture, declared):
    graph, rows = fixture
    for row in rows[preflight._METADATA["node_properties"]]:
        if row["propertyName"] == "scores":
            row["propertyTypes"] = declared
    assert invoke(rows, graph) == invoke(rows, graph, True)


@pytest.mark.parametrize(
    "value,expected",
    [
        (True, "Boolean"),
        (42, "Long"),
        (1.5, "Double"),
        ("text", "String"),
        ([True, False], "BooleanArray"),
        ([1, 2], "LongArray"),
        ([1.0, 2.0], "DoubleArray"),
        (["a", "b"], "StringArray"),
        ([], None),
        ([1, 2.0], None),
        (Date(2001, 2, 3), None),
        (None, None),
    ],
)
def test_type_inference_is_narrow(value, expected):
    assert preflight._known_property_type(value) == expected
