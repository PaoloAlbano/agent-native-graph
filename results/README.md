# Results Directory

This directory is intentionally versionable.

Use it only for curated benchmark evidence that is referenced by documentation.
Raw exploratory outputs should stay outside the repository, for example under
`/tmp/agent-native-graph-runs/`.

Current layout:

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
```

Keep only complete full-split ANA runs (`limit=347`) in this directory. The
planned external comparison uses the pinned 100-QID set from the reference
repository; it is not a static projection currently published here.
Historical first-100, n20, and four September 28 full runs are kept only in
the ignored local `.local-results/` archive; new diagnostics belong outside
`results/` as well.

Every `manifest.json` must include the tested `model`, model settings, benchmark
name, limit, run hash, and git commit. `summary.json` keeps aggregate metrics,
while `failures.jsonl` keeps only non-matching rows for faster analysis.
All four retained full runs pass run-hash, QID, summary, and failure-list
checks. Their manifests also contain task-file and graph-dump hashes matching
the current local assets. The four September 28 runs lack those provenance
fields and were moved to the ignored local archive rather than published.

Current representative results are summarized in `../docs/cypherbench-company-results.md`.

Comparison reports are not curated in `results/`. The planned comparison to
the reference repository is scoped to its pinned 100 Company QIDs and will
be presented in `../docs/multigraphrag-comparison.md` once scored consistently.
Historical 347-question baseline runs are kept only in the ignored local
`.local-results/baselines/` archive.

`index.json` catalogs only full ANA runs. A presentation leaderboard, if needed,
belongs under `docs/`, not among the raw results.
