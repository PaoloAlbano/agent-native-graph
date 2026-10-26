# Repository Hygiene

The repository separates research code, reusable wrapper code, regenerable data,
temporary benchmark output, and curated evidence.

## Versionable by default

- `src/`: reusable ANA package, service shape, and reproducible research commands.
- `tests/`: backend/tool-contract tests.
- `docs/`: methodology, results summaries, and tool contracts.
- `results/`: selected benchmark outputs referenced by docs.
- `pyproject.toml`, `uv.lock`, `Dockerfile`, `README.md`.

## Ignored by default

- `downloads/`: raw downloaded graph/dataset files.
- `scripts/`: local fixes, discovery, and historical experiments.
- `data/*.json`, `data/*.jsonl`, `data/*.txt`: generated task/schema files.
- virtualenvs, caches, logs, build artifacts.

## Outside the repository

- `/tmp/agent-native-graph-runs/`: temporary benchmark JSONL/log output.
- External baseline repositories and their raw run artifacts.

## Promotion rule

A run should be promoted from temporary storage to `results/` only when it is
comparable, complete, and documented with model, profile, limit, scoring metric,
and known caveats.
