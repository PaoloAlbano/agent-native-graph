# Contribute a Company Run

## Setup Once

```bash
make sync
```

Prepare Company tasks, the graph and schema using [reproduction.md](reproduction.md).
Use a dedicated Neo4j database. **`make load-company` clears it**; the benchmark
only checks the graph and never reloads it automatically.

Set `API_KEY` or `API_KEY_FILE`, plus your Neo4j connection variables. Set
`BASE_URL` for a private OpenAI-compatible gateway; the default is OpenRouter.
Never commit keys, private endpoints or raw local metadata.

## Run

```bash
make benchmark MODEL=Qwen/Qwen3.5-27B PROFILE=temp0-none
```

The supplied profiles form a 2 x 2 matrix; all other call settings are equal:

| Temperature | Thinking off (`none`) | Thinking on, effort `medium` |
| --- | --- | --- |
| 0 | `temp0-none` | `temp0-medium` |
| 1 | `temp1-none` | `temp1-medium` |

Thinking settings are requests to the provider. Temperature 0 does not guarantee
determinism. `CONCURRENCY=3` is the default and can be overridden.

Profiles are editable YAML files in `src/agent_native_graph/profiles/`, shipped
with the installed package. They configure LLM calls, independently of the
model name. For example, the main fields of `temp1-medium.yaml` are:

```yaml
temperature: 1.0
max_tokens: 16000
enable_thinking: true
thinking_effort: medium
tool_choice: auto
timeout_s: 60.0
max_attempts: 3
rate_limit_retry_s: 30.0
```

Add another `*.yaml` in that folder and select its filename without the extension:
`PROFILE=my-profile`. No Python registry needs updating. The shipped YAML files
list all supported fields explicitly; omitted fields use `LLMCallSettings`
defaults, and the full effective settings are always saved in run metadata.

| Fields | Meaning |
| --- | --- |
| `temperature`, `max_tokens` | Generation randomness and per-call output-token budget |
| `top_p`, `seed`, `presence_penalty`, `frequency_penalty`, `stop` | Optional generation controls; `null` omits them from the request |
| `enable_thinking`, `thinking_effort` | Thinking request and `null`/low/medium/high effort; effort must be null when thinking is off |
| `retry_low_effort_on_length` | Whether to retry a medium/high-effort length-truncated response once at low effort |
| `tool_choice` | Native tool selection: auto, required or none |
| `timeout_s`, `max_attempts`, `retry_base_s`, `rate_limit_retry_s` | Client-side HTTP timeout, attempt limit, base retry delay and 429 wait |

Generation options depend on the model/provider; leave optional ones null to
retain server defaults. `max_attempts` limits the outer HTTP retry loop; the
optional low-effort length retry is an additional request within an attempt.
The supplied profiles retain 16k tokens and auto tool choice, but another YAML
can explicitly change them. Unknown fields and invalid values are rejected.

Model name, endpoint and credentials remain outside shared profiles. Dataset
size, maximum agent steps, Neo4j timeout and concurrency are benchmark settings,
not LLM-call settings. Names are conventions; archived values show what was used
even if someone later edits a file with the same name. A YAML profile takes
precedence over direct generation flags and the HTTP environment defaults;
without a profile, the diagnostic CLI continues to use those defaults.

The runner automatically checks inputs, saves the actual settings, verifies
Neo4j content against the graph file, and launches all **347 Company questions**.
It prints the output path, which is generated uniquely under
`/tmp/agent-native-graph-runs/`. Override `RUN_DIR` for another directory, or
`OUT=/tmp/my-run.jsonl` to choose a specific new file. It never overwrites one.

There are no separate prepare/check/start commands. To check inputs without
LLM or Neo4j calls, add `CHECK_ONLY=1`; this still saves the metadata. Use a new
output for the real run, or the resume workflow below for that checked output.

## Archive

Use the output path printed by the benchmark:

```bash
make archive-result OUT=/tmp/agent-native-graph-runs/the-printed-file.jsonl
```

No model, temperature or concurrency flags are needed: the archiver reads the
saved settings, checks all QIDs and task contents, and preserves the original.
It does not contact Neo4j or an LLM, re-hash current code, or need the original
input files. Archiving after a code/docs update is supported. Supplying a
contradictory model/profile to the direct archive CLI is rejected.

Commit the complete generated archive under
`results/cypherbench-company/full/runs/<run_id>/`, including `run-config.json`,
and the refreshed index. Review errors/transcripts for sensitive content first.
Do not commit the temporary raw output or its local `.config.json` sidecar.
The PR Action validates/builds; merging to `main` updates GitHub Pages.

## Resume and Replicas

Repeat the original benchmark command with its original settings and output:

```bash
make benchmark MODEL=Qwen/Qwen3.5-27B PROFILE=temp0-none \
  OUT=/tmp/agent-native-graph-runs/the-printed-file.jsonl RESUME=1
```

Keep the original concurrency, inputs, endpoint and executable environment.
Resume checks the recorded configuration and existing rows, then runs only
missing QIDs. Completed failures are not silently retried. Metadata-less legacy
outputs cannot be resumed by guessing their provenance. A truncated JSONL line
fails explicitly: preserve the original before diagnosing it locally.

To make a new independent replica, run again without `OUT` or `RESUME`.
Concurrency differences are recorded, not automatically deemed quality failures.

An exclusive `.lock` permits one writer per output. After a hard kill, verify
the recorded process is no longer running before removing a stale lock. The
archiver refuses an active/locked run; it never clears a lock automatically.

## What Is Recorded

One local `<output-stem>.config.json` contains settings, input hashes/paths,
effective prompt/tool/source hashes, lockfile, Python/client-library versions,
retry settings and the launch commit. Endpoint identities are hashes, not their
addresses; credentials are not recorded. Resume verifies this metadata against
the current treatment. A docs-only commit does not invalidate matching code.
The selected YAML's SHA-256 is also saved, so editing it blocks a mixed-profile
resume. Archiving still uses the saved values/hash even if the YAML was changed
or removed afterwards.

The archived `run-config.json` is a public projection without local paths or
endpoint bindings; its checksum is in `manifest.json`. Historical four-file
archives remain unchanged; new runs have that fifth provenance file.

The shipped profiles use `tool_choice=auto` and 16,000 tokens. Company runs use
native tools, schema entry `overview`, 12 steps and a 30-second Neo4j query
timeout, independently of the LLM HTTP timeout in YAML. Optional planning tools,
wrapper planning, auto-fetch-on-done and runner guardrails are off. Benchmark
evaluation collects all final pages; this is not unbounded service output.
The default provider retry policy is retained, including the recorded
low-effort retry after a medium-thinking `length` response; YAML can change it.
Actual served model
versions/reasoning policies may be unknown; requested settings do not prove them.

For advanced diagnostics use `benchmark-neo4j --help` directly, without a fixed
profile. These controls are not another orchestration layer. The implementation
is the existing runner, the existing archiver and shared metadata helpers in
`application/run_config.py`; there is no command-rebuilding subprocess wrapper.

See [benchmark-protocol.md](benchmark-protocol.md) for scoring and
[multigraphrag-comparison.md](multigraphrag-comparison.md) for the separate
100-QID baseline comparison. A complete preflight graph check is not a database
snapshot held across the benchmark: keep the graph read-only during the run.
