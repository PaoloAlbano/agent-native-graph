# Repository Hygiene

The repository separates research code, reusable wrapper code, regenerable data,
temporary benchmark output, and curated evidence.

## Versionable by default

- `src/`: reusable ANA package, service shape, and reproducible research commands.
- `tests/`: backend/tool-contract tests.
- `docs/`: methodology, results summaries, and tool contracts.
- `results/`: selected benchmark outputs referenced by docs.
- `tests/schema_fixture.py`: synthetic schema for offline tests, not downloaded
  graph data. `data/reference_company100_qids.json` is also explicitly versioned.
- `pyproject.toml`, `uv.lock`, `Dockerfile`, `README.md`.

## Ignored by default

- `downloads/`: raw downloaded graph/dataset files.
- `scripts/`: local fixes, discovery, and historical experiments.
- `data/*.json`, `data/*.jsonl`, `data/*.txt`: generated task/schema files.
- virtualenvs, caches, logs, build artifacts.
- `.local-notes/`: private roadmaps, collaboration decisions and session diaries.
  Public contributor instructions and scientific caveats remain in `docs/`.

## Outside the repository

- `/tmp/agent-native-graph-runs/`: temporary benchmark JSONL/log output.
- External baseline repositories and their raw run artifacts.

## Promotion rule

A run should be promoted from temporary storage to `results/` only when it is
comparable, complete, and documented with model, profile, limit, scoring metric,
and known caveats.

New full runs use [the frozen run standard](run-standard.md). Complete derived
query-reexecution evaluations are versionable in their separate archive; they
are not partial ANA runs. Generated static HTML/assets/JSON are ignored; their
sources under `docs/site/` are versioned. Both local and CI builds write output
to ignored `build/site/`, not back into `docs/`.
