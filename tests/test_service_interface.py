from pathlib import Path
from typing import Any

from agent_native_graph.core.handle_store import HandleStore


def test_docker_build_includes_license_and_excludes_private_artifacts() -> None:
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile").read_text()
    assert "COPY pyproject.toml uv.lock README.md LICENSE ./" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert "HEALTHCHECK" in dockerfile and "http://127.0.0.1:8080/health" in dockerfile
    assert "ENV NEO4J_PASSWORD" not in dockerfile
    assert "MIT License" in (root / "LICENSE").read_text()
    ignored = (root / ".dockerignore").read_text().splitlines()
    for path in (
        ".local-notes/",
        ".local-results/",
        ".local-secrets/",
        "scripts/",
        "*.config.json",
    ):
        assert path in ignored


def test_service_backend_introspects_schema_when_no_schema_file(monkeypatch) -> None:
    from agent_native_graph.backends.neo4j import backend as backend_entrypoint
    from agent_native_graph.backends.neo4j import introspection
    from agent_native_graph.interfaces import service

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
        database: str | None = None,
    ) -> dict[str, Any]:
        calls["introspection"] = {
            "uri": uri,
            "user": user,
            "password": password,
            "query_timeout_s": query_timeout_s,
            "database": database,
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
            database: str | None = None,
            handle_store: HandleStore | None = None,
        ) -> None:
            self.uri = uri
            self.user = user
            self.password = password
            self.schema = loaded_schema
            self.query_timeout_s = query_timeout_s
            self.schema_entry = schema_entry
            self.database = database
            self.store = handle_store

    monkeypatch.delenv("ANA_SCHEMA_JSON", raising=False)
    monkeypatch.setenv("NEO4J_URI", "bolt://example:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j-user")
    monkeypatch.setenv("NEO4J_PASSWORD", "neo4j-password")
    monkeypatch.setenv("ANA_NEO4J_QUERY_TIMEOUT_S", "7")
    monkeypatch.setenv("NEO4J_DATABASE", "custom-graph")
    monkeypatch.setattr(introspection, "introspect_schema", fake_introspect_schema)
    monkeypatch.setattr(backend_entrypoint, "Neo4jGraphBackend", FakeBackend)

    store = HandleStore(namespace="workflow")
    factory = service._default_backend_factory("overview")
    monkeypatch.setenv("NEO4J_DATABASE", "changed-after-configuration")
    backend = factory(store)

    assert calls["introspection"] == {
        "uri": "bolt://example:7687",
        "user": "neo4j-user",
        "password": "neo4j-password",
        "query_timeout_s": 7,
        "database": "custom-graph",
    }
    assert backend.schema is schema
    assert backend.schema_entry == "overview"
    assert backend.database == "custom-graph" and backend.store is store
