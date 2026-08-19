# Lessons Learned

## 1. Tool shape matters as much as model choice

Changing descriptions, parameter contracts, and result payloads can move quality by several points. For LLM agents, a tool schema is not only a type contract: it is also instruction, affordance, and search space.

## 2. Dataset-specific shortcuts are tempting but dangerous

Vertical tools can improve a benchmark quickly, but they weaken the claim. The useful direction is generic graph operations that happen to solve benchmark questions well.

## 3. Schema discovery is mandatory

Agents need reliable ways to discover labels, properties, relationship directions, examples, and possible paths. Passing a single huge schema blob works on small graphs, but large graphs need targeted schema tools.

## 4. Handles are the right abstraction

Server-side handles let the agent build intermediate state without pulling large row sets into the prompt. They also make pagination, summaries, and lineage possible.

## 5. Pagination and limits must be default behavior

Every graph operation can explode. ANA tools should return counts, samples, limit hints, and explicit next-page mechanisms instead of dumping everything.

## 6. Broad pattern tools are a tradeoff

`pattern_query` and `constraint_query` improve coverage, but if they become too free-form they start to approximate generated Cypher. The design target is structured power: enough expressiveness for real questions, not arbitrary query synthesis.

## 7. More reasoning is not always better

Higher temperature and reasoning can improve some models and hurt others. We need evaluate both deterministic and realistic agent profiles.

## 8. Technical success and answer correctness are different

A run can complete without tool errors and still return semantically wrong answers. The benchmark must track both.

## 9. MCP is insufficient as a design answer

MCP can expose a tool list, but it does not guarantee the tools are agent-native. ANA focuses on the design of the operations themselves.
