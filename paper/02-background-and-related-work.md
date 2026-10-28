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

This direction predates ANA. [StructGPT](https://aclanthology.org/2023.emnlp-main.574/)
separates reading structured sources through specialized interfaces from
reasoning about retrieved evidence, using an iterative loop across knowledge
graphs, tables and databases. It is a close conceptual precedent: this draft
does not introduce interface-mediated access to structured data for LLMs.

[AgentBench's KG environment](https://arxiv.org/html/2308.03688v3)
already exposes relation discovery, neighbor traversal, intersection, extrema
and counting. Its appendix represents intermediate entity sets with numbered
variables and selects a final variable as the answer. This directly overlaps
with ANA's composition over handles. Neither intermediate references nor graph
operations exposed to agents are novel by themselves. Differences in grounding
assumptions, graph representation and evaluation prevent treating AgentBench's
published scores as baselines for our Company experiment.

## Tool-Using Agents

Recent agent systems expose external functions to LLMs through tool calling,
function calling, or transport protocols such as MCP. These mechanisms are
important, but they mostly define how tools are advertised and invoked. They do
not answer the interface-design question: which tools should exist, how much
power each tool should have, how results should be bounded, and what state
should be kept outside the prompt.

[ReAct](https://arxiv.org/abs/2210.03629v3) interleaves reasoning and actions
that gather observations from external sources. ANA uses an action/observation
loop, but studies a data-access vocabulary rather than introducing that loop.
Our saved records do not contain the model's raw reasoning text; calling them
tool trajectories must not imply that they reproduce ReAct thought traces.

## Graph Question Answering And GraphRAG

Knowledge graph question answering and GraphRAG systems both highlight the
importance of schema, entity grounding, traversal, and evidence retrieval.
Text-to-Cypher approaches test whether a model can generate executable graph
queries, while GraphRAG-style approaches often combine retrieval and reasoning
over graph neighborhoods. ANA is related to both, but focuses on the shape of
the data-access interface itself.

[Think-on-Graph](https://arxiv.org/abs/2307.07697v6) uses an LLM to explore
entities and relations through iterative beam search over a KG. Graph exploration
and evidence-grounded reasoning are therefore established precedents. ANA's
case study emphasizes table-shaped retrieval, role joins and aggregation through
an explicit API; it does not establish that these outperform ToG or replace
its search strategy. ToG has not been run as a Company baseline here.

## Beyond Graphs

The same pattern appears in relational data and technical software interfaces.
Text-to-SQL systems ask models to discover schema, plan joins, aggregate, and
project results in one query. Agents using SDKs, command-line tools, or
programming languages face similar issues: human-oriented interfaces expose
powerful abstractions, but not necessarily the safest or most legible
interaction loop for an agent.

[DIN-SQL](https://arxiv.org/abs/2304.11015v3) decomposes text-to-SQL into
subproblems and includes self-correction. Consequently, a contrast between
ANA and query generation must not imply that all text-to-query systems are
monolithic or non-interactive. The distinction under study is the public
operation/state contract, not decomposition alone. SQL transfer remains a
future experiment rather than a result borrowed from this work.

## Positioning This Study

[CypherBench](https://arxiv.org/abs/2412.18702v2) introduces property-graph views
and a text-to-Cypher evaluation setting for knowledge retrieval. We reuse its
Company tasks and graph, while changing the interface presented to the model.
Our exact-answer metric is defined separately from its official execution and
provenance metrics. This is an interface case study, not a replacement benchmark.

[Multi-Agent GraphRAG](https://arxiv.org/abs/2511.08274v1) studies iterative
Cypher generation with execution feedback and entity verification. We compare
against saved runs from an independent, pinned implementation, not the paper's
published experimental scores. Our distinction is operational: models compose
graph-access tools rather than refine an end-to-end query. Both approaches can
use multiple steps and recover from errors.

The [MCP tool specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
defines discovery, schemas and invocation. ANA complements that protocol-level
contract by treating operation granularity and state semantics as design choices.
Native tool calling alone is not the proposed contribution. Verified
bibliographic entries are maintained in [references.bib](references.bib).

## Overlap And Evaluation Boundary

| Prior work | Established overlap | Scope of the present study |
| --- | --- | --- |
| StructGPT | Iterative access to structured data through specialized reading interfaces. | A concrete property-graph API with exact-table scoring and archived Company trajectories; no head-to-head StructGPT experiment. |
| AgentBench KG | Discovery, graph operations and numbered intermediate variables. | Grounding and composition contracts on Company, not invention of graph tools or intermediate references; no AgentBench score comparison. |
| ReAct | Alternating actions and observations to support multi-step reasoning. | The data-access interface vocabulary; no claim of a new agent loop or reconstructed thought traces. |
| Think-on-Graph | LLM-guided exploration of graph entities and relations. | A broader operator case study, without a controlled comparison to ToG's search. |
| DIN-SQL | Decomposition and correction within a query-generation workflow. | API semantics rather than the first use of decomposition; no SQL result is reported. |
| Multi-Agent GraphRAG | Feedback-driven refinement of generated Cypher. | Saved-query comparison to a pinned independent implementation, with generation-condition caveats. |
| MCP | Tool discovery, schemas and invocation. | Complementary operation design, not a replacement protocol or a measured MCP advantage. |

These precedents narrow the contribution: ANA is a design framing and an
auditable implementation/evaluation case study, not the first graph-tool API,
the first stateful graph agent, or evidence that all human-oriented languages
are unsuitable for LLMs. A future controlled experiment should include a
minimal discovery/traversal/intersection/count vocabulary inspired by existing
KG interfaces, alongside the broader ANA catalog. That ablation is proposed,
not executed. This review is selective rather than an exhaustive priority search.
