# 11. Future Work

`ANA-PAPER-FUTURE-WORK`

Near-term research remains focused on Company:

A [prospective protocol](../docs/controlled-company-protocol.md) now defines the
matched-condition design and implementation gates. It is not executable today
and requires separate approval before inference; the entries below remain
future work rather than completed experimental evidence.

- freeze an interface treatment and repeat profiles to estimate variation;
- generate future evaluation tasks independently of tool-design feedback;
- run fresh baseline generations with aligned graph, model revision and budgets;
- ablate descriptions, catalog breadth, handles and broad pattern operators;
- compare the broader catalog with a minimal KG-operation vocabulary grounded
  in existing interface-based approaches, not only query-generation baselines;
- capture failed response diagnostics safely and separate terminal/recovered errors;
- measure cost and latency with complete, consistently defined call accounting.

The current implementation already separates backend contracts from research
orchestration and provides Python and demo HTTP access. These engineering steps
are not pending research results. Future work includes scalable schema discovery,
resource limits, additional backend adapters and optional MCP exposure; those
features should not alter a benchmark treatment without a recorded new version.

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

Cross-domain validation is necessary before claiming generalization, but no
additional CypherBench category is part of the current experiment plan. The
relational/SQL direction tests the broader ANA hypothesis rather than assuming
that a graph-specific tool vocabulary transfers unchanged.
