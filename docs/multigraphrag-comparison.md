# Multi-Agent GraphRAG Comparison (100 Questions)

The static `comparison.html` section presents ANA alongside the
[Multi-Agent GraphRAG implementation](https://github.com/PaoloAlbano/multi-agent-graphrag-implementation)
on the **same 100 Company questions**. It is separate from the
[347-question ANA behavior analysis](cypherbench-company-results.md).

The QID set is pinned in
[`data/reference_company100_qids.json`](../data/reference_company100_qids.json)
with the source trace, checkout commit, and QID hash. It is not simply the
first 100 rows of the current CypherBench task file.

## Before Publishing Scores

- Resolve identical QIDs, graph snapshot, model profile, and evaluation method
  for both approaches. The reference repository's existing judge score is not
  interchangeable with ANA's exact `answer_json` match.
- Identify the reference run and commit for each model/profile; record how its
  final answers are normalized and scored under a common metric.
- Report per-question outcomes, aggregate accuracy, call and token budgets,
  uncertainty across replicates, and important failure categories.
- Link each table to its exact source runs or an immutable artifact. Do not
  promote the old 347-question paired reports as the 100-question comparison.

The common query-result metric is now published separately from the original
LLM-judge scores, using the saved re-execution evidence described below. This
100-question experiment is separate from the full-split 347-question ANA analysis.

## Implemented Evidence Explorer

`docs/site/comparison-source.json` pins branch `llm_calls_recap` and commit
`72fe7105310c85ebe6b1b3b7d4c6152ddb206393`. Builds read `git show COMMIT:path`,
not mutable working-tree files. Generated provenance records the QID-set hash
and SHA-256 of source artifacts. CI checks out that exact revision.

```bash
make docs-build REFERENCE_REPO=../multigraphrag
make docs-serve REFERENCE_REPO=../multigraphrag
```

For a fresh checkout of the reference source:

```bash
git clone --branch llm_calls_recap https://github.com/PaoloAlbano/multi-agent-graphrag-implementation.git ../multigraphrag
```

Only matching model, temperature and requested reasoning profiles are paired.
Build validation rejects incomplete/duplicate QID sets, mismatched questions or
gold queries, invalid QID hashes, mixed scopes, and inconsistent summary counts.
Without the external source, plain `build-docs` renders an explicit unavailable
page rather than inventing or retaining comparison scores.

The overview links to one static page per ANA run and then one page per question.
Only a question page fetches its evidence. It shows ANA tool arguments/results
and external generated Cypher, textual answer, verdict, logged prompts and
responses. Original and fixed-judge logs are separate from pipeline calls.

### What the Percentages Mean

The website deliberately keeps two tables separate:

| Table | ANA | Direct Cypher / multi-agent |
| --- | --- | --- |
| Original source metrics | Exact match of archived result rows against benchmark answers | Original LLM-judge verdict on the final textual answer |
| Common exact-result metric | Same archived result rows, checked with the exact comparator | Saved Cypher re-executed on the verified graph and checked with the same exact comparator |

For example, expected rows `[["Alice"]]` do not exactly match returned rows
`[["Alice", 2009]]`. A judge might still accept a textual answer containing
both facts. Neither score replaces the other. The common metric measures query
results, not the interpreter's final answer; it makes the evaluator consistent,
not every historical experimental condition identical.

- ANA retains `matches_answer_json`, restricted to the pinned 100 questions.
- External percentages retain `correct` under the source LLM judge, not ANA's
  exact-answer comparator. No gain, delta or cross-method ranking is calculated.
- Token budgets, concurrency, dates, schema prompts and workflows differ.
- External manifests name `simplekg` but do not establish graph snapshot hash
  equivalence. Graph equivalence is not assumed.
- `single` means the direct text-to-Cypher pipeline, including interpretation;
  it does not necessarily mean one LLM call.
- External logs undercount some evaluator calls. Counts are explicitly labeled
  **logged calls**, not total calls, and not equated with ANA runner counters.
- Repeated ANA runs remain separate against the same external baselines.

### Saved Query Re-execution

The selected comparison is
`results/cypherbench-company/query-reexecution/current-ana-matrix/`.
It covers all twelve current ANA full runs and twenty-four matched historical
baseline runs on the pinned 100 QIDs. The original baseline evaluation contains
100 golden-query executions and 2,400 baseline-query attempts.

The current refresh re-scores the new ANA saved rows and **reuses unchanged**
gold and baseline execution records. Its `ana_refresh` field identifies the
original evaluation manifest, checksum and execution date. Baseline manifests,
trace hashes, row payloads, execution errors and scores are not regenerated or
rewritten. This refresh performs no LLM calls and no database queries. The
storage index reuses the existing content-addressed objects.

The original saved-query evaluation checked the full graph against the dataset
before execution and again afterwards. Queries were checked with EXPLAIN,
executed in read mode with a 30-second transaction timeout and rolled back.
The row limit was 100,000; errors and exceeded limits count as failures, never
partial successes. Queries were not repaired. Current ANA graph-integrity
reports independently verify the same graph content. The common comparator
ignores row order but preserves duplicate multiplicity and column order.

99/100 golden queries reproduce expected rows. QID
`8536d1ef-cb04-4bc6-8f9a-4aff1279dc0f` returns a different youngest board
member. All 100 cases remain in the primary denominator; diagnostic 99-case
counts do not replace it.

| Observation | ANA / 100 | Direct / 100 | Multi-agent / 100 |
| --- | ---: | ---: | ---: |
| G-0M | 89/100 | 63/100 | 68/100 |
| G-0N | 90/100 | 66/100 | 65/100 |
| G-1M | 88/100 | 63/100 | 68/100 |
| G-1N | 89/100 | 61/100 | 70/100 |
| Q-0M | 89/100 | 64/100 | 67/100 |
| Q-0N | 84/100 | 47/100 | 48/100 |
| Q-1M | 82/100 | 59/100 | 62/100 |
| Q-1N | 79/100 | 40/100 | 50/100 |
| S-0M | 71/100 | 64/100 | 60/100 |
| S-0N | 67/100 | 66/100 | 67/100 |
| S-1M | 65/100 | 63/100 | 66/100 |
| S-1N | 65/100 | 59/100 | 68/100 |

Observation prefixes denote GPT-OSS-120B (G), GPT-OSS-20B (S) and Qwen3.5-27B
(Q); suffixes denote temperature and requested reasoning none (N) or medium
(M). Linked full-run manifests and call means are in the
[paper results](../paper/07-results.md). These are pinned-subset scores, not
the 347-question ANA scores.

All current ANA runs use shared graph/schema preflight and bounded-v1 result
handling. The external generations remain historical and did not use that
treatment. Reusing their verified query executions aligns retrieval evaluation,
not generation prompts, budgets or served model revisions. Original source
LLM-judge scores remain a separate website table. No controlled causal claim
or new full-split baseline inference follows from this comparison.

Baseline call logs remain incomplete and expose no uniform token-usage totals.
The site reports logged baseline calls separately from ANA request counters;
unknown token costs must not be represented as zero or used for efficiency claims.

### GPT-OSS-20B Request Observability

All means below use the same pinned 100 questions, including failures. ANA
tokens are the sum of observed prompt plus completion usage from settled
request accounting, including usage observed before a parsing failure. They
are not billing estimates and may omit usage from attempts without a response.
Baseline logged calls exclude the separate judge logs and may omit internal
evaluator calls, so they cannot support a total-cost ranking.

| Profile | ANA mean LLM calls | ANA mean tool calls | Direct mean logged calls | Multi-agent mean logged calls | ANA observed total tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| T0/none | 5.55 | 5.52 | 2.40 | 6.60 | 13117637 |
| T0/medium | 5.36 | 5.33 | 2.50 | 7.08 | 12633614 |
| T1/none | 5.51 | 5.44 | 2.43 | 6.42 | 13103556 |
| T1/medium | 5.44 | 5.35 | 2.40 | 6.58 | 13029193 |

Baseline token totals and comparable tool-call counters are unavailable, not
zero. Source logs are pinned with the same commit as the accuracy table; ANA
usage is in each full archive's per-question `request_accounting` field.

To repeat without LLM calls, with the Company graph already loaded:

```bash
make reexecute-reference REFERENCE_REPO=../multigraphrag \
  REEXECUTION_OUT=/tmp/ana-query-reexecution-new
```

The output directory must not exist. Completed evidence can be selected through
`execution_evaluation` in `docs/site/comparison-source.json`. Builds reject
incomplete evaluations and mismatched checksums, source traces, or QID coverage.

Completed evaluations are sealed automatically into shared compact storage:
`storage.json` plus content-addressed gzip packs in the parent `_objects/`.
The original manifest/checksums and every logical JSONL byte are preserved;
the site reads both compact and historical standalone formats. See
[the evidence layout and export command](../results/README.md) before moving
an evaluation between archives. The module's `--storage legacy` option retains
standalone JSONL output when needed. Compaction does not execute queries or models.

No original baseline archive is added to `results/`. External evidence remains sourced
from its Git repository; sources under `docs/site/` generate the presentation
under ignored `build/site/` (or the clean CI output directory). Large JSON disclosures are lazy
and bounded, while complete generated records remain downloadable.

## Contributor Workflow

### Reproduce the Published Comparison

1. Install dependencies with `make sync` and clone the reference repository as
   above. The commit in `docs/site/comparison-source.json` must exist locally;
   the evaluator reads committed Git objects, not uncommitted baseline files.
2. Obtain the Company graph following [reproduction.md](reproduction.md).
   Use a dedicated Neo4j database with that graph already loaded. The evaluator
   does not load, clear or repair it: a graph-content mismatch aborts evaluation.
   **Do not run `make load-company` on a database you want to preserve:** that
   command clears the database before loading.
3. From this repository's root, run the following with a new output directory:

   ```bash
   make reexecute-reference REFERENCE_REPO=../multigraphrag \
     GRAPH=downloads/company_simplekg.json \
     REEXECUTION_OUT=results/cypherbench-company/query-reexecution/my-evaluation
   ```

   Override `NEO4J_URI`, `NEO4J_USER` and `NEO4J_PASSWORD` as needed; never commit
   credentials. No inference endpoint or API key is required. To override the
   30-second timeout or database name, use the module CLI (`--help`).
4. Check `manifest.json`: it must say `status: complete`. Inspect golden-query
   discrepancies, query failures and coverage before interpreting the scores.
   A failed or interrupted output is diagnostic evidence, not publishable data;
   preserve it locally and use a fresh directory for another attempt.
5. Set `execution_evaluation` in `docs/site/comparison-source.json` to the new
   repository-relative directory and run `make docs-build`. Existing evaluation
   folders are immutable evidence: do not overwrite them or manually edit scores.
6. Commit the complete evaluation directory, referenced `_objects/` packs and
   updated source configuration. Include `manifest.json` and `storage.json`
   together with the packs, not only summary scores. For legacy output, include
   all JSONL files with the manifest instead.
   Do not commit the downloaded graph, credentials, or generated website files.
   The pull-request Action validates/builds; merge to `main` publishes Pages.

### Compare New Model Runs

Add a complete 347-question ANA archive under `full/runs/`; the website selects
the pinned 100 shared QIDs. Generate and commit matching Company `single` and
`agentic` traces in the external repository using its own harness. They must
cover those exact QIDs, question texts and golden queries, with matching model,
temperature and requested reasoning profile. Keep the external layout and
`run.json` / `trace.jsonl` contracts used by the current importer.

Update the pinned external commit in `comparison-source.json`, then repeat the
evaluation into a new folder. The current re-execution command requires a pair
of external baselines for **every ANA profile present in the local archive**;
it does not yet accept a per-profile selector. It also requires all ANA archives
to reference the same graph-file hash. Do not silently drop unmatched profiles
or substitute a different QID set to make a comparison pass.

Adding an ANA run alone is still supported: it appears in the ANA section,
while missing baselines or pending common-metric validation are explicitly
reported in the comparison section. The static build never launches models,
Neo4j, or a new evaluation automatically.
