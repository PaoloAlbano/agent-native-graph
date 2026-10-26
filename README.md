# **Agent-Native APIs: Rethinking Data Access for LLM Agents**

This repository contains a research prototype for **Agent-Native APIs (ANA)** applied to knowledge graph question answering.

The central hypothesis is simple: query languages such as Cypher, SQL, and SPARQL were designed to give humans a compact formal language for data access. That does not necessarily make them the best interface for an LLM agent. Instead of asking a model to synthesize one perfect query end-to-end, ANA exposes bounded, composable, inspectable operations that match how agents explore, verify, and refine intermediate state.

In this project we study that idea on the `company` slice of CypherBench, comparing:

1. direct text-to-Cypher generation;
2. multi-agent/self-correcting text-to-Cypher;
3. an agent-first tool interface over Neo4j using server-side handles.

## Why ANA?

**MCP is transport. ANA is interface design.**

MCP can expose tools to agents, but it does not say how those tools should be shaped. ANA is the design layer: it asks which operations should exist, how they should be bounded, how schema discovery should work, how intermediate state should be represented, and how an agent can safely compose graph operations without materializing huge result sets.

## Research Website

Preview the static research website from the repository root:

```bash
make docs-serve
```

Open <http://127.0.0.1:8000>. Use `DOCS_PORT=8001` to select another port.
`make docs-build` regenerates the site without starting a server. Rebuild and
refresh the browser after changing the content or tool definitions.

The first section explains ANA and documents every currently exposed tool,
including its effective LLM description, required parameters, nested schemas,
and Python source. The catalog is generated from code. The second section,
`results.html`, explores all 347 Company questions across complete ANA runs:
scores, outcome filters, golden queries, answers, tool sequences, handle links,
and side-by-side run comparisons. The third section (`comparison.html`) pairs
the same 100 Company QIDs with the pinned Multi-Agent GraphRAG repository,
with separate profile and question pages. ANA exact-answer scores and external
LLM-judge scores are explicitly different metrics. A separate table uses saved
baseline query re-executions and the same exact-result comparator as ANA.
See the [comparison and contributor workflow](docs/multigraphrag-comparison.md).
Results are grouped by model, with dedicated static model pages and direct
links to a separate static page for each run. Overview and model pages require
no JavaScript or benchmark-data downloads. Only a run page loads its question
index and the selected question's details; this is not a single-page application.

Benchmark writers save to `results/`; the website reads those archives and
generates a static presentation under `docs/`. It never rewrites the evidence.
Checksums, question sets and summary counts are checked during the build.

Editable website sources live in [`docs/site/`](docs/site/). The Markdown
research notes remain in `docs/`; generated HTML, assets, and catalog JSON are
ignored locally. GitHub Actions validates the site on pull requests and builds
and deploys it on pushes to `main`. Enable **Settings → Pages → Source → GitHub
Actions** in GitHub to activate publication. The build requires neither a
running database nor an LLM API key.

## Paper / Preprint Draft

The paper-like research narrative lives in [`paper/`](paper/):

- [`paper/README.md`](paper/README.md): navigable table of contents and stable reference labels.
- [`paper/00-abstract.md`](paper/00-abstract.md): abstract.
- [`paper/01-introduction.md`](paper/01-introduction.md) through [`paper/12-conclusion.md`](paper/12-conclusion.md): section-by-section draft.

Use the paper directory when you want something easy to reference or later turn
into a preprint/PDF. Use `docs/` for repository documentation, reproduction
notes, tool contracts, and engineering decisions.

## Repository layout

- `scripts/`: ignored local fixes, discovery, and historical experiments; not part of the public reproduction workflow.
- `tests/`: unit tests for the wrapper/tool backend and analysis helpers.
- `data/`: CypherBench company tasks and schema exports. This is ignored by default because it can be regenerated or replaced.
- `downloads/`: raw downloaded graph/dataset files. Ignored by default.
- `results/`: selected benchmark runs kept as research evidence.
- `docs/`: methodology, tool definitions, results, and lessons learned.
- `paper/`: navigable paper/preprint draft with section-level files and stable reference labels.
- `src/agent_native_graph/`: installable ANA package, stable tool contract metadata, backend protocol, CLI/service interfaces, LLM providers, and concrete database adapters.

The package is being shaped toward a clean architecture:

```text
src/agent_native_graph/
  core/            # stable ANA contracts, backend protocol, and native tool-call metadata
  domain/          # stable domain primitives such as server-side handles
  tools/           # executable ANA tool functions and graph helpers
  backends/        # concrete database adapters, currently Neo4j
  llm_providers/   # model access adapters, starting with OpenAI-compatible APIs
  application/     # benchmark and agent orchestration entrypoints
  interfaces/      # CLI and HTTP/service transport adapters
  research/        # reproducible Company preparation, baselines, archives, and audits
```

Research commands are exposed through `agent-native-graph`; local `scripts/`
are not required to reproduce the benchmark.

## Current Implementation

The main Neo4j backend is currently implemented in:

```text
src/agent_native_graph/backends/neo4j/backend.py
```

