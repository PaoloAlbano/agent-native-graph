# ANA Company Methodology and Failure Audit

This audit concerns the current twelve complete 347-question Company runs.
The [external comparison](multigraphrag-comparison.md) has a separate pinned
100-question scope.

## Current Matrix

The previous curated matrix has been replaced in full by three models times
four YAML profiles. No run was selected for improved accuracy; GPT-OSS-20B
T1/none is retained despite a lower observed score than its predecessor.
The public archive has one complete observation per configuration, not enough
replication to estimate within-profile variance.

All current runs use the same frozen source treatment, native tool catalog,
system prompts, tasks and graph inputs. Model/profile-specific hashes are
retained in sanitized launch configurations. The source-tree hash matters:
a declared Git revision alone does not identify uncommitted executed code.
Concurrency is 10 per GPT run and 3 per Qwen run, with two profile runs at a
time. Temperature 0 does not guarantee deterministic inference.

The treatment uses shared graph/schema preflight, bounded-v1 result handling,
16,000 output tokens, a 12-step budget and 30-second backend query timeouts.
All twelve runs have verified before/after graph-content reports. The loaded
graph contains 581,306 nodes and 299,581 relationships. This is block verification,
not a database snapshot-isolation guarantee.

## Experimental Boundaries

The matrix is observational, not a controlled ablation. Historical score
differences do not establish a causal explanation. Requested reasoning settings
are not proof of the provider's internal behavior or model revision.

## Gold Answers And Scoring

All 347 stored gold Cypher queries execute on this graph, but only 345 reproduce
CypherBench `answer_json`; null birth-date ordering causes the known
discrepancies. The pinned comparison subset reproduces 99/100. Both primary
denominators retain all tasks. See the
[gold-validation report](../results/cypherbench-company/gold-validation.md).

ANA's primary metric compares normalized multisets of rows against stored
`answer_json`. Row order is ignored, column order and duplicate multiplicity
matter, and a list property is not interchangeable with several flattened rows.
This is not official CypherBench Execution Accuracy or a judgment of final
natural-language explanations.

The `audit-execution` command can compare ANA final rows with saved
[gold query executions](../results/cypherbench-company/gold-execution-20261025.jsonl)
using execution-equivalent result rules. That remains a different metric,
not a replacement for the primary published score.

## Errors And Completion

`ok` means the runner completed its result-return path, not answer correctness
or an error-free trajectory. A rejected call can be repaired; a final fetched
answer can still be wrong. The [current failure tables](../paper/08-error-analysis.md)
are recomputed from all 347 records per run and distinguish terminal step-budget
or parsing failures from recoverable timeout-affected tasks.

Inspect actions, arguments, returned handles and expected result shape before
assigning responsibility to a tool. Difficult tasks naturally use more calls;
tool frequency alone is not causality. The current descriptions contain some
Company-flavored examples, so these runs do not establish cross-domain transfer.

## Common-Metric Comparison

The selected `current-ana-matrix` comparison re-scores all twelve new ANA
archives on the 100 pinned QIDs and reuses unchanged baseline/gold executions
from the earlier content-verified evaluation. Its manifest records the source
evaluation checksum and preserves original graph fingerprints and execution
timestamps. It does not claim a new baseline execution or new inference.

Current ANA graphs share the saved baseline evaluation's graph hash. Baseline
trace hashes, source commit, comparator, QIDs and expected answers are checked
before publication. The refresh uses the same exact-result comparator, not
the source LLM judge. No model or database calls occur during site builds.

Historical baseline generations still differ in schema prompts, budgets and
unobserved serving conditions. Logged baseline calls are incomplete; unknown
token costs are not zero. Neither cost superiority nor a causal interface
effect follows from the current comparison.

## Next Evidence Standard

Follow [run-standard.md](run-standard.md) for complete runs and
[the controlled protocol](controlled-company-protocol.md) for prospective
matched-treatment experiments. Do not edit archived verdicts, exclude failed
tasks, fill missing provenance retrospectively, or cherry-pick successful reruns.
