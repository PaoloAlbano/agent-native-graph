# 2. Background And Related Work

`ANA-PAPER-BACKGROUND`

## Human-Native Query Languages

Cypher, SQL, and SPARQL expose powerful formal abstractions for humans.
They optimize for compactness, expressiveness, and control. They assume the user
can inspect schema, understand operators, and debug syntax or semantic mistakes.

## Text-To-Query

Text-to-query approaches ask an LLM to translate natural language into a formal
query. This is attractive because it reuses mature database interfaces, but it
also makes one generation carry many responsibilities:

- schema selection;
- relationship and join planning;
- entity resolution;
- filter construction;
- aggregation;
- projection;
- ordering;
- syntax validity;
- execution correctness.

## Agentic Data Access

Agents can interact with tools over multiple steps. This allows a different
design: instead of generating a complete formal query immediately, the model can
discover schema, build intermediate handles, inspect partial results, combine
sets, aggregate, and fetch the final answer.

## Tool-Using Agents

Recent agent systems expose external functions to LLMs through tool calling,
function calling, or transport protocols such as MCP. These mechanisms are
important, but they mostly define how tools are advertised and invoked. They do
not answer the interface-design question: which tools should exist, how much
power each tool should have, how results should be bounded, and what state
should be kept outside the prompt.

## Graph Question Answering And GraphRAG

Knowledge graph question answering and GraphRAG systems both highlight the
importance of schema, entity grounding, traversal, and evidence retrieval.
Text-to-Cypher approaches test whether a model can generate executable graph
queries, while GraphRAG-style approaches often combine retrieval and reasoning
over graph neighborhoods. ANA is related to both, but focuses on the shape of
the data-access interface itself.

## Beyond Graphs

The same pattern appears in relational data and technical software interfaces.
Text-to-SQL systems ask models to discover schema, plan joins, aggregate, and
project results in one query. Agents using SDKs, command-line tools, or
programming languages face similar issues: human-oriented interfaces expose
powerful abstractions, but not necessarily the safest or most legible
interaction loop for an agent.
