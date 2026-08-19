# ANA v0 Tool Contract

ANA v0 is the first stable-ish tool surface for the research prototype. It is not a permanent standard yet, but it gives us a shared boundary between:

- reusable API design;
- benchmark runners;
- optional HTTP/MCP transports;
- future GraphArrow integration.

The public catalog lives in `src/agent_native_graph/core/tool_contract.py`.
Executable tools should declare metadata next to their implementation with
`@tool(...)` from `src/agent_native_graph/core/tooling.py`; native LLM tool-call
specs are generated from those decorators as tools are migrated.

## Stability classes

- `core`: generic tools that should remain available in the first production-oriented wrapper.
- `experimental`: useful but still semantically risky or too broad.
- `deprecated`: kept only for backward compatibility with old runs.

## Current core categories

- Schema discovery: `schema_overview`, `schema_search`, `schema_describe_label`, `schema_describe_relationship`, `inspect_paths`.
- Entity lookup: `entity_resolve`, `node_search`.
- Safe traversal: `expand`, `relationship_query`.
- Logic and state: `entity_set_operation`, `summarize_handle`, `handle_recap`.
- Aggregation/projection/finalization: `group_handle`, `project`, `fetch`.
- Optional semantics: `optional_expand_count`.

## Experimental tools to keep watching

- `pattern_query`: very useful, but can become text-to-Cypher-by-proxy if it is too permissive.
- `constraint_query`: powerful for multi-constraint questions, but needs strict contracts.
- `multi_hop_query`: can become expensive and semantically ambiguous.
- `optional_count_by_pattern`: useful for zero-count grouped queries, but contract is still fragile.
- `node_scan`: useful for small labels, risky as a default plan.

## Design requirements

Every ANA tool should define:

- when to use it;
- when not to use it;
- required parameters only;
- default limits;
- pagination behavior;
- handle semantics;
- whether it is `readonly` or `readwrite`;
- failure modes that the model can recover from.
