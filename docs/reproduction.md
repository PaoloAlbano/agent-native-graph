# Reproduction

Install the project with `uv`:

```bash
uv sync --extra dev --extra service
```

Or use the Makefile:

```bash
make sync
```


## Defaults used in recent investigation runs

- `max_tokens`: 16000
- `max_steps`: 12
- deterministic profile: `temperature=0`
- realistic profile: `temperature=1`, reasoning/thinking enabled, effort `medium`
- default concurrency: 3, lowered for rate-limited models and raised only when stable
- raw output directory: `/tmp/agent-native-graph-runs`
- use `RESUME=1` with the same `OUT` path to continue an interrupted ANA or
  baseline run; archive only after all 347 QIDs are present
- API key env: `API_KEY`
- API key file option: `--api-key-file /tmp/grapharrow-agent-key`

The benchmark protocol is specified in `docs/benchmark-protocol.md`.

The reference baseline is run from this repository using the sibling
`multigraphrag` checkout. After `make load-company` and `make export-schema`, validate the shared task
order and graph dump with `make baseline-check`. Then run `make baseline-run`
once with `BASELINE_MODE=direct` and once with `BASELINE_MODE=agentic`, setting
`MODEL`, `TEMPERATURE`, `REASONING`, `BASE_URL`, `API_KEY_FILE`, and unique
`BASELINE_OUT` values. `RESUME=1` continues an interrupted output file.
`make baseline-archive` verifies the complete qid set and stores the reference
commit, graph hash, task hash, per-question rows and LLM call logs. The
historical archived baseline runs have 347 questions; they are not the planned
100-question external comparison. See the distinct
[ANA full-split analysis](cypherbench-company-results.md) and
[external comparison protocol](multigraphrag-comparison.md). A new static
presentation will be built after that comparison is scored consistently.

## Prepare/load data

Build the CypherBench Company test tasks from Hugging Face:

```bash
make prepare-company-tasks
```

Equivalent explicit command:

```bash
uv run --with datasets --with pandas --with pyarrow \
  agent-native-graph prepare-company-tasks \
  --from-hf \
  --graph company \
  --split test \
  --out data/tasks_company_test.jsonl
```

The current Neo4j loader expects a local SimpleKG graph dump at:

```text
downloads/company_simplekg.json
```

That raw graph file is intentionally not versioned in this repository. Place it
there before loading Neo4j.

```bash
make load-company
```

Generate the benchmark's local schema JSON and prompt from Neo4j:

```bash
make export-schema
```

Equivalent explicit command:

```bash
uv run agent-native-graph load-company \
  --neo4j-uri bolt://127.0.0.1:7687 \
  --neo4j-user neo4j \
  --neo4j-password password \
  --graph downloads/company_simplekg.json \
  --clear \
  --batch-size 2000
```

## Run agent-native tools

```bash
make benchmark
```

Equivalent explicit command:

```bash
uv run agent-native-graph benchmark-neo4j \
  --tasks data/tasks_company_test.jsonl \
  --schema-json data/company_schema.json \
  --out /tmp/agent-native-graph-runs/agent_tools_first100_gpt_oss_120b_temp0.jsonl \
  --limit 100 \
  --native-tools \
  --model openai/gpt-oss-120b \
  --api-key-file /tmp/grapharrow-agent-key \
  --max-tokens 16000 \
  --max-steps 12 \
  --concurrency 3
```

By convention, raw benchmark outputs are written outside the repository first,
usually under `/tmp/agent-native-graph-runs`. Promote only complete, curated
runs into `results/` with `make archive-result`.

## Run the full Company split

The current CypherBench Company test slice has 347 examples in this repository.

```bash
make benchmark-full \
  MODEL=openai/gpt-oss-120b \
  LIMIT=347 \
  CONCURRENCY=5 \
  OUT=/tmp/agent-native-graph-runs/company_gpt_oss_120b_temp0_reasoning_none_n347.jsonl
```

