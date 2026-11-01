# ANA on CypherBench Company (347 Questions)

This page describes ANA's behavior on the complete `company` test split.
The [external comparison](multigraphrag-comparison.md) has a separate
100-question scope.

## Current Evidence

The twelve complete ANA runs under
[`results/cypherbench-company/full/runs/`](../results/cypherbench-company/full/runs/)
replace the previous matrix in full. There is one run per model/profile,
including profiles whose score decreased. Every archive contains its manifest,
347 per-question records, summary, failure subset, sanitized configuration and
graph-integrity report. The [index](../results/cypherbench-company/index.json)
is derived from these archives.

| Model | Temperature | Requested reasoning | Exact answers | Executed |
| --- | ---: | --- | ---: | ---: |
| GPT-OSS-120B | 0 | medium | 305/347 | 342/347 |
| GPT-OSS-120B | 0 | none | 302/347 | 343/347 |
| GPT-OSS-120B | 1 | medium | 299/347 | 339/347 |
| GPT-OSS-120B | 1 | none | 305/347 | 341/347 |
| Qwen3.5-27B | 0 | medium | 295/347 | 343/347 |
| Qwen3.5-27B | 0 | none | 294/347 | 342/347 |
| Qwen3.5-27B | 1 | medium | 294/347 | 342/347 |
| Qwen3.5-27B | 1 | none | 286/347 | 340/347 |
| GPT-OSS-20B | 0 | medium | 238/347 | 317/347 |
| GPT-OSS-20B | 0 | none | 231/347 | 314/347 |
| GPT-OSS-20B | 1 | medium | 234/347 | 313/347 |
| GPT-OSS-20B | 1 | none | 220/347 | 303/347 |

`Exact answers` counts matches to CypherBench `answer_json`.
`Executed` means the runner completed its result-return path, not that every
tool call succeeded or that the answer is correct. Counts are single-run
observations, not estimates of model-level variance.

## Execution Settings And Provenance

All runs use native tools, `tool_choice=auto`, 16,000 maximum output tokens,
12 agent steps and a 30-second backend query timeout. Requested thinking is
off or medium according to the named YAML profile. Provider behavior and
served model revision are not inferred from those requested settings.

The matrix uses shared graph/schema preflight, `bounded-v1` result handling,
and graph-content verification. GPT-OSS runs use concurrency 10 each; Qwen uses
3 each. Two profile runs execute concurrently. The source, catalog and prompts
were frozen for the entire matrix; each configuration records actual launch
hashes rather than relying only on a declared Git commit.

Benchmark-only all-page evaluation can collect the rest of a final fetched
handle for scoring. It does not give extra observations to the model or
restore rows omitted by an earlier bounded operation. See
[run settings](run-standard.md) and [result handling](reproduction.md).

## Reading The Results

The best observed count is 305/347 (87.9%) for GPT-OSS-120B T0/medium and
T1/none. GPT-OSS-20B spans 220-238 correct answers, Qwen3.5-27B spans
286-295. Reasoning does not improve every pair: GPT-OSS-120B T1/medium scores
six fewer answers than T1/none. No configuration has enough replication to
estimate a stable reasoning effect.

The [results explorer](https://paoloalbano.github.io/agent-native-graph/results.html)
provides every question, saved response and tool trajectory. The
[paper results](../paper/07-results.md) report exact tables and call means;
[error analysis](../paper/08-error-analysis.md) separates terminal failures,
recoverable errors and result-shape mismatches.

## Gold And Comparison Boundaries

The [gold-validation report](../results/cypherbench-company/gold-validation.md)
records 345/347 stored answers reproduced by gold Cypher on this graph.
All 347 cases remain in primary ANA denominators.

The comparison uses the pinned external set of 100 QIDs, not the first 100
tasks. All twelve current ANA runs are scored against unchanged saved direct
and multi-agent baseline executions. The comparison manifest explicitly
records this refresh and the original baseline evidence; it does not claim
new baseline inference or matched historical generation conditions. See the
[comparison protocol](multigraphrag-comparison.md).
