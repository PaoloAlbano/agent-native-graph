# ANA Company Methodology and Failure Audit

This audit concerns ANA's complete 347-question Company runs. The
[Multi-Agent GraphRAG comparison](multigraphrag-comparison.md) has a separate
100-question scope and is not scored here.

## Gold Answers

On the loaded Neo4j graph, all 347 stored gold Cypher queries execute, but
only 345 reproduce CypherBench `answer_json`. The two exceptions involve
`ORDER BY date_of_birth DESC LIMIT 1` with null birth dates. See the
[gold-validation report](../results/cypherbench-company/gold-validation.md).
The primary score includes all 347 questions. These discrepancies are reported
without excluding cases or silently repairing the benchmark answers.

## Scoring Semantics

The primary ANA metric is row-wise matching to stored `answer_json`. The
CypherBench execution evaluator instead compares predicted and gold query
results, preserving order for ordered queries and allowing a consistent column
permutation. ANA emits answers rather than Cypher, so its result cannot be
submitted to that evaluator unchanged. The `audit-execution` command applies
corresponding result-equivalence rules to ANA's final rows and the saved
[gold executions](../results/cypherbench-company/gold-execution-20261025.jsonl).
Call this *execution-equivalent result accuracy*, not the official CypherBench
Execution Accuracy metric. For the October 24 GPT-OSS temp-0 run, it was
292/347 rather than 296/347 under the primary metric, mostly because ordered
answers had different row order.

## Repeatability and Diagnosis

Two October GPT-OSS temp-0 runs scored 296/347 and 291/347. They used
different concurrency (5 and 3), an operational difference to record rather than
an automatic quality exclusion. This is not evidence that concurrency caused
the score difference. Each archived `manifest.json` records the run profile and
commit; use the corresponding `run.jsonl` and `failures.jsonl` for per-question
investigation. Technical execution success must not be equated with answer
correctness.

Before attributing a failure to a particular tool, inspect its trajectory and
the expected cardinality, ordering, and projected properties. Difficult
questions naturally require more tool calls; tool frequency alone does not
establish causality. The current tool descriptions contain some Company-flavored
examples, so these runs do not by themselves demonstrate domain-neutral
prompting.

## Historical Run Comparability

The four historical October 24-25 manifests share task hash
`7b4c336e5a0e1f6441daf93031b7964d5ae48db7c00be03e9530aa4360bd964f`,
graph hash `54d15b5db4c30b9d7d0e31cbc30ca7c144d3e2cad30bddf8d92390a095f0b82b`,
and declared commit `0dbdd9c17fda4900a6f3f06e8fd4704ce46491a3`. They declare
native tools, `auto`, 16,000 tokens and 12 steps. GPT T1 used concurrency 5;
Qwen T0 used 2. The two GPT T0 runs agree on correctness for 322 questions:
281 both correct, 41 both incorrect. Of the 25 changed outcomes, 10 improved
and 15 regressed from October 24 to October 25. These are observed trajectory
outcomes, not a causal explanation or a precise model-variance estimate.

Historical manifests do not contain effective prompt/tool hashes, schema-export
hash, runtime source-tree hash, dirty-code provenance or served model revision.
The declared commit was captured by the archiver; it does not prove which
uncommitted sources were executed at launch. Do not retroactively populate those
fields or claim identical treatment is established. Existing runs remain useful
historical observations. Future runs should follow [run-standard.md](run-standard.md).

The two October 27 runs (GPT-OSS T0/medium and T1/none) follow that standard and
retain their launch configuration in `run-config.json`, including effective
prompt, tool, source and input hashes. They share commit
`e34e0a45465f7229cc8a9b89820f5e081a6e5b2c` and concurrency 3, with matching
recorded execution identities. They complete the requested profile matrix but
do not retroactively establish equivalent historical conditions or provide
within-profile replication. Requested thinking settings remain distinct from
unobserved provider internals and served model revision.

## October 28 Qwen Audit

Three new Qwen3.5-27B runs cover exactly the same 347 unique Company questions.
Their run/config checksums, failure subsets, recomputed summaries and input
hashes were checked against the local task, schema and graph files. Their
recorded execution identities match each other; source-tree, native catalog and
prompt hashes distinguish effective code from the declared Git commit. Private
gateway, local home path, secret-file path and the configured key value were
not found in the new public artifacts. Raw logs remain outside the repository.

