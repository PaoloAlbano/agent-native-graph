# Use ANA on Your Own Neo4j

This repository is both a research codebase and a Python package with an
experimental HTTP transport. The graph-access layer does not embed an LLM.
Your agent/application chooses operations; ANA executes them on Neo4j.

Company files, benchmark questions and an LLM API key are **not required** for
ordinary graph access. Do not run `make load-company` on your own graph.
The current package is a prototype, not a stable production SDK or service.

## Install From Source

From a checkout, `make sync` installs the package plus development/service
extras. For a library-only environment, install the checkout into your own uv
project instead:

```bash
uv add --editable ../agent-native-graph
```

For HTTP support use `uv add --editable ../agent-native-graph --extra service`.
Adjust the relative checkout path. These are source installs; this guide does
not assume a published PyPI release. Python 3.11+ is required.

Configure `NEO4J_URI`, `NEO4J_USER` and `NEO4J_PASSWORD` outside version control.
Use an account limited to the graph access and schema procedures you require.
Pass `database="your-database"` to the Python factory, or set `NEO4J_DATABASE`
for the default HTTP adapter. Both data queries and schema discovery use that
database. If omitted, Neo4j's default database for the account is retained.

## Python Library

### Current Graph Identity Requirement

The prototype is not fully schema-agnostic. Handle-based traversal and several
set/count operations currently identify nodes through their **`id` property**,
not Neo4j's internal element ID. For these operations, provide stable, non-null
IDs unique across participating graph nodes, not merely unique within a label.
ANA does not add IDs, install constraints or migrate your graph automatically.
Missing IDs can currently surface as backend errors; duplicate IDs can produce
incorrect joins. Discovery and scalar whole-label counts do not imply that
traversal is compatible with an unkeyed graph.

Domain labels need not be Company/Person, and a `name` property is not required
for scan/project/traversal. Lookup tools may default to `name`; use their
explicit property parameters where supported. Identifier-independent traversal
and a consistent precondition-error taxonomy remain future work. Validate your
schema before connecting the demo to an existing application graph.

### Experimental Transaction Identity (Opt-In)

The default `identity_mode="property"` retains the requirement above and the
historical benchmark behavior. To remove that requirement for a Python workflow,
pass `identity_mode="transaction"` to `connect_neo4j`; optionally set
`workflow_timeout_s` (a positive integer, default 30). For the HTTP adapter:

```bash
ANA_NEO4J_IDENTITY_MODE=transaction ANA_NEO4J_WORKFLOW_TIMEOUT_S=30 \
  uv run uvicorn agent_native_graph.interfaces.service:app --host 127.0.0.1 --port 8080
```

This does **not** migrate properties, add constraints or treat `elementId()` as
a persistent identifier. The Neo4j adapter holds one explicit read transaction
per workflow and attaches internal, owner-scoped references to node payloads.
These references are not serialized into tool JSON or graph properties. Two
nodes remain distinct even when their application `id` values or all their
properties are identical; nodes without `id` are supported in this mode.
Business-property filters and projections of `id` still access that property,
not the internal reference. Other backends need not use Neo4j's mechanism.
This also applies to `count_handle(distinct=true)` without `var`: whole-row
comparison preserves entity identity, distinguishing different nodes with equal
properties and treating cached versions of the same node as the same entity.
Scalar-only row comparison and the default property mode remain unchanged.

The transaction starts lazily at the first data query and ends by rollback on
close. Its **total lifetime**, not a fresh budget per tool call, is the smaller
of `workflow_timeout_s` and `query_timeout_s` when the latter is set. With
`query_timeout_s=None`, the workflow bound still applies. Within this mode
Neo4j's timeout is transaction-scoped. The configured HTTP session idle TTL is
independent and may be longer: an expired identity workflow must still be
deleted and replaced with a new session. No transaction is silently reopened.
The server/next-call lifetime checks are not a hard wall-clock interruption of
blocked connection acquisition or network I/O.

Before each subsequent tool operation, observed node references are checked
for continued visibility, including references that contributed to a later
scalar/count handle. Deletion, workflow expiry or transaction/connection failure
invalidates the workflow and discards all its handles. Create a new workflow
explicitly; a node recreated with the same business properties is not a
replacement for a deleted reference. Invalid arguments alone remain repairable.