Archive the completed run:

```bash
make archive-result \
  MODEL=openai/gpt-oss-120b \
  LIMIT=347 \
  TEMPERATURE=0 \
  REASONING=none \
  CONCURRENCY=5 \
  OUT=/tmp/agent-native-graph-runs/company_gpt_oss_120b_temp0_reasoning_none_n347.jsonl
```

This writes:

```text
results/cypherbench-company/full/runs/<run_id>/
  manifest.json
  summary.json
  failures.jsonl
  run.jsonl
```

and refreshes:

```text
results/cypherbench-company/index.json
```

## Run temp 1 + reasoning

```bash
make benchmark-temp1
```

Equivalent explicit command:

```bash
uv run agent-native-graph benchmark-neo4j \
  --tasks data/tasks_company_test.jsonl \
  --schema-json data/company_schema.json \
  --out /tmp/agent-native-graph-runs/agent_tools_first100_gpt_oss_120b_temp1_reasoning.jsonl \
  --limit 100 \
  --native-tools \
  --model openai/gpt-oss-120b \
  --api-key-file /tmp/grapharrow-agent-key \
  --temperature 1 \
  --enable-thinking \
  --thinking-effort medium \
  --max-tokens 16000 \
  --max-steps 12 \
  --concurrency 3
```

The same profile can be run through the generic target:

```bash
make benchmark-full \
  MODEL=openai/gpt-oss-120b \
  LIMIT=347 \
  TEMPERATURE=1 \
  THINKING=1 \
  THINKING_EFFORT=medium \
  REASONING=medium \
  CONCURRENCY=5 \
  OUT=/tmp/agent-native-graph-runs/company_gpt_oss_120b_temp1_reasoning_medium_n347.jsonl
```

Archive with the same profile metadata:

```bash
make archive-result \
  MODEL=openai/gpt-oss-120b \
  LIMIT=347 \
  TEMPERATURE=1 \
  REASONING=medium \
  CONCURRENCY=5 \
  OUT=/tmp/agent-native-graph-runs/company_gpt_oss_120b_temp1_reasoning_medium_n347.jsonl
```

## Test another model

Override `MODEL`, `OUT`, and often `CONCURRENCY`. Keep all other settings fixed
when comparing models.

```bash
make benchmark-full \
  MODEL=Qwen/Qwen3.6-27B \
  LIMIT=347 \
  CONCURRENCY=1 \
  OUT=/tmp/agent-native-graph-runs/company_qwen3_6_27b_temp0_reasoning_none_n347.jsonl
```

For providers that rate-limit native tool calls, lower `CONCURRENCY` first
instead of changing the benchmark protocol.

## Evaluate

```bash
make evaluate
```

Equivalent explicit command:

```bash
uv run agent-native-graph evaluate-run --run /tmp/agent-native-graph-runs/agent_tools_first100_gpt_oss_120b_temp0.jsonl
```

## Unit tests

```bash
make test
```

Equivalent explicit commands:

```bash
uv run pytest tests/test_agent_tool_backend.py -q
uv run pytest tests/test_tool_quality_analysis.py -q
```

## Useful overrides

Make targets use variables that can be overridden from the command line:

```bash
make benchmark MODEL=Qwen/Qwen3.6-27B LIMIT=100 CONCURRENCY=1 OUT=/tmp/agent-native-graph-runs/qwen36_first100.jsonl
make evaluate OUT=/tmp/agent-native-graph-runs/qwen36_first100.jsonl
```

## Inspect curated results

Machine-readable metadata lives in:

```text
results/cypherbench-company/index.json
```

Each archived run includes:

- `manifest.json`: model, provider, temperature, reasoning, tool mode, limit,
  hash, and git commit.
- `summary.json`: accuracy, executable rate, tool/LLM calls, token usage, and
  failure class counts.
- `failures.jsonl`: non-matching rows with `failure_category` for analysis.
- `run.jsonl`: complete per-task transcript and outputs.
