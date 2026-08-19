from typing import Any


def test_service_backend_introspects_schema_when_no_schema_file(monkeypatch) -> None:
    from agent_native_graph.backends import neo4j
    from agent_native_graph.interfaces import service
    from agent_native_graph.tools import backend as backend_entrypoint

    calls: dict[str, Any] = {}
    schema = {
        "labels": ["Company"],
        "relationship_types": [],
        "node_properties": [],
        "relationship_properties": [],
        "label_relationships": [],
    }

    def fake_introspect_schema(
        uri: str,
        user: str,
        password: str,
        *,
        query_timeout_s: int | None = None,
    ) -> dict[str, Any]:
        calls["introspection"] = {
            "uri": uri,
            "user": user,
            "password": password,
            "query_timeout_s": query_timeout_s,
        }
        return schema

    class FakeBackend:
        def __init__(
            self,
            uri: str,
            user: str,
            password: str,
            loaded_schema: dict[str, Any],
            *,
            query_timeout_s: int | None = None,
            schema_entry: str = "overview",
        ) -> None:
            self.uri = uri
            self.user = user
            self.password = password
            self.schema = loaded_schema
            self.query_timeout_s = query_timeout_s
            self.schema_entry = schema_entry

    monkeypatch.delenv("ANA_SCHEMA_JSON", raising=False)
    monkeypatch.setenv("NEO4J_URI", "bolt://example:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j-user")
    monkeypatch.setenv("NEO4J_PASSWORD", "neo4j-password")
    monkeypatch.setenv("ANA_NEO4J_QUERY_TIMEOUT_S", "7")
    monkeypatch.setattr(neo4j.backend, "introspect_schema", fake_introspect_schema)
    monkeypatch.setattr(backend_entrypoint, "AgentToolBackend", FakeBackend)

    backend = service._load_current_research_backend()

    assert calls["introspection"] == {
        "uri": "bolt://example:7687",
        "user": "neo4j-user",
        "password": "neo4j-password",
        "query_timeout_s": 7,
    }
    assert backend.schema is schema
    assert backend.schema_entry == "overview"
