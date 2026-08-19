"""Minimal service shape for Agent-Native Graph.

This is intentionally a thin transport layer over the packaged Neo4j research
backend. The next refactor should split execution, handles, and tool schemas
inside the package; this module already defines the intended HTTP shape.
"""

import json
import os
from pathlib import Path
from typing import Any

from agent_native_graph.core.tool_contract import get_tool_contract

try:  # FastAPI is an optional dependency exposed by the `service` extra.
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover - exercised only without extras.
    FastAPI = None  # type: ignore[assignment]
    HTTPException = None  # type: ignore[assignment]
    BaseModel = object  # type: ignore[assignment,misc]
    Field = None  # type: ignore[assignment]
    _FASTAPI_IMPORT_ERROR = exc
else:
    _FASTAPI_IMPORT_ERROR = None


if Field is not None:

    class ToolCallRequest(BaseModel):
        tool: str = Field(
            ..., description="ANA tool name to call, e.g. schema_overview or entity_resolve."
        )
        args: dict[str, Any] = Field(
            default_factory=dict, description="Tool arguments matching the ANA tool schema."
        )

else:

    class ToolCallRequest:  # pragma: no cover
        pass


_backend: Any | None = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_current_research_backend() -> Any:
    """Load the current packaged Neo4j ANA backend."""
    from agent_native_graph.backends.neo4j.backend import introspect_schema
    from agent_native_graph.tools.backend import AgentToolBackend

    uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    query_timeout_s = int(os.getenv("ANA_NEO4J_QUERY_TIMEOUT_S", "20"))
    schema_path_value = os.getenv("ANA_SCHEMA_JSON")
    if schema_path_value:
        schema_path = Path(schema_path_value)
        if not schema_path.is_absolute():
            schema_path = _repo_root() / schema_path
        if not schema_path.exists():
            raise RuntimeError(
                f"Schema file not found: {schema_path}. Set ANA_SCHEMA_JSON to a schema JSON path."
            )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    else:
        schema = introspect_schema(
            uri,
            user,
            password,
            query_timeout_s=query_timeout_s,
        )
    return AgentToolBackend(
        uri,
        user,
        password,
        schema,
        query_timeout_s=query_timeout_s,
        schema_entry=os.getenv("ANA_SCHEMA_ENTRY", "overview"),
    )


def _get_backend() -> Any:
    global _backend
    if _backend is None:
        _backend = _load_current_research_backend()
    return _backend


def create_app() -> Any:
    if FastAPI is None:
        raise RuntimeError(
            "Install service dependencies with `uv sync --extra service`."
        ) from _FASTAPI_IMPORT_ERROR

    app = FastAPI(
        title="Agent-Native Graph Service",
        version="0.1.0",
        description="HTTP service shape for ANA tools over a graph backend.",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/tools")
    def tools(status: str | None = None) -> dict[str, Any]:
        if status not in {None, "core", "experimental", "deprecated"}:
            raise HTTPException(
                status_code=400, detail="status must be core, experimental, or deprecated"
            )
        return {"version": "ana-v0", "tools": get_tool_contract(status)}

    @app.post("/tools/call")
    def call_tool(request: ToolCallRequest) -> dict[str, Any]:
        try:
            result = _get_backend().call(request.tool, request.args)
        except Exception as exc:  # noqa: BLE001 - service boundary turns backend errors into JSON.
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"tool": request.tool, "result": result}

    return app


app = create_app() if FastAPI is not None else None
