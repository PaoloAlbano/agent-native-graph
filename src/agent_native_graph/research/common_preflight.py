"""Read-only graph-content fingerprints and shared initial schema evidence.

This is not an atomic snapshot or a concurrent-writer exclusion protocol.
"""

import hashlib
import json
import math
from pathlib import Path

from neo4j import READ_ACCESS, Query

from agent_native_graph.research.load_simplekg_neo4j import load_simplekg

_NODES = "MATCH (n) RETURN labels(n) AS labels, properties(n) AS props"
_EDGES = (
    "MATCH (a)-[r]->(b) RETURN a.id AS source, type(r) AS type, "
    "b.id AS target, properties(r) AS props"
)
_METADATA = {
    "labels": "CALL db.labels() YIELD label RETURN label",
    "relationship_types": (
        "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType"
    ),
    "node_properties": (
        "CALL db.schema.nodeTypeProperties() "
        "YIELD nodeType, nodeLabels, propertyName, propertyTypes, mandatory "
        "RETURN nodeType, nodeLabels, propertyName, propertyTypes, mandatory"
    ),
    "relationship_properties": (
        "CALL db.schema.relTypeProperties() "
        "YIELD relType, propertyName, propertyTypes, mandatory "
        "RETURN relType, propertyName, propertyTypes, mandatory"
    ),
    "label_relationships": (
        "MATCH (source)-[rel]->(target) "
        "UNWIND labels(source) AS source_label UNWIND labels(target) AS target_label "
        "RETURN DISTINCT source_label, type(rel) AS relationship_type, target_label"
    ),
}


def _json(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize(value):
    # Match research_common's snapshot normalization without importing model clients.
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    return value


def fingerprint(items):
    """Hash a sorted multiset, including duplicate multiplicity."""
    hashes = sorted(hashlib.sha256(_json(_normalize(item)).encode()).digest() for item in items)
    return {"count": len(hashes), "sha256": hashlib.sha256(b"".join(hashes)).hexdigest()}


def expected_snapshot(graph: Path) -> dict:
    normalized = load_simplekg(graph)

    def properties(props):
        return {key: value for key, value in props.items() if value is not None}

    return {
        "nodes": fingerprint(
            [sorted(set(["Entity", *node["labels"]])), properties(node["properties"])]
            for node in normalized["nodes"]
        ),
        "edges": fingerprint(
            [edge["source_id"], edge["type"], edge["target_id"], properties(edge["properties"])]
            for edge in normalized["edges"]
        ),
    }


def _graph_evidence(graph):
    # The loader reads the path independently. Bracket that read with both byte
    # hashes and stat identity checks, including changes restored to equal bytes.
    def identity():
        stat = graph.stat()
        return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)

    before = identity()
    graph_hash = hashlib.sha256(graph.read_bytes()).hexdigest()
    expected = expected_snapshot(graph)
    after_hash = hashlib.sha256(graph.read_bytes()).hexdigest()
    if before != identity() or graph_hash != after_hash:
        raise ValueError("Graph file changed while computing expected snapshot")
    return graph_hash, expected


def _strings(value):
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ValueError("Malformed schema string list")
    return sorted(set(value))


def _name(value):
    if not isinstance(value, str) or not value:
        raise ValueError("Malformed schema identifier")
    return value


def _quoted(value):
    return ":`" + value.replace("`", "``") + "`"


def _rel_name(value):
    value = _name(value)
    if value.startswith(":"):
        value = value[1:]
        if value.startswith("`"):
            if not value.endswith("`") or len(value) < 3:
                raise ValueError("Malformed relationship identifier")
            inner = value[1:-1]
            if "`" in inner.replace("``", ""):
                raise ValueError("Malformed relationship escaping")
            return _name(inner.replace("``", "`"))
    return _name(value)


