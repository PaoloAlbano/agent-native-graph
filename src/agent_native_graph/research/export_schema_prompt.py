import argparse
import json
from pathlib import Path
from typing import Any

from agent_native_graph.research_common import Neo4jRunner, add_neo4j_args


def main() -> None:
    parser = argparse.ArgumentParser()
    add_neo4j_args(parser)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    args = parser.parse_args()

    runner = Neo4jRunner(args.neo4j_uri, args.neo4j_user, args.neo4j_password, args.query_timeout_s)
    try:
        schema = export_schema(runner)
    finally:
        runner.close()

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_schema_prompt(schema), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "json_out": str(args.json_out)}, sort_keys=True))


def export_schema(runner: Neo4jRunner) -> dict[str, Any]:
    labels = _first_column(
        runner.execute("MATCH (n) UNWIND labels(n) AS label RETURN DISTINCT label ORDER BY label")
    )
    rel_types = _first_column(
        runner.execute(
            "MATCH ()-[r]->() RETURN DISTINCT type(r) AS relationshipType ORDER BY relationshipType"
        )
    )
    node_props = runner.execute(
        "CALL db.schema.nodeTypeProperties() "
        "YIELD nodeType, nodeLabels, propertyName, propertyTypes, mandatory "
        "RETURN nodeType, nodeLabels, propertyName, propertyTypes, mandatory"
    )
    rel_props = runner.execute(
        "CALL db.schema.relTypeProperties() "
        "YIELD relType, propertyName, propertyTypes, mandatory "
        "RETURN relType, propertyName, propertyTypes, mandatory"
    )
    label_relationships = runner.execute(
        "MATCH (s)-[r]->(t) "
        "UNWIND labels(s) AS source_label "
        "UNWIND labels(t) AS target_label "
        "RETURN DISTINCT source_label, type(r) AS relationship_type, target_label "
        "ORDER BY source_label, relationship_type, target_label"
    )
    return {
        "labels": labels,
        "relationship_types": rel_types,
        "node_properties": _rows_to_dicts(node_props.columns, node_props.rows),
        "relationship_properties": _rows_to_dicts(rel_props.columns, rel_props.rows),
        "label_relationships": _rows_to_dicts(
            label_relationships.columns, label_relationships.rows
        ),
    }


def render_schema_prompt(schema: dict[str, Any]) -> str:
    lines = [
        "You are generating Cypher for a Neo4j labeled property graph.",
        "Use only labels, relationship types, and properties listed below.",
        "",
        "Labels:",
    ]
    lines.extend(f"- {label}" for label in schema["labels"])
    lines.append("")
    lines.append("Relationship types:")
    lines.extend(f"- {rel_type}" for rel_type in schema["relationship_types"])
    lines.append("")
    lines.append("Node properties:")
    for row in schema["node_properties"]:
        labels = ", ".join(row.get("nodeLabels") or [])
        lines.append(
            f"- {labels}: {row.get('propertyName')} "
            f"types={row.get('propertyTypes')} mandatory={row.get('mandatory')}"
        )
    lines.append("")
    lines.append("Label relationship patterns:")
    for row in schema["label_relationships"]:
        lines.append(
            f"- (:{row.get('source_label')})-[:{row.get('relationship_type')}]->"
            f"(:{row.get('target_label')})"
        )
    lines.append("")
    lines.append("Relationship properties:")
    for row in schema["relationship_properties"]:
        lines.append(
            f"- {row.get('relType')}: {row.get('propertyName')} "
            f"types={row.get('propertyTypes')} mandatory={row.get('mandatory')}"
        )
    lines.append("")
    lines.append("Return only executable Cypher. Do not include explanations.")
    return "\n".join(lines)


def _first_column(result: Any) -> list[Any]:
    if not result.ok:
        return []
    return [row[0] for row in result.rows]


def _rows_to_dicts(columns: list[str], rows: list[list[Any]]) -> list[dict[str, Any]]:
    return [dict(zip(columns, row, strict=True)) for row in rows]


if __name__ == "__main__":
    main()
