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

The four archived manifests share task hash
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
