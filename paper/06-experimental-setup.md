# 6. Experimental Setup

`ANA-PAPER-EXPERIMENTS`

The study has two separate scopes: full-split ANA behavior and a matched-question
comparison with historical text-to-Cypher traces. Neither scope includes other
CypherBench categories.

## Data

The task set is `graph == "company"` in the test split of the
[CypherBench dataset](https://huggingface.co/datasets/megagonlabs/cypherbench):
347 questions, each with `qid`, `nl_question`, `gold_cypher` and `answer_json`.
The normalized graph is loaded into Neo4j from the Company SimpleKG dump. The
dump hash, task hashes and content fingerprints are retained with the evidence;
the [reproduction guide](../docs/reproduction.md) describes local preparation.

## Compared Approaches

The reported comparison has three approaches: ANA, the reference implementation's
`single` pipeline (called direct text-to-Cypher below), and its `agentic`
multi-agent pipeline. Golden-query execution is a validation control, not a
fourth competing model. Older investigative runners are not additional reported
baselines. The baseline evidence is read from an independent implementation at
commit `72fe7105310c85ebe6b1b3b7d4c6152ddb206393` on branch `llm_calls_recap`:
[pinned source](https://github.com/PaoloAlbano/multi-agent-graphrag-implementation/tree/72fe7105310c85ebe6b1b3b7d4c6152ddb206393).

## Benchmark Protocol

Full-split analysis retains all 347 questions in each of nine ANA runs. The
external comparison uses exactly the 100 QIDs pinned from the reference Company
trace in [reference_company100_qids.json](../data/reference_company100_qids.json).
This set differs from the first 100 local tasks by one question; a numerical
limit of 100 is not a substitute. Runs are paired by model name, temperature and
requested reasoning setting. The repeated GPT-OSS T0/none observations remain
separate and share the corresponding external pair.

For the common metric, saved baseline queries are checked with `EXPLAIN` and
only read queries are executed, with a 30-second transaction timeout, rollback
and a 100,000-row cap. Missing queries, query errors and exceeded caps count as
failures, never partial successes. The graph is fingerprinted against the dump
before evaluation and again afterwards. The selected complete evaluation
contains 100 golden queries and 1,600 baseline-query attempts, plus re-scoring
of ANA's already saved rows. No LLM call is made during this evaluation.

## Baseline Implementations

The reference `single` runner generates Cypher, executes it and interprets the
result. Its code permits retries after errors or empty results, without the
semantic evaluator/entity-verification loop. Thus "direct" does not mean one
LLM call, an unconditionally one-shot query or an identical token budget to ANA.

The reference `agentic` runner generates, executes and evaluates each candidate.
An incorrect candidate receives evaluator feedback; an error/empty branch can
also extract and verify entities and generate correction instructions. A
feedback aggregator informs the next generation, bounded by the configured
iteration limit; an interpreter produces the final textual answer. This is the
behavior of the pinned implementation, not a claim of bit-for-bit reproduction
of the [Multi-Agent GraphRAG paper](https://arxiv.org/abs/2511.08274v1).

ANA receives a fixed native tool catalog and composes operations over handles.
The reported standard treatment uses `overview` schema entry, no optional
planning tools, no wrapper planner, no automatic final fetch and no runner
guardrails that replace the model's choices. Benchmark-only all-page evaluation
can retrieve the rest of a final fetched handle for scoring; those extra pages
are not supplied as additional observations to guide the agent. They cannot
recover rows already omitted by an upstream bounded operation.

## Metrics

The primary metric is **exact-result match against `answer_json`**, not official
CypherBench Execution Accuracy. The implementation normalizes supported values
and compares multisets of rows: row order is ignored, but column order and
duplicate multiplicity matter. Extra answer columns can therefore turn an
otherwise relevant result into a mismatch. This comparator does not assess
natural-language explanation quality or prove correct ordering for ordered tasks.

The common-metric table applies that same comparator to ANA final rows and
re-executed baseline query results. The reference's original LLM-judge verdicts
remain separately available in the site; they do not enter this table. Query
re-execution evaluates retrieval, not the baseline interpreter's final prose.

ANA's `ok` flag means the runner completed its result-return path, not that the
answer is correct or that every tool succeeded. LLM/tool-call means include all
347 tasks, including failures. Historical external logs undercount some calls;
we do not infer cost superiority by comparing them with ANA's runner counters.

Golden-query validation executes all 347 queries but reproduces only 345 stored
answers; the pinned subset reproduces 99/100. The discrepancies concern null
birth-date ordering and remain in both primary denominators. They are not
silently corrected or excluded. [Gold evidence](../results/cypherbench-company/gold-validation.md)
and [metric details](../docs/multigraphrag-comparison.md) identify the cases.

## Default Run Settings

Two model identifiers are observed: `openai/gpt-oss-120b` and
`Qwen/Qwen3.5-27B`. Four YAML profiles cross temperature 0/1 with requested
thinking off/medium. Native tools, `tool_choice=auto`, 16,000 output tokens per
call and 12 agent steps are used; temperature 0 is not a determinism guarantee.
The standard profiles use a 60-second HTTP timeout, at most three outer transport
attempts and a 30-second wait before rate-limit retries. Medium-thinking length
responses permit a low-effort retry, whose use is recorded. Requested thinking
does not prove what a serving backend executed internally.

The five October 27-28 runs have sanitized launch `run-config.json` files with
input, source-tree, prompt, tool and profile hashes. They use concurrency 3;
their source-tree identities need not match across different launch dates.
The three new Qwen identities match each other. The four older runs have less
complete provenance and concurrency 2-5. A declared Git commit does not identify
uncommitted launch code; missing historical fields are not reconstructed.
Provider/model revision, runtime effects and some generation conditions cannot
be equated with the historical baselines.

The [run standard](../docs/run-standard.md) and
[comparison protocol](../docs/multigraphrag-comparison.md) provide executable
commands and full artifact paths. The current demo HTTP authentication/session
layer is not in the measured benchmark path, which calls the backend directly.

## Prospective Matched-Condition Study

The [controlled Company design](../docs/controlled-company-protocol.md) specifies
a future matched-condition study, not additional results. It proposes shared
model-call settings, canonical schema facts, generation budgets, safe candidate
execution, counterbalanced replicas and complete accounting across ANA and
retrieval-only reference variants. The latter omit prose interpretation because
the primary outcome scores retrieved rows; this is an explicit variant, not a
relabeling of the historical baseline. The implementation audit identifies
unmet gates, and no inference is authorized by publishing the design.

Matching these conditions compares whole systems, not API shape alone. A later
same-controller vocabulary ablation is specified separately. Neither study
turns development-exposed Company questions into a fresh holdout or changes the
evidence already reported in Section 7.