def canonical_schema(raw_metadata) -> dict:
    """Canonical ANA metadata, retaining unknown types and mandatory=None.

    All five collections are required, even for an empty graph. Node type
    identifiers are rebuilt from authoritative nodeLabels, not parsed by colon.
    """
    if not isinstance(raw_metadata, dict) or any(
        key not in raw_metadata or not isinstance(raw_metadata[key], list) for key in _METADATA
    ):
        raise ValueError("Incomplete schema metadata")
    try:
        result = {
            "labels": _strings(raw_metadata["labels"]),
            "relationship_types": _strings(raw_metadata["relationship_types"]),
        }
        for key in ("node_properties", "relationship_properties"):
            unique = {}
            for row in raw_metadata[key]:
                name = row["propertyName"]
                if name is not None:
                    _name(name)
                types = row["propertyTypes"]
                types = [] if types is None else _strings(types)
                mandatory = row["mandatory"]
                if mandatory is not None and type(mandatory) is not bool:
                    raise ValueError("Malformed mandatory flag")
                if name is None and types:
                    raise ValueError("Property types without a property")
                item = {"propertyName": name, "propertyTypes": types, "mandatory": mandatory}
                if key == "node_properties":
                    if not isinstance(row["nodeType"], str):
                        raise ValueError("Malformed nodeType")
                    labels = _strings(row["nodeLabels"])
                    item.update(
                        nodeLabels=labels, nodeType="".join(_quoted(label) for label in labels)
                    )
                    identity = (tuple(labels), name)
                else:
                    rel_type = _rel_name(row["relType"])
                    item["relType"] = _quoted(rel_type)
                    identity = (rel_type, name)
                if identity in unique and unique[identity] != item:
                    raise ValueError("Conflicting schema property metadata")
                unique[identity] = item
            result[key] = sorted(unique.values(), key=_json)
        endpoints = []
        for row in raw_metadata["label_relationships"]:
            endpoints.append(
                {
                    key: _name(row[key])
                    for key in ("source_label", "relationship_type", "target_label")
                }
            )
        result["label_relationships"] = [
            json.loads(item) for item in sorted({_json(row) for row in endpoints})
        ]
        _schema_references(result)
        return result
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Malformed schema metadata") from exc


def _schema_references(schema):
    labels = set(schema["labels"])
    types = set(schema["relationship_types"])
    for row in schema["node_properties"]:
        if not set(row["nodeLabels"]) <= labels:
            raise ValueError("Node property references unknown schema label")
    for row in schema["relationship_properties"]:
        if _rel_name(row["relType"]) not in types:
            raise ValueError("Relationship property references unknown schema type")
    for row in schema["label_relationships"]:
        if row["source_label"] not in labels or row["target_label"] not in labels:
            raise ValueError("Endpoint references unknown schema label")
        if row["relationship_type"] not in types:
            raise ValueError("Endpoint references unknown schema type")


def schema_digest(schema) -> str:
    return _digest(_json(canonical_schema(schema)))


def _snapshot(nodes, edges):
    return {
        "nodes": fingerprint([sorted(row["labels"]), row["props"]] for row in nodes),
        "edges": fingerprint(
            [row["source"], row["type"], row["target"], row["props"]] for row in edges
        ),
    }


def _verify(expected, nodes, edges):
    actual = _snapshot(nodes, edges)
    if actual != expected:
        raise ValueError(
            f"Graph content mismatch; schema not collected: expected={expected}, actual={actual}"
        )
    return actual


def _schema(raw):
    raw["labels"] = [row["label"] for row in raw["labels"]]
    raw["relationship_types"] = [row["relationshipType"] for row in raw["relationship_types"]]
    return canonical_schema(raw)


def _coverage(schema, nodes, edges):
    labels = {label for row in nodes for label in row["labels"]}
    rels = {row["type"] for row in edges}
    # db.labels/types may retain unused tokens; they must cover all live facts.
    if not labels <= set(schema["labels"]) or not rels <= set(schema["relationship_types"]):
        raise ValueError("Truncated label/type metadata")
    wanted_nodes = {
        (tuple(sorted(row["labels"])), name)
        for row in nodes
        for name in (row["props"] or {None: None})
    }
    got_nodes = {
        (tuple(row["nodeLabels"]), row["propertyName"]) for row in schema["node_properties"]
    }
    wanted_rels = {(row["type"], name) for row in edges for name in (row["props"] or {None: None})}
    got_rels = {
        (_rel_name(row["relType"]), row["propertyName"])
        for row in schema["relationship_properties"]
    }
    by_id = {row["props"].get("id"): row["labels"] for row in nodes}
    endpoints = {
        (source, edge["type"], target)
        for edge in edges
        for source in by_id.get(edge["source"], [])
        for target in by_id.get(edge["target"], [])
    }
    got_endpoints = {
        (row["source_label"], row["relationship_type"], row["target_label"])
        for row in schema["label_relationships"]
    }
    if wanted_nodes != got_nodes or wanted_rels != got_rels or endpoints != got_endpoints:
        raise ValueError("Incomplete or inconsistent property/endpoint metadata")
    node_groups = {}
    for row in nodes:
        node_groups.setdefault(tuple(sorted(row["labels"])), []).append(row["props"])
    rel_groups = {}
    for row in edges:
        rel_groups.setdefault(row["type"], []).append(row["props"])
    for row in schema["node_properties"]:
        _property_claims(row, node_groups[tuple(row["nodeLabels"])])
    for row in schema["relationship_properties"]:
        _property_claims(row, rel_groups[_rel_name(row["relType"])])


