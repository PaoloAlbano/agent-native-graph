"""Synthetic Company-shaped schema for offline contract tests, not graph data."""


def company_schema() -> dict:
    labels = ["Company", "Country", "Entity", "Industry", "Person"]
    targets = {
        "basedIn": "Country",
        "foundedBy": "Person",
        "hasBoardMember": "Person",
        "hasCEO": "Person",
        "operatesIn": "Industry",
        "subsidiaryOf": "Company",
    }
    node_properties = []
    for label in ("Company", "Country", "Industry", "Person"):
        props = {
            "id": "STRING",
            "eid": "STRING",
            "name": "STRING",
            "description": "STRING",
            "aliases": "LIST<STRING NOT NULL>",
        }
        if label == "Company":
            props["launch_year"] = "INTEGER"
        if label == "Person":
            props.update(
                country_of_citizenship="LIST<STRING NOT NULL>",
                place_of_birth="STRING",
                gender="STRING",
                date_of_birth="DATE",
                date_of_death="DATE",
            )
        node_properties.extend(
            {
                "nodeType": f":`{label}`:`Entity`",
                "nodeLabels": [label, "Entity"],
                "propertyName": name,
                "propertyTypes": [f"{kind} NOT NULL"],
                "mandatory": name in {"id", "eid", "name", "aliases"},
            }
            for name, kind in props.items()
        )
    relationship_properties = []
    for rel in targets:
        props = {"id": "STRING"}
        if rel in {"hasCEO", "hasBoardMember"}:
            props.update(start_year="INTEGER", end_year="INTEGER")
        relationship_properties.extend(
            {
                "relType": f":`{rel}`",
                "propertyName": name,
                "propertyTypes": [f"{kind} NOT NULL"],
                "mandatory": name == "id",
            }
            for name, kind in props.items()
        )
    return {
        "labels": labels,
        "relationship_types": list(targets),
        "node_properties": node_properties,
        "relationship_properties": relationship_properties,
        "label_relationships": [
            {"source_label": source, "relationship_type": rel, "target_label": target_label}
            for rel, target in targets.items()
            for source in ("Company", "Entity")
            for target_label in (target, "Entity")
        ],
    }
