# Benchmark Protocol

This document defines the current reproducible benchmark protocol for the
Agent-Native Graph research prototype.

This document describes the current reproducible treatment. A separate
[prospective matched-condition design](controlled-company-protocol.md) audits
what must change before a new controlled comparison; it is not implemented or
an instruction to reinterpret the historical runs.

For new full ANA runs, use [Contribute a Company Run](run-standard.md): launch
with `make benchmark`, then archive the printed output with
`make archive-result OUT=...`. Checks and metadata capture are automatic.

## Benchmark Scope

- Dataset: CypherBench.
- Split: `test`.
- Graph/category field: `graph == "company"`.
- Current full Company size: 347 examples.
- New benchmark runs default to all 347 Company examples; a smaller limit
  must be requested explicitly for diagnostics.
- External comparison: the exact 100 QIDs from the published
  Multi-Agent GraphRAG Company trace, captured in
  `data/reference_company100_qids.json` with checkout commit and QID hash.
- Task file: `data/tasks_company_test.jsonl`.
- Graph dump for Neo4j loading: `downloads/company_simplekg.json`.
- Gold validation: `results/cypherbench-company/gold-validation.jsonl` and
  `results/cypherbench-company/gold-validation.md`.

The Company task file is regenerated from Hugging Face with:

```bash
make prepare-company-tasks
```

The full Company size can be checked directly against Hugging Face:

```bash
uv run --with datasets python - <<'PY'
from collections import Counter
from datasets import load_dataset

ds = load_dataset("megagonlabs/cypherbench", split="test")
counts = Counter(str(row.get("graph")) for row in ds)
print(counts["company"])
PY
```

Expected output:

```text
347
```

## Graph Backend

- Primary backend for ANA runs: Neo4j.
- Default URI: `bolt://127.0.0.1:7687`.
- Use a dedicated Company database and verify its content before comparable
  batches; the standard launcher checks content and does not mutate the graph.
- Loader target: `make load-company`; it clears the target database. Use only
  when explicitly preparing a disposable database, never as an automatic preflight.
- On Neo4j 2026.05.0, all 347 gold queries execute, but two do not reproduce
  `answer_json` because `date_of_birth` is null for the selected entities.
  Keep all 347 in primary scores. Discrepancies remain documented for future
  investigation; do not silently remove or repair them.

## Agent-Native Run Profile

All comparable ANA runs should keep these settings fixed unless the experiment
explicitly studies that variable:

- tool calling: native OpenAI/vLLM-compatible tool calls;
- `tool_choice`: `auto`;
- `max_tokens`: `16000`;
- `max_steps`: `12`;
- `temperature`: `0` for the low-temperature comparison (not guaranteed deterministic);
- alternate profile: `temperature=1` with reasoning/thinking enabled at
  `medium` effort;
- default concurrency: `3`;
- lower concurrency for rate-limited models;
- query timeout: 30 seconds.

Concurrency is recorded as an operational variable; a difference alone does
not invalidate quality comparisons. Investigate retries, provider behavior and
state isolation before attributing score changes to it.

LLM call profiles are defined in `src/agent_native_graph/profiles/*.yaml`,
not in a Python lookup table. The runner validates their values and records
both effective parameters and the selected file hash. See [the run guide](run-standard.md)
for editing or adding profiles. Existing archives are never reinterpreted using
the current YAML contents.
The files include output-token budget, sampling, thinking, tool choice and HTTP
timeout/retry policy. The reference profiles keep 16k/auto and existing retry
defaults; changing a field defines a different experimental treatment. Model,
gateway credentials and benchmark controls are not part of these YAML files.
The supplied matrix crosses temperature 0/1 with requested thinking off/medium:
`temp0-none`, `temp0-medium`, `temp1-none`, `temp1-medium`. All other parameters
are identical so temperature and thinking can be studied independently.

## Output Policy

Raw benchmark JSONL files are temporary and should not live inside the
repository. The Makefile writes them to:

```text
/tmp/agent-native-graph-runs/
```

Only complete, curated runs should be archived into:

```text
results/cypherbench-company/<suite>/runs/<run_id>/
```

Only the `full` suite (`n=347`) is curated as ANA runs under `results/`. Complete
derived query re-executions have a separate `query-reexecution/` archive and are
not LLM runs. Diagnostic suites
can be generated locally; `archive-result` sends them to the ignored
`.local-results/` directory by default.

Each archived run contains:

- `manifest.json`: model, profile, benchmark, limit, hash, and git commit;
- `summary.json`: aggregate scores and usage metrics;
- `failures.jsonl`: non-matching examples for analysis;
- `run.jsonl`: complete per-example records.

New standard archives also include `run-config.json`: saved treatment, effective
prompt/tool/code/environment fingerprints and input hashes. Historical four-file
archives remain unchanged. Never infer missing historical fingerprints.

The full-run index is regenerated by `archive-result`:

```text
results/cypherbench-company/index.json
```

## Reference ANA Commands

Full low-temperature run (not guaranteed deterministic):

```bash
make benchmark MODEL=openai/gpt-oss-120b PROFILE=temp0-none
```

Archive it:

```bash
make archive-result OUT=/tmp/agent-native-graph-runs/the-printed-file.jsonl
```

Full high-temperature reasoning run:

```bash
make benchmark MODEL=openai/gpt-oss-120b PROFILE=temp1-medium
```

## External Comparison Protocol

ANA's 347-question full-split results are for behavioral analysis. The
comparison to the
[Multi-Agent GraphRAG implementation](https://github.com/PaoloAlbano/multi-agent-graphrag-implementation)
uses its Company run's exact 100-QID set. The snapshot in
`data/reference_company100_qids.json` records the source trace, checkout
commit, and QID hash. It differs from the first 100 tasks in the current
Company file by one QID, so `LIMIT=100` alone does not select the same sample.

The reference repository's historical Company runs use an LLM judge or a
value-overlap fallback. Neither is ANA's exact row-wise `answer_json` metric.
Do not interpret those published percentages as a homogeneous comparison.
The separately labelled common query-result metric re-executes saved baseline
Cypher on the verified ANA graph and uses the same exact comparator on returned
rows. It does not re-evaluate the baseline's final prose answer. Preserve
per-question outcomes and source commits. See the
[comparison page](multigraphrag-comparison.md) for the reporting contract.

The separate `baseline-run` research command defaults to 347 Company questions.
Its output is not a replacement for the reference repository's pinned 100-QID
traces. Use the comparison guide's source and QID contract for published
head-to-head evidence rather than substituting a different sample.
