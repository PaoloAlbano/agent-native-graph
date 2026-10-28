# 3. Agent-Native APIs

`ANA-PAPER-METHOD`

Agent-Native APIs are APIs designed around the behavior and constraints of LLM
agents.

ANA concerns interface semantics, independently of the transport used to expose
them. MCP standardizes tool discovery and invocation, among other capabilities;
it does not select a task's operation vocabulary. An ANA implementation can use
MCP, native function calls, HTTP or a CLI without changing the underlying use
cases. The current benchmark uses native function calls, not an MCP server.

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

In a graph setting, this means replacing the generated-query boundary with
operations such as `schema_overview`, `entity_resolve`, `expand`,
`entity_set_operation`, `group_handle`, `project`, and `fetch`.

## Scope Of The Abstraction

The model selects the next operation and its arguments using the question and
previous responses. The backend validates and executes the operation, owns
intermediate state and returns observations. It contains no LLM that plans or
answers on the agent's behalf. The public catalog is fixed across questions;
there is no benchmark-QID router that chooses a tool subset for a known task.

The API does not eliminate planning: the model still chooses variables,
directions, predicates and result shape. Entity handles retain identity for
composition; projection can instead produce scalar tables that are unsuitable
for later entity traversal. Descriptions and shape metadata must make that
transition explicit. Generic operations are intended to transfer to new graphs,
but developing them against Company questions does not demonstrate transfer.

Bounding results is a design goal, not a universal complexity guarantee. Small
pages can still require expensive upstream graph operations, and the current
prototype has no global row/byte quota. State visibility and execution safety
must therefore be evaluated separately from final-answer accuracy.
