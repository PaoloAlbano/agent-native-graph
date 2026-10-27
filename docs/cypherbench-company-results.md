# ANA on CypherBench Company (347 Questions)

This page describes ANA's behavior on the complete `company` test split. It is
not a comparison with Multi-Agent GraphRAG. That comparison has a separate
[100-question protocol](multigraphrag-comparison.md).

## Evidence

The four retained complete ANA runs are under
[`results/cypherbench-company/full/runs/`](../results/cypherbench-company/full/runs/).
Each run has a manifest, all 347 per-question records, a summary, and the
non-matching cases. [`index.json`](../results/cypherbench-company/index.json)
lists their model, profile, and score. The October runs have complete task,
graph, and run hashes. They are individual observations; concurrency differs
between the two GPT-OSS temperature-0 runs.

| Model | Profile | Run date | Exact answers | Executed |
|---|---|---|---:|---:|
| GPT-OSS-120B | temp 0, no reasoning | Oct 24 | 296/347 | 341/347 |
| GPT-OSS-120B | temp 1, medium reasoning | Oct 24 | 292/347 | 336/347 |
| GPT-OSS-120B | temp 0, no reasoning | Oct 25 | 291/347 | 346/347 |
| Qwen3.5-27B | temp 0, no reasoning | Oct 25 | 294/347 | 344/347 |

`Exact answers` counts row-wise matches to CypherBench `answer_json`.
`Executed` counts questions without an execution or termination failure; it
does not imply a correct answer. Scores are observations from individual runs,
not estimates of model-level variance.

## Interpreting Failures

The [`gold-validation` report](../results/cypherbench-company/gold-validation.md)
shows that the stored gold Cypher executes for all 347 questions but reproduces
`answer_json` for only 345 on this Neo4j graph. Keep all 347 in the primary
denominator. The discrepancies remain documented; no question is excluded
from the primary scores.

The full per-question `run.jsonl` files, including tool trajectories and error
classes, are the source for deeper analysis. A first
[methodology and failure audit](methodology-audit.md) records known scoring and
repeatability caveats, separately from the 100-question external comparison.
