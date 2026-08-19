# Abstract

`ANA-PAPER-ABSTRACT`

Large language model agents are increasingly used to access structured data, but
the dominant interface pattern still asks models to generate human-oriented
formal query languages such as Cypher, SQL, or SPARQL. These languages
are compact and expressive for trained human users, yet they force an LLM to
solve schema discovery, entity resolution, join planning, aggregation, and result
projection in a single brittle artifact.

This project studies **Agent-Native APIs (ANA)**: data-access APIs designed
around the operational needs of LLM agents. Instead of producing one end-to-end
query, an agent composes bounded tools for schema discovery, entity resolution,
graph traversal, set operations, aggregation, pagination, and final fetching.

We evaluate the idea on the `company` slice of CypherBench using a Neo4j-backed
research wrapper and compare it with direct text-to-Cypher and multi-agent
text-to-Cypher baselines. Current results suggest that generic agent-native graph
tools can reach competitive accuracy while providing safer intermediate state,
explicit pagination, and more inspectable failure modes.