The concrete class is `Neo4jGraphBackend`. It calls Neo4j and delegates
server-side handle state to `agent_native_graph.core.handle_store.HandleStore`.
Interfaces should depend on the abstract
`agent_native_graph.core.backend.AgentGraphBackend` contract and instantiate the
concrete Neo4j adapter at their backend boundary.

Benchmark orchestration is now separate from the backend:

```text
src/agent_native_graph/application/neo4j_benchmark.py
```

The benchmark module runs CypherBench tasks, drives the LLM/tool loop, records
metrics, and scores answers against CypherBench `answer_json`.

The backend contract lives in `agent_native_graph.core.backend.AgentGraphBackend`.
Tool metadata should be declared near executable tool code with `@tool(...)`
from `agent_native_graph.core.tooling`; decorated metadata is then used to build
native OpenAI/vLLM-compatible tool-call specs.

Tool registration flow:

```text
tools/*.py function
  -> @tool(name=..., status=..., profile=..., purpose=..., description=...)
  -> core.tooling registry
  -> core.tool_specs._tool_specs(...) for native LLM tool calls
  -> core.tool_specs._native_system_prompt(...) for the native LLM guidance
     used alongside the exposed tool specs
```

`tools/load_tool_modules()` imports the modules that contain decorated tools.
Decorated metadata supplies the CLI/API contracts and MCP adapter skeleton.
Native LLM tool specs additionally pass through the compatibility overrides in
`core/tool_specs.py`; the website documents that effective model-facing surface.

The refactor has separated the concrete Neo4j adapter, reusable handle storage,
tool layer, service interface, and benchmark runner. The Neo4j backend is still
kept as one implementation file for now; the next structural split can be done
later if it becomes useful.

## Quick start

Install dependencies with `uv`:

```bash
uv sync --extra dev --extra service
```

The repository is an installable `uv` project. Reusable code and reproducible
research commands live under `src/agent_native_graph` and use the packaged CLI.

The common workflow is also available through `make`:

```bash
make help
make sync
make prepare-company-tasks
make load-company
make export-schema
make benchmark
make evaluate
```

Set Neo4j and LLM environment variables:

```bash
export NEO4J_URI="bolt://127.0.0.1:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="password"
export BASE_URL="https://openrouter.ai/api/"
export MODEL="your_model"
export API_KEY_FILE="/tmp/grapharrow-agent-key"
```

Load the company graph into Neo4j:

First prepare the CypherBench Company task file:

```bash
make prepare-company-tasks
```

The raw graph dump itself is not versioned. Place it at
`downloads/company_simplekg.json`, then load it:

```bash
make load-company
```

Export the schema consumed by the benchmark from the loaded graph:

```bash
make export-schema
```

Equivalent explicit command:

```bash
uv run agent-native-graph load-company \
  --neo4j-uri "$NEO4J_URI" \
  --neo4j-user "$NEO4J_USER" \
  --neo4j-password "$NEO4J_PASSWORD" \
  --graph downloads/company_simplekg.json \
  --clear \
  --batch-size 2000
```

Run the agent-native benchmark on the first 100 company tasks:

```bash
make benchmark
```

Equivalent explicit command:

```bash
uv run agent-native-graph benchmark-neo4j \
  --tasks data/tasks_company_test.jsonl \
  --schema-json data/company_schema.json \
  --out /tmp/agent-native-graph-runs/agent_tools_first100_gpt_oss_120b.jsonl \
  --limit 100 \
  --native-tools \
  --model your_model \
  --api-key-file /tmp/grapharrow-agent-key \
  --tool-choice auto \
  --max-tokens 16000 \
  --max-steps 12 \
  --concurrency 3 \
  --evaluation-fetch-all-pages
```

Run the full company split by overriding `LIMIT` and choosing a temporary output
file outside the repository:

```bash
make benchmark-full \
  MODEL=openai/gpt-oss-120b \
  LIMIT=347 \
  OUT=/tmp/agent-native-graph-runs/company_gpt_oss_120b_temp0_reasoning_none_n347.jsonl
```

Run another OpenAI-compatible model with the same protocol:

```bash
make benchmark-full \
  MODEL=Qwen/Qwen3.6-27B \
  CONCURRENCY=1 \
  OUT=/tmp/agent-native-graph-runs/company_qwen3_6_27b_temp0_reasoning_none_n347.jsonl
```

Run the higher-temperature reasoning profile used in the investigation:

```bash
make benchmark-full \
  MODEL=openai/gpt-oss-120b \
  TEMPERATURE=1 \
  THINKING=1 \
  THINKING_EFFORT=medium \
  REASONING=medium \
  OUT=/tmp/agent-native-graph-runs/company_gpt_oss_120b_temp1_reasoning_medium_n347.jsonl
```

Neo4j query timeout defaults to 30 seconds. Override it with
`--neo4j-query-timeout-s` for benchmark runs.

Evaluate a run:

```bash
make evaluate OUT=/tmp/agent-native-graph-runs/agent_tools_first100_gpt_oss_120b.jsonl
```

