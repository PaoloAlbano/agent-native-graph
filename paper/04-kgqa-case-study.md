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
