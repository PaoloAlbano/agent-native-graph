# Repository Hygiene

The repository separates research code, reusable wrapper code, regenerable data, exploratory runs, and curated evidence.

## Versionable by default

- `src/`: reusable ANA package and service shape.
- `scripts/`: research runners and migration source for package refactors.
- `tests/`: backend/tool-contract tests.
- `docs/`: methodology, results summaries, and tool contracts.
- `results/`: selected benchmark outputs referenced by docs.
- `pyproject.toml`, `uv.lock`, `Dockerfile`, `README.md`.

## Ignored by default

- `downloads/`: raw downloaded graph/dataset files.
- `runs/`: exploratory outputs, logs, partial experiments.
- `data/*.json`, `data/*.jsonl`, `data/*.txt`: generated task/schema files.
- virtualenvs, caches, logs, build artifacts.

## Promotion rule

A run should be promoted from `runs/` to `results/` only when it is comparable, complete, and documented with model, profile, limit, scoring metric, and known caveats.
