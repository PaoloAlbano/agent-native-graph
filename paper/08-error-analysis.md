# 8. Error Analysis

`ANA-PAPER-ERROR-ANALYSIS`

We distinguish operation-level errors, terminal runner failures and answer
mismatches. An invalid argument can arise from model planning, a misleading
contract, an implementation defect or a serving failure. The observed exception
alone is not enough to assign responsibility. Likewise, a tool error can be
followed by a successful final fetch without restoring answer correctness.

Semantic failures happen when the tool calls execute successfully but implement
the wrong plan. Examples include:

- choosing the wrong grouping variable;
- selecting the wrong entity type;
- using a broad pattern where a constrained one was needed;
- failing to combine OR branches;
- mishandling list properties;
- using optional semantics incorrectly;
- returning plausible but incomplete final projections.

## Three New Qwen Runs

This audit uses Q28-0M, Q28-1N and Q28-1M from Section 7. Counts below concern
the complete 347-question runs, not the 100-question comparison subset.

| Observation | No final fetch at step limit | Parsing exceptions | Tasks with a timed-out tool | Timeout-affected tasks later correct |
| --- | ---: | ---: | ---: | ---: |
| Q28-0M | 3 | 0 | 8 | 0 |
| Q28-1N | 8 | 2 | 6 | 1 |
| Q28-1M | 5 | 0 | 4 | 1 |

All step-limit cases consume the 12 allowed steps. Every timeout-affected task
later reaches a final fetch, so those timeout counts are not terminal failure
counts. The primary archived `backend_timeout` labels cover 8, 5 and 3
non-matching answers, excluding the two correct recoveries. Most timed-out
operations are `optional_expand_count` (7, 4 and 3 calls respectively); `expand`
and one `repair_empty_result` call also time out. This suggests a backend-query
investigation, not proof that eliminating timeouts would repair every plan.

The two parsing exceptions occur in Q28-1N. Each record contains one completed
`schema_overview` step and two attempted LLM calls, but metrics for only the
first response. The failed response body was not saved. We cannot distinguish
malformed tool arguments from response-body decoding or assign a finish reason
to those failed attempts. No recorded rate-limit retry, length-finished response
or low-effort retry occurred; this observation does not reconstruct missing
metrics. Q28-0M records two HTTP retries.

## Recurrent Trajectory Fragility

The following cases are selected because both recur among terminal failures in
all three new profiles, not because they represent the entire error distribution.

The AT&T shared-role question (`625ba586-61df-402a-97dd-4f176e9ded1f`) reaches
the step limit in all three new profiles. Its trajectories repeatedly rebuild
relationship patterns and revisit schema or entity grounding rather than finish
the role join. The McDonald's CEO/board-count question
(`b7aa6d83-68c1-4302-85ee-b905d6a43b9f`) also exhausts all three budgets, with
repeated seed resolution and changes of traversal strategy.

These cases motivate better generic shape/identity and grounding contracts,
but do not by themselves demonstrate a faulty operator. Adding a tool named
after either question would not test a transferable API design. We preserve
their trajectories rather than inserting question-specific repairs or raising
the budget for only failed tasks.

## Evidence Limits

The [worked examples](appendix-a-worked-examples.md) show a short success and
an executed mismatch selected by an explicit QID rule, including every call's
arguments and both baseline queries. The mismatch preserves the right facts
but flattens a list into rows. Thus the archive's `semantic_mismatch` label also
contains representation differences; it should not be read as uniformly false
knowledge or failed entity grounding.

Frequency is not causality: difficult tasks invoke more tools and may use broad
operators more often. We have not isolated the effect of tool count, wording,
handles or grouping primitives with controlled ablations. The present audit
provides hypotheses and reproducible cases, not validated explanations for
every semantic mismatch. Full details remain in `run.jsonl` and `failures.jsonl`;
the [results explorer](https://paoloalbano.github.io/agent-native-graph/results.html)
loads one question at a time and links input handles to recorded producing steps.
