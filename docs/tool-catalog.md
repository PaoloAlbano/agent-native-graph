# Tool Catalog

This catalog describes the current research tool surface exposed from
decorated functions in `src/agent_native_graph/tools/` and executed today by
the Neo4j adapter in `src/agent_native_graph/backends/neo4j/backend.py`. The
exact Python schemas live in code; this document explains the intent.

## Schema and discovery

- `schema_overview`: first-call graph overview. Returns labels, relationship patterns, property names, safe start points, relationship navigation hints, and planning hints.
- `schema_search`: keyword search over labels, relationships, node properties, and relationship properties. Use when question wording must be mapped to schema names.
- `schema_describe_label`: focused description for one label, including properties, examples, lookup candidates, and traversals.
- `schema_describe_relationship`: focused description for one relationship type, including direction, endpoints, properties, and temporal affordances.
- `schema_inspect`: combined schema/affordance payload from earlier experiments. Useful but too large for very large graphs.
- `inspect_paths`: explores possible schema paths between labels when relationship direction or multi-hop structure is uncertain.

## Entity lookup and scans

- `entity_resolve`: fuzzy/exact resolution of a named entity within a label and lookup properties.
- `node_search`: property-based node lookup, usually exact or textual.
- `node_scan`: bounded scan of nodes by label. Useful for small labels; overuse is a smell because it may indicate missing schema/entity anchoring.
- `count_nodes`: count nodes by label with optional filters.

## Traversal and graph query

- `expand`: traverse from a handle through one relationship and create a new handle.
- `expand_aggregate`: traverse and aggregate in one bounded operation.
- `relationship_query`: query relationship instances with endpoints and properties.
- `multi_hop_query`: bounded multi-hop traversal.
- `pattern_query`: generic pattern query for one or more hops. Powerful, but needs careful limits because it can approach free-form Cypher.
- `constraint_query`: structured query with explicit entity/relationship constraints and selected return variables.

## Optional and zero-count queries

- `optional_expand_count`: start from source entities and count optional matches, preserving zero counts.
- `optional_count_by_pattern`: optional grouped count by a structured pattern. Recent fixes make missing optional relationship contracts fail with clear errors.

## Set and logic operations

- `entity_set_operation`: union, intersection, and difference over entity handles.
- `set_count_by_patterns`: count set-style branches without materializing all rows where possible.
- `combine`: combine handles for downstream operations.
- `join_handles`: join two handles on compatible variables/properties.
- `filter`: filter a handle using property predicates.
- `filter_same_node`: enforce that two variables refer to the same node.
- `same_target_role_intersection`: require one entity to satisfy multiple roles against the same target.
- `shared_role_aggregate`: aggregate peers that share an intermediate target/role with a seed entity.

## Aggregation, projection, and finalization

- `project`: project variables or properties from a handle.
- `group_handle` / `aggregate`: group rows by variables/properties and compute metrics such as count/min/max.
- `count_handle`: count rows or distinct entities in a handle.
- `top_entities_by_property`: rank entities by a property.
- `compare`: compare scalar or aggregate outputs.
- `fetch`: retrieve final paginated rows for answer comparison or user-facing output.

## Debug and recovery

- `summarize_handle`: inspect variables, row count, samples, and next traversals for an intermediate handle.
- `handle_recap`: return the lineage of operations that produced a handle.
- `repair_empty_result`: helper for diagnosing empty results.
- `draft_tool_plan` / `validate_tool_plan`: planning tools from experiments. Disabled by default in cleaner benchmark runs.

## Current design judgement

The most useful generic primitives so far are schema discovery, entity resolution, bounded traversal, set operations, grouping, projection, and fetch. The riskiest tools are the broad pattern tools: they improve coverage, but if they become too expressive they recreate text-to-Cypher under another name.
