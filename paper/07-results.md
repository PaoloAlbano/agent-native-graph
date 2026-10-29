# 7. Results

`ANA-PAPER-RESULTS`

This evidence snapshot includes all thirteen curated ANA runs available on October
29, 2026. Full-split results and shared-question comparisons are reported
separately. Observation IDs identify model, date and profile: G denotes
GPT-OSS-120B, S denotes GPT-OSS-20B, Q denotes Qwen3.5-27B, N denotes reasoning off and M denotes
requested medium reasoning. Each linked observation opens its source manifest.

## ANA Full-Split Observations

| Observation | Model | T | Thinking | Correct / 347 | OK / 347 | Mean LLM | Mean tools |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| [G24-0N](../results/cypherbench-company/full/runs/2026-10-24_openai-gpt-oss-120b_temp0_reasoning-none_tools-native_n347_company_ana_gptoss120_temp0_none_current_n347/manifest.json) | GPT-OSS-120B | 0 | none | 296/347 | 341/347 | 5.20 | 5.20 |
| [G24-1M](../results/cypherbench-company/full/runs/2026-10-24_openai-gpt-oss-120b_temp1_reasoning-medium_tools-native_n347_company_ana_gptoss120_temp1_medium_current_n347/manifest.json) | GPT-OSS-120B | 1 | medium | 292/347 | 336/347 | 5.22 | 5.21 |
| [G25-0N](../results/cypherbench-company/full/runs/2026-10-25_openai-gpt-oss-120b_temp0_reasoning-none_tools-native_n347_company_gptoss120_temp0_repeat2_n347/manifest.json) | GPT-OSS-120B | 0 | none | 291/347 | 346/347 | 5.09 | 5.09 |
| [Q25-0N](../results/cypherbench-company/full/runs/2026-10-25_qwen-qwen3.5-27b_temp0_reasoning-none_tools-native_n347_qwen35_temp0_full_n347/manifest.json) | Qwen3.5-27B | 0 | none | 294/347 | 344/347 | 6.02 | 6.02 |
| [G27-0M](../results/cypherbench-company/full/runs/2026-10-27_openai-gpt-oss-120b_temp0_reasoning-medium_tools-native_n347_2026-10-27t20-30-54.912565-00-00/manifest.json) | GPT-OSS-120B | 0 | medium | 302/347 | 343/347 | 5.19 | 5.19 |
| [G27-1N](../results/cypherbench-company/full/runs/2026-10-27_openai-gpt-oss-120b_temp1_reasoning-none_tools-native_n347_2026-10-27t20-58-50.991279-00-00/manifest.json) | GPT-OSS-120B | 1 | none | 295/347 | 343/347 | 5.22 | 5.22 |
| [Q28-0M](../results/cypherbench-company/full/runs/2026-10-28_qwen-qwen3.5-27b_temp0_reasoning-medium_tools-native_n347_2026-10-28t10-49-03.059153-00-00/manifest.json) | Qwen3.5-27B | 0 | medium | 290/347 | 344/347 | 5.60 | 5.60 |
| [Q28-1N](../results/cypherbench-company/full/runs/2026-10-28_qwen-qwen3.5-27b_temp1_reasoning-none_tools-native_n347_2026-10-28t11-36-33.015601-00-00/manifest.json) | Qwen3.5-27B | 1 | none | 273/347 | 337/347 | 6.15 | 6.15 |
| [Q28-1M](../results/cypherbench-company/full/runs/2026-10-28_qwen-qwen3.5-27b_temp1_reasoning-medium_tools-native_n347_2026-10-28t12-03-16.667771-00-00/manifest.json) | Qwen3.5-27B | 1 | medium | 292/347 | 342/347 | 5.73 | 5.73 |
| [S28-0N](../results/cypherbench-company/full/runs/2026-10-28_openai-gpt-oss-20b_temp0_reasoning-none_tools-native_n347_2026-10-28t18-25-24.196537-00-00/manifest.json) | GPT-OSS-20B | 0 | none | 217/347 | 311/347 | 6.29 | 6.27 |
| [S28-0M](../results/cypherbench-company/full/runs/2026-10-28_openai-gpt-oss-20b_temp0_reasoning-medium_tools-native_n347_2026-10-28t20-02-37.971912-00-00/manifest.json) | GPT-OSS-20B | 0 | medium | 222/347 | 314/347 | 6.24 | 6.22 |
| [S28-1N](../results/cypherbench-company/full/runs/2026-10-28_openai-gpt-oss-20b_temp1_reasoning-none_tools-native_n347_2026-10-28t19-16-15.494749-00-00/manifest.json) | GPT-OSS-20B | 1 | none | 229/347 | 311/347 | 5.69 | 5.64 |
| [S29-1M](../results/cypherbench-company/full/runs/2026-10-29_openai-gpt-oss-20b_temp1_reasoning-medium_tools-native_n347_2026-10-28t21-07-28.153292-00-00/manifest.json) | GPT-OSS-20B | 1 | medium | 227/347 | 300/347 | 5.83 | 5.76 |

