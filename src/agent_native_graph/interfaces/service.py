"""HTTP transport with app-owned, engine-independent workflow sessions.

Static demo API keys authenticate callers; workflow tokens remain separate.
Readiness and shared multi-worker session storage remain separate.
"""

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from agent_native_graph.application.auth import (
    ApiKeyAuth,
    AuthenticationError,
    AuthNotConfigured,
    Principal,
)
from agent_native_graph.application.sessions import (
    BackendFactory,
    BackendSessions,
    SessionCapacityError,
    SessionConfig,
    SessionNotFound,
)
from agent_native_graph.core.tool_contract import get_tool_contract
from agent_native_graph.core.tool_specs import get_tool_specs

try:  # FastAPI is an optional dependency exposed by the `service` extra.
    from fastapi import Depends, FastAPI, Header, HTTPException, Response
    from pydantic import BaseModel, Field
    from starlette.concurrency import run_in_threadpool
except ImportError as exc:  # pragma: no cover - exercised only without extras.
    FastAPI = None  # type: ignore[assignment]
    HTTPException = None  # type: ignore[assignment]
    Header = None  # type: ignore[assignment]
    Response = None  # type: ignore[assignment]
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


def _default_backend_factory(schema_entry: str) -> BackendFactory:
    """Wire the default adapter; an injected factory may use any graph engine."""
    from agent_native_graph import connect_neo4j
    from agent_native_graph.backends.neo4j.config import Neo4jConfig

    config = Neo4jConfig.from_env()
    schema_path_value = os.getenv("ANA_SCHEMA_JSON")
    schema = None
    if schema_path_value:
        schema_path = Path(schema_path_value)
        if not schema_path.exists():
            raise RuntimeError(
                f"Schema file not found: {schema_path}. Set ANA_SCHEMA_JSON to a schema JSON path."
            )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

    def factory(store):
        return connect_neo4j(
            config.uri,
            config.user,
            config.password,
            schema=schema,
            database=config.database,
            query_timeout_s=config.query_timeout_s,
            schema_entry=schema_entry,
            handle_store=store,
        )

    return factory


def create_app(
    *,
    backend_factory: BackendFactory | None = None,
    session_config: SessionConfig | None = None,
    schema_entry: str | None = None,
    auth: ApiKeyAuth | None = None,
) -> Any:
    if FastAPI is None:
        raise RuntimeError(
            "Install service dependencies with `uv sync --extra service`."
        ) from _FASTAPI_IMPORT_ERROR

    mode = schema_entry if schema_entry is not None else os.getenv("ANA_SCHEMA_ENTRY", "overview")
    get_tool_specs(schema_entry=mode)
    config = session_config or SessionConfig(
        max_sessions=int(os.getenv("ANA_MAX_SESSIONS", "128")),
        idle_timeout_s=float(os.getenv("ANA_SESSION_IDLE_TIMEOUT_S", "1800")),
    )
    sessions = BackendSessions(backend_factory or _default_backend_factory(mode), config)
    access = auth if auth is not None else ApiKeyAuth.from_env()
    contracts = {item["name"]: item for item in get_tool_contract()}
    callable_names = {
        spec["function"]["name"]
        for spec in get_tool_specs(enable_planning_tools=True, schema_entry=mode)
    }

    def authenticate(
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> Principal:
        try:
            return access.authenticate(authorization)
        except AuthNotConfigured as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except AuthenticationError as exc:
            raise HTTPException(
                status_code=401, detail=str(exc), headers={"WWW-Authenticate": "Bearer"}
            ) from exc

    def permitted(principal: Principal, name: str) -> bool:
        contract = contracts.get(name)
        return bool(contract and principal.permits(contract["profile"]))

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            await run_in_threadpool(sessions.close)

    app = FastAPI(
        title="Agent-Native Graph Service",
        version="0.1.0",
        description="HTTP service shape for ANA tools over a graph backend.",
        lifespan=lifespan,
    )
    app.state.sessions = sessions

    @app.post("/sessions", status_code=201)
    def create_session(
        response: Response,
        principal: Annotated[Principal, Depends(authenticate)],
    ) -> dict[str, Any]:
        try:
            token = sessions.create(owner_id=principal.subject)
        except SessionCapacityError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Could not open workflow session") from exc
        response.headers["Cache-Control"] = "no-store"
        return {"session_id": token, "idle_timeout_s": config.idle_timeout_s}

    @app.delete("/sessions/current", status_code=204)
    def delete_session(
        principal: Annotated[Principal, Depends(authenticate)],
        session_id: str | None = Header(default=None, alias="X-ANA-Session"),
    ) -> Response:
        if not session_id:
            raise HTTPException(status_code=401, detail="X-ANA-Session is required")
        try:
            sessions.delete(session_id, owner_id=principal.subject)
        except SessionNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Session cleanup failed") from exc
        return Response(status_code=204)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/tools")
    def tools(
        principal: Annotated[Principal, Depends(authenticate)],
        status: str | None = None,
    ) -> dict[str, Any]:
        if status not in {None, "core", "experimental"}:
            raise HTTPException(status_code=400, detail="status must be core or experimental")
        return {
            "version": "ana-v0",
            "tools": [
                item for item in get_tool_contract(status) if permitted(principal, item["name"])
            ],
        }

    @app.get("/tools/specs")
    def tool_specs(
        principal: Annotated[Principal, Depends(authenticate)],
        enable_planning_tools: bool = False,
    ) -> dict[str, Any]:
        try:
            specs = get_tool_specs(
                enable_planning_tools=enable_planning_tools,
                schema_entry=mode,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "version": "ana-v0",
            "tools": [spec for spec in specs if permitted(principal, spec["function"]["name"])],
        }

    @app.post("/tools/call")
    def call_tool(
        request: ToolCallRequest,
        principal: Annotated[Principal, Depends(authenticate)],
        session_id: str | None = Header(default=None, alias="X-ANA-Session"),
    ) -> dict[str, Any]:
        if not session_id:
            raise HTTPException(status_code=401, detail="X-ANA-Session is required")
        if request.tool not in callable_names or not permitted(principal, request.tool):
            raise HTTPException(status_code=403, detail="Tool is not permitted")
        try:
            result = sessions.call(
                session_id, request.tool, request.args, owner_id=principal.subject
            )
        except SessionNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - service boundary turns backend errors into JSON.
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"tool": request.tool, "result": result}

    return app


app = create_app() if FastAPI is not None else None
