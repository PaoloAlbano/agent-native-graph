# 8. Error Analysis

`ANA-PAPER-ERROR-ANALYSIS`

We distinguish operation-level errors, terminal runner failures and answer
mismatches. An invalid argument can arise from model planning, a misleading
contract, an implementation defect or a serving failure. The exception alone
does not establish responsibility. A tool error can be followed by a successful
final fetch without restoring answer correctness.

The following tables are recomputed from the current twelve full-run
trajectories, not retained from the replaced matrix. All denominators are 347.
A task is counted as timeout-affected if a recorded tool error contains
`timeout` or `timed out`; this is not a terminal-error label. Correct
recoveries remain included. Parsing counts below are terminal `json_decode`
records, not a classification of every possible malformed response.

## GPT-OSS-120B

| Observation | No final fetch at step limit | Parsing exceptions | Tasks with a timed-out tool | Timeout-affected tasks later correct |
| --- | ---: | ---: | ---: | ---: |
| G-0M | 2 | 1 | 2 | 0 |
| G-0N | 3 | 0 | 1 | 0 |
| G-1M | 4 | 4 | 0 | 0 |
| G-1N | 4 | 2 | 2 | 1 |

## Qwen3.5-27B

| Observation | No final fetch at step limit | Parsing exceptions | Tasks with a timed-out tool | Timeout-affected tasks later correct |
| --- | ---: | ---: | ---: | ---: |
| Q-0M | 4 | 0 | 1 | 0 |
| Q-0N | 5 | 0 | 1 | 1 |
| Q-1M | 5 | 0 | 2 | 1 |
| Q-1N | 6 | 0 | 1 | 1 |

## GPT-OSS-20B

| Observation | No final fetch at step limit | Parsing exceptions | Tasks with a timed-out tool | Timeout-affected tasks later correct |
| --- | ---: | ---: | ---: | ---: |
| S-0M | 21 | 3 | 0 | 0 |
| S-0N | 25 | 3 | 0 | 0 |
| S-1M | 13 | 20 | 1 | 0 |
| S-1N | 17 | 27 | 1 | 0 |

The current GPT-OSS-20B temperature-1 runs have substantially more terminal
parsing failures than its temperature-0 runs. This observation does not prove
that temperature caused those failures or identify every missing/invalid
response payload. Transport retries, finish reasons and observed usage must be
read from each run's request accounting rather than inferred from accuracy.

A timeout can affect an eventually correct answer, and an executable trajectory
can still be semantically wrong.

## Generic Failure Modes

Repeated risks include choosing the wrong relationship direction or grouping
variable, confusing node and relationship properties, referencing a missing
handle, failing to combine alternatives, and projecting the wrong answer shape.
These are generic hypotheses to inspect in saved trajectories, not an assertion
that one operator caused every mismatch.

## Evidence Limits

The [worked examples](appendix-a-worked-examples.md) show a short success and
an executed mismatch selected by an explicit QID rule, including every call's
arguments and both baseline queries. The mismatch preserves the right facts
but flattens a list into rows. Thus `semantic_mismatch` includes representation
differences; it is not uniformly false knowledge or failed entity grounding.

Frequency is not causality: difficult tasks invoke more tools and may use broad
operators more often. We have not isolated tool count, wording, handles or
grouping primitives with controlled ablations. Full details remain in
`run.jsonl` and `failures.jsonl`; the
[results explorer](https://paoloalbano.github.io/agent-native-graph/results.html)
loads one question at a time and links handles to their recorded producing steps.
