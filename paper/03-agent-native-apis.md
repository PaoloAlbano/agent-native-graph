# 3. Agent-Native APIs

`ANA-PAPER-METHOD`

Agent-Native APIs are APIs designed around the behavior and constraints of LLM
agents.

The slogan for this project is:

> MCP is transport. ANA is interface design.

MCP can expose tools, but it does not determine which tools should exist, how
they should be bounded, what intermediate state should look like, or how an
agent should recover from uncertainty.

ANA prioritizes:

- discovery before execution;
- handles instead of raw intermediate rows;
- bounded operations by default;
- pagination and safe limits;
- explicit set operations;
- explicit grouping and aggregation;
- result lineage and inspectability;
- generic tools rather than dataset-specific shortcuts.

## ANA Interface Model

An ANA interface can be described as a small set of typed operations over
server-side state:

- **Discovery operations** expose schema, examples, affordances, and safe
  starting points before the agent commits to a plan.
- **Grounding operations** map user text to concrete entities, properties, or
  identifiers in the data system.
- **State-building operations** create bounded intermediate results and return
  handles instead of large raw payloads.
- **Composition operations** combine, filter, join, compare, or aggregate
  existing handles.
- **Finalization operations** project and fetch the answer with explicit limits
  and pagination.

A handle is the key abstraction. It is an opaque server-side reference to an
intermediate result plus metadata such as row count, variables, sample values,
lineage, and pagination state. The model keeps large intermediate data outside
the prompt while still giving the agent enough information to decide the next
step.

The intended execution trace is therefore not a single generated artifact, but a
sequence:

```text
question
  -> discover schema
  -> ground entities/properties
  -> build bounded intermediate handles
  -> compose/filter/aggregate handles
  -> fetch final answer
```

In a graph setting, this means replacing one-shot query generation with
operations such as `schema_overview`, `entity_resolve`, `expand`,
`entity_set_operation`, `group_handle`, `project`, and `fetch`.
