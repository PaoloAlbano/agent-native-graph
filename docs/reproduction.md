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
- API key env: `API_KEY`
- API key file option: `--api-key-file /tmp/grapharrow-agent-key`

## Prepare/load data

```bash
make load-company
```

Equivalent explicit command:

```bash
uv run python scripts/load_simplekg_neo4j.py \
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
  --out results/agent_tools_first100_gpt_oss_120b_temp0.jsonl \
  --limit 100 \
  --native-tools \
  --model openai/gpt-oss-120b \
  --api-key-file /tmp/grapharrow-agent-key \
  --max-tokens 16000 \
  --max-steps 12 \
  --concurrency 3
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
  --out results/agent_tools_first100_gpt_oss_120b_temp1_reasoning.jsonl \
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

## Evaluate

```bash
make evaluate
```

Equivalent explicit command:

```bash
uv run python scripts/evaluate_run.py --run results/agent_tools_first100_gpt_oss_120b_temp0.jsonl
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
make benchmark MODEL=Qwen/Qwen3.6-27B LIMIT=100 CONCURRENCY=1 OUT=results/qwen36_first100.jsonl
make evaluate OUT=results/qwen36_first100.jsonl
```
