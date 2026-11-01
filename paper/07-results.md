# 7. Results

`ANA-PAPER-RESULTS`

The current evidence snapshot contains twelve complete ANA runs: one observation
for each combination of three models, temperature 0 or 1, and requested
reasoning none or medium. It replaces the earlier curated matrix in full,
including the configuration that regressed; no run was selected by score.
Observation IDs identify model and profile, without encoding a date: G denotes
GPT-OSS-120B, S denotes GPT-OSS-20B, Q denotes Qwen3.5-27B, N denotes
reasoning off and M denotes requested medium reasoning.

## ANA Full-Split Observations

| Observation | Model | T | Thinking | Correct / 347 | OK / 347 | Mean LLM | Mean tools |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| [G-0M](../results/cypherbench-company/full/runs/2026-10-31_openai-gpt-oss-120b_temp0_reasoning-medium_tools-native_n347_openai--gpt-oss-120b_temp0-medium-replacement/manifest.json) | GPT-OSS-120B | 0 | medium | 305/347 | 342/347 | 5.10 | 5.10 |
| [G-0N](../results/cypherbench-company/full/runs/2026-10-31_openai-gpt-oss-120b_temp0_reasoning-none_tools-native_n347_openai--gpt-oss-120b_temp0-none-replacement/manifest.json) | GPT-OSS-120B | 0 | none | 302/347 | 343/347 | 5.08 | 5.08 |
| [G-1M](../results/cypherbench-company/full/runs/2026-10-31_openai-gpt-oss-120b_temp1_reasoning-medium_tools-native_n347_openai--gpt-oss-120b_temp1-medium-replacement/manifest.json) | GPT-OSS-120B | 1 | medium | 299/347 | 339/347 | 5.28 | 5.27 |
| [G-1N](../results/cypherbench-company/full/runs/2026-10-31_openai-gpt-oss-120b_temp1_reasoning-none_tools-native_n347_openai--gpt-oss-120b_temp1-none-replacement/manifest.json) | GPT-OSS-120B | 1 | none | 305/347 | 341/347 | 5.12 | 5.12 |
| [Q-0M](../results/cypherbench-company/full/runs/2026-10-31_qwen-qwen3.5-27b_temp0_reasoning-medium_tools-native_n347_qwen--qwen3.5-27b_temp0-medium-replacement/manifest.json) | Qwen3.5-27B | 0 | medium | 295/347 | 343/347 | 4.65 | 4.65 |
| [Q-0N](../results/cypherbench-company/full/runs/2026-10-31_qwen-qwen3.5-27b_temp0_reasoning-none_tools-native_n347_qwen--qwen3.5-27b_temp0-none-replacement/manifest.json) | Qwen3.5-27B | 0 | none | 294/347 | 342/347 | 5.27 | 5.27 |
| [Q-1M](../results/cypherbench-company/full/runs/2026-10-31_qwen-qwen3.5-27b_temp1_reasoning-medium_tools-native_n347_qwen--qwen3.5-27b_temp1-medium-replacement/manifest.json) | Qwen3.5-27B | 1 | medium | 294/347 | 342/347 | 4.82 | 4.82 |
| [Q-1N](../results/cypherbench-company/full/runs/2026-10-31_qwen-qwen3.5-27b_temp1_reasoning-none_tools-native_n347_qwen--qwen3.5-27b_temp1-none-replacement/manifest.json) | Qwen3.5-27B | 1 | none | 286/347 | 340/347 | 5.41 | 5.41 |
| [S-0M](../results/cypherbench-company/full/runs/2026-10-31_openai-gpt-oss-20b_temp0_reasoning-medium_tools-native_n347_openai--gpt-oss-20b_temp0-medium-replacement/manifest.json) | GPT-OSS-20B | 0 | medium | 238/347 | 317/347 | 5.51 | 5.48 |
| [S-0N](../results/cypherbench-company/full/runs/2026-10-31_openai-gpt-oss-20b_temp0_reasoning-none_tools-native_n347_openai--gpt-oss-20b_temp0-none-replacement/manifest.json) | GPT-OSS-20B | 0 | none | 231/347 | 314/347 | 5.76 | 5.75 |
| [S-1M](../results/cypherbench-company/full/runs/2026-10-31_openai-gpt-oss-20b_temp1_reasoning-medium_tools-native_n347_openai--gpt-oss-20b_temp1-medium-replacement/manifest.json) | GPT-OSS-20B | 1 | medium | 234/347 | 313/347 | 5.55 | 5.49 |
| [S-1N](../results/cypherbench-company/full/runs/2026-10-31_openai-gpt-oss-20b_temp1_reasoning-none_tools-native_n347_openai--gpt-oss-20b_temp1-none-replacement/manifest.json) | GPT-OSS-20B | 1 | none | 220/347 | 303/347 | 5.38 | 5.30 |

