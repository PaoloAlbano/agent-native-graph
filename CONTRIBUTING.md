# Contributing

You can contribute research evidence, improve the reusable graph tools, or work
on the experimental HTTP service. These share the same package, but a benchmark
run is not a prerequisite for using ANA on your own Neo4j.

| Goal | Start here |
| --- | --- |
| Add a model run or replica | [Contribute a Company Run](docs/run-standard.md) |
| Prepare the benchmark inputs | [Reproduction](docs/reproduction.md#prepare-company-data) |
| Add or refresh baseline comparison evidence | [Comparison workflow](docs/multigraphrag-comparison.md#contributor-workflow) |
| Use your own graph through Python or HTTP | [Library and server guide](docs/library-and-server.md) |

## Setup and Checks

Use Python 3.11+ and uv. From the repository root:

```bash
make sync
make lint
make test
uv run ruff format --check src/agent_native_graph tests
```

`make format` applies formatting. Offline tests need no Neo4j, model key or
ignored dataset files. `make test-backend` opts in to read-only integration
tests against the prepared Company graph; a skip is not a verified integration.
Never load or clear someone else's database to make a test pass.

For library/container distribution, `make test-distribution` builds a wheel
and the shipped Dockerfile and exercises a synthetic graph in a disposable
Neo4j container. It creates and cleans up its own Docker resources; it does not
use the Company database or call a model. Docker and uv are required. This is
opt-in and skipped in the ordinary offline suite. See the
[distribution smoke](docs/library-and-server.md#reproducible-distribution-smoke)
for coverage, graph identity requirements and cleanup limitations.

For documentation, run `make docs-build` with the pinned reference repository
available as described in [site maintenance](docs/site/README.md). CI validates
every branch push and pull request, and publishes Pages from `main` only.
Do not commit the generated `build/site/` output.

GitHub Actions starts in [ci.yml](.github/workflows/ci.yml), with separate checks:

| Stage | Feature branches and pull requests | `main` |
| --- | --- | --- |
| Lint and Format | Python lint/format and browser syntax | Same checks |
| Code Tests | `make test` and browser tests | Same tests |
| Documentation | Check Documentation Build, no release artifact | Build Release Documentation and upload the Pages artifact |
| Publish GitHub Pages | Never | Deploy only after all preceding stages pass |

[docs.yml](.github/workflows/docs.yml) is the reusable documentation builder,
not the entry point for code tests. A lint failure stops tests; a test failure
stops the docs build. The builder repeats no lint/tests. Python tests need no
model inference or opt-in external integrations; skipped tests are not verified
integrations. Only the docs builder checks out the pinned comparison repository.

Opening or updating a pull request can create a separate check run in addition
to its branch-push run. Manual runs are available on the **CI** workflow; a manual
run on a feature branch still cannot publish Pages. If branch protection requires
old check names, update required checks to the names shown on the current PR.
Changing these workflows does not configure repository protection rules.

## Add Research Results

The public benchmark scope is **CypherBench Company, test, all 347 questions**.
Use the existing `make benchmark MODEL=... PROFILE=...` and
`make archive-result OUT=...` commands; do not hand-write verdicts or manifests.
Each new run or replica needs a new output path. See the run guide for resume,
profiles and recorded provenance.

Include the entire new archive and refreshed index in the PR:

```text
results/cypherbench-company/full/runs/<new-run-id>/
  manifest.json
  summary.json
  failures.jsonl
  run.jsonl
  run-config.json
results/cypherbench-company/index.json
```

Keep all 347 outcomes, including failures. Review transcripts and errors for
secrets, private service addresses or personal paths before publishing. Do not
rewrite existing archives, infer missing historical settings, or select only
successful questions. State the model, YAML profile and run ID in the PR.

Short diagnostics belong in ignored `.local-results/`, not the full archive.
Raw output sidecars, model keys, downloaded graphs and generated schema files
remain local. Adding a complete run automatically adds it to the ANA website;
no HTML page or JavaScript registry needs to be edited.

The baseline comparison uses the **100 pinned QIDs**, not the first 100 current
task rows. Matching baseline traces remain in the external repository. A new
model/profile may appear as unavailable for comparison until those traces and
a new complete query re-execution evaluation exist. Keep original judge scores
separate from the common exact-result metric. Follow the comparison guide;
do not copy baseline archives into ANA's `results/`.

## Add Data Without Mixing Experiments

There are three different operations:

- **New results:** contribute complete archives as above, on the existing inputs.
- **New or changed benchmark inputs:** this changes the experiment. Do not put
  custom questions, sampled graphs, another category or a changed graph into
  the Company full archive. Agree on scope, task/QID contract, graph snapshot,
  loader, comparator and publication path before changing the benchmark. The
  current static site and fixed profiles are Company-specific, not a general
  multi-dataset publishing system.
- **Data in your own Neo4j:** manage it through your normal Neo4j ingestion
  workflow, then use ANA's library or server for access. Neither automatically
  loads Company. `make load-company` is a research setup command that **clears
  its target database**, not a safe generic import command.

For local diagnostic tasks, the runner reads JSONL records containing `qid`,
`graph`, `nl_question`, `gold_cypher`, and `answer_json` (JSON-encoded result
rows). `qid` must be nonempty and unique. Custom tasks need gold queries and
answers compatible with their own graph; run them through the diagnostic CLI
without a fixed Company profile and keep their outputs local. Merely changing
`--benchmark` does not make them eligible for the Company website.

## Change Tools or Runtime Code

Keep interfaces thin: reusable behavior belongs behind the backend contract,
Neo4j query logic in `backends/neo4j/`, and tool wrappers in `tools/`. Do not
require a model provider, benchmark input or source checkout for ordinary graph
access. Use absolute `agent_native_graph...` imports.

Define tools with `@tool` and parameter descriptions via `Annotated`/`ToolParam`;
backend operations implement `core/backend.py`. Review the effective native
specifications too: compatibility overrides in `core/tool_specs.py` can differ
from the decorator's schema. `make list-tools` lists metadata, while the built
tool catalog includes the effective descriptions and parameter schemas.
Python callers use `get_tool_specs()` or `graph.tool_specs()`; HTTP exposes the
same native schema builder at `/tools/specs`. Ordinary library imports must
not load benchmark runners or LLM providers.

Add tests for behavior, invalid inputs and relevant limits. Keep examples and
hints generic, not tailored to known Company answers. Changes to descriptions,
tool surfaces, scoring or runner intervention policies are experimental changes:
do not resume an old run under changed settings or edit its evidence to fit.

## Before Opening a PR

- Explain what changed and which checks actually ran; disclose skipped tests.
- Keep paper edits, new research results and unrelated refactors separable.
- Preserve immutable evidence and include every file needed by the validator.
- Check `git diff --cached` for credentials, raw local metadata and large inputs.
- Rebuild the site when changing results or documentation; never edit generated
  scores to repair a failing build.
