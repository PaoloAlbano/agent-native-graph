# Agent-Native APIs

Agent-Native APIs (ANA) are APIs designed around the operational needs of LLM agents rather than the habits of human operators.

The core claim is not that Cypher, SQL, SPARQL, or other formal query languages are bad. They are excellent human-facing abstractions: concise, expressive, compositional, and precise. The question is whether asking an LLM to generate one complete formal query is always the best interface for agentic data access.

ANA explores a different interface contract.

## Human-native query languages

Human-native query languages optimize for:

- compact syntax;
- expert control;
- end-to-end expressiveness;
- readability for trained users;
- transportability across tools and notebooks;
- one-shot execution.

This is powerful, but it makes text-to-query brittle. An LLM must infer schema, choose labels and relationships, get directionality right, compose filters, express joins, handle grouping, avoid accidental cartesian products, and return the right projection in a single formal artifact.

## Agent-native graph operations

Agent-native graph APIs optimize for:

- schema discovery before execution;
- safe entity resolution;
- bounded traversal;
- server-side handles for intermediate state;
- explicit set operations;
- explicit aggregation and projection;
- pagination and result limits;
- inspectable execution traces;
- recovery from empty or suspicious intermediate results.

Instead of generating one complete query, the agent composes graph operations step by step.

## Design principles

1. **Discovery is a first-class operation.** The agent should ask what labels, relationships, properties, examples, and directions exist before choosing a plan.

2. **Handles beat raw rows.** Large intermediate results should stay server-side and can be cached. The agent receives a handle, summary, count, sample, and next-action hints.

3. **Operations should be bounded by default.** Every scan, traversal, projection, and fetch should have limits and pagination.

4. **Composition should be explicit.** OR, AND, intersection, union, difference, group-by, order-by, and max/min should be exposed as operations instead of hidden in generated Cypher.

5. **Tool descriptions are part of the API.** For an LLM, the function name, description, parameter schema, examples, and counterexamples are equivalent to developer documentation.

6. **Generic does not mean unconstrained.** Tools should not be vertical shortcuts for one dataset, but they should still encode safe graph affordances.

7. **MCP is not enough by itself.** MCP can transport tools. ANA defines how to design the tools.

## Graph use case

This repository applies ANA to knowledge graph question answering. The current
backend is Neo4j, but the interface design is not meant to be Neo4j-specific or
even graph-only. The same ideas should be portable to other graph engines and,
more broadly, to other data systems where an agent needs to discover structure,
retrieve evidence, compose intermediate state, and extract answers safely.