_PRIMITIVE_TYPES = {str: "String", bool: "Boolean", int: "Long", float: "Double"}
_CHECKABLE_TYPES = set(_PRIMITIVE_TYPES.values()) | {
    name + "Array" for name in _PRIMITIVE_TYPES.values()
}


def _known_property_type(value):
    scalar = _PRIMITIVE_TYPES.get(type(value))
    if scalar:
        return scalar
    if isinstance(value, (list, tuple)) and value:
        types = {_PRIMITIVE_TYPES.get(type(item)) for item in value}
        if len(types) == 1 and None not in types:
            return types.pop() + "Array"
    return None


def _property_claims(metadata, properties):
    name = metadata["propertyName"]
    if name is None:
        if metadata["mandatory"] is True:
            raise ValueError("Mandatory claim without a property")
        return
    if metadata["mandatory"] is True and any(props.get(name) is None for props in properties):
        raise ValueError("Mandatory property absent from verified live values")
    declared = set(metadata["propertyTypes"])
    # Unknown vocabulary may describe types not recognized here. Do not guess
    # aliases, temporal variants, mixed/empty arrays, or custom driver values.
    if declared and declared <= _CHECKABLE_TYPES:
        for props in properties:
            known = _known_property_type(props.get(name))
            if known is not None and known not in declared:
                raise ValueError("Property types contradict verified live values")


def _options(database, timeout):
    if not isinstance(database, str) or not database.strip():
        raise ValueError("An explicit named database is required")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise ValueError("query_timeout_s must be finite and positive")
    return {"database": database, "default_access_mode": READ_ACCESS, "fetch_size": 2000}


def _report(database, graph_hash, snapshot, schema, nodes, edges):
    _coverage(schema, nodes, edges)
    prompt = _json(schema)
    return {
        "version": "shared-preflight-v1",
        "database": database,
        "graph_sha256": graph_hash,
        "snapshot": snapshot,
        "schema": schema,
        "schema_sha256": schema_digest(schema),
        "schema_prompt": prompt,
        "schema_prompt_sha256": _digest(prompt),
    }


def prepare_preflight(driver, database, graph: Path, *, query_timeout_s=300) -> dict:
    """Verify full content before collecting metadata; never close the caller's driver."""
    options = _options(database, query_timeout_s)
    graph_hash, expected = _graph_evidence(graph)
    with driver.session(**options) as session:
        nodes = [dict(row) for row in session.run(Query(_NODES, timeout=query_timeout_s))]
        edges = [dict(row) for row in session.run(Query(_EDGES, timeout=query_timeout_s))]
        snapshot = _verify(expected, nodes, edges)
        raw = {
            key: [dict(row) for row in session.run(Query(query, timeout=query_timeout_s))]
            for key, query in _METADATA.items()
        }
    return _report(database, graph_hash, snapshot, _schema(raw), nodes, edges)


def graph_snapshot(driver, database, *, query_timeout_s=300):
    """Read the same full content fingerprint without rebuilding initial schema facts."""
    with driver.session(**_options(database, query_timeout_s)) as session:
        nodes = [dict(row) for row in session.run(Query(_NODES, timeout=query_timeout_s))]
        edges = [dict(row) for row in session.run(Query(_EDGES, timeout=query_timeout_s))]
    return _snapshot(nodes, edges)


async def graph_snapshot_async(driver, database, *, query_timeout_s=300):
    """Async counterpart; this full scan is still not an atomic database snapshot."""
    async with driver.session(**_options(database, query_timeout_s)) as session:
        nodes = [
            dict(row) async for row in await session.run(Query(_NODES, timeout=query_timeout_s))
        ]
        edges = [
            dict(row) async for row in await session.run(Query(_EDGES, timeout=query_timeout_s))
        ]
    return _snapshot(nodes, edges)


async def prepare_preflight_async(driver, database, graph: Path, *, query_timeout_s=300) -> dict:
    """Async counterpart with exactly the same queries, validation, and evidence."""
    options = _options(database, query_timeout_s)
    graph_hash, expected = _graph_evidence(graph)
    async with driver.session(**options) as session:
        nodes = [
            dict(row) async for row in await session.run(Query(_NODES, timeout=query_timeout_s))
        ]
        edges = [
            dict(row) async for row in await session.run(Query(_EDGES, timeout=query_timeout_s))
        ]
        snapshot = _verify(expected, nodes, edges)
        raw = {}
        for key, query in _METADATA.items():
            raw[key] = [
                dict(row) async for row in await session.run(Query(query, timeout=query_timeout_s))
            ]
    return _report(database, graph_hash, snapshot, _schema(raw), nodes, edges)
