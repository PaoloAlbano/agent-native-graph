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
  query-reexecution/<evaluation_id>/
    manifest.json
    gold.jsonl
    baseline-*.jsonl
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

Follow [Contribute a Company Run](../docs/run-standard.md) to launch and archive
results. Keep incomplete, retry-only, small-sample and exploratory outputs
outside this archive. The archiver preserves original temporary output.

## Derived Query Re-executions

`query-reexecution/` stores complete evaluations of saved baseline Cypher,
not new LLM runs. The evaluation manifest pins source traces, QIDs, graph
fingerprints, scoring provenance and artifact checksums. Its JSONL files retain
queries, returned rows, execution errors and exact-match verdicts.

Original external baseline archives remain in the pinned reference repository;
they are not copied here. Their LLM-judge verdicts and the re-executed exact-result
scores measure different outputs. See the [comparison protocol](../docs/multigraphrag-comparison.md)
for reproduction and interpretation limits.

`index.json` catalogs only full ANA runs. The site validates evidence and writes
its presentation into ignored `build/site/`; it does not change these archives
or execute new queries/models during the build. Read the
[methodology caveats](../docs/methodology-audit.md) before comparing scores.