Exact-result match ranges from 62.5% to 87.0%. The largest observed count is
302/347 for G27-0M; this is an observed maximum, not a model-selection protocol
or an estimate of expected performance. Technical completion ranges from
300/347 to 346/347 and is not answer correctness.

GPT-OSS-20B ranges from 217 to 229 correct answers (62.5%-66.0%), compared
with 291-302 for GPT-OSS-120B and 273-294 for Qwen3.5-27B. These observations
do not establish a causal model-size effect. For GPT-OSS-20B, medium reasoning
adds five exact matches at T0 but removes two at T1; technical completion at T1
falls from 311 to 300. There is no uniform reasoning benefit across this matrix.
The four 20B runs share source, prompt, tools and input-file hashes and use
concurrency 3, but each configuration has only one observation.

At temperature 1, requested medium thinking scores 19 more Qwen answers than
thinking off in this pair of observations. It does not exceed the historical
T0/none Qwen result (294/347). GPT-OSS T0/none observations differ by five
answers overall and change correctness on 25 individual questions. We retain
both; concurrency and incomplete historical provenance prevent attributing the
difference to a single factor. No profiles have sufficient replication for
within-treatment variance estimates.

## External Comparison

The table below uses the same 100 pinned questions and exact-result comparator
for every approach. It evaluates ANA saved rows and re-executed baseline queries,
not original LLM-judge scores or final textual explanations. Source evidence is
the [complete evaluation manifest](../results/cypherbench-company/query-reexecution/2026-10-29-three-model-matrix/manifest.json).
The direct baseline can retry; it is not a single-call baseline.

| Observation | ANA / 100 | Direct / 100 | Multi-agent / 100 |
| --- | ---: | ---: | ---: |
| G24-0N | 87/100 | 66/100 | 65/100 |
| G24-1M | 87/100 | 63/100 | 68/100 |
| G25-0N | 88/100 | 66/100 | 65/100 |
| Q25-0N | 85/100 | 47/100 | 48/100 |
| G27-0M | 86/100 | 63/100 | 68/100 |
| G27-1N | 86/100 | 61/100 | 70/100 |
| Q28-0M | 85/100 | 64/100 | 67/100 |
| Q28-1N | 79/100 | 40/100 | 50/100 |
| Q28-1M | 87/100 | 59/100 | 62/100 |
| S28-0N | 60/100 | 66/100 | 67/100 |
| S28-0M | 62/100 | 64/100 | 60/100 |
| S28-1N | 70/100 | 59/100 | 68/100 |
| S29-1M | 63/100 | 63/100 | 66/100 |

ANA has more exact matches in all GPT-OSS-120B and Qwen comparisons, but not
uniformly for GPT-OSS-20B. Its T0/none run loses to both baselines; T0/medium
lies between them; T1/none beats both; T1/medium ties direct and loses to
multi-agent. The interface's advantage is therefore model/profile dependent
in this evidence, not a universal consequence of replacing Cypher.
These are not thirteen
independent randomized experiments: the same questions and some baseline runs
are reused. Re-execution aligns the current graph and evaluator, not historical
schema prompts, compute budgets, model revisions, development exposure or
query-generation conditions. The table supports an observational interface
case study, not a causal claim that ANA alone explains the gaps.

## Auditability And Reporting Boundaries

All 347 and 100 denominators include known gold discrepancies. No task is
removed, no failed attempt is replaced by a hand-selected rerun, and no
cross-run average is presented as an independent sample. Public records include
all per-question tool trajectories, including incorrect ones. Raw reasoning
text was not retained for these records and is not reconstructed.

LLM/tool means describe ANA only. No end-to-end cost or latency superiority is
claimed against incomplete external call logs. Native tool/prompt hashes are
available for the nine standard runs, while historical observations remain
explicitly less reconstructible. See the [methodology audit](../docs/methodology-audit.md)
and [interactive results](https://paoloalbano.github.io/agent-native-graph/results.html).
