# ANA on CypherBench Company (347 Questions)

This page describes ANA's behavior on the complete `company` test split. It is
not a comparison with Multi-Agent GraphRAG. That comparison has a separate
[100-question protocol](multigraphrag-comparison.md).

## Evidence

The thirteen retained complete ANA runs are under
[`results/cypherbench-company/full/runs/`](../results/cypherbench-company/full/runs/).
Each run has a manifest, all 347 per-question records, a summary, and the
non-matching cases. [`index.json`](../results/cypherbench-company/index.json)
lists their model, profile, and score. All have task, graph, and run hashes;
the nine October 27-29 runs also include sanitized `run-config.json` provenance.
They are individual observations; concurrency differs between the two historical
GPT-OSS temperature-0, reasoning-off runs.

| Model | Requested profile | Run date | Exact answers | Executed |
|---|---|---|---:|---:|
| GPT-OSS-120B | temp 0, no reasoning | Oct 24 | 296/347 | 341/347 |
| GPT-OSS-120B | temp 1, medium reasoning | Oct 24 | 292/347 | 336/347 |
| GPT-OSS-120B | temp 0, no reasoning | Oct 25 | 291/347 | 346/347 |
| Qwen3.5-27B | temp 0, no reasoning | Oct 25 | 294/347 | 344/347 |
| GPT-OSS-120B | temp 0, medium reasoning | Oct 27 | 302/347 | 343/347 |
| GPT-OSS-120B | temp 1, no reasoning | Oct 27 | 295/347 | 343/347 |
| Qwen3.5-27B | temp 0, medium reasoning | Oct 28 | 290/347 | 344/347 |
| Qwen3.5-27B | temp 1, no reasoning | Oct 28 | 273/347 | 337/347 |
| Qwen3.5-27B | temp 1, medium reasoning | Oct 28 | 292/347 | 342/347 |
| GPT-OSS-20B | temp 0, no reasoning | Oct 28 | 217/347 | 311/347 |
| GPT-OSS-20B | temp 0, medium reasoning | Oct 28 | 222/347 | 314/347 |
| GPT-OSS-20B | temp 1, no reasoning | Oct 28 | 229/347 | 311/347 |
| GPT-OSS-20B | temp 1, medium reasoning | Oct 29 | 227/347 | 300/347 |

`Exact answers` counts row-wise matches to CypherBench `answer_json`.
`Executed` counts questions without an execution or termination failure; it
does not imply a correct answer. Scores are observations from individual runs,
not estimates of model-level variance.

The October 27 runs complete the GPT-OSS profile matrix. Both use commit
`e34e0a45465f7229cc8a9b89820f5e081a6e5b2c`, concurrency 3, native tools,
`tool_choice=auto`, 16,000 output tokens per call, 12 agent steps and a
30-second Neo4j query timeout. Their recorded code, prompt, tool and input
identities match. T0/medium used 1,801 LLM calls and 1,800 tool calls; T1/none
used 1,812 and 1,811 respectively. Neither had a 429 retry, length-truncated
response or low-effort retry; T0/medium recorded two HTTP retries. Both recorded
18 tool errors, some recovered within a trajectory.

Thinking settings are requests, not proof of the provider's internal behavior;
no separate reasoning-token counts were returned. The higher single-run score
for T0/medium is not evidence of a causal improvement over the historical runs:
their effective treatment is not fully reconstructible, and these are not
replicated estimates. See the [comparability audit](methodology-audit.md).

## Qwen Profile Matrix

The October 28 runs complete the Qwen3.5-27B matrix. They use the same recorded
source, tool, prompt and input identities, native tools, `tool_choice=auto`,
16,000 output tokens, 12 steps, a 30-second database query timeout and concurrency
3. They ran sequentially; the historical T0/none observation used concurrency 2
and has less complete provenance. The declared commit alone does not identify
the uncommitted implementation: use the launch source-tree hash as well.

| Requested profile | Exact answers | Executed | LLM / tool calls | Non-OK endings | Tasks encountering a tool timeout |
| --- | ---: | ---: | ---: | ---: | ---: |
| temp 0, medium reasoning | 290/347 (83.6%) | 344/347 | 1,943 / 1,943 | 3 step-limit endings | 8 |
| temp 1, no reasoning | 273/347 (78.7%) | 337/347 | 2,135 / 2,133 | 8 step-limit endings, 2 parsing errors | 6 |
| temp 1, medium reasoning | 292/347 (84.1%) | 342/347 | 1,990 / 1,990 | 5 step-limit endings | 4 |

All timeout-affected tasks subsequently reached a final fetch; only 0, 1 and 1
of those tasks respectively matched the answer. A resumed workflow is not
necessarily semantically repaired. The saved primary `failure_class` counts
are 8/5/3 backend timeouts: those labels cover only non-matching answers and
therefore exclude the two correctly answered timeout-affected tasks. Do not
interpret that classification as a count of terminal exceptions.

No recorded rate-limit retry, length-finished response or low-effort retry
occurred. T0/medium recorded two HTTP retries; the other two recorded none.
The two T1/none parsing exceptions have no saved response/metric for the failed
call, so the exact malformed payload and its finish reason cannot be established
from the archive. The LLM-call counter includes those attempts, whereas the
token/finish-reason aggregates cover only responses whose metrics were saved.

Within these observations, medium reasoning at temperature 1 scores 19 answers
above reasoning-off. It does not establish a causal improvement or outperform
the historical T0/none result (294/347). No failed question was rerun, excluded
or silently replaced. Use the [static results explorer](https://paoloalbano.github.io/agent-native-graph/results.html)
to inspect every saved trajectory and compare individual QIDs.

The [100-question common-metric comparison](multigraphrag-comparison.md#saved-query-re-execution)
is also complete for these three profiles. ANA scores 85/100, 79/100 and 87/100
respectively against matched saved-query baselines; these are a pinned subset,
not substitutes for the 347-question scores above. No new LLM calls were used
to derive those comparison results.

## GPT-OSS-20B Matrix

The four full runs share source-tree, prompt, tool and input-file identities,
use concurrency 3, native tool calls, `tool_choice=auto`, 16,000 output tokens
and 12 steps. Their exact-match rates are 62.5%, 64.0%, 66.0% and 65.4% in the
table order above. Medium reasoning adds five answers at temperature 0 but
removes two at temperature 1; these unreplicated observations do not establish
a systematic reasoning benefit.

Parsing exceptions number 5, 5, 17 and 22; step-limit endings number 29, 27,
18 and 23. All request accounting is settled, with 15, 18, 3 and 0 HTTP retries
and no failed logical calls or observed length finishes. The failed parsing
inputs were not archived, so malformed tool arguments cannot be assumed to be
the sole cause. `pattern_query` repeatedly encounters node-versus-relationship
property confusion, missing start labels and invented handles. Counts include
recovered operation errors, not only terminal failures.

These historical full runs did **not** use shared preflight. The opt-in live
smoke check is diagnostic only and is not archived as a full run or mixed into
these scores. See [reproduction](reproduction.md#opt-in-common-graph-and-schema-preflight).

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