This is not snapshot isolation: property and relationship changes can be visible
between calls, and cached node properties reflect when they were retrieved.
The check is not an atomic exclusion of concurrent writers. Keep the graph
read-only externally when stable multi-step results are required. Holding
transactions and checking references add connection/server cost, including for
otherwise-local fetches. Public Python workflows are not thread-safe; HTTP
serializes calls within each session. This experimental mode is not enabled
in the benchmark runners or the default server. Do not reinterpret historical
results or resume old runs under changed source code.

The choice of a single transaction follows Neo4j's documented limits on
[element ID validity](https://neo4j.com/docs/cypher-manual/current/functions/scalar/#functions-elementid).
Returning serialized payloads does not export reusable internal references;
clients continue to compose operations through the original server-side handles.

### Public Factory

The public entry points are `connect_neo4j`, `get_tool_specs` and
`AgentGraphBackend`, imported from `agent_native_graph`. The factory returns
the existing backend, not a second implementation of graph operations. This
example discovers schema, counts one discovered label and fetches its result:

```python
import os

from agent_native_graph import connect_neo4j, get_tool_specs

uri = os.environ["NEO4J_URI"]
user = os.environ["NEO4J_USER"]
password = os.environ["NEO4J_PASSWORD"]
tools = get_tool_specs()  # Native LLM schemas; no database or model access.
with connect_neo4j(uri, user, password, database=os.getenv("NEO4J_DATABASE")) as graph:
    assert graph.tool_specs() == tools
    overview = graph.call("schema_overview", {})
    if overview["labels"]:
        label = overview["labels"][0]["label"]
        count = graph.call("count_nodes", {"label": label, "alias": "node_count"})
        page = graph.call("fetch", {"from": count["handle"], "limit": 1, "offset": 0})
        print(label, page["columns"], page["rows"])
    else:
        print("No domain labels are available.")
```

The factory defaults to a 30-second per-query timeout; pass a positive integer
as `query_timeout_s` to change it. `None` explicitly disables it. The context
manager closes the owned driver even when a tool raises; `close()` is also
available and idempotent. Tool calls after closing raise `RuntimeError`.
Low-level backend imports remain available, but are not needed for ordinary use.
The benchmark entry point belongs to the CLI, not the backend module.

`connect_neo4j(..., schema=metadata)` optionally reuses an explicit schema and
skips discovery; it does not verify connectivity until an operation needs it.
`schema_entry` selects an existing discovery/catalog mode (default `overview`).
`graph.tool_specs()` follows that mode. `get_tool_specs()` also accepts
`schema_entry` and `enable_planning_tools`; planning tools are hidden by default.
Both return independent, complete OpenAI-compatible native tool schemas,
including effective description/parameter overrides. A caller may customize its
copy without changing later requests. No model is called by these methods.

Introspection uses Neo4j's label/type/property metadata
procedures and endpoint patterns; it requires access to those procedures and
can scan graph data. It is not a cost-free or fully paginated schema lookup.

One backend owns the handles for one workflow. Reuse it for successive calls
and pass returned handles rather than guessing IDs. A handle from another
backend/process is not transferable. Do not share a backend concurrently across
untrusted users. Handles are in memory, not persisted cursors. Public factory
workflows use independent opaque handle namespaces; do not infer handle IDs or
transfer them to another workflow. Direct low-level construction retains the
historical local IDs for benchmark compatibility. Python workflows have no idle
expiry; close them when finished. HTTP lifecycle limits are described below.

### Fetch Page Contract

Python and HTTP calls return `contract_version: "ana-fetch-v1"`:

| Field | Meaning |
| --- | --- |
| `rows` | The complete requested page, not a 20-row preview |
| `columns` | Column names in the order used by every row |
| `returned_count` | Exactly `len(rows)` |
| `preview` | The first at most 20 rows of this page |
| `preview_truncated` | The preview is shorter than the returned page |
| `total_count` | Rows in this stored handle, after applicable entity deduplication |
| `offset`, `limit` | Effective pagination arguments |
| `next_offset` | Offset for the next page, or null when no page remains |
| `truncated` | More handle rows remain after this page, independently of the preview |

Pass `limit` as a positive integer (default 1000) and `offset` as a nonnegative
integer (default 0). Omitted or null optional arguments use their defaults;
booleans, fractions, numeric strings and negative values are rejected. An offset
at or beyond the end returns an empty page and null `next_offset`. Reuse the
handle and advance with `next_offset`; a `limit` greater than 20 no longer
silently loses rows. Prefer `preview` when a small display is enough.

This is a response-contract change from the prototype, whose `rows` field
contained only a preview. Consumers should check the version and use
`preview` explicitly if they relied on that behavior. The research runner
deliberately retains its historical preview transcript through an adapter,
while scoring complete fetched rows; the adapter is not the Python/HTTP page API.
Archived research results have not been rewritten.

Pagination covers only the stored handle: an upstream operation may already
have capped its result. Inspect its metadata before claiming a complete graph
answer. No global byte quota or strict maximum requested page size is enforced
by this fetch contract yet; choose modest pages and do not treat it as a
resource-isolation boundary.

## HTTP Server

With the service extra installed, connection variables configured and
`ANA_AUTH_FILE` set as below:

```bash
uv run uvicorn agent_native_graph.interfaces.service:app --host 127.0.0.1 --port 8080
```

### Demo Authentication

The server uses static bearer keys for a controlled demo, not OAuth or a
production identity service. Keep credentials outside Git and the Docker build
context. This creates one random read-only client and a separate key file for
the example client, without printing either secret:

```bash
uv run python - <<'PY'
import json
import secrets
from pathlib import Path

directory = Path('.local-secrets')
directory.mkdir(mode=0o700, exist_ok=True)
directory.chmod(0o700)
auth = directory / 'demo.config.json'
key_file = directory / 'demo.key'
if auth.exists() or key_file.exists():
    raise SystemExit('Demo credentials already exist; not overwriting them')
key = secrets.token_urlsafe(32)
auth.write_text(json.dumps({'clients': [
    {'id': 'demo-reader', 'api_key': key, 'profile': 'readonly'}
]}))
auth.chmod(0o644)
key_file.write_text(key)
key_file.chmod(0o600)
PY
export ANA_AUTH_FILE="$PWD/.local-secrets/demo.config.json"
export ANA_API_KEY_FILE="$PWD/.local-secrets/demo.key"
```

The host directory is private (0700). The auth file is 0644 so a **single-file**
read-only bind mount can be read by container UID 10001; other host users cannot
traverse the private parent directory. Do not copy this file into a public
directory or mount the entire private directory. A deployment secret mount
readable by UID 10001 is an alternative. Do not commit these files.

`ANA_AUTH_FILE` has the shape `{"clients": [{"id": "client-id", "api_key":
"<random-key-at-least-32-characters>", "profile": "readonly"}]}`. Multiple
clients need distinct IDs and keys. Generate keys with a cryptographic random
generator, not passwords. Clients sharing a key share the same identity.
`readonly` permits only read tools; `readwrite` also permits future write tools.
All currently implemented tools are read-only: assigning `readwrite` does not
create ingestion capabilities. Profiles are assigned in the file, never by
query parameters, request arguments or an LLM. They are separate from benchmark
YAML profiles. Tool status (`core`/`experimental`) is not an authorization grant.

No file or an empty client list leaves authenticated endpoints closed (503).
Malformed configuration prevents app creation. Configuration is snapshotted;
restart to rotate/revoke keys. An in-flight operation is not cancelled by key
rotation. Never reuse a client ID for a different person while its sessions live.
Send `Authorization: Bearer <client-key>` on every data/catalog request. Wrong
or missing credentials return 401. `/health`, `/docs` and `/openapi.json` do not
require credentials. Health only checks liveness.

Each HTTP session owns an independent backend/handle store. No backend is
created by importing the app, checking health or reading the catalog. A new
session discovers schema unless `ANA_SCHEMA_JSON` supplies an override; creating
many sessions can therefore incur schema-discovery cost. A relative override
path is resolved against the server's working directory, not a source checkout.
Connection settings and the optional schema file are read when the app is
created; restart to change them. No benchmark data is imported.

Schema is not automatically refreshed within a session. Finish existing
workflows and create a fresh session when the graph's schema changes (a static
file override additionally needs updating/restarting). Concurrent graph mutations
are not a snapshot-isolation guarantee across tool calls.

