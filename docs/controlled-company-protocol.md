# Prospective Controlled Company Protocol

**Status: design draft, not executable and not authorization to start inference.**
This protocol defines a new experiment. Existing archived results remain
observational evidence and are not relabeled as controlled runs. The current
commands do not yet enforce all conditions below. Implementation checks,
a frozen launch manifest and explicit budget approval are required first.

## Question And Scope

The primary question is whether the three **systems** differ in retrieval
quality under matched data, model-call settings and scoring, with each method's
native stopping limits declared and generation usage measured.
It is not an isolated causal test of API shape: controllers, instructions,
output formats and available operations necessarily differ. A separate
same-controller interface ablation is described below, not included in the
initial run count.

Only the full Company test split is used: 347 questions per run. The pinned
100-QID comparison is a secondary projection of each complete run, not a
separately selected or tuned sample. These questions have already informed
development; improved experimental control does not create an untouched holdout.
No other CypherBench category is included.

The following YAML is a **design manifest**, not an LLM profile or a supported
runner input. Models belong to the study matrix; the referenced LLM profiles
remain model-independent. Changing a decision requires a new protocol version
before inference, not a post-hoc reinterpretation.

```yaml
protocol_id: company-matched-v2-draft
status: design-only
execution_authorized: false
scope:
  benchmark: cypherbench-company
  graph: company
  split: test
  questions_per_run: 347
  secondary_qid_file: data/reference_company100_qids.json
matrix:
  models: [openai/gpt-oss-120b]
  profiles: [temp0-none, temp1-medium]
  arms: [ana, single_retrieval, agentic_retrieval]
  replicas: 3
  expected_runs: 18
  expected_question_executions: 6246
stages:
  first: {profile: temp0-none, runs: 9, question_executions: 3123}
  second: {profile: temp1-medium, runs: 9, question_executions: 3123}
profile_sha256:
  temp0-none: 7df9f84334621e74be43eeca55d73e4111906f657759a797f19d90701817b00c
  temp1-medium: 794741a227eb0db93d8946fb2b053a07b697127ff86d41b10d3f6293af4a1a95
controls:
  max_tokens_per_generation: 16000
  semantic_generation_budget_per_question: null
  budget_policy: observe-native-limits-first
  native_limits:
    ana_decision_turns: 12
    reference_query_generator_iterations: 5
  global_http_concurrency: 3
  database: neo4j
  query_timeout_s: 30
  task_deadline_s: 900
  result_row_cap: 100000
  feedback_preview_rows: 20
  primary_metric: exact_answer_json_multiset
  automatic_final_fetch: false
  wrapper_planning: false
  runner_guardrails: false
schedule:
  seed: 20261028
  arm_orders:
    - [ana, single_retrieval, agentic_retrieval]
    - [single_retrieval, agentic_retrieval, ana]
    - [agentic_retrieval, ana, single_retrieval]
```

## Arms And Finalization

| Arm | Frozen behavior | Difference from historical evidence |
| --- | --- | --- |
| `ana` | The same 35-tool `overview` catalog for every question, native calling and `auto`; no optional planner, tool routing by QID or runner substitution. A model-requested `fetch` finalizes the answer; retain 12 decision turns. | A common schema bootstrap and telemetry make this a new treatment; it is not a replay of an old run. |
| `single_retrieval` | Reference `SinglePassRunner` generation/execution loop with its bounded error/empty retries. The final query supplies the result rows. | No LLM interpreter after retrieval; a documented local adapter bypasses prose synthesis. It is not the `--mode direct` one-generation path. |
| `agentic_retrieval` | Reference generation, execution, evaluation and correction/verification branches, retaining its five-generator-iteration limit and recording every role's calls. | Prose interpretation is bypassed; no additional cross-role generation cap is imposed. |

The reference source is pinned to
`72fe7105310c85ebe6b1b3b7d4c6152ddb206393`; the local adapter and its hashes are
additional treatment provenance. Do not edit the reference checkout or imply
that these retrieval-only variants reproduce its original published pipelines.
The original `single` and `agentic` workflows remain available for historical
reproduction. A strict one-generation `direct` arm is optional future work,
not a silent substitute for `single_retrieval`.

All arms return structured rows. A baseline's internal evaluator remains part
of its retrieval workflow; an external correctness judge is not added. Removing
the baseline interpreter avoids spending retrieval budget on prose that is not
scored. If final prose is studied later, use a separate, identically configured
finalization experiment after freezing retrieval outputs, and report its calls
and latency separately for every arm.

