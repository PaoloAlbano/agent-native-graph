"""Build the static research website from the current native tool contract."""

import argparse
import hashlib
import inspect
import json
import re
import shutil
from html import escape
from pathlib import Path
from typing import Any

from agent_native_graph.core.tool_specs import _tool_specs
from agent_native_graph.core.tooling import registered_tools
from agent_native_graph.research.docs_comparison import publish_comparison
from agent_native_graph.research.docs_results import publish_results

REPOSITORY_URL = "https://github.com/PaoloAlbano/agent-native-graph"
GROUPS = (
    (
        "schema",
        "Schema & discovery",
        "Discover the graph's vocabulary and valid directions.",
        (
            "schema_overview",
            "schema_search",
            "schema_describe_label",
            "schema_describe_relationship",
            "inspect_paths",
        ),
    ),
    (
        "lookup",
        "Entity lookup",
        "Find an anchor or select nodes by their properties.",
        (
            "entity_resolve",
            "node_search",
            "value_search",
            "node_scan",
            "count_nodes",
        ),
    ),
    (
        "traversal",
        "Traversal & patterns",
        "Follow relationships and express connected constraints.",
        (
            "expand",
            "expand_aggregate",
            "relationship_query",
            "multi_hop_query",
            "pattern_query",
            "constraint_query",
        ),
    ),
    (
        "optional",
        "Optional matches",
        "Preserve source entities when related matches are absent.",
        (
            "optional_expand_count",
            "optional_count_by_pattern",
        ),
    ),
    (
        "composition",
        "Composition & filters",
        "Combine branches and refine intermediate handles.",
        (
            "entity_set_operation",
            "filter",
            "filter_same_node",
            "join_handles",
            "same_target_role_intersection",
            "shared_role_aggregate",
            "combine",
        ),
    ),
    (
        "answers",
        "Aggregation & answers",
        "Group, rank, project, and retrieve the answer.",
        (
            "count_handle",
            "group_handle",
            "project",
            "top_entities_by_property",
            "compare",
            "scalar_compute",
            "fetch",
        ),
    ),
    (
        "inspection",
        "Inspection & planning",
        "Inspect intermediate state, diagnose errors, or plan calls.",
        (
            "summarize_handle",
            "handle_recap",
            "repair_empty_result",
            "draft_tool_plan",
            "validate_tool_plan",
        ),
    ),
)


def collect_catalog(repo_root: Path) -> dict[str, Any]:
    """Document the actual LLM payload, including the runtime's contract overrides."""
    default_names = {spec["function"]["name"] for spec in _tool_specs(enable_planning_tools=False)}
    definitions = registered_tools()
    grouped_names = {name: group[0] for group in GROUPS for name in group[3]}
    tools = []
    for spec in _tool_specs(enable_planning_tools=True):
        function = spec["function"]
        name = function["name"]
        if name not in grouped_names:
            raise ValueError(f"Assign the new public tool {name!r} to a documentation group.")
        definition = definitions[name]
        source_file = inspect.getsourcefile(definition.function)
        source_path = Path(source_file).resolve().relative_to(repo_root.resolve())
        source_line = inspect.getsourcelines(definition.function)[1]
        tools.append(
            {
                "name": name,
                "group": grouped_names[name],
                "status": definition.status.value,
                "profile": definition.profile.value,
                "availability": "default" if name in default_names else "opt-in",
                "purpose": definition.purpose,
                "native_spec": spec,
                "source": f"{REPOSITORY_URL}/blob/main/{source_path.as_posix()}#L{source_line}",
            }
        )
    return {
        "contract": "Current native tool surface; schema_entry=overview",
        "groups": [
            {"id": slug, "title": title, "description": description}
            for slug, title, description, _ in GROUPS
        ],
        "default_count": len(default_names),
        "optional_count": len(tools) - len(default_names),
        "tools": tools,
    }


