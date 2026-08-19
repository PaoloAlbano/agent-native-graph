# CypherBench Company Results

This repository focuses on the `company` graph/category from the CypherBench test split.

The current deterministic metric is execution accuracy against CypherBench `answer_json`. We also track technical success, tool-call count, LLM token usage, and tool errors.

## Status

This page is an evidence index for historical investigation runs, not a final
paper-ready leaderboard. The runs listed here are useful because they document
what we observed while shaping the ANA tool interface, but they should be
regenerated before making final claims.

For final comparisons, rerun all approaches with the same:

- code revision;
- CypherBench `company` task subset;
- loaded graph snapshot;
- model list;
- temperature/reasoning profile;
- max token and max step settings;
- scoring implementation.

Curated JSONL run files live in `results/`. Raw exploratory logs should stay in
`runs/` and are not intended to be referenced as stable evidence.

## Historical Representative Agent-Native Runs

| Run file | Model | Profile | Examples | Correct | Technical success | Avg tool calls |
|---|---:|---|---:|---:|---:|---:|
| `results/agent_tools_first100_gpt_oss_120b_optional_fix_c5_temp0_maxtokens16k_steps12.jsonl` | `openai/gpt-oss-120b` | temp 0 | 100 | 86 | 98 | 5.00 |
| `results/agent_tools_first100_gpt_oss_120b_optional_fix_c5_temp1_thinking_medium_maxtokens16k_steps12.jsonl` | `openai/gpt-oss-120b` | temp 1 + thinking medium | 100 | 87 | 98 | 4.91 |
| `results/agent_tools_first100_gemma_4_31b_it_clean_reload_c3_temp1_thinking_medium_retry8_maxtokens16k_steps12.jsonl` | `google/gemma-4-31B-it` | temp 1 + thinking medium | 100 | 90 | 100 | 5.20 |
| `results/agent_tools_first100_qwen3_6_27b_clean_reload_c1_temp0_retry8_maxtokens16k_steps12.jsonl` | `Qwen/Qwen3.6-27B` | temp 0 | 100 | 86 | 98 | 6.06 |
| `results/agent_tools_first100_qwen3_5_397b_a17b_clean_reload_c3_temp1_thinking_medium_retry8_maxtokens16k_steps12_nosandbox.jsonl` | `Qwen/Qwen3.5-397B-A17B` | temp 1 + thinking medium | 100 | 87 | 100 | n/a |
| `results/agent_tools_first100_qwen3_5_27b_clean_reload_c1_temp0_retry8_maxtokens16k_steps12.jsonl` | `Qwen/Qwen3.5-27B` | temp 0 | 100 | 71 | 85 | 6.62 |

These are research runs, not final claims. Some variance remains even at temperature 0 because hosted model/tool-call behavior can still change across runs.

## Baselines

The repository includes runners for:

- zero-shot text-to-Cypher;
- multi-agent text-to-Cypher correction;
- Multi-Agent GraphRAG-style text-to-Cypher;
- gold Cypher execution on Neo4j.

The next step is to consolidate comparable baseline tables from the external run repository and align them with the same `company` subset, model list, limit, and scoring code.

## Current interpretation

The historical runs suggest that the agent-native approach can be competitive
on this slice without dataset-specific tools. The best observed results cluster
in the high 80s to around 90/100 on the first 100 examples. This interpretation
should be treated as provisional until the comparison suite is rerun end-to-end.
