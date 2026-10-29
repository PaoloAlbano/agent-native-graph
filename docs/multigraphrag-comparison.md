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

The currently selected evaluation,
`results/cypherbench-company/query-reexecution/2026-10-29-three-model-matrix/`, contains
a manifest, 100 golden-query executions and twenty-four files of 100 baseline-query
executions. It covers all thirteen current ANA full runs, including all four
GPT-OSS-20B profiles. Previous evaluations, including `2026-10-28-qwen-matrix/`,
remain unchanged as historical evidence. All sixteen previously evaluated
baseline scores were reproduced; eight newly evaluated baselines complete the
GPT-OSS-20B matrix. In total, 2,500 saved queries were attempted with
no model calls. Missing future comparisons are still explicitly marked rather
than silently borrowing another profile's baseline.
It is a derived evaluation, not a new LLM run or a copy of the baseline archive.
The source commit, trace checksums, QID hash, ANA run hashes, comparator checksum
and graph-content fingerprints are recorded. Nodes, labels, properties, edge
types, endpoints and multiplicities are checked against the dataset file before
execution; the database fingerprint is checked again afterwards.

All queries are checked with EXPLAIN, executed in read mode with a 30-second
transaction timeout and rolled back. The row limit is 100,000; errors and
exceeded limits are failures, never partial successes. Queries are not repaired.
ANA archived rows and baseline re-executed rows use the same exact comparator:
row order is ignored, but duplicates and column order matter. Source judge
verdicts remain separate. No LLM or database calls happen during the site build.

99/100 golden queries reproduce the expected rows. QID
`8536d1ef-cb04-4bc6-8f9a-4aff1279dc0f` returns a different youngest board member;
all 100 cases remain included in the published scores. This is a known
golden-answer discrepancy. The saved manifest retains the
diagnostic 99-case counts, but they are not the site's comparison metric.
Re-execution verifies the current common graph, not the undocumented historical
graph used to generate the external queries. This is query-result correctness,
not end-to-end answer judging or a controlled causal estimate of improvement.

For the two October 27 ANA runs, the common metric on the pinned 100 QIDs is:

| GPT-OSS-120B requested profile | ANA exact | Direct Cypher re-executed exact | Multi-agent re-executed exact |
| --- | ---: | ---: | ---: |
| temp 0, reasoning medium | 86/100 | 63/100 | 68/100 |
| temp 1, reasoning off | 86/100 | 61/100 | 70/100 |

These are not the full-split ANA scores of 302/347 and 295/347. The denominator
and comparator are shared within this table, but historical generation
conditions still differ as described above. Original judge scores remain in
their own website table and are not substituted for these query-result scores.

For the three October 28 Qwen3.5-27B runs, the same metric is now complete:

| Qwen3.5-27B requested profile | ANA exact | Direct Cypher re-executed exact | Multi-agent re-executed exact |
| --- | ---: | ---: | ---: |
| temp 0, reasoning medium | 85/100 | 64/100 | 67/100 |
| temp 1, reasoning off | 79/100 | 40/100 | 50/100 |
| temp 1, reasoning medium | 87/100 | 59/100 | 62/100 |

The corresponding direct/multi-agent query-error counts are 1/0, 2/8 and 2/4.
Errors remain failures in the full denominator, not exclusions. These exact
result scores do not replace the original source LLM-judge scores and are not
the ANA full-split results of 290/347, 273/347 and 292/347. Individual questions
and the three saved trajectories are available from each comparison page.

For GPT-OSS-20B, all four pinned reference pairs exist and cover the same 100 QIDs:

| GPT-OSS-20B requested profile | ANA exact | Direct Cypher re-executed exact | Multi-agent re-executed exact |
| --- | ---: | ---: | ---: |
| temp 0, reasoning off | 60/100 | 66/100 | 67/100 |
| temp 0, reasoning medium | 62/100 | 64/100 | 60/100 |
| temp 1, reasoning off | 70/100 | 59/100 | 68/100 |
| temp 1, reasoning medium | 63/100 | 63/100 | 66/100 |

The direct/multi-agent query-error counts are respectively 1/1, 2/3, 1/2 and
3/1. ANA does not dominate this matrix: only T1/off beats both baselines.
These are historical generation comparisons, not shared-preflight experiments.
No new full-split baseline inference was needed to fill these existing 100-QID
comparisons; full 347-question, shared-preflight baseline generations remain
future experiments rather than missing values invented from the subset.

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
| T0/none | 6.67 | 6.66 | 2.40 | 6.60 | 15118704 |
| T0/medium | 6.04 | 6.01 | 2.50 | 7.08 | 13560964 |
| T1/none | 5.51 | 5.46 | 2.43 | 6.42 | 12407671 |
| T1/medium | 5.56 | 5.50 | 2.40 | 6.58 | 12660250 |

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
6. Commit the complete evaluation directory and updated source configuration.
   Include all JSONL files and the manifest together, not only summary scores.
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
