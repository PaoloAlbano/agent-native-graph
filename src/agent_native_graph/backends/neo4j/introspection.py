"""Neo4j schema introspection adapter."""

from typing import Any

from neo4j import GraphDatabase, Query

from agent_native_graph.core.introspection import GraphSchemaIntrospector


class Neo4jSchemaIntrospector(GraphSchemaIntrospector):
    """Build ANA schema metadata from Neo4j system procedures and data patterns."""

    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        *,
        query_timeout_s: int | None = None,
    ) -> None:
        self._driver = GraphDatabase.driver(
            uri, auth=(user, password), connection_timeout=120.0, max_transaction_retry_time=120.0
        )
        self._query_timeout_s = query_timeout_s

    def close(self) -> None:
        self._driver.close()

    def introspect_schema(self) -> dict[str, Any]:
        try:
            with self._driver.session() as session:
                labels = [
                    str(record["label"])
                    for record in self._run(
                        session,
                        "CALL db.labels() YIELD label RETURN label ORDER BY label",
                    )
                ]
                relationship_types = [
                    str(record["relationshipType"])
                    for record in self._run(
                        session,
                        (
                            "CALL db.relationshipTypes() YIELD relationshipType "
                            "RETURN relationshipType ORDER BY relationshipType"
                        ),
                    )
                ]
                node_properties = [
                    {
                        "nodeType": record["nodeType"],
                        "nodeLabels": list(record["nodeLabels"] or []),
                        "propertyName": record["propertyName"],
                        "propertyTypes": list(record["propertyTypes"] or []),
                        "mandatory": bool(record["mandatory"]),
                    }
                    for record in self._run(
                        session,
                        (
                            "CALL db.schema.nodeTypeProperties() "
                            "YIELD nodeType, nodeLabels, propertyName, propertyTypes, mandatory "
                            "RETURN nodeType, nodeLabels, propertyName, propertyTypes, mandatory "
                            "ORDER BY nodeType, propertyName"
                        ),
                    )
                ]
                relationship_properties = [
                    {
                        "relType": record["relType"],
                        "propertyName": record["propertyName"],
                        "propertyTypes": list(record["propertyTypes"] or []),
                        "mandatory": bool(record["mandatory"]),
                    }
                    for record in self._run(
                        session,
                        (
                            "CALL db.schema.relTypeProperties() "
                            "YIELD relType, propertyName, propertyTypes, mandatory "
                            "RETURN relType, propertyName, propertyTypes, mandatory "
                            "ORDER BY relType, propertyName"
                        ),
                    )
                ]
                label_relationships = [
                    {
                        "source_label": record["source_label"],
                        "relationship_type": record["relationship_type"],
                        "target_label": record["target_label"],
                    }
                    for record in self._run(
                        session,
                        (
                            "MATCH (source)-[rel]->(target) "
                            "UNWIND labels(source) AS source_label "
                            "UNWIND labels(target) AS target_label "
                            "RETURN DISTINCT source_label, type(rel) AS relationship_type, target_label "
                            "ORDER BY source_label, relationship_type, target_label"
                        ),
                    )
                ]
        finally:
            self.close()
        return {
            "labels": labels,
            "relationship_types": relationship_types,
            "node_properties": node_properties,
            "relationship_properties": relationship_properties,
            "label_relationships": label_relationships,
        }

    def _run(self, session: Any, query: str) -> Any:
        statement: str | Query = (
            Query(query, timeout=self._query_timeout_s) if self._query_timeout_s else query
        )
        return session.run(statement)


def introspect_schema(
    uri: str,
    user: str,
    password: str,
    *,
    query_timeout_s: int | None = None,
) -> dict[str, Any]:
    """Build the ANA schema payload directly from Neo4j metadata."""
    return Neo4jSchemaIntrospector(
        uri,
        user,
        password,
        query_timeout_s=query_timeout_s,
    ).introspect_schema()
