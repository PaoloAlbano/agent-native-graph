# Tool Catalog

The complete reference is generated into the research website from the same
native tool specifications used by the runner:

```bash
make docs-serve
```

Open <http://127.0.0.1:8000/#tool-catalog>. The reference includes every tool in
the standard native profile and the two optional planning tools. Each entry
contains its purpose, effective LLM description, parameter names and types,
required arguments, nested JSON schemas, status, availability, and source link.

The catalog is organized into seven families:

| Family | Role |
|---|---|
| Schema and discovery | Discover labels, properties, relationships, and directions. |
| Entity lookup | Resolve names or select nodes and property values. |
| Traversal and patterns | Follow relationships and compose connected constraints. |
| Optional matches | Preserve source entities without matching related nodes. |
| Composition and filters | Combine branches, join handles, and refine rows. |
| Aggregation and answers | Group, rank, project, compare, and fetch results. |
| Inspection and planning | Inspect handles, diagnose errors, and optionally plan. |

The definitions start in `src/agent_native_graph/tools/` with `@tool` and
`ToolParam` annotations. `core/tool_specs.py` selects the exposed surface and
applies runtime compatibility overrides. The website uses the resulting
LLM-facing specifications rather than duplicating their descriptions here.

The generated `docs/data/tool-catalog.json` can be downloaded from the site.
It describes the current code, not necessarily the contract used by a historical
run. See [the contract notes](ana-v0-tool-contract.md) for status and design rules,
and [site maintenance](site/README.md) for the build workflow.
