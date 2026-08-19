# 11. Future Work

`ANA-PAPER-FUTURE-WORK`

Near-term work:

- consolidate comparable baseline tables;
- test on more CypherBench categories and additional graph datasets;
- split the Neo4j backend from benchmark orchestration;
- make schema discovery scalable for large graphs;
- stabilize ANA v0 tool contracts;
- evaluate read-only versus read-write tool profiles;
- expose the same backend through CLI, HTTP, and MCP adapters.

Longer-term work:

- port ANA operations to GraphArrow;
- compare agent-native graph access against text-to-Cypher on multiple graph
  engines;
- test whether ANA-style interfaces improve agent performance on structured
  relational data, especially SQL workloads where schema discovery, joins,
  aggregation, and result shaping are common failure points;
- explore ANA-style wrappers for other human-oriented technical interfaces,
  including SDKs, command-line tools, and programming-language workflows;
- study cost, latency, and tool-call efficiency;
- define a reusable methodology for designing agent-native APIs beyond graphs.
