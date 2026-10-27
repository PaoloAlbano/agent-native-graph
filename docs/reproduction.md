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

The raw SimpleKG graph dump is not versioned. Place it at
`downloads/company_simplekg.json`, then load only a **dedicated disposable**
database:

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
