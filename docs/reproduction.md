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
(including its existing recovery rules). The reference workflows, including the
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
budgets, global HTTP concurrency, common approved deadline values,
retrieval-only variants and full observation parity still require implementation.
The opt-in preflight below provides before-run verification and equal initial
schema facts only, not the complete matched-condition protocol.
No historical results are rewritten by these commands.

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
