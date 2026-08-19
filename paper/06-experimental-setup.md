# 6. Experimental Setup

`ANA-PAPER-EXPERIMENTS`

The current experiments focus on the `company` slice of the CypherBench test
split.

## Data

The graph is loaded into Neo4j from the CypherBench SimpleKG company data. The
repository keeps generated data and raw downloads out of git by default; the
reproduction guide documents how to regenerate or provide them locally.

## Compared Approaches

The research code supports:

- gold Cypher execution;
- zero-shot text-to-Cypher;
- multi-agent/self-correcting text-to-Cypher;
- Multi-Agent GraphRAG-style text-to-Cypher;
- ANA tool-call trajectories over Neo4j.

## Benchmark Protocol

All approaches should be evaluated on the same ordered task subset and the same
loaded Neo4j graph snapshot. Each task contains a natural-language question,
gold Cypher, and expected `answer_json`. A run is considered correct when the
produced answer matches the expected answer under the deterministic evaluator.

For paper-ready comparisons, every run should record:

- model name and provider;
- temperature and reasoning/thinking profile;
- max token budget;
- max agent/tool steps;
- retry and timeout policy;
- number of LLM calls;
- number of tool calls;
- technical success or failure reason;
- final answer and correctness.

The current default comparison target is the first 100 examples from the
CypherBench `company` test split, but final experiments should also report
larger subsets when rate limits and cost allow.

## Baseline Implementations

The direct text-to-Cypher baseline gives the model schema information and asks
it to produce a Cypher query for Neo4j. The generated query is executed and the
result is scored against `answer_json`.

The multi-agent/self-correcting baseline adds an iterative correction loop:
failed or suspicious Cypher generations can be revised using execution errors,
empty results, or evaluator feedback, depending on the configured baseline.

The Multi-Agent GraphRAG-style baseline follows the related-paper framing more
closely by separating planning, generation, execution, and correction roles.
The exact role prompts and stopping rules should be documented before final
comparison.

The ANA approach gives the model native tool-call access to the agent-native
tool catalog. Instead of producing Cypher, the model composes schema discovery,
entity grounding, handle-building, set operation, aggregation, projection, and
fetch tools until it returns a final answer.

## Metrics

The primary metric is deterministic execution accuracy against CypherBench
`answer_json`. We also track technical success, tool-call count, LLM-call count,
token usage, and error classes.

## Default Run Settings

Current investigation defaults:

- `max_tokens=16000`;
- `max_steps=12`;
- deterministic profile: `temperature=0`;
- realistic profile: `temperature=1` with reasoning/thinking effort `medium`;
- default concurrency: `3`, adjusted for rate limits.