Equivalent explicit command:

```bash
uv run agent-native-graph evaluate-run --run /tmp/agent-native-graph-runs/agent_tools_first100_gpt_oss_120b.jsonl
```

## Reference Baselines

The external Multi-Agent GraphRAG implementation can be run through the local
research harness. Its historical Company trace has 100 questions, whereas
ANA's full-split behavior analysis has 347. The published query-result comparison
uses the pinned 100 QIDs and a common evaluator; historical scores from the
reference repo's judge are not directly comparable with ANA's exact scores.
See the [comparison scope](docs/multigraphrag-comparison.md).

```bash
make baseline-check
make baseline-run BASELINE_MODE=direct MODEL=openai/gpt-oss-120b
make baseline-run BASELINE_MODE=agentic MODEL=openai/gpt-oss-120b
```

Set `BASE_URL` and `API_KEY_FILE` for your OpenAI-compatible model gateway.
Use `RESUME=1` with the same `BASELINE_OUT` after an interrupted run. Archive
only complete runs with `make baseline-archive BASELINE_OUT=...`. The existing
347-question baseline archives are retained as historical data, not as the
100-question comparison. See the [benchmark protocol](docs/benchmark-protocol.md).
`make baseline-run` currently defaults to 347 cases; it does not reproduce the
reference repository's 100-case evaluation by itself.
The archived runs live only in the ignored local `.local-results/baselines/`
directory. The gold-query check found two Company questions with
non-reproducible answers.


## Service shape

The repository includes an experimental HTTP service shape over the packaged
Neo4j backend. The concrete adapter lives under `backends/neo4j`, while
interfaces depend on stable package entrypoints.

Run it locally with:

```bash
make serve
```

Equivalent explicit command:

```bash
uv run agent-native-graph serve
```

Useful endpoints:

- `GET /health`
- `GET /tools`
- `POST /tools/call` with `{"tool": "schema_overview", "args": {}}`

Configure it with:

```bash
export NEO4J_URI="bolt://127.0.0.1:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="password"
export ANA_NEO4J_QUERY_TIMEOUT_S="30"
```

By default the service discovers graph schema directly from Neo4j at startup.
Set `ANA_SCHEMA_JSON` only when you deliberately want to override discovery with
a fixed schema file for a controlled experiment.

Neo4j query timeout defaults to `ANA_NEO4J_QUERY_TIMEOUT_S=30`.

## Results Hygiene

`results/` contains curated full-split CypherBench Company runs (`limit=347`)
and separately archived, complete 100-question query re-execution evaluations.
Diagnostic runs remain outside `results/`, for example under
`/tmp/agent-native-graph-runs` or the ignored local `.local-results/` archive.

Incomplete, single-case, retry, and debugging outputs should remain outside
the repository, for example under `/tmp/agent-native-graph-runs`.

The [347-question ANA analysis](docs/cypherbench-company-results.md) and the
[100-question external comparison](docs/multigraphrag-comparison.md)
are separate research sections, both presented by the generated static site.

Curated runs live under:

```text
results/cypherbench-company/
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

The four retained runs have complete model, task-file, graph-dump, and run
hash metadata. Four earlier runs lacking task and graph hashes were moved to
the ignored local archive. See the [results format and provenance
notes](results/README.md). Use `make archive-result` after a benchmark run to
create this structure and refresh the benchmark index.

Example archive command for a complete full run:

```bash
make archive-result \
  MODEL=openai/gpt-oss-120b \
  LIMIT=347 \
  TEMPERATURE=0 \
  REASONING=none \
  CONCURRENCY=5 \
  OUT=/tmp/agent-native-graph-runs/company_gpt_oss_120b_temp0_reasoning_none_n347.jsonl
```

The reproducible benchmark protocol is defined in
[`docs/benchmark-protocol.md`](docs/benchmark-protocol.md).


## Docker

Build and run the experimental service container:

```bash
make docker-build
make docker-run
```

Equivalent explicit commands:

```bash
docker build -t agent-native-graph .
docker run --rm -p 8080:8080 \
  -e NEO4J_URI=bolt://host.docker.internal:7687 \
  -e NEO4J_USER=neo4j \
  -e NEO4J_PASSWORD=password \
  agent-native-graph
```

The container starts the HTTP service and discovers schema from Neo4j. Raw
datasets are intentionally not baked into the image.

## Tool Catalog

Print the current ANA tool catalog generated from decorated tool functions:

```bash
make list-tools
```

Equivalent explicit command:

```bash
uv run agent-native-graph tools
```

This shows the native tool-call metadata exposed to LLM agents: tool names,
profiles, statuses, descriptions, and JSON schemas for parameters. The
human-readable contract is in `docs/ana-v0-tool-contract.md`.

## Research notes

Start with:

- `docs/agent-native-apis.md`
- `docs/tool-catalog.md`
- `docs/ana-v0-tool-contract.md`
- `docs/repo-hygiene.md`
- `docs/cypherbench-company-results.md`
- `docs/lessons-learned.md`
- `docs/reproduction.md`
