# 4. Knowledge Graph QA Case Study

Knowledge graph question answering is a strong testbed for Agent-Native APIs
because graph questions often require explicit reasoning over schema and
relationships.

Common failure points for text-to-Cypher include:

- choosing the wrong relationship direction;
- using a label or property that does not exist;
- confusing entity names with property names;
- missing optional zero-count semantics;
- grouping by the wrong variable;
- returning duplicate entities;
- generating broad queries that are syntactically valid but semantically wrong.

ANA exposes those choices as separate steps. This makes the trajectory easier to
inspect and gives the agent more opportunities to correct itself before the
final answer.

The empirical scope here is deliberately limited to Company. The normalized
graph used by the archived experiments contains 581,306 nodes and 299,581
relationships, as recorded by the verified evaluation fingerprints. Its 347
test questions cover operations such as entity lookup, relationship constraints,
set composition, optional counts and property-based ordering. A second scope
uses the exact 100 questions shared with the reference baseline traces.

This is one case study of data access, not a benchmark of document summarization
or a demonstration of universal knowledge-graph reasoning. Graph storage and
query execution still use Neo4j; the intervention is the interface and agent
workflow. SQL, SDKs and other data interfaces remain prospective applications.