| Request | Current behavior |
| --- | --- |
| `GET /health` | Liveness only, not a Neo4j readiness check |
| `GET /tools` | Contract metadata; optional `status=core` or `status=experimental` |
| `GET /tools/specs` | Full native tool schemas; optional `enable_planning_tools=true`, no database access |
| `POST /sessions` | Open a workflow; returns `session_id` and `idle_timeout_s`, HTTP 201 |
| `POST /tools/call` | Requires `X-ANA-Session`; JSON `{"tool": "schema_overview", "args": {}}` returns `{"tool": ..., "result": ...}` |
| `DELETE /sessions/current` | Requires `X-ANA-Session`; closes the workflow, HTTP 204 |

For example, from a separate terminal with the client key available:

```bash
curl --fail http://127.0.0.1:8080/health
AUTH_HEADER="Authorization: Bearer $(cat "$ANA_API_KEY_FILE")"
curl --fail -H "$AUTH_HEADER" http://127.0.0.1:8080/tools
curl --fail -H "$AUTH_HEADER" http://127.0.0.1:8080/tools/specs
SESSION_ID=$(curl --fail --silent --show-error -H "$AUTH_HEADER" -X POST http://127.0.0.1:8080/sessions \
  | python3 -c 'import json, sys; print(json.load(sys.stdin)["session_id"])')
curl --fail http://127.0.0.1:8080/tools/call \
  -H "$AUTH_HEADER" \
  -H "X-ANA-Session: $SESSION_ID" \
  -H 'Content-Type: application/json' \
  --data '{"tool":"schema_overview","args":{}}'
curl --fail -X DELETE http://127.0.0.1:8080/sessions/current \
  -H "$AUTH_HEADER" \
  -H "X-ANA-Session: $SESSION_ID"
```

