import argparse
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase
from neo4j.time import Date

from agent_native_graph.research_common import add_neo4j_args


def main() -> None:
    parser = argparse.ArgumentParser()
    add_neo4j_args(parser)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--limit-nodes", type=int)
    parser.add_argument("--limit-edges", type=int)
    args = parser.parse_args()

    graph = load_simplekg(args.graph)
    nodes = graph["nodes"]
    edges = graph["edges"]
    if args.limit_nodes is not None:
        nodes = nodes[: args.limit_nodes]
        allowed_ids = {node["id"] for node in nodes}
        edges = [
            edge
            for edge in edges
            if edge["source_id"] in allowed_ids and edge["target_id"] in allowed_ids
        ]
    if args.limit_edges is not None:
        edges = edges[: args.limit_edges]

    driver = GraphDatabase.driver(args.neo4j_uri, auth=(args.neo4j_user, args.neo4j_password))
    try:
        with driver.session() as session:
            if args.clear:
                session.run("MATCH (n) DETACH DELETE n").consume()
            create_constraints(session)
            load_nodes(session, nodes, args.batch_size)
            load_edges(session, edges, args.batch_size)
            counts = session.run(
                "MATCH (n) WITH count(n) AS nodes MATCH ()-[r]->() RETURN nodes, count(r) AS edges"
            ).single()
            print(
                json.dumps(
                    {
                        "loaded_nodes": len(nodes),
                        "loaded_edges": len(edges),
                        "neo4j_nodes": counts["nodes"] if counts else None,
                        "neo4j_edges": counts["edges"] if counts else None,
                    },
                    sort_keys=True,
                )
            )
    finally:
        driver.close()


def load_simplekg(path: Path) -> dict[str, list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("SimpleKG payload must be a JSON object.")
    raw_nodes = _first_existing(payload, ("nodes", "entities", "vertices"))
    raw_edges = _first_existing(payload, ("edges", "relationships", "relations", "triples"))
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise ValueError(f"Unsupported SimpleKG shape. Top-level keys: {list(payload.keys())}")
    return {
        "nodes": [_normalize_node(node) for node in raw_nodes],
        "edges": [_normalize_edge(edge) for edge in raw_edges],
    }


def create_constraints(session: Any) -> None:
    session.run(
        "CREATE CONSTRAINT grapharrow_simplekg_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE"
    ).consume()


def load_nodes(session: Any, nodes: list[dict[str, Any]], batch_size: int) -> None:
    for batch in _chunks(nodes, batch_size):
        grouped: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for node in batch:
            labels = tuple(dict.fromkeys(["Entity", *node["labels"]]))
            grouped.setdefault(labels, []).append(node)
        for labels, rows in grouped.items():
            label_clause = "".join(f":`{_safe_cypher_name(label)}`" for label in labels)
            session.run(
                f"""
                UNWIND $rows AS row
                MERGE (n:Entity {{id: row.id}})
                SET n += row.properties
                SET n{label_clause}
                RETURN count(n)
                """,
                rows=rows,
            ).consume()


def load_edges(session: Any, edges: list[dict[str, Any]], batch_size: int) -> None:
    for batch in _chunks(edges, batch_size):
        grouped: dict[str, list[dict[str, Any]]] = {}
        for edge in batch:
            grouped.setdefault(edge["type"], []).append(edge)
        for rel_type, rows in grouped.items():
            safe_rel_type = _safe_cypher_name(rel_type)
            session.run(
                f"""
                UNWIND $rows AS row
                MATCH (s:Entity {{id: row.source_id}})
                MATCH (t:Entity {{id: row.target_id}})
                MERGE (s)-[r:`{safe_rel_type}` {{id: row.id}}]->(t)
                SET r += row.properties
                RETURN count(r)
                """,
                rows=rows,
            ).consume()


def _first_existing(payload: Mapping[str, Any], keys: Iterable[str]) -> object:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _normalize_node(raw: object) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError(f"Unsupported node row: {raw!r}")
    node_id = (
        raw.get("id")
        or raw.get("node_id")
        or raw.get("eid")
        or raw.get("qid")
        or raw.get("wikidata_qid")
    )
    if node_id is None:
        raise ValueError(f"Node without id: {raw!r}")
    labels = (
        raw.get("labels") or raw.get("label") or raw.get("type") or raw.get("types") or ["Entity"]
    )
    if isinstance(labels, str):
        labels = [labels]
    properties = _properties(
        raw,
        reserved={
            "id",
            "node_id",
            "eid",
            "qid",
            "wikidata_qid",
            "labels",
            "label",
            "type",
            "types",
            "provenance",
        },
    )
    properties["id"] = str(node_id)
    properties["eid"] = str(node_id)
    return {
        "id": str(node_id),
        "labels": [_safe_label(str(label)) for label in labels],
        "properties": properties,
    }


def _normalize_edge(raw: object) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError(f"Unsupported edge row: {raw!r}")
    source_id = (
        raw.get("source")
        or raw.get("source_id")
        or raw.get("src")
        or raw.get("start")
        or raw.get("subj_id")
    )
    target_id = (
        raw.get("target")
        or raw.get("target_id")
        or raw.get("dst")
        or raw.get("end")
        or raw.get("obj_id")
    )
    rel_type = (
        raw.get("type") or raw.get("label") or raw.get("relationship_type") or raw.get("predicate")
    )
    if source_id is None or target_id is None or rel_type is None:
        raise ValueError(f"Edge missing source/target/type: {raw!r}")
    edge_id = (
        raw.get("id")
        or raw.get("edge_id")
        or raw.get("rid")
        or f"{source_id}|{rel_type}|{target_id}"
    )
    properties = _properties(
        raw,
        reserved={
            "id",
            "edge_id",
            "rid",
            "source",
            "source_id",
            "src",
            "start",
            "subj_id",
            "target",
            "target_id",
            "dst",
            "end",
            "obj_id",
            "type",
            "label",
            "relationship_type",
            "predicate",
            "provenance",
        },
    )
    properties["id"] = str(edge_id)
    return {
        "id": str(edge_id),
        "source_id": str(source_id),
        "target_id": str(target_id),
        "type": str(rel_type),
        "properties": properties,
    }


def _properties(raw: Mapping[str, Any], *, reserved: set[str]) -> dict[str, Any]:
    explicit = raw.get("properties")
    props = {str(key): value for key, value in raw.items() if key not in reserved | {"properties"}}
    if isinstance(explicit, Mapping):
        props.update(dict(explicit))
    return {
        str(key): _coerce_neo4j_value(key, value)
        for key, value in props.items()
        if _is_neo4j_value(value)
    }


def _coerce_neo4j_value(key: object, value: Any) -> Any:
    if isinstance(value, str) and str(key).startswith("date_"):
        parts = value.split("-")
        if len(parts) == 3 and all(part.isdigit() for part in parts):
            return Date(int(parts[0]), int(parts[1]), int(parts[2]))
    if isinstance(value, list):
        return [_coerce_neo4j_value(key, item) for item in value]
    return value


def _is_neo4j_value(value: Any) -> bool:
    if value is None or isinstance(value, bool | int | float | str):
        return True
    if isinstance(value, list):
        return all(_is_neo4j_value(item) and item is not None for item in value)
    return False


def _safe_label(label: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_]", "_", label)
    if not cleaned:
        return "Entity"
    if cleaned[0].isdigit():
        return "L_" + cleaned
    return cleaned


def _safe_cypher_name(name: str) -> str:
    return name.replace("`", "``")


def _chunks(rows: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


if __name__ == "__main__":
    main()
