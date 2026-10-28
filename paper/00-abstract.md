# Abstract

`ANA-PAPER-ABSTRACT`

Large language model agents are increasingly used to access structured data, but
a common interface pattern asks models to generate human-oriented
formal query languages such as Cypher, SQL, or SPARQL. These languages
are compact and expressive, but each generated query must encode schema choices,
entity grounding, relationships, aggregation and projection correctly. Query
repair can be iterative; the interface itself nevertheless remains query-centric.

This project studies **Agent-Native APIs (ANA)**: data-access APIs designed
around the operational needs of LLM agents. Instead of producing one end-to-end
query, an agent composes bounded tools for schema discovery, entity resolution,
graph traversal, set operations, aggregation, pagination, and final fetching.

We study a Neo4j-backed implementation on the 347-question Company test split
of CypherBench. Nine archived runs across GPT-OSS-120B and Qwen3.5-27B obtain
78.7%-87.0% exact answer matches. A separate comparison on 100 shared questions
re-executes saved direct and multi-agent text-to-Cypher queries on a verified
graph, applying the same exact-result comparator to all three approaches.
For Qwen3.5-27B at temperature 1 with requested medium reasoning, ANA matches
87/100 answers, versus 59/100 for direct and 62/100 for multi-agent queries.
These are observational comparisons of archived systems, not a controlled
causal estimate or official full-benchmark CypherBench execution accuracy.

The evidence motivates treating API design as an experimental variable in
agent reliability. It does not establish cross-domain generalization, lower
cost or production safety: the tools were developed with Company feedback,
historical generation conditions differ, and replication remains limited.
