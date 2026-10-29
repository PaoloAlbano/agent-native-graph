"""Public connection factory shared by Python callers and service transports."""

from typing import Any

from agent_native_graph.backends.neo4j import backend, introspection
from agent_native_graph.backends.neo4j.config import Neo4jConfig
from agent_native_graph.core.handle_store import HandleStore
from agent_native_graph.core.tool_specs import SCHEMA_ENTRY_MODES


def connect_neo4j(
    uri: str,
    user: str,
    password: str,
    *,
    schema: dict[str, Any] | None = None,
    query_timeout_s: int | None = 30,
    schema_entry: str = "overview",
    database: str | None = None,
    handle_store: HandleStore | None = None,
    identity_mode: str = "property",
    workflow_timeout_s: int = 30,
) -> backend.Neo4jGraphBackend:
    """Open a tool workflow on an existing Neo4j graph, without a model or benchmark.

    Discover schema unless explicitly supplied. The returned backend owns its
    driver: use it as a context manager or call close(). A supplied schema avoids
    discovery but does not verify connectivity. None disables the query timeout.
    Schema-entry modes control discovery/catalog behavior, not authorization.
    Database selection applies to discovery and queries; None keeps the account
    default. A session owner may inject its store; otherwise IDs are isolated
    to this public workflow rather than using the research runner's local IDs.

    identity_mode='transaction' opts into engine references inside a single
    bounded read transaction. It never writes id properties. Its lifetime starts
    at the first query and is min(workflow_timeout_s, query_timeout_s) when the
    latter is set. It is not a durable ID or snapshot-isolation contract.
    Deletion of any observed node, timeout, or transaction failure invalidates
    the workflow; callers must explicitly close/recreate it, never resume it.
    """
    Neo4jConfig(uri, user, password, database, query_timeout_s, identity_mode, workflow_timeout_s)
    if schema_entry not in SCHEMA_ENTRY_MODES:
        raise ValueError(f"Unknown schema entry mode: {schema_entry}")
    database_options = {"database": database} if database is not None else {}
    if schema is None:
        schema = introspection.introspect_schema(
            uri, user, password, query_timeout_s=query_timeout_s, **database_options
        )
    return backend.Neo4jGraphBackend(
        uri,
        user,
        password,
        schema,
        query_timeout_s=query_timeout_s,
        schema_entry=schema_entry,
        **database_options,
        handle_store=handle_store if handle_store is not None else HandleStore.isolated(),
        **(
            {"identity_mode": identity_mode, "workflow_timeout_s": workflow_timeout_s}
            if identity_mode != "property"
            else {}
        ),
    )