def schema_type(schema: dict[str, Any]) -> str:
    """Provide a readable type while retaining the full schema for inspection."""
    for union in ("anyOf", "oneOf"):
        if union in schema:
            return " | ".join(schema_type(item) for item in schema[union])
    value = schema.get("type")
    if value == "array":
        return f"array<{schema_type(schema.get('items', {}))}>"
    if isinstance(value, list):
        return " | ".join(value)
    return value or ("enum" if "enum" in schema else "any JSON value")


def _json_block(value: Any) -> str:
    return f"<pre><code>{escape(json.dumps(value, indent=2, ensure_ascii=False))}</code></pre>"


def render_parameters(schema: dict[str, Any]) -> str:
    properties = schema.get("properties", {})
    if not properties:
        return (
            '<p class="empty-parameters">No arguments. Send an empty object: <code>{}</code>.</p>'
        )
    required = set(schema.get("required", []))
    rows = []
    for name, parameter in properties.items():
        presence = "Required" if name in required else "Optional"
        description = escape(
            parameter.get("description", "No description in the current contract.")
        )
        constraints = []
        for key in ("enum", "default", "minimum", "maximum", "minItems", "maxItems", "pattern"):
            if key in parameter:
                constraints.append(
                    f'<span class="constraint">{key}: <code>'
                    f"{escape(json.dumps(parameter[key], ensure_ascii=False))}</code></span>"
                )
        nested = ""
        if any(key in parameter for key in ("items", "properties", "anyOf", "oneOf", "$ref")):
            nested = (
                '<details class="nested-schema"><summary>Inspect parameter schema</summary>'
                f"{_json_block(parameter)}</details>"
            )
        rows.append(
            f'<tr><th scope="row"><code>{escape(name)}</code></th>'
            f'<td><code class="type">{escape(schema_type(parameter))}</code>'
            f'<span class="presence {presence.lower()}">{presence}</span></td>'
            f"<td>{description}{''.join(constraints)}{nested}</td></tr>"
        )
    return (
        '<div class="parameter-table"><table><caption class="sr-only">Tool parameters</caption>'
        '<thead><tr><th scope="col">Parameter</th><th scope="col">Type / presence</th>'
        '<th scope="col">Description & constraints</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def render_tool(tool: dict[str, Any]) -> str:
    function = tool["native_spec"]["function"]
    parameters = function["parameters"]
    name = tool["name"]
    availability = "Default" if tool["availability"] == "default" else "Planning opt-in"
    parameter_count = len(parameters.get("properties", {}))
    return f'''
    <details class="tool-card" id="tool-{escape(name)}" data-tool="{escape(name)}"
        data-status="{escape(tool["status"])}" data-availability="{escape(tool["availability"])}">
      <summary>
        <span class="tool-summary"><span class="tool-name">{escape(name)}</span>
          <span class="tool-purpose">{escape(tool["purpose"])}</span></span>
        <span class="tool-tags"><span class="badge {escape(tool["status"])}">{escape(tool["status"])}</span>
          <span class="parameter-count">{parameter_count} parameters</span><span class="expand-mark" aria-hidden="true">+</span></span>
      </summary>
      <div class="tool-body">
        <div class="tool-meta"><span>{availability}</span><span>{escape(tool["profile"])}</span>
          <a class="permalink" href="#tool-{escape(name)}">Permanent link</a>
          <a href="{escape(tool["source"])}">Python source ↗</a></div>
        <h4>Description sent to the model</h4>
        <p class="llm-description">{escape(function["description"])}</p>
        <h4>Parameters</h4>
        {render_parameters(parameters)}
        <details class="native-schema"><summary>Full native tool definition · JSON</summary>
          {_json_block(tool["native_spec"])}
        </details>
      </div>
    </details>'''


def render_catalog(catalog: dict[str, Any]) -> str:
    tools = {tool["name"]: tool for tool in catalog["tools"]}
    groups = []
    for slug, title, description, names in GROUPS:
        members = [tools[name] for name in names if name in tools]
        groups.append(
            f'<section class="tool-group" id="group-{slug}" data-group="{slug}" '
            f'aria-labelledby="heading-{slug}">'
            f'<div class="group-heading"><div><h3 id="heading-{slug}">{escape(title)}</h3>'
            f'<p>{escape(description)}</p></div><span class="group-count">{len(members):02d}</span></div>'
            + "".join(render_tool(tool) for tool in members)
            + "</section>"
        )
    return "".join(groups)


def load_example(repo_root: Path) -> dict[str, Any]:
    """Select a recorded trajectory without altering its arguments or tool results."""
    selection = json.loads((repo_root / "docs/site/example.json").read_text())
    run_id = selection["run_id"]
    if not run_id or Path(run_id).name != run_id:
        raise ValueError("The example must name a run directory, not a path.")
    run_dir = repo_root / "results/cypherbench-company/full/runs" / run_id
    manifest = json.loads((run_dir / "manifest.json").read_text())
    run_file = run_dir / "run.jsonl"
    with run_file.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if digest != manifest["run_sha256"]:
        raise ValueError("The example run does not match its manifest checksum.")
    records = []
    with run_file.open() as source:
        for line in source:
            record = json.loads(line)
            if record["qid"] == selection["qid"]:
                records.append(record)
    if len(records) != 1:
        raise ValueError("The example QID must identify exactly one recorded question.")
    record = records[0]
    if len(selection["guide_notes"]) != len(record["transcript"]):
        raise ValueError("Each recorded step must have a corresponding editorial guide note.")
    return {
        "run": {
            key: manifest[key]
            for key in (
                "run_id",
                "model",
                "temperature",
                "reasoning",
                "created_at",
                "run_sha256",
                "git_commit",
            )
        },
        "record": record,
        "guide_notes": selection["guide_notes"],
        "source": f"{REPOSITORY_URL}/blob/main/{run_file.relative_to(repo_root).as_posix()}",
    }


def render_example(example: dict[str, Any]) -> str:
    record = example["record"]
    run = example["run"]
    steps = []
    for index, (step, note) in enumerate(
        zip(record["transcript"], example["guide_notes"], strict=True), 1
    ):
        action = step["action"]
        result = step["result"]
        name = escape(action["tool"])
        handle = result.get("handle")
        source_handle = action["args"].get("from")
        links = []
        if source_handle:
            links.append(
                f'Input <a class="handle-link" href="#example-handle-{escape(source_handle)}">{escape(source_handle)}</a>'
            )
        snapshot = ""
        if handle:
            safe_handle = escape(handle)
            links.append(
                f'Output <a class="handle-link" href="#example-handle-{safe_handle}">{safe_handle}</a>'
            )
            view = {
                key: result[key]
                for key in (
                    "handle",
                    "kind",
                    "focus",
                    "entity_variables",
                    "columns",
                    "matched_count",
                    "preview",
                    "truncated",
                    "limited",
                )
                if key in result
            }
            snapshot = (
                f'<details class="handle-snapshot" id="example-handle-{safe_handle}">'
                f"<summary><code>{safe_handle}</code> · recorded preview & metadata</summary>"
                "<p>This is the handle view saved in the tool response. The complete internal "
                "entity records were not archived; alternative candidates are suggestions "
                "in the full response, not rows in this handle.</p>"
                f"{_json_block(view)}</details>"
            )
        handle_flow = '<span aria-hidden="true">→</span>'.join(links)
        steps.append(
            f'<li><span class="step-index">{index:02d}</span><div>'
            f'<h3><a href="#tool-{name}">{name}</a></h3>'
            f'<p class="guide-note"><span>Guide note</span> {escape(note)}</p>'
            f'<div class="handle-flow">{handle_flow}</div>'
            f'<details class="call-arguments"><summary>Tool arguments · recorded JSON</summary>{_json_block(action["args"])}</details>'
            f'<details class="call-result"><summary>Tool response · complete recorded JSON</summary>{_json_block(result)}</details>'
            f"{snapshot}</div></li>"
        )
    matched = (
        "Matches the benchmark answer"
        if record["matches_answer_json"]
        else "Does not match the benchmark answer"
    )
    return (
        f'<p class="example-question">“{escape(record["nl_question"])}”</p>'
        '<div class="example-provenance">'
        f"<span>{escape(run['model'])}</span><span>Temperature {run['temperature']:g}</span>"
        f"<span>Reasoning: {escape(run['reasoning'])}</span><span>{escape(run['created_at'][:10])}</span></div>"
        "<p>These are actual calls and responses from a Company benchmark run. "
        'Click a handle such as <a class="handle-link" href="#example-handle-h1">h1</a> '
        "to inspect its recorded preview and metadata.</p>"
        '<aside class="recording-note"><strong>About reasoning.</strong> This run requested medium '
        "reasoning, but reasoning text was not saved in the archive. The guide notes below are "
        "editorial explanations of the operations, not statements made by the model.</aside>"
        f'<ol class="trajectory">{"".join(steps)}</ol>'
        f'<div class="example-answer"><p class="eyebrow">Final answer · {matched}</p>{_json_block(record["rows"])}</div>'
        f'<details class="example-metrics"><summary>Recorded LLM call metrics</summary>{_json_block(record["llm_call_metrics"])}</details>'
        f'<p class="example-source">QID: <code>{escape(record["qid"])}</code><br>'
        f'<a href="{escape(example["source"])}">Source run ↗</a> · '
        '<a href="data/example-trajectory.json" download>Download this example · JSON ↓</a></p>'
    )


def build_site(
    repo_root: Path, output_dir: Path | None = None, reference_repo: Path | None = None
) -> Path:
    """Write owned site artifacts only; preserve Markdown and curated results."""
    repo_root = repo_root.resolve()
    output_dir = output_dir or repo_root / "docs"
    sources = repo_root / "docs" / "site"
    catalog = collect_catalog(repo_root)
    example = load_example(repo_root)
    replacements = {
        "DEFAULT_COUNT": str(catalog["default_count"]),
        "OPTIONAL_COUNT": str(catalog["optional_count"]),
        "TOTAL_COUNT": str(len(catalog["tools"])),
        "GROUP_COUNT": str(len(GROUPS)),
        "TOOL_CATALOG": render_catalog(catalog),
        "EXAMPLE_TRAJECTORY": render_example(example),
        "GROUP_OPTIONS": "".join(
            f'<option value="{slug}">{escape(title)}</option>' for slug, title, _, _ in GROUPS
        ),
    }
    template = (sources / "index.template.html").read_text()
    # Substitute only template tokens, never token-like strings in tool descriptions.
    page = re.sub(r"@@([A-Z_]+)@@", lambda match: replacements[match[1]], template)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "assets").mkdir(exist_ok=True)
    (output_dir / "data").mkdir(exist_ok=True)
    (output_dir / "index.html").write_text(page, encoding="utf-8")
    (output_dir / "data" / "tool-catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "data" / "example-trajectory.json").write_text(
        json.dumps(example, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    publish_results(repo_root, output_dir, REPOSITORY_URL)
    publish_comparison(repo_root, output_dir, reference_repo)
    for name in (
        "site.css",
        "site.js",
        "results.css",
        "results-ui.js",
        "results.js",
        "comparison.js",
    ):
        shutil.copyfile(sources / name, output_dir / "assets" / name)
    (output_dir / ".nojekyll").write_text("")
    return output_dir / "index.html"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, help="Defaults to <repo-root>/docs.")
    parser.add_argument(
        "--reference-repo",
        type=Path,
        help="Read pinned external Company evidence from this Git repository.",
    )
    args = parser.parse_args()
    reference = args.reference_repo
    if reference is None and (args.repo_root.resolve().parent / "multigraphrag").is_dir():
        reference = args.repo_root.resolve().parent / "multigraphrag"
    page = build_site(args.repo_root, args.out, reference)
    print(f"Built {page}")


if __name__ == "__main__":
    main()
