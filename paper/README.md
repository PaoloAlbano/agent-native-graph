# Agent-Native APIs: Rethinking Data Access for LLM Agents

This directory is the navigable paper/preprint draft for the Agent-Native APIs
research project.

The project documentation in `../docs/` explains how to use and reproduce the
repository. This directory is different: it is the paper-like narrative that
frames the research question, method, results, and argument.

**Draft status, October 28, 2026:** the results section reports nine complete
Company runs and a common-metric comparison on 100 pinned questions. Tables
link to immutable evidence and are checked against it by tests. This is an
observational research draft, not a submission-ready claim of causal or
cross-domain superiority. The selective review identifies close predecessors;
further literature coverage, controlled replications and matched-budget
generation experiments remain open.

## How To Read

Start from the abstract and read sections in order. Each section is a separate
Markdown file so it can be referenced, reviewed, and edited independently.

## Table Of Contents

| Section | File | Purpose |
|---:|---|---|
| 0 | [Abstract](./00-abstract.md) | Short summary of the hypothesis, method, and findings. |
| 1 | [Introduction](./01-introduction.md) | Motivation and research question. |
| 2 | [Background and Related Work](./02-background-and-related-work.md) | Human-native query languages, text-to-query, agents, and graph QA context. |
| 3 | [Agent-Native APIs](./03-agent-native-apis.md) | Core ANA design principles. |
| 4 | [Knowledge Graph QA Case Study](./04-kgqa-case-study.md) | Why graph question answering is the first testbed. |
| 5 | [Tool Design](./05-tool-design.md) | Tool categories, handles, pagination, and safety boundaries. |
| 6 | [Experimental Setup](./06-experimental-setup.md) | CypherBench company slice, baselines, models, and metrics. |
| 7 | [Results](./07-results.md) | All nine full-split observations and the separate shared-100 comparison. |
| 8 | [Error Analysis](./08-error-analysis.md) | Failure classes and lessons from tool-call trajectories. |
| 9 | [Discussion](./09-discussion.md) | What ANA changes compared with text-to-Cypher and MCP-only exposure. |
| 10 | [Limitations](./10-limitations.md) | Current limits and validity threats. |
| 11 | [Future Work](./11-future-work.md) | Next experiments and implementation work. |
| 12 | [Conclusion](./12-conclusion.md) | Concise closing argument. |
| A | [Recorded Worked Examples](./appendix-a-worked-examples.md) | Complete call arguments, literal response excerpts and baseline queries for a selected success and mismatch. |

## Stable Reference Labels

Use these labels when referencing sections from issues, docs, or future papers:

- `ANA-PAPER-ABSTRACT`
- `ANA-PAPER-INTRODUCTION`
- `ANA-PAPER-BACKGROUND`
- `ANA-PAPER-METHOD`
- `ANA-PAPER-TOOL-DESIGN`
- `ANA-PAPER-EXPERIMENTS`
- `ANA-PAPER-RESULTS`
- `ANA-PAPER-ERROR-ANALYSIS`
- `ANA-PAPER-DISCUSSION`
- `ANA-PAPER-LIMITATIONS`
- `ANA-PAPER-FUTURE-WORK`
- `ANA-PAPER-WORKED-EXAMPLES`

## Related Repository Docs

- [Agent-Native APIs concept](../docs/agent-native-apis.md)
- [ANA v0 tool contract](../docs/ana-v0-tool-contract.md)
- [Tool catalog](../docs/tool-catalog.md)
- [CypherBench company results](../docs/cypherbench-company-results.md)
- [Reproduction guide](../docs/reproduction.md)
- [Benchmark protocol](../docs/benchmark-protocol.md)
- [Common-metric comparison](../docs/multigraphrag-comparison.md)
- [Methodology and failure audit](../docs/methodology-audit.md)
- [Prospective controlled Company design](../docs/controlled-company-protocol.md)
- [References](./references.bib)

## Evidence Checks

Run `uv run pytest tests/test_paper_evidence.py -q` to validate linked results,
call means, common-metric tables, Qwen failure counts, tool names, worked-example
selection/arguments/queries and local links.
The checks read saved artifacts only; they do not query Neo4j or call a model.
They validate the reported snapshot rather than automatically inserting future
runs. `make paper` prints this index; the public website remains the results
explorer, not a typeset PDF/preprint build.