`/tools` remains metadata for compatibility. For an LLM provider use the
`tools` array from `/tools/specs`, which includes descriptions, parameters,
required fields and the effective compatibility overrides. It uses the same
catalog builder as the Python API, without creating a database connection.
Backend tool failures currently become HTTP 400 with `detail`; invalid request
bodies can receive FastAPI's HTTP 422. A missing session header returns 401;
unknown, closed, expired or another app's session returns 404. Session capacity
returns 429; failed backend creation/cleanup returns 503 with a generic message.
Unauthorized, unknown or nonpublic tools return 403 without backend execution.
The full backend-error taxonomy is not stable yet.
After a 404, create a new session and rebuild the workflow; old handles cannot
be transferred to it. The research commands retain their existing database
selection behavior; `NEO4J_DATABASE` here configures the default HTTP adapter.

**Migration:** calls without a session no longer fall back to a shared backend.
Keep both tokens private and send them in headers, never in URLs. A session
is bound to its authenticated client ID: another valid client cannot call or
delete it even with its session token (404). Authentication and tool grants
apply at HTTP boundaries; the trusted Python library does not require an API
key. All sessions still use the app's configured backend credentials/database:
no graph-row/tenant-specific permissions are imposed by client IDs.

The server serializes calls within a session; different sessions can execute
concurrently. Deletion waits for the in-flight operation, clears handles and
closes the owned backend. App shutdown drains backends, including concurrent
session creation. Each `create_app()` owns its own manager; state is not global.

Defaults are `ANA_MAX_SESSIONS=128` and `ANA_SESSION_IDLE_TIMEOUT_S=1800` seconds.
Idle expiration is checked during session/tool requests, not by a background
reaper. Busy/queued workflows are not expired mid-call; shutdown still cleans up
idle sessions if no more requests arrive. These are session-count/idle limits,
not byte, row, connection-pool or per-user rate quotas.

For another engine, inject `create_app(backend_factory=factory, ...)`. The
factory takes a `HandleStore` and must return a **fresh owned**
`AgentGraphBackend` using that store (call the base constructor with
`handle_store=store`). The server manager and `SessionConfig` are engine-neutral;
Neo4j URI/database configuration stays in its adapter. An injected factory does
not cause the default Neo4j connection factory to run.

`ANA_NEO4J_QUERY_TIMEOUT_S` defaults to 30. `ANA_SCHEMA_ENTRY` defaults to
`overview`. Authorization checks decorator profiles on execution as well as
catalog visibility. A schema-entry mode is not a permission. Use database-level
least privilege as well; ANA read-tool grants are not a database security sandbox.

### Standalone Client Example

[`examples/http_workflow.py`](../examples/http_workflow.py) uses only `httpx` and
the standard library. With the server running and `ANA_API_KEY_FILE` configured:

```bash
make demo-client
uv run python examples/http_workflow.py --label YourLabel --page-size 10 --scan-limit 25
```

