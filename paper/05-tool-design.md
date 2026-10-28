# 5. Tool Design

`ANA-PAPER-TOOL-DESIGN`

The default `overview` native catalog contains 35 read-only operations. The
catalog stays fixed across questions; two optional planning tools are excluded
from the reported treatment. Definitions, descriptions and parameter schemas
come from decorated functions, with effective compatibility overrides captured
by the standard run's tool hash. The [catalog](../docs/tool-catalog.md) exposes
the current contracts; archived hashes identify the measured treatment.

| Family | Operations | Design responsibility |
| --- | --- | --- |
| Discovery | `schema_overview`, `schema_search`, `schema_describe_label`, `schema_describe_relationship`, `inspect_paths` | Identify schema and plausible routes before constructing a data-access plan. |
| Grounding and lookup | `entity_resolve`, `node_search`, `value_search`, `node_scan` | Anchor text to entities or property values; scans are a fallback, not a counting strategy. |
| Traversal and patterns | `expand`, `expand_aggregate`, `optional_expand_count`, `optional_count_by_pattern`, `relationship_query`, `multi_hop_query`, `pattern_query`, `constraint_query` | Build graph-derived state, including optional and multi-constraint cases. |
| Composition and filtering | `entity_set_operation`, `filter`, `filter_same_node`, `join_handles`, `combine` | Preserve identities and bindings while composing branches or joining intermediate results. |
| Role joins | `same_target_role_intersection`, `shared_role_aggregate` | Express shared-entity constraints through role parameters rather than named question-specific endpoints. |
| Aggregation and finalization | `count_nodes`, `count_handle`, `group_handle`, `top_entities_by_property`, `project`, `compare`, `scalar_compute`, `fetch` | Compute metrics, shape answers and retrieve a stored result page. |
| Diagnostics | `summarize_handle`, `handle_recap`, `repair_empty_result` | Inspect shape, lineage and schema-grounded recovery suggestions. |

Five operations are marked experimental: `node_scan`,
`optional_count_by_pattern`, `multi_hop_query`, `pattern_query` and
`constraint_query`. Status is a design-maturity label, not a permission grant.

## Schema Discovery

Schema tools help the agent map language to graph structure before execution.
Examples: `schema_overview`, `schema_search`, `schema_describe_label`,
`schema_describe_relationship`, `inspect_paths`.

These tools answer questions such as: which labels exist, which relationships
connect them, which properties are available, which directions are valid, and
which paths are plausible. They are intended to reduce hallucinated labels,
wrong relationship directions and unnecessary scans; the present experiment
does not isolate that effect with an ablation.

## Entity Resolution

Entity tools anchor the plan to concrete graph nodes. Examples: `entity_resolve`
and `node_search`.

These tools separate entity grounding from traversal. The agent should not need
to guess whether a user phrase is a node name, an alias, a property value, or a
label. Resolution tools return candidate nodes, confidence-relevant metadata,
and handles that later operations can consume.

## Handles

Most operations return server-side handles. A handle represents intermediate
state without forcing the agent to materialize every row into the prompt.

Handle-oriented tools include `summarize_handle`, `handle_recap`, and
`count_handle`. They let the agent inspect row counts, variables, samples,
lineage, and result shape before deciding whether to continue, refine, or fetch.

## Traversal And Query

Traversal tools expose bounded graph movement. Examples: `expand`,
`relationship_query`, `multi_hop_query`, `pattern_query`, `constraint_query`.

`expand` constrains movement to one hop from an existing handle; this limits
operator scope, not necessarily result cardinality or runtime.
`relationship_query` starts from an explicit single-hop pattern
without requiring a prior handle. Broader tools such as `pattern_query`,
`constraint_query`, and `multi_hop_query` cover questions that are awkward to
express as many small steps, but they remain experimental because too much
expressiveness can recreate text-to-Cypher behind a tool boundary.

## Set Operations

Set operations make OR, AND, and NOT explicit. Example:
`entity_set_operation`.

They allow the agent to solve compound questions by building separate handles
and then applying union, intersection, or difference. This is important for
questions such as "entities that satisfy A or B" and avoids forcing the model to
encode all logic inside a single generated query.

## Aggregation And Finalization

Aggregation and finalization tools control answer shape. Examples:
`group_handle`, `project`, `count_handle`, `fetch`.

`group_handle` computes grouped metrics such as count, min, or max over an
existing handle. `project` extracts the properties needed for the answer.
`fetch` is the final boundary: it materializes a page of rows for benchmark
scoring or user-facing output, with pagination available for large results.
The public `ana-fetch-v1` contract separates a complete page from a small preview.
The research adapter retains the historical preview transcript and evaluates
full final rows, including benchmark-only all-page collection when enabled.
This distinction must not be presented as model-driven pagination or perfect
completeness of the upstream graph query.

## Recovery And Diagnostics

Recovery tools help the agent understand suspicious or empty intermediate
results. Examples: `repair_empty_result`, `summarize_handle`, and
`handle_recap`.

These tools are not meant to answer the user directly. They expose enough
execution context for the agent to repair direction mistakes, missing
constraints, wrong variable choices, or malformed handle references without
falling back to arbitrary broad scans.

## Safety Requirements

ANA tools should define limits, pagination, handle semantics, failure modes, and
read-only/read-write profiles. Broad tools remain useful, but they must not
quietly become arbitrary query-generation backdoors.

These are requirements with partial implementation, not a demonstrated safety
theorem. The demo HTTP layer has client authentication, session ownership and
profile checks, while the benchmark calls a backend directly. Both are separate
from row-level tenancy or proof of bounded resource use. The backend builds
Cypher internally; broad pattern tools still require the model to select
variables and constraints. Tool calling shifts some query-construction work
into reusable code rather than eliminating formal structure or failure modes.