An exhausted native limit without the arm's legitimate terminal result is a failure.
Do not automatically fetch an ANA intermediate handle, select a previous query
using the gold answer, or add a final model call outside the budget. Baseline
iteration caps and stopping rules are frozen alongside the adapter, never
extended for individual failing questions.

## Common Information And Leakage Boundary

Create one canonical schema export from the verified graph: labels, properties,
available type/list information and directed relationship patterns. Unknown
types remain unknown. Render the same schema facts into each arm's bootstrap
and record both the canonical hash and each exact rendered-prompt hash. Use the
same policy for examples/counts; do not supply extra entity examples to one arm
through its initial prompt. The schema and all examples are generated without
consulting task answers.

ANA may still call schema/grounding tools; reference verification may inspect
the graph. These are method-specific observations and costs, not equal
per-step information. A fixed bootstrap does not make the interaction histories
identical. Tool descriptions and method-specific instructions remain different
and are frozen rather than silently rewritten to match.

Models receive the question, allowed metadata and live observations. Gold
Cypher, `answer_json`, template metadata and QID-derived tool-routing rules must
not enter model requests. Template fields are used only for post-run analysis.
Test this data flow with sentinel gold fields, not by banning ordinary entity
strings that can legitimately appear in both the question and answer.

## Budget, Transport And Concurrency

A semantic generation is a model decision in any role: generator, evaluator,
entity extraction, verification/ranking, correction or aggregation. A low-effort
retry after a length-finished response is another generation and must be counted.
Every generation keeps the 16k token cap.

Revision v2 follows the decision to measure usage without imposing a new common
cap: 12 ANA decision turns are not equivalent to 12 generations across all
reference roles. Retain each runner's native stopping limits, declare them, and
count all roles/fallbacks. The earlier proposal of a shared 12-generation cap is
withdrawn. Equal-budget curves, if useful, are a separate predeclared sensitivity
experiment after accounting is reliable, not a replacement primary score.

Only a small diagnostic is currently authorized, not new full Company runs.
For a prefix diagnostic, fix the sample and limits before inference, keep the
prompt budget-unaware, and report whether a model-requested final result exists
within each observed prefix. Such truncation measures completion under the same
trajectory, not how an agent would adapt when told a different budget. A tiny,
development-exposed sample cannot establish a general accuracy effect.

Transport retries repeat an identical payload; they do not reset workflow state
or give the model a new observation. They are counted separately as actual HTTP
attempts and possible cost. Apply the same policy in all clients: the selected
profile's timeout, outer-attempt limit and fixed 30-second 429 wait; retryable
network/timeouts/selected 5xx only, with permanent request/authentication errors
failing rather than restarting the entire question. The retry-status policy is
part of the new adapter configuration and is not currently enforced uniformly.

All shared generation options must agree, including omission of null options
and requested thinking fields. Every model role uses the matrix cell's model;
no stronger evaluator or hidden per-role model override is allowed in this
treatment. Method-specific `tools` versus structured query
output are intentional differences. Test outgoing payloads, not just labels
such as "medium". Provider support and served revision may be unavailable;
record that uncertainty rather than infer identical internal reasoning.

The global endpoint limit is three in-flight HTTP requests, including nested
roles, not three per client multiplied by all roles. A common 900-second task
deadline includes generation, retry waits and data access, but excludes batch
setup. These hard caps are prospective and require implementation. They are not
claims about the demo server's resource isolation.

Record actual usage where returned, including unsuccessful attempts and length
fallbacks; missing usage is unknown, not zero. Equal call/token caps would not mean
equal consumed input tokens, reasoning tokens, cached tokens, compute or price.
Without a common generation cap there is no shared 12-generation upper
allowance. A full-run spending bound must be computed from the frozen native
workflows and fallback rules before any later approval; no full run is approved.

## Graph, Execution And Result Policy

Use the same named Neo4j database and content-verified Company dump. Record
node/edge/property multiset fingerprints before and after each method block;
any change invalidates that block. Never reload, clear or mutate the graph as
an automatic preflight. Keep the database otherwise read-only during execution.

Reject write-capable generated queries before execution, at **every candidate
execution**, not only final scoring. Reuse the query-type/transaction checks
in [reexecute_reference.py](../src/agent_native_graph/research/reexecute_reference.py)
with a compatible adapter and least-privilege database credentials. Read-mode
routing alone is not a write-rejection policy. The foundation reference adapter
now applies these checks to live candidates as well as final scoring; common
graph fingerprints and feedback observations remain separate pending gates.