Alternatively set `ANA_API_KEY` (not the model provider's `API_KEY`). The example
discovers the authorized native catalog and schema, selects an existing label,
creates a bounded `node_scan` handle and follows `fetch.next_offset` until that
handle is exhausted. It prints the rows of each page and closes the workflow
in a `finally` path, including tool failures and empty graphs. It does not
claim the bounded sample contains every matching graph node, retry mutations,
or silently rebuild expired workflows. No Company labels, model, benchmark
files or LLM API key are needed. HTTP failures produce a short diagnostic.

## Docker Server

The Dockerfile packages this HTTP service, not an inference engine or an
ingestion job. It requires a reachable Neo4j and no model API key. From the
repository root, with credentials already exported:

```bash
make docker-build
docker run --rm -p 127.0.0.1:8080:8080 \
  --mount "type=bind,src=$ANA_AUTH_FILE,dst=/run/secrets/ana-auth.json,readonly" \
  -e ANA_AUTH_FILE=/run/secrets/ana-auth.json \
  -e NEO4J_URI=bolt://host.docker.internal:7687 \
  -e NEO4J_USER -e NEO4J_PASSWORD -e NEO4J_DATABASE agent-native-graph
```

The URI above is for Docker Desktop connecting to a host Neo4j. On a Docker
network use your Neo4j container's network address instead; `localhost` inside
the container refers to that container, not the host. Override the example
credentials; use your deployment's environment/secret management rather than
committing them or baking them into an image. `make docker-run` uses the same
loopback binding and requires `ANA_AUTH_FILE`; `make serve` listens on all
interfaces. The image runs as UID/GID 10001 and sets no database credentials in
Docker ENV. The runtime retains local-development connection defaults; configure
your own credentials explicitly. Its healthcheck probes `/health` with the standard library:
healthy does not imply Neo4j or authentication is configured/ready.

**Local, controlled demo only:** static API-key authentication and ownership
checks are not a production identity system, graph-level tenant authorization,
or shared multi-worker storage. Use a trusted TLS reverse proxy outside loopback:
plain HTTP exposes both bearer credentials. Do not expose it to untrusted
networks or add workers expecting sessions to be shared. No rate/byte quotas
or dedicated readiness check have been added in this slice. A successful image
build and smoke test are not a security audit or production-readiness claim.

## Reproducible Distribution Smoke

With uv and Docker running, from the repository root:

```bash
make test-distribution
```

This opt-in check builds the wheel, installs it into a fresh environment outside
the checkout, and runs a copied client with Python isolated mode (`-I`). It
also builds the shipped Dockerfile and calls the real HTTP server. No LLM,
reference repository, Company files or existing Neo4j service is used.

The test creates its own Docker network, a disposable Neo4j container and ANA
containers for property/transaction modes, with dynamically allocated loopback-only ports and generated demo
client keys. It seeds 25 multi-label devices, two zones and one deliberately
unkeyed node. Data includes custom property names, lists, dates and nulls.
The default-mode traversal fixture has globally unique IDs; its unkeyed fixture
documents the unsupported traversal. Additional opt-in probes exercise missing
and duplicate business IDs, nodes with identical properties, changing `id`
between calls, and deletion followed by recreation. Distinct counting is checked
with and without an explicit variable on both duplicate-ID and no-ID twins,
through the installed wheel and the real HTTP service. Legacy and opt-in behavior
are tested separately, not silently substituted for one another.

Checks cover dynamic schema discovery, native catalog parity, counts,
projection, 7/7/7/4-row pagination, batched traversal, workflow/session isolation,
authentication, session deletion/capacity reuse, close on exception and graceful
container shutdown. Five live tests cover installed-wheel and HTTP paths in
both identity modes, plus benchmark finalization from the installed wheel and
inside the shipped image. Finalization checks script model decisions only,
while executing real count/fetch queries against the disposable graph: bounded
mode requires an explicit fetch, including after a rejected `done`, and legacy
fallbacks remain intact. No model endpoint or key is used. The fixture cleans up only its own containers, anonymous
volumes, network and tagged service image, including after test failures. It
never clears or reloads a pre-existing graph. A forcibly killed test process
cannot guarantee cleanup; its temporary resource names begin with `ana-dist-`.

The graph image defaults to `neo4j:2026.05.0`; override it with
`ANA_TEST_NEO4J_IMAGE=<image>` if needed and report that image with test results.
Image/package downloads may be necessary. This check is skipped by ordinary
`make test` and does not certify production security, arbitrary graph shapes,
multi-worker behavior, quotas or automatic schema refresh.

## Your Data and Contributions

Keep your existing ingestion pipeline; ANA's ordinary library/server surface
provides graph access, not generic data loading or write tools. Company is only
the current research benchmark. Some tool behavior still carries historical
assumptions about graph identifiers, names and result shapes; inspect the
effective catalog and test representative operations on your schema before
assuming arbitrary-graph compatibility.

For code and evidence contributions, follow [CONTRIBUTING.md](../CONTRIBUTING.md).
Shared logic belongs behind the same backend/tool contract for Python, CLI and
HTTP, not in a separate implementation for each transport.
