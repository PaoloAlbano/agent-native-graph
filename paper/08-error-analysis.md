# 8. Error Analysis

`ANA-PAPER-ERROR-ANALYSIS`

The most useful distinction is between technical failure and semantic failure.

Technical failures include invalid tool arguments, backend errors, missing
handles, timeouts, or model responses without valid tool calls. These are mostly
wrapper/tool-contract problems.

Semantic failures happen when the tool calls execute successfully but implement
the wrong plan. Examples include:

- choosing the wrong grouping variable;
- selecting the wrong entity type;
- using a broad pattern where a constrained one was needed;
- failing to combine OR branches;
- mishandling list properties;
- using optional semantics incorrectly;
- returning plausible but incomplete final projections.

The current system has reduced many wrapper crashes, so remaining failures are
increasingly semantic planning errors. This is encouraging: it means the next
improvements should come from better generic tool contracts and trajectory-level
analysis, not dataset-specific shortcuts.
