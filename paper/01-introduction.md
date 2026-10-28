# 1. Introduction

`ANA-PAPER-INTRODUCTION`

Formal query languages were designed to let humans describe data access
precisely. Cypher, SQL, and SPARQL are successful because they compress
complex data operations into compact, readable syntax for trained operators.

LLM agents are different users. They can write formal language, but they are also
good at iterative exploration: inspect, try, summarize, repair, combine, and
verify. This raises the central question of this project:

**Should data systems expose only human-native query languages to agents, or
should they expose agent-native APIs designed for how agents actually operate?**

We investigate this question in knowledge graph question answering, where the
gap is especially visible. Each text-to-Cypher candidate encodes schema,
relationship direction, entity names, optional semantics, grouping and return
shape. Even with iterative repair, a mistake can affect the whole query. ANA
offers an alternative decomposition into explicit, composable operations.

The broader goal, however, is not limited to graphs. The same design question
appears whenever agents are asked to use interfaces originally designed for
humans: SQL over relational databases, SPARQL over RDF stores, command-line
interfaces, SDKs, or programming languages. ANA frames these not as fixed
interfaces that agents must adapt to, but as design spaces where we can build
agent-facing operations that improve reliability, inspectability, and task
performance.

The core claim is not that Cypher should disappear or that LLMs cannot use
formal languages. Human-facing query interfaces remain useful, as do agentic
systems that inspect schema and repair generated queries. ANA asks whether
explicit operations and intermediate state offer a useful alternative. A tool
call is itself a formal contract; the question is where expressiveness and
responsibility should live, not whether to eliminate structure.

This draft contributes a design framing, an executable graph case study and
auditable observational evidence. The implementation exposes a fixed catalog
without a question-answering model inside the data service. The evaluation
separates full-split behavior from a shared-question comparison, preserves
per-question trajectories and reports known scoring/provenance limitations.
It does not claim the first tool-based graph interface or a generally superior
replacement for query languages.

## Research Questions

- **RQ1, retrieval quality:** how do ANA and saved query-generation pipelines
  compare on the same Company questions under a common exact-result metric?
- **RQ2, reliability:** which trajectories fail to terminate, and which finish
  with incorrect answers despite valid operations or recovered tool errors?
- **RQ3, profile sensitivity:** how do observed outcomes change across requested
  temperature/thinking profiles, without assuming a single run estimates variance?
- **RQ4, transfer and efficiency:** can the interface improve unseen-domain
  behavior or compute efficiency under controlled budgets? This remains open;
  the current Company observations do not answer it.
