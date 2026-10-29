# Reproduction

For the normal contribution workflow, follow [Contribute a Company Run](run-standard.md):
one benchmark command and one archive command. This page covers setup and
advanced diagnostics rather than duplicating that workflow.

## Install and Configure

```bash
make sync
```

This uses `uv sync --locked --extra dev --extra service`. Set `NEO4J_URI`,
`NEO4J_USER`, `NEO4J_PASSWORD`, and either `API_KEY` or `API_KEY_FILE` in your
environment. The Makefile defaults to a local Neo4j and OpenRouter; override
`BASE_URL` for another compatible gateway. Never commit real credentials or
private service addresses. The key-file default is `/tmp/grapharrow-agent-key`.

## Prepare Company Data

```bash
make prepare-company-tasks
```

This downloads CypherBench `test` and selects `graph == "company"`, currently
347 questions, into `data/tasks_company_test.jsonl`. The task file is ignored.
To select the published comparison subset, use the pinned QIDs, not `LIMIT=100`.

The raw SimpleKG graph dump is not versioned. The official
[CypherBench dataset](https://huggingface.co/datasets/megagonlabs/cypherbench)
provides `graphs/simplekg/company_simplekg.json`. On a fresh checkout, download
the full graph (not the sampled variant) from this fixed upstream revision:

```bash
curl --fail --location --create-dirs \
  --output downloads/company_simplekg.json \
  'https://huggingface.co/datasets/megagonlabs/cypherbench/resolve/fd80c26a9f5447e4c9ba952cc70575544117306c/graphs/simplekg/company_simplekg.json'
```

Do not overwrite a local dump you need to preserve. Its expected SHA-256 for the
current archives is
`54d15b5db4c30b9d7d0e31cbc30ca7c144d3e2cad30bddf8d92390a095f0b82b`;
the benchmark validates it and the loaded graph content. Task preparation above
currently uses the upstream default revision, not this pinned graph revision;
the runner records task hashes and the publisher rejects mismatched archived
question sets. Do not assume a future upstream revision is the same experiment.

Then load only a **dedicated disposable** database:

```bash
make load-company
make export-schema
```

**`make load-company` clears the target database before loading.** Do not use
it merely to check existing data. The benchmark itself verifies graph content
and aborts on a mismatch; it never clears or repairs the graph.

`export-schema` writes the benchmark's local schema JSON and prompt from Neo4j.
Override `GRAPH`, `TASKS`, `SCHEMA_JSON` or `SCHEMA_PROMPT` when needed. These
generated files stay local; curated run metadata records their hashes.

## Run and Archive

```bash
make benchmark MODEL=openai/gpt-oss-120b PROFILE=temp0-none
```

The runner prints a new output path. Use it when archiving:

```bash
make archive-result OUT=/tmp/agent-native-graph-runs/the-printed-file.jsonl
```

`PROFILE=temp1-medium` selects temperature 1 plus requested medium thinking;
`CONCURRENCY` controls parallel requests. Model/profile parameters need not be
repeated in the archive command. Full archives contain `manifest.json`,
`summary.json`, `failures.jsonl`, `run.jsonl`, and, for new runs, `run-config.json`.
Only complete curated 347-question runs go into the full archive. Diagnostics
are sent to ignored `.local-results/` by the archiver. See
[the run standard](run-standard.md) for resume, replicas, provenance and safety.

## Advanced Diagnostics

For a short local check, use the direct runner without a fixed Company profile:

```bash
uv run agent-native-graph benchmark-neo4j \
  --tasks data/tasks_company_test.jsonl \
  --schema-json data/company_schema.json \
  --model your_model --limit 20 --native-tools --tool-choice auto \
  --out /tmp/ana-diagnostic.jsonl --max-tokens 16000 --max-steps 12
```

The output path must be new. It also has a metadata sidecar, so archiving can
read its actual settings. Diagnostics are not full Company evidence. Historical
raw files without sidecars require the direct `archive-result` CLI with the
original model/profile parameters, not guesses; do not invent missing metadata.

For deterministic answer comparison after execution:

```bash
make evaluate OUT=/tmp/ana-diagnostic.jsonl
```

This comparison is deterministic; model inference at temperature zero is not
guaranteed to be. See [benchmark-protocol.md](benchmark-protocol.md).

## Tests and Documentation

```bash
make lint
make test
make docs-build
```

Offline contract tests use a versioned synthetic schema and need neither
Neo4j nor `data/company_schema.json`. Opt in to real Company integration tests
only against the prepared dataset:

```bash
make test-backend
```

This sets `ANA_TEST_NEO4J=1`; unavailable integrations are reported as skipped,
not certified by the unit-test pass. Documentation build uses curated archives
and a pinned external Git source; no inference or database connection is needed.

## External Baselines

The [published external comparison](multigraphrag-comparison.md) uses exactly
the pinned 100 Company QIDs. Its original judge scores and derived exact query
re-execution scores are distinct metrics.

The separate local research harness also supports `make baseline-check`,
`make baseline-run BASELINE_MODE=direct` and `BASELINE_MODE=agentic`, using the
sibling `multigraphrag` checkout. Configure its `MODEL`, `TEMPERATURE`,
`REASONING`, `BASE_URL`, `API_KEY_FILE` and unique `BASELINE_OUT`. Its default
347-question runs are not the published 100-QID experiment. Follow the comparison
guide's source/QID contract, not that harness alone, when contributing a new
published comparison.

### Pinned Source And Shared Provider

Opt in explicitly to the foundation adapter using a model-independent YAML
profile and a full reference Git commit (the commit must already exist locally):

```bash
make baseline-check BASELINE_PROFILE=temp0-none REFERENCE_COMMIT=<full-40-character-sha>
make baseline-run BASELINE_MODE=single BASELINE_PROFILE=temp0-none \
  REFERENCE_COMMIT=<full-40-character-sha> MODEL=<model-id> BASELINE_OUT=<new-output.jsonl>
```

`baseline-check` does not read an API key or call a model. It validates task
contents and graph dump identity, discovers the live schema, and executes a
read-only scoring probe. It does **not** verify the entire loaded graph against
the dump. Make installs reference dependencies through the project's `reference`
extra; the sibling checkout supplies source and data, not its Python environment.
The current pinned reference source requires Python 3.12 or newer. For direct
CLI use, run `uv run --extra reference agent-native-graph baseline-run ...`.
Committed source/configuration files are exported to a temporary directory;
uncommitted reference code is not executed and its branch is not switched.
Datasets are read from the original checkout. The sidecar records source-file,
adapter, provider, input and profile hashes plus installed dependency versions;
it records neither credentials nor endpoint URLs. A changed identity rejects
resume, including an old sidecar without these fields.

With `BASELINE_PROFILE`, every reference role uses ANA's provider, call settings,
timeouts and HTTP retry policy; profile settings override the legacy generation
flags. Structured generation still uses the pinned reference JSON parser
(including its existing recovery rules). The original `single` and `agentic` workflows, including the
prose interpreter, are unchanged. The profile path never restarts a whole question
on HTTP 429; only the shared provider retries the request. Without a profile,
the reference's legacy LLM client and workflow-level retries remain available
and are identified as `reference-legacy` in metadata.

Both paths now use named-database, EXPLAIN-classified read queries, explicit
transaction timeouts, rollback and a streaming hard row cap during candidate
execution, introspection and final scoring. Over-limit results are errors, never
partial answers. The default cap is 100,000 rows with a profile, 10,000 without;
the CLI allows `--max-score-rows` and `--database`. This is a research guard,
not a replacement for database read-only credentials and procedure permissions.

This is **foundation-only**, not compliance with the
[controlled Company protocol](controlled-company-protocol.md). Shared generation
budget experiments, global HTTP concurrency, common approved deadline values
and full observation parity still require separate work. Retrieval-only variants
are implemented as the explicit opt-in modes below.
The opt-in preflight below provides before-run verification and equal initial
schema facts only, not the complete matched-condition protocol.
No historical results are rewritten by these commands.

### Retrieval-Only Reference Variants

Two explicit research modes, `single_retrieval` and `agentic_retrieval`, use the
same pinned controllers but replace only the terminal prose interpreter with a
stateless local finalizer. They require a YAML profile and reference commit
`72fe7105310c85ebe6b1b3b7d4c6152ddb206393`; other revisions are rejected until
their control flow is validated. The reference checkout is never modified.

`single_retrieval` retains the original bounded retries after execution errors
or empty results. `agentic_retrieval` retains generation, semantic evaluation,
entity extraction/verification, ranking, correction and aggregation. All native
iteration limits and feedback stay unchanged. `direct` is still the separate
one-generation baseline, not an alias for either new mode.

Per-question `answer` is `null`, and the metadata records
`finalization: retrieval-only-v1` with a distinct mode/approach. Only the final
query selected by the original controller is replayed through the existing
bounded read-only scorer to collect complete rows. That replay is database
work, not another model decision; its errors/row-cap failures are not scored
as partial successes. No earlier candidate is chosen using the gold answer.
The controller's `accepted` flag remains diagnostic, not a correctness judge:
it can reject a query whose rows are correct or accept a wrong one. Exhaustion
keeps the original final candidate and iteration count, never an invented answer.

Verify actual pinned-controller parity without database or inference calls:

```bash
make test-reference REFERENCE_REPO=../multigraphrag
```

This needs the local pinned source and reference dependencies (Python 3.12+).
Tests compare every generated prompt/response and graph observation against the
original workflow, excluding only its final interpreter call. They cover blind
retries, semantic correction, both entity-verification branches, ranking,
iteration exhaustion, request accounting, cancellation and resume identity.

Only after approving an inference experiment, select a variant through the
existing command, for example:

```bash
make baseline-run BASELINE_MODE=single_retrieval BASELINE_PROFILE=temp0-none \
  REFERENCE_COMMIT=72fe7105310c85ebe6b1b3b7d4c6152ddb206393 \
  SHARED_PREFLIGHT=1 MODEL=<model-id> BASELINE_OUT=<new-output.jsonl>
```

Use `BASELINE_MODE=agentic_retrieval` for the multi-agent variant. These are new
treatments, not replacements for historical runs or automatic additions to the
published comparison. Their common feedback policy/global resource controls
remain pending in the [controlled protocol](controlled-company-protocol.md).

### Opt-In Bounded Result Policy

`RESULT_POLICY=bounded-v1` is a separate experimental treatment, disabled by
default for ANA and baseline commands. It does not edit tool definitions,
system instructions or the reference controllers. Select it explicitly on
both arms of a newly approved experiment, never when resuming a historical run:

```bash
# Examples only; these commands launch inference when credentials are configured.
make benchmark MODEL=<model-id> PROFILE=temp0-none RESULT_POLICY=bounded-v1
make baseline-run MODEL=<model-id> BASELINE_MODE=single_retrieval \
  BASELINE_PROFILE=temp0-none RESULT_POLICY=bounded-v1 \
  REFERENCE_COMMIT=72fe7105310c85ebe6b1b3b7d4c6152ddb206393
```

The common limits are **100,000 collected rows** and **at most 20 preview rows**.
Baseline mode requires a pinned profile and rejects a contradictory
`--max-score-rows`. The candidate result shown to its controller is capped at
20; entity verification and schema discovery keep their original per-query
limits so that schema facts are not silently sampled. ANA intermediate previews
retain their historical, sometimes smaller size; this is a shared ceiling,
not a claim that each arm observes the same number of rows.

ANA collects only the stored handle explicitly finalized by the model. If its
fetch is one page, even a later/final page, evaluation may issue one additional
bounded fetch from offset zero. The recorded `evaluation_collection` flag marks
that extra data access. This supersedes the historical unbounded
`--evaluation-fetch-all-pages` helper in this policy. It never selects another
handle, generates a final fetch when the model did not request one, or repairs
an earlier tool limit. Paging is delivery, not semantic top-k: express intended
selection in the query/handle rather than expecting the fetch page size to be
the answer definition. Invalid, changed, incomplete or over-cap pages cannot
leave a partial `last_fetch` available for successful scoring. No final fetch
cannot exactly match an empty gold answer under this policy.
`done` is rejected as a tool error rather than converted into a fetch; the
model may still request `fetch` in a remaining decision turn. The legacy
end-of-budget automatic fetch is also disabled, even if its legacy option was
enabled. Both historical fallbacks remain unchanged when this policy is absent.

Baseline evaluation still replays its controller's final query using the bounded
read-only scorer, not its preview. Over-cap results fail without retaining a
prefix. `result_observations` records candidate/introspection/scoring coverage
separately for each question, including asynchronous child roles. This metadata
is archived, not inserted into model instructions. The reference evaluator's
existing "possibly truncated" wording is unchanged; equal explicit coverage
information in all controller observations remains future G5 work.

`result_completeness` separates `available_count`, `collected_count`,
`preview_count` and `preview_truncated`. Its `complete` flag means collection
of the named scope only: a stored ANA handle or one baseline Cypher query.
**It does not certify that the answer covers the entire graph.** Upstream
coverage is `unknown` for ANA handles, since operations may have applied limits;
a model's semantic `LIMIT` also remains part of its query, not a transport error.
Failed/unfinished collection is not scored as a complete answer.

The policy is saved in both run configurations; changing it rejects resume.
The ANA archiver routes these exploratory runs to `.local-results/` by default,
including complete 347-QID runs, to avoid pairing a new treatment with historical
baselines. Keep them separate until a new publication protocol is approved.
This slice does not implement after-block graph certification, a snapshot,
global resource admission or production-server quotas.

### Before/After Graph Block Verification

`VERIFY_GRAPH_BLOCK=1 SHARED_PREFLIGHT=1` opts ANA `make benchmark` and
`make baseline-run` into the same integrity check. The CLI flag is
`--verify-graph-block`. Default/historical runs remain unchanged. A block here
is **one fresh runner invocation**, not one question or the entire proposed
matrix. Baseline mode also requires its pinned profile through shared preflight.
No graph is loaded, cleared or changed automatically.

The initial shared preflight verifies the loaded named database against the
Company dump. After all local question tasks/requests settle and result writers
close, a content-only scan reads all node labels/properties and all relationship
types/properties/endpoints. The same multiset fingerprint includes duplicate
multiplicity, not only counts. These verification scans use the preflight's
300-second per-query timeout, not the per-question 30-second query timeout;
they are block overhead, not model-request latency.

The runner creates `<raw-stem>.integrity.json` before execution with
`status: running`, then atomically seals it as:

- `verified`: equal before/after content, unchanged dump/configuration, and the
  exact expected QID set with no omissions or duplicates.
- `invalid`: graph content, dump bytes or configuration changed.
- `incomplete`: execution failed/interrupted, coverage is incomplete, evidence
  cannot be read, or the postcheck fails. A process crash may leave `running`,
  which is also not eligible for archiving.

Any unsuccessful seal causes a normally completed runner to fail explicitly.
If the benchmark already raised an exception/cancellation, its original failure
is preserved. Raw answers and call logs are retained unchanged for diagnosis;
successful per-question scores do not override an invalid block. Error evidence
contains exception types, not connection strings or exception messages.

The sidecar binds exact raw-result and source-configuration SHA-256 values,
QID coverage, the named database, and before/after fingerprints. Both archivers
require verified evidence when the configuration declares this feature, copy
it as `graph-integrity.json`, and record its checksum in the manifest. The
static site checks that evidence too, without contacting Neo4j. Historical
archives without this feature need no invented verification report.

`--resume` and `--check-only` are deliberately rejected for a verified block;
use a fresh output for a new attempt and retain interrupted evidence locally.
Combining separately verified resumed segments is not implemented. Existing
resume behavior without this feature is unchanged. All checks are read-only.

**Limits:** two endpoint fingerprints do not exclude concurrent writers,
provide snapshot isolation, or detect a transient change later restored to
identical content. Keep the graph externally read-only during the experiment.
A verified report certifies only its declared graph/coverage checks, not every
gate of the controlled protocol. Equal explicit completeness information and
global execution/resource limits remain separate work.

### Opt-In Common Graph And Schema Preflight

`SHARED_PREFLIGHT=1` is a new experimental treatment, not a reinterpretation of
historical runs. Leave it off to preserve the existing runner behavior. It uses
the same SimpleKG-to-Neo4j normalization and full-content fingerprint for ANA and
profile-enabled reference baselines, then collects canonical live metadata:
labels, relationship types, node/relationship property types and mandatory flags,
and directed label endpoint patterns. Unknown types/mandatory flags stay unknown.
No entity samples or property values are added to the initial schema prompt.

```bash
make benchmark MODEL=<model-id> PROFILE=temp0-none SHARED_PREFLIGHT=1
make baseline-run MODEL=<model-id> BASELINE_MODE=single \
  BASELINE_PROFILE=temp0-none REFERENCE_COMMIT=<full-40-character-sha> SHARED_PREFLIGHT=1
```

Both can select `NEO4J_DATABASE=<name>` (default `neo4j` in this mode). The same
canonical JSON schema is passed as baseline `schema_text` and as ANA's explicit
`schema_bootstrap` user-message field. ANA schema tools use that same canonical
metadata. The controllers still have different prompts, tools and subsequent
observations; this is equal initial schema evidence, not identical trajectories.
The existing ANA `SCHEMA_JSON` input remains recorded for compatibility, but is
not used to supply the shared model/bootstrap metadata; the config explicitly
records `schema_source=shared-live-preflight-v1`.

New `shared_preflight` evidence in the saved ANA config/reference metadata records
the graph dump hash, verified node/edge fingerprints, named database, canonical
schema and its prompt hashes. Node/edge counts alone are insufficient: property,
label, endpoint or duplicate differences fail before inference. A graph/schema
identity change rejects resume. Shared mode requires an explicit pinned profile
for reference baselines. ANA `CHECK_ONLY=1` cannot be combined with this live
verification; baseline check-only still allows live preflight without model calls.

The preflight performs full graph reads and schema metadata collection before
question timing. It never loads, clears or mutates Neo4j. This is **before-run**
verification, not an atomic snapshot or exclusion of concurrent writers, and it
does not certify after-run state or the entire controlled protocol. Keep the graph
read-only externally. The schema bootstrap can be large; this research mode does
not replace the bounded discovery tools used by ordinary library/server clients.

For a small diagnostic ANA run, use the direct `benchmark-neo4j` CLI without
`--profile`: official ANA profiles intentionally require all 347 cases. Pass
`--limit 3 --native-tools --tool-choice auto --temperature 0 --max-tokens 16000
--max-steps 12 --evaluation-fetch-all-pages --shared-preflight --database neo4j`
along with the usual task/schema/graph, model and output arguments. Store smoke
outputs outside `results/`. The baseline CLI can combine `--limit 3`, its pinned
`--profile` and `--shared-preflight`. Compare the two saved `shared_preflight`
objects, including schema/prompt hashes and graph snapshots; they must match.
Such diagnostics do not estimate quality or validate the full controlled protocol.

### Request Accounting

New ANA runs and profile-enabled reference baselines save `request_accounting`
per question. This is passive instrumentation: it does not change tool/prompt
payloads, stopping limits, sampling, HTTP retries or fallback behavior. Legacy
baseline transport is not instrumented and records `null`; historical archives
are not backfilled and must not be interpreted as zero consumption.

The ledger distinguishes a logical provider call from each actual HTTP POST,
including failed requests, transport retries and low-effort length fallbacks.
`observed_completion_responses` counts returned completion responses, including
discarded length responses; it cannot reveal generations whose response was lost.
Reference calls are labeled by role. It records status codes, error class,
finish reason, elapsed time and numeric token usage, but no API keys, endpoint
URLs, prompts, responses or exception messages. Those question/response traces
remain in their existing benchmark artifacts, not in the accounting ledger.

Use `request_accounting.summary.observed_usage_totals` for observed request-level
usage, including discarded initial responses before a fallback. The older
`llm_metric_summary` / `llm_*tokens` fields retain their historical semantics
(returned-response usage) for compatibility; do not add those totals together.
`attempts_without_usage` and `usage_field_coverage` distinguish unavailable token
counts from actual reported zero. No token estimate or model-price estimate is
invented for failed requests whose usage is unavailable.

Question rows retain request observations even when the provider raises before
returning `__chat_meta`. Archive summaries aggregate only instrumented ledgers
and report coverage of legacy/uninstrumented rows. Latency sums are service
time across calls, not batch wall time, because roles/questions can overlap.

Profile-enabled reference roles now await `provider.achat()` directly, not a
synchronous client in `asyncio.to_thread`. Cancellation closes the async client;
the question waits for active sibling requests to settle before saving its
ledger. The harness also records cancelled in-flight questions before closing
the output file. `requests_settled` describes client requests, not confirmed
remote-server cancellation or complete billing information.
Batch helpers also cancel and drain work still queued at their semaphore;
successful batch ordering and concurrency limits remain unchanged.

Custom callers that still put synchronous `provider.chat()` in a thread cannot
cancel that thread by cancelling its await. Such snapshots retain pending flags
and remain incomplete. Use `await provider.achat()` in asynchronous applications.
Durable recovery after process crashes or forced termination remains future work.

No full benchmark rerun is needed to preserve historical quality results.
Unit/integration tests check payload equality, failure and retry accounting,
per-question isolation and the real pinned workflows with simulated responses.
Only small inference smoke tests are needed for gateway compatibility. New
metrics become available for future runs; old missing metrics stay unknown.

### Timeouts And Cancellation

The YAML `timeout_s` remains the HTTP client's per-operation timeout. It is
distinct from the total elapsed-time allowance for a question, which includes
retry waits and length fallbacks. Neither sampling nor retry decisions change
when requests complete within their existing limits.

ANA's diagnostic `--task-timeout-s N` now works at concurrency above one without
process-global signals. A worker with an explicit deadline uses cancellable
async HTTP internally, then closes it before returning its result. The default
is still no task deadline, and standard Company profiles still reject custom
task-timeout overrides. A task timeout is classified as `task_timeout`, distinct
from a backend query timeout. Requested deadlines are saved even with concurrency.

Profile-enabled reference runs retain `--task-timeout` (default 240 seconds),
but apply it once to the question, including final query scoring, rather than
giving scoring extra time. One monotonic deadline is inherited by every role;
retry waits and active requests are interruptible. The legacy unprofiled path
retains its separate per-generation-attempt timeout behavior and is labeled
`reference-legacy`; it is not certified by the new request-lifecycle tests.

ANA's graph tools are still synchronous: deadline checks occur before/after
each tool, including final pagination. An already-running synchronous Neo4j
query is not forcibly killed by the question deadline; it retains its separate
query timeout (normally 30 seconds), so cleanup can overrun the question limit.
This is not a hard real-time execution guarantee or a common 900-second study
policy. Shared approved values and global endpoint admission remain pending.

Closing an HTTP connection stops client work and prevents subsequent retries;
it cannot guarantee that a remote gateway stops model computation. That needs
provider-supported abort semantics. Tests use mock transports and a real local
TCP server to verify socket closure, no leaked sibling requests, settled ledgers,
and unchanged sync/async payloads across all four profiles. No full inference
rerun is required for these lifecycle checks.