Stream and bound results rather than materializing arbitrarily many rows before
truncating. Save up to the common result cap; exceeded caps are explicit
failures, never silently scored prefixes. Give every controller a bounded
20-row feedback preview plus completeness/count metadata. A semantic `LIMIT`
chosen by the model is distinct from server-side truncation; log both.

Score full final rows, not the preview. ANA all-page collection may retrieve
the rest of a model-finalized stored handle solely for scoring; it cannot repair
an upstream bounded operation. Capture truncation/lineage metadata and do not
claim complete graph retrieval because a stored handle was exhausted. Report
final retrieval, scoring and optional postprocessing costs separately.

## Scheduling And Replicas

Run one full arm at a time. Within it, question execution uses the declared
global concurrency. The three arm orders above counterbalance method position
across replicas. For each profile/replica, derive one task permutation from
the schedule seed and QIDs and reuse it across all arms. Keep task-set identity
separate from task-order hashes. When scheduling both profiles, alternate which
profile starts a replica and record the realized schedule.

The schedule seed controls ordering, not model determinism; provider `seed`
remains null unless a new treatment explicitly changes it. Do not treat
temperature zero as deterministic. Keep cache policy fixed and report warm/cold
conditions where observable; this plan does not guarantee identical cache
contents or eliminate endpoint time drift.

Stage one proposes nine full T0/none runs, then stage two proposes nine full
T1/medium runs. Each stage requires explicit approval. Qwen extension, the two
other profiles and the minimal-interface arm are not included in these counts.
Historical runs cannot substitute for any of these replicas.

## Outcomes, Failures And Analysis

Primary outcome: exact multiset-of-rows match to `answer_json` on all 347 QIDs.
Preserve column order, list structure and duplicate multiplicity; ignore row
order as in the current comparator. Keep the two known gold discrepancies in
the primary denominator. Report a labeled sensitivity view and ordered-query
diagnostics separately; never change the primary scorer after viewing results.
The pinned 100-QID view is secondary and retains all 100 cases.

Report terminal status separately from recovered tool/query errors. A final
fetch/query can be wrong without an exception; an error-free execution can
still flatten lists incorrectly. Report correctness, non-OK endings, tool/query
errors, truncation, retries, length finishes, attempted generations, HTTP
attempts, token coverage and latency distributions. Include zero-call failures.
Do not call incomplete external logs complete cost accounting.

Pair outcomes by QID and replica, report both raw counts and per-replica
differences, and keep repeated questions distinct from independent samples.
For uncertainty, a proposed paired QID-cluster bootstrap retains all arms and
replicas for each sampled QID; any interval is conditional/exploratory for this
development-exposed Company set. Also report descriptive groups from
`from_template.match_category` and `return_pattern_id`; template dependence
limits broader interpretation. No significance or generalization claim follows
from three replicas. Disclose all planned comparisons rather than selecting
the winning profile after execution.

Permanent authentication failure or graph mismatch stops the batch. Five
consecutive terminal infrastructure failures in completion order stop the
current run for diagnosis. Exhausted transient retries remain recorded failures;
do not quietly requeue only wrong answers. Resume only missing QIDs with frozen
state/accounting; if an interrupted task cannot be resumed faithfully, retain
the interruption record and diagnose it, not a hidden extra attempt. An
incomplete/changed-treatment block is not publishable as a completed replica.
Report all completed replicas regardless of which method wins.

## Implementation Gates Before Inference

