# Agent-Native APIs: Rethinking Data Access for LLM Agents

This directory is the navigable paper/preprint draft for the Agent-Native APIs
research project.

The project documentation in `../docs/` explains how to use and reproduce the
repository. This directory is different: it is the paper-like narrative that
frames the research question, method, results, and argument.

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
| 7 | [Results](./07-results.md) | Current representative benchmark results. |
| 8 | [Error Analysis](./08-error-analysis.md) | Failure classes and lessons from tool-call trajectories. |
| 9 | [Discussion](./09-discussion.md) | What ANA changes compared with text-to-Cypher and MCP-only exposure. |
| 10 | [Limitations](./10-limitations.md) | Current limits and validity threats. |
| 11 | [Future Work](./11-future-work.md) | Next experiments and implementation work. |
| 12 | [Conclusion](./12-conclusion.md) | Concise closing argument. |

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

## Related Repository Docs

- [Agent-Native APIs concept](../docs/agent-native-apis.md)
- [ANA v0 tool contract](../docs/ana-v0-tool-contract.md)
- [Tool catalog](../docs/tool-catalog.md)
- [CypherBench company results](../docs/cypherbench-company-results.md)
- [Reproduction guide](../docs/reproduction.md)
