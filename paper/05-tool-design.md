# 5. Tool Design

`ANA-PAPER-TOOL-DESIGN`

The current ANA v0 graph tool surface is organized around a few reusable
categories.

## Schema Discovery

Schema tools help the agent map language to graph structure before execution.
Examples: `schema_overview`, `schema_search`, `schema_describe_label`,
`schema_describe_relationship`, `inspect_paths`.

These tools answer questions such as: which labels exist, which relationships
connect them, which properties are available, which directions are valid, and
which paths are plausible. They reduce hallucinated labels, wrong relationship
directions, and unnecessary scans.

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

`expand` is the safest primitive because it moves exactly one hop from an
existing handle. `relationship_query` starts from an explicit single-hop pattern
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
