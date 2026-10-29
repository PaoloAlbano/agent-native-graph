# Curated Benchmark Evidence

This directory contains versioned evidence, not generated website files.
Browse the [published ANA results](https://paoloalbano.github.io/agent-native-graph/results.html)
or the [100-QID comparison](https://paoloalbano.github.io/agent-native-graph/comparison.html)
for an interactive view of the underlying records.

## Layout

```text
cypherbench-company/
  index.json
  gold-validation.jsonl
  gold-validation.md
  gold-execution-20261025.jsonl
  full/runs/<run_id>/
    manifest.json
    summary.json
    failures.jsonl
    run.jsonl
    run-config.json  # new runs; historical archives retain four files
    graph-integrity.json  # only when before/after block verification is enabled
  query-reexecution/<evaluation_id>/
    manifest.json
    storage.json
  query-reexecution/_objects/
    <sha256>.jsonl.gz
```

## Full ANA Runs

Curate only complete Company runs with all **347 unique expected QIDs**.
The manifest identifies model, settings, benchmark, limit, source revision and
checksums. The summary contains aggregate metrics; `failures.jsonl` contains
non-matching cases, and `run.jsonl` preserves all per-question records.

New runner outputs have a local `.config.json` sidecar. The archiver uses it to
validate task contents and save effective model settings, input/code/contract
hashes and sanitized provenance as `run-config.json`. Do not commit the raw
sidecar: it includes local input paths. Historical archives are preserved as
recorded, without inventing missing provenance. A declared historical commit
alone does not prove the exact uncommitted code used at inference time.

Optional before/after verification creates a separate raw `.integrity.json`
sidecar; it does not mutate the saved model configuration or question records.
When declared in configuration, archiving requires a verified, complete block
with matching raw/configuration hashes. Its archived `graph-integrity.json` is
checksummed in the manifest and validated by the site. Invalid/incomplete/running
reports remain local diagnostics, never publishable graph-verified results.
See [block verification](../docs/reproduction.md#beforeafter-graph-block-verification)
for opt-in flags, interruption policy and non-snapshot limitations.

Follow [Contribute a Company Run](../docs/run-standard.md) to launch and archive
results. Keep incomplete, retry-only, small-sample and exploratory outputs
outside this archive. The archiver preserves original temporary output.

## Derived Query Re-executions

`query-reexecution/` stores complete evaluations of saved baseline Cypher,
not new LLM runs. The evaluation manifest pins source traces, QIDs, graph
fingerprints, scoring provenance and artifact checksums. Its logical JSONL files retain
queries, returned rows, execution errors and exact-match verdicts.

Complete evaluations use `ana-query-records-v1` compact storage. Each evaluation's
`storage.json` records ordered references and original execution times. Shared
gzip packs in `_objects/` contain identical records only once, excluding only
`elapsed_s` from the shared record. These packs are evidence, not disposable caches.
Manifests and their original JSONL checksums are unchanged. Reads reconstruct and
verify the exact original bytes, including row order, errors and execution times.
Legacy standalone JSONL directories remain readable.

```bash
# Compact existing complete evaluations; no database or LLM requests.
make compact-evaluations
# Export one portable standalone evaluation; destination must not exist.
uv run python -m agent_native_graph.research.evaluation_storage export \
  results/cypherbench-company/query-reexecution/2026-10-29-three-model-matrix \
  --out /tmp/ana-evaluation-export
```

Keep each index with its referenced shared packs. Do not copy only an evaluation
directory to another archive: export it first, then optionally compact it at its
destination. Migration never changes Git history and does not delete shared packs.
Run compaction only when no process is modifying the selected evaluations.

Original external baseline archives remain in the pinned reference repository;
they are not copied here. Their LLM-judge verdicts and the re-executed exact-result
scores measure different outputs. See the [comparison protocol](../docs/multigraphrag-comparison.md)
for reproduction and interpretation limits.

`index.json` catalogs only full ANA runs. The site validates evidence and writes
its presentation into ignored `build/site/`; it does not change these archives
or execute new queries/models during the build. Read the
[methodology caveats](../docs/methodology-audit.md) before comparing scores.
