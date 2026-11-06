# Agent-Native Graph v0.1.3

## Shared runtime for graph adapters

`SharedGraphBackend` is available from `agent_native_graph` and
`agent_native_graph.core.runtime`. Schema discovery, planning and local handle
operations now live in engine-neutral modules. The Neo4j backend inherits them
and retains all driver/query implementations and identity handling. GraphArrow
and other graph engines can implement the data hooks without subclassing Neo4j.

## Session-local short handles

Isolated workflow stores now return `h1`, `h2`, and subsequent local names.
The internal workflow namespace remains independent and supplies entity identity.
A handle is identified by its workflow/session and local name together. Clients
that cached handles globally must instead retain that pair. HTTP calls continue
to require authentication and `X-ANA-Session`; another client's session remains
inaccessible. Short handle names are not authentication credentials.

Use `HandleStore.isolated(compact_ids=False)` for the prior namespaced formatting.
Direct low-level stores retain their previous default format. Store counters are
not reset by `clear()`, and summary/repair hints follow creation order beyond h9.

Session creation returns `X-ANA-Session` in both the response header and existing
JSON body. Successful tool calls and deletion echo the header; authenticated
execution errors echo it after ownership checks. JSON envelopes and all 35
default tool schemas plus the two opt-in planning schemas remain unchanged.

See [the library/server guide](library-and-server.md) for adapter hooks and
[the release procedure](releases.md) for artifact verification. These changes do
not add graph writes, distributed workflow state or operating-system memory limits.
