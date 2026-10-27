# Agent-Native APIs: Rethinking Data Access for LLM Agents

**Design the data interface for the agent, rather than only teaching the agent
to use an interface designed for humans.**

[Live Website](https://paoloalbano.github.io/agent-native-graph/) |
[ANA Results](https://paoloalbano.github.io/agent-native-graph/results.html) |
[Baseline Comparison](https://paoloalbano.github.io/agent-native-graph/comparison.html) |
[Paper Draft](paper/README.md)

Agent-Native Graph is a research prototype for **Agent-Native APIs (ANA)**.
Instead of asking an LLM to generate one complete formal query, the agent
discovers the schema, resolves entities, composes operations and inspects
intermediate results through server-side handles.

The idea concerns data access more generally; **knowledge graph question
answering is the current case study**, not a demonstrated result for every
domain. This repository studies CypherBench **Company** over Neo4j, alongside
direct text-to-Cypher and multi-agent/self-correcting text-to-Cypher approaches.

Cypher, SQL and SPARQL remain valuable formal interfaces. The research question
is whether an interface designed explicitly for agents can improve their
reliability and answer quality on a given task. **MCP is transport; ANA is
interface design.** The current findings are exploratory, not a claim of
universal superiority or production readiness.

## Explore the Published Results

The [GitHub Pages website](https://paoloalbano.github.io/agent-native-graph/)
is public: **no installation, database or API key is needed to browse it**.

| Section | What you can inspect |
| --- | --- |
| [Approach and tools](https://paoloalbano.github.io/agent-native-graph/#approach) | The design, an example trajectory and the [effective tool catalog](https://paoloalbano.github.io/agent-native-graph/#tool-catalog), including parameters and source links |
| [ANA on Company](https://paoloalbano.github.io/agent-native-graph/results.html) | Complete 347-question runs grouped by model and configuration, with individual questions, expected/returned answers and recorded tool-call sequences |
| [Comparison](https://paoloalbano.github.io/agent-native-graph/comparison.html) | The exact 100 shared Company QIDs, matched model/settings, direct and multi-agent baseline evidence, and per-question drill-down |

Results pages preserve the distinction between **technical execution success**
and **correct answers**. The comparison also separates two different evaluations:

- **Original metrics:** ANA exact-answer matching beside the baseline source's
  LLM-judge verdicts on final textual answers. These evaluators are not equivalent.
- **Common query-result metric:** saved baseline Cypher re-executed on the
  verified ANA graph and scored with the same exact-result comparator as ANA.
  This measures returned rows, not the baseline's final prose answer.

Questions, graph provenance, budgets and historical execution conditions still
matter. See the [methodology caveats](docs/methodology-audit.md) and
[comparison protocol](docs/multigraphrag-comparison.md) before interpreting
cross-method differences. Missing historical prompts, reasoning or full handle
contents are not reconstructed as if they had been recorded.

Raw curated evidence lives in [`results/`](results/), not in the generated site.
The website reads and validates those archives without changing them. GitHub
Actions validates pull requests and publishes Pages after relevant changes
merge to `main`; branch-local work is not automatically the published version.

## Contribute a Benchmark Run

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/), a Neo4j database
prepared with Company data, and an OpenAI-compatible model endpoint/API key.

```bash
git clone https://github.com/PaoloAlbano/agent-native-graph.git
cd agent-native-graph
make sync
```

Follow [data preparation](docs/reproduction.md#prepare-company-data) before
launching. Raw task/schema files and the graph dump are not bundled with the
repository. **`make load-company` clears its target database**: only use a
dedicated disposable database, never a database you want to preserve.

Configure `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, and either `API_KEY` or
`API_KEY_FILE` in your environment. `BASE_URL` defaults to OpenRouter; override
it for another compatible gateway. Use the exact model ID accepted by that
provider. Never commit real credentials or private endpoint addresses.

Run all 347 Company questions:

```bash
make benchmark MODEL=your-model-id PROFILE=temp0-none
```

The runner checks inputs and graph content, creates a unique output path, saves
the actual configuration and prints where results are being written. It does
not overwrite existing output or reload Neo4j. `CONCURRENCY=3` is the default;
add `CHECK_ONLY=1` for an offline input check without inference or a database call.

Archive the completed run using the printed path:

```bash
make archive-result OUT=/tmp/agent-native-graph-runs/the-printed-file.jsonl
```

The archiver reads saved settings, checks QIDs/task contents, preserves the
original output and refreshes the index. You do not need to repeat model,
temperature or token settings. Commit the complete archive and index, not the
temporary output or local metadata sidecar. CI builds the presentation; it
never launches a paid benchmark.

See [Contribute a Company Run](docs/run-standard.md) for resume, replicas,
configuration validation and publishing, or [reproduction](docs/reproduction.md)
for advanced CLI diagnostics. `make help` lists available commands.

### YAML Model-Call Profiles

Profiles live in [`src/agent_native_graph/profiles/`](src/agent_native_graph/profiles/)
and contain no model name, endpoint or credentials. The reference matrix is:

| Temperature | Thinking requested off | Thinking requested on, medium effort |
| --- | --- | --- |
| 0 | [`temp0-none`](src/agent_native_graph/profiles/temp0-none.yaml) | [`temp0-medium`](src/agent_native_graph/profiles/temp0-medium.yaml) |
| 1 | [`temp1-none`](src/agent_native_graph/profiles/temp1-none.yaml) | [`temp1-medium`](src/agent_native_graph/profiles/temp1-medium.yaml) |

All other settings are equal, including **16k output tokens and `tool_choice=auto`**.
The YAML files also expose optional sampling controls, seed, penalties, stop
sequences and HTTP timeout/retry policy. Optional `null` values are omitted from
the request. Add a `*.yaml` and select its filename stem as `PROFILE`; no Python
registry needs updating. Effective values and the file hash are recorded.

These are **LLM-call profiles, not graph-access permissions**. Agent-step limits,
dataset size, Neo4j timeout and concurrency are separate benchmark settings.
Temperature zero does not guarantee determinism, and requested reasoning does
not prove how the provider executed it. Changing a profile is a new experimental
treatment, not a retroactive change to archived results.

### Reference Baselines

Published comparison evidence is read from a pinned commit of
[Multi-Agent GraphRAG implementation](https://github.com/PaoloAlbano/multi-agent-graphrag-implementation).
It uses the exact [100 shared QIDs](data/reference_company100_qids.json), not
simply the first 100 current task rows. Original baseline archives remain in
that source repository; derived query re-executions are stored separately here.

The packaged research commands also support baseline execution, checking and
archiving. Their default full-split experiment is not automatically the published
100-QID comparison. Follow the [comparison contributor workflow](docs/multigraphrag-comparison.md#contributor-workflow)
to add compatible baseline evidence or repeat the common-result evaluation.

## Preview or Build the Website

```bash
make docs-serve
```

Open [localhost:8000](http://127.0.0.1:8000). `DOCS_PORT=8001` changes the port;
`make docs-build` builds without starting a server. Source templates, styles
and scripts live in [`docs/site/`](docs/site/); generated output goes to ignored
`build/site/`, both locally and in CI. Rebuild/restart the preview after changes.

Building needs neither Neo4j nor an LLM key. The comparison uses a local checkout
of its pinned external Git source; see [site maintenance](docs/site/README.md).
To enable deployment in a fork, select **Settings > Pages > Source > GitHub Actions**.
The existing [workflow](.github/workflows/docs.yml) handles validation, build and
publication; do not commit generated HTML/JSON or create a separate `gh-pages` branch.

## Experimental HTTP Service

The service exposes graph operations without embedding an LLM. It is a prototype:
**there is no authentication or multi-client handle isolation guarantee**, and
the backend/handle state is currently process-global. Do not expose it directly
to untrusted networks or describe it as production-ready.

With Neo4j connection variables configured, start a loopback-only instance:

```bash
uv run uvicorn agent_native_graph.interfaces.service:app --host 127.0.0.1 --port 8080
```

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Process liveness only; does not verify Neo4j readiness |
| `GET /tools` | Public tool-contract metadata, optionally filtered by design status |
| `POST /tools/call` | Execute an operation, e.g. `{"tool":"schema_overview","args":{}}` |

Schema is discovered from Neo4j when the backend is first needed by a tool call,
not during `/health`. `ANA_SCHEMA_JSON` is an optional explicit schema override;
no Company-specific JSON is required for ordinary service discovery.
`ANA_NEO4J_QUERY_TIMEOUT_S` defaults to 30 seconds.

A [Dockerfile](Dockerfile) is provided for this experimental service, not for
loading datasets or running benchmarks automatically. For a Docker Desktop
local example, configure the URI to reach Neo4j from inside the container:

```bash
make docker-build
docker run --rm -p 127.0.0.1:8080:8080 \
  -e NEO4J_URI=bolt://host.docker.internal:7687 \
  -e NEO4J_USER -e NEO4J_PASSWORD agent-native-graph
```

Adjust the URI for your container network. The `make serve` / `make docker-run`
shortcuts bind more broadly; use the loopback examples above for local-only access.

## Code and Tool Contracts

```text
src/agent_native_graph/
  core/           # backend contracts, tool registry, prompts and handle storage
  domain/         # graph/handle primitives
  tools/          # decorated, executable graph operations
  backends/       # concrete adapters, currently Neo4j
  llm_providers/  # model-call settings and OpenAI-compatible adapter
  profiles/       # editable YAML model-call profiles
  application/    # agent loop, benchmark runner and run metadata
  interfaces/     # CLI and experimental HTTP/MCP transports
  research/       # reproducible preparation, scoring, archive and site commands
```

`Neo4jGraphBackend` implements `AgentGraphBackend`; reusable handle state lives
in `HandleStore`. Tool definitions and parameter annotations live beside the
functions under `tools/`, using `@tool`. The native runner applies the effective
specification/compatibility rules in `core/tool_specs.py`.

```bash
make list-tools
```

This prints decorator-derived names, statuses, access profiles and purpose
metadata. Full effective LLM descriptions and parameter schemas are in the
[live tool reference](https://paoloalbano.github.io/agent-native-graph/#tool-catalog).
The current catalog is not assumed to be the contract of a historical run.

## Tests and Evidence

```bash
make lint
make test
```

Offline tests use a versioned synthetic schema. `make test-backend` opts in to
Neo4j integration tests and requires the prepared Company dataset. Skipped
integration cases are not certified by an offline test pass. See
[reproduction](docs/reproduction.md#tests-and-documentation) for details.

Curated ANA archives contain `manifest.json`, `summary.json`, `failures.jsonl`
and `run.jsonl`; new runs also include sanitized `run-config.json` provenance.
Incomplete diagnostics remain outside the public archive. See the
[results format](results/README.md), [benchmark protocol](docs/benchmark-protocol.md)
and [methodology caveats](docs/methodology-audit.md).

## Paper and Further Reading

The [paper/preprint draft](paper/README.md) is a navigable work in progress,
not a published or peer-reviewed paper. Public documentation includes:

- [ANA approach](docs/agent-native-apis.md)
- [Tool contract](docs/ana-v0-tool-contract.md) and [catalog guide](docs/tool-catalog.md)
- [Company evidence](docs/cypherbench-company-results.md)
- [Comparison protocol](docs/multigraphrag-comparison.md)
- [Repository conventions](docs/repo-hygiene.md)

## License

This project's code is available under the [MIT License](LICENSE). External
datasets and baseline artifacts remain subject to their own licenses.