The primary scores are 290/347 for T0/medium, 273/347 for T1/none and 292/347
for T1/medium. All profiles use concurrency 3; the prior T0/none Qwen observation
used 2 and does not have complete effective execution provenance. No claim of
identical historical treatment or repeated-run significance follows.

### Terminal Failures Versus Tool Errors

The non-OK questions are 3, 10 and 5 respectively. Sixteen reach the 12-step
limit without a final fetch; two T1/none questions raise `JSONDecodeError`.
Those two archives stop after `schema_overview`, with two attempted LLM calls
but metrics for only the first. This does not establish whether the second
failure was HTTP-body decoding or tool-argument decoding; the failed payload
was not retained. Do not claim malformed model arguments, exhausted tokens or
a provider bug without additional evidence.

There are 8, 6 and 4 questions with at least one timed-out tool call. Every one
later fetches a final result, but only 0, 1 and 1 are correct. The static
`backend_timeout` primary labels (8, 5 and 3) do not include correct recoveries.
Most timeout steps are in `optional_expand_count` (7, 4 and 3); other affected
operations include `expand` and one `repair_empty_result` call. This identifies
a future backend investigation, not proof that every answer would become
correct after removing the timeout.

The AT&T shared-role question (`625ba586-61df-402a-97dd-4f176e9ded1f`) and the
McDonald's CEO/board-count question (`b7aa6d83-68c1-4302-85ee-b905d6a43b9f`)
exhaust the step budget in all three new profiles. The former repeatedly
rebuilds role patterns; the latter repeatedly searches for the seed entity and
changes traversal strategy. These are trajectory/planning candidates, not
automatic evidence that a tool implementation is wrong. No tool descriptions,
runner interventions, scoring rules or archived verdicts were changed during
this audit. Detailed outputs remain in the run archives rather than a new
Markdown report for every run.

### Common-Metric Comparison Completed

The selected `2026-10-29-three-model-matrix` query re-execution covers all thirteen ANA
archives and twenty-four matched external baseline runs on the pinned 100 QIDs.
It contains 2,500 saved-query attempts including golden queries; no LLM calls
were made. All queries pass the same read-only query-type gate, timeout and
result-size policy; queries are not repaired. Graph content matches the dataset
before execution and remains identical afterwards. Gold reproduction remains
99/100 and the full denominator is retained.

All sixteen previously evaluated baseline scores are reproduced unchanged. For
Qwen T0/medium, T1/none and T1/medium, ANA/direct/multi-agent exact scores are
85/64/67, 79/40/50 and 87/59/62 out of 100. The prior evaluations and full ANA
archives were not rewritten. Source LLM-judge verdicts stay distinct from this
query-result comparator, and historical model-generation conditions are still
not a controlled causal comparison. See the [comparison protocol](multigraphrag-comparison.md).

For GPT-OSS-20B, ANA/direct/multi-agent scores are 60/66/67 at T0/none,
62/64/60 at T0/medium, 70/59/68 at T1/none and 63/63/66 at T1/medium.
There is no uniform ANA advantage for this model. Full-split 20B runs share
execution identities and have settled accounting, but the historical baseline
generation treatment remains different. Their call logs cannot establish
complete token costs or efficiency rankings.

### Shared-Preflight Integration Smoke

A separate live diagnostic on October 29 compared synchronous and asynchronous
preflight evidence and then the artifacts saved by ANA and the reference
`single` runner. All three evidence objects match exactly: the named Company
database contains 581,306 nodes and 299,581 relationships, with identical
content fingerprints and canonical schema/prompt hashes. Both runners completed
the same three tasks with settled request accounting. ANA matched 3/3 and the
baseline 2/3; these tiny diagnostic scores are not quality estimates.

Diagnostic artifacts remain local, outside the public full-run archive. This
is integration validation, not frozen replication evidence; the historical
347-question and 100-question tables were not relabelled as shared-preflight
experiments. No graph mutation, prompt tuning or tool-contract change was made.