| Gate | Current support and required work |
| --- | --- |
| G1: frozen sources and inputs | Foundation implemented: explicit profile + full commit exports committed reference source without switching branches; source/configuration, adapter/provider/input/profile hashes and runtime versions are recorded, and full task contents checked. The final common launch manifest and approval freeze remain pending. Legacy checkout mode is separately identified. |
| G2: shared call policy | Foundation implemented: profile-enabled reference roles call the same ANA provider with the same YAML settings; offline sync/async payload tests cover all four profiles. Pinned reference structured parsing is retained. Request accounting is implemented; common approved deadline values and global HTTP bounds remain G6 work. |
| G3: generation accounting, no new cap | Passive request ledgers implemented for ANA and profile-enabled reference roles: logical calls, actual POSTs, retry/fallback attempts, observed tokens/coverage, finish/error status and latency. Native limits unchanged. Missing usage remains unknown; a shared cross-role cap is deferred. Legacy reference transport is explicitly uninstrumented. |
| G4: safe common execution | Foundation implemented: sync saved-query scoring and async live baseline candidate/introspection/final scoring share read classification, named database, transaction timeout, rollback and streaming row-cap semantics. Fake-driver tests cover rejection, bounds, cancellation and non-partial scoring. Database least-privilege permissions remain required; this is not a procedure sandbox. |
| G5: data/schema/completeness | ANA standard runs check graph content; baseline preflight currently compares dump files and performs connectivity/schema probes, not a full database fingerprint. Add common snapshot and schema-fact checks, result completeness and preview policy. |
| G6: deadline and accounting | Cancellable async HTTP and question-owned sibling cleanup implemented for profile baselines; the existing 240s deadline now includes final scoring. ANA explicit diagnostic deadlines work at concurrency above one, with async HTTP and cooperative checks around synchronous tools. Ledger snapshots follow client cleanup, including cancelled questions. Default ANA/profile values are not unified; common approved values, hard cancellation of synchronous DB work, remote abort confirmation, crash recovery and global HTTP bounds remain pending. Legacy reference transport remains distinct. |
| G7: frozen retrieval variants | Bypass only the reference prose interpreter, preserving and documenting generation/refinement logic; do not claim the adapter is already implemented. |
| G8: dry-run and publication | Test with fake providers/graphs first, then an explicitly authorized technical smoke. Freeze a manifest, approve the exact cells, and only then launch complete replicas. Keep new evidence separate from historical archives. |

The relevant implementations are
[ANA runner](../src/agent_native_graph/application/neo4j_benchmark.py),
[launch provenance](../src/agent_native_graph/application/run_config.py),
[reference harness](../src/agent_native_graph/research/run_reference_baseline.py)
and [saved-query evaluation](../src/agent_native_graph/research/reexecute_reference.py).
The table distinguishes foundation support from remaining gaps; it does not certify
the controlled protocol. No new orchestration
framework or command family is required: extend the existing runner/adapter
boundaries and `make benchmark` / `make baseline-run` after the gates are tested.
Do not use today's commands as if they enforced this design.

The G1/G2/G4 foundation slice is available through explicit profile/pin options
documented in [reproduction](reproduction.md#pinned-source-and-shared-provider).
Passive request accounting and cancellable HTTP are implemented too, with native
generation limits retained. An [opt-in shared preflight](reproduction.md#opt-in-common-graph-and-schema-preflight)
now verifies graph content and supplies equal canonical initial schema facts.
It does not provide an atomic snapshot or after-run certification. G5/G7 still
require full observation parity and retrieval-only variants; G6 requires common approved
deadline values, global endpoint admission and crash recovery.
Only after G8 checks pass should either stage be submitted for launch approval.

### Preserve Running Experiments

Do not edit executable sources, model profiles, dependencies or the live graph
while a benchmark matrix is running. Each matrix command starts a new process;
later cells could otherwise load a different treatment even if an earlier cell
already imported its code. Develop changes in an isolated copy and test them
with fake providers/graphs until the active run block ends. Documentation and
workflow edits do not change model payloads. Never apply a prepared source patch
automatically when a process exits: review the diff and activate a new version
explicitly. Do not resume an old run under the changed execution identity.

## Prospective Artifacts And Approval

Before launch, save protocol/profile/source/prompt/schema/task/order hashes,
model identifiers, known server revision, adapter versions, schedule, budgets
and approval scope. This document is a dated design, not an externally registered
preregistration; preserve its frozen launch hash before any inference.

Keep raw events outside the versioned results: one event per role decision,
HTTP attempt, database query, preview/fetch and termination, with stable
question/replica IDs and timings. Retain failed-response diagnostics after
secret redaction, with explicit missing/truncated flags. Do not archive
authorization headers, keys or private endpoint URLs. Public artifacts need
privacy review, complete expected QID coverage and reconstructible scores.
The existing historical archives and their site tables remain untouched.

## Separate Interface Ablation

A later experiment can keep the same controller, provider, canonical bootstrap,
backend, scorer and budgets while changing only a predeclared tool vocabulary:
the broader ANA catalog versus a minimal discovery/grounding/traversal/set/
aggregation/fetch surface inspired by existing KG interfaces. Freeze its
semantic coverage before selecting questions, expose the same subset to every
question, and report unsupported operations and budget-driven failures rather
than filtering them out. Changing this vocabulary is a new treatment, not a
per-question convenience switch. It is neither an implementation of AgentBench
nor an experiment executed in this repository today.