Exact-result match ranges from 63.4%-87.9%. The largest observed count is
305/347, reached by G-0M and G-1N. This is an observed maximum, not a
model-selection protocol or an estimate of expected performance. Technical
completion ranges from 303/347 to 343/347 and is not answer correctness.

GPT-OSS-20B ranges from 220 to 238 correct answers (63.4%-68.6%), compared
with 299-305 for GPT-OSS-120B and 286-295 for Qwen3.5-27B. Medium reasoning
adds 7, 3 and 1 correct answers at T0 for 20B, 120B and Qwen respectively.
At T1 it adds 14 for 20B and 8 for Qwen, but removes 6 for 120B.
There is no uniform reasoning benefit across all model/profile pairs.

All twelve runs use the frozen native catalog and prompts, `auto`, 16,000
maximum output tokens per call, 12 steps, a 30-second backend query timeout,
`bounded-v1` result handling and shared graph/schema preflight. Each archived
graph-integrity report verifies the graph content. Concurrency is 10 per GPT
run and 3 per Qwen run; two profile runs execute concurrently. Source, input,
profile, prompt and tool identities are recorded in sanitized configurations.

Each configuration has only one observation. Provider nondeterminism and
unobserved model revisions remain possible, including at temperature 0.
These observations do not establish a causal model-size, reasoning or
concurrency effect, and do not estimate within-treatment variance.

## External Comparison

The table below uses the same 100 pinned questions and exact-result comparator
for every approach. It evaluates ANA saved rows and saved baseline query
executions, not original LLM-judge scores or final textual explanations.
Source evidence is the [complete evaluation manifest](../results/cypherbench-company/query-reexecution/current-ana-matrix/manifest.json).
The direct baseline can retry; it is not a single-call baseline.

| Observation | ANA / 100 | Direct / 100 | Multi-agent / 100 |
| --- | ---: | ---: | ---: |
| G-0M | 89/100 | 63/100 | 68/100 |
| G-0N | 90/100 | 66/100 | 65/100 |
| G-1M | 88/100 | 63/100 | 68/100 |
| G-1N | 89/100 | 61/100 | 70/100 |
| Q-0M | 89/100 | 64/100 | 67/100 |
| Q-0N | 84/100 | 47/100 | 48/100 |
| Q-1M | 82/100 | 59/100 | 62/100 |
| Q-1N | 79/100 | 40/100 | 50/100 |
| S-0M | 71/100 | 64/100 | 60/100 |
| S-0N | 67/100 | 66/100 | 67/100 |
| S-1M | 65/100 | 63/100 | 66/100 |
| S-1N | 65/100 | 59/100 | 68/100 |

ANA has more exact matches in all GPT-OSS-120B and Qwen comparisons. For
GPT-OSS-20B, T0/none beats direct and ties multi-agent; T0/medium beats both;
T1/none and T1/medium lie between the two baselines. The advantage remains
model/profile dependent, not a universal consequence of replacing Cypher.

The comparison refresh re-scores the twelve new ANA archives and reuses the
unchanged, previously content-verified baseline and gold executions. Its
manifest records the source evaluation manifest and checksum. It does not
claim that those baseline queries were newly executed, nor that their LLM
generations used shared preflight. No new baseline inference was performed.

These are not twelve independent randomized experiments: the same questions
and historical baseline evidence are reused. The common graph and evaluator
do not align historical schema prompts, compute budgets, model revisions,
development exposure or query-generation conditions. The table supports an
observational interface case study, not a causal claim that ANA alone explains
the gaps.

## Auditability And Reporting Boundaries

All 347 and 100 denominators include known gold discrepancies. No task is
removed, no failed attempt is replaced by a hand-selected rerun, and no
cross-run average is presented as an independent sample. Public records include
all per-question tool trajectories, including incorrect ones. Raw reasoning
text is not reconstructed when absent from recorded responses.

LLM/tool means describe ANA only. No end-to-end cost or latency superiority is
claimed against incomplete external call logs. Each current run includes
sanitized configuration and graph-integrity evidence. See the
[methodology audit](../docs/methodology-audit.md) and
[interactive results](https://paoloalbano.github.io/agent-native-graph/results.html).
