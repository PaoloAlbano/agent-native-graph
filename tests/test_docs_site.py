import json
import shutil
from html.parser import HTMLParser
from pathlib import Path

from agent_native_graph.core.tool_specs import _tool_specs
from agent_native_graph.research import build_docs as builder
from agent_native_graph.research.build_docs import (
    build_site,
    collect_catalog,
    load_example,
    render_tool,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


class PageLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.fragments = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if "id" in attributes:
            self.ids.append(attributes["id"])
        if tag == "a" and attributes.get("href", "").startswith("#"):
            self.fragments.append(attributes["href"][1:])
        if tag == "script":
            self.scripts.append(attributes)


def test_catalog_matches_effective_native_contract_and_availability():
    catalog = collect_catalog(REPO_ROOT)
    published = {tool["name"]: tool for tool in catalog["tools"]}
    effective = {spec["function"]["name"]: spec for spec in _tool_specs(enable_planning_tools=True)}
    default_names = {spec["function"]["name"] for spec in _tool_specs(enable_planning_tools=False)}
    assert published.keys() == effective.keys()
    for name, tool in published.items():
        assert tool["native_spec"] == effective[name]
        assert (tool["availability"] == "default") == (name in default_names)
    assert catalog["default_count"] == len(default_names)
    # Project's LLM-facing contract intentionally differs from its Python wrapper.
    project = published["project"]["native_spec"]["function"]["parameters"]
    assert "select" in project["required"]
    assert "group_by" not in project["properties"]
    assert "from" in project["properties"]
    assert "from_" not in project["properties"]


def test_default_build_keeps_docs_source_only_and_excludes_private_notes(tmp_path, monkeypatch):
    sources = tmp_path / "docs/site"
    shutil.copytree(REPO_ROOT / "docs/site", sources)
    (tmp_path / "docs/public.md").write_text("Public documentation")
    private = tmp_path / ".local-notes"
    private.mkdir()
    (private / "roadmap.md").write_text("Private planning, never publish")
    before = {
        p.relative_to(tmp_path): p.read_bytes()
        for p in (tmp_path / "docs").rglob("*")
        if p.is_file()
    }
    catalog, example = collect_catalog(REPO_ROOT), load_example(REPO_ROOT)
    monkeypatch.setattr(builder, "collect_catalog", lambda root: catalog)
    monkeypatch.setattr(builder, "load_example", lambda root: example)
    monkeypatch.setattr(builder, "publish_results", lambda *args: None)
    monkeypatch.setattr(builder, "publish_comparison", lambda *args: None)
    page = builder.build_site(tmp_path)
    assert page == tmp_path / "build/site/index.html"
    assert before == {
        p.relative_to(tmp_path): p.read_bytes()
        for p in (tmp_path / "docs").rglob("*")
        if p.is_file()
    }
    assert not (page.parent / "roadmap.md").exists()
    assert "Private planning" not in page.read_text()


def test_build_preserves_existing_docs_and_has_resolvable_tool_links(tmp_path):
    existing = tmp_path / "editorial.md"
    existing.write_text("Keep this research note.\n")
    page = build_site(REPO_ROOT, tmp_path)
    assert existing.read_text() == "Keep this research note.\n"
    parsed = PageLinks()
    parsed.feed(page.read_text())
    assert len(parsed.ids) == len(set(parsed.ids))
    assert set(parsed.fragments) <= set(parsed.ids)
    catalog = json.loads((tmp_path / "data/tool-catalog.json").read_text())
    assert {f"tool-{tool['name']}" for tool in catalog["tools"]} <= set(parsed.ids)
    assert parsed.scripts == [{"defer": None, "src": "assets/site.js"}]
    assert "@@TOOL_CATALOG@@" not in page.read_text()
    assert "will make the recorded runs explorable" not in page.read_text()
    results_page = (tmp_path / "results.html").read_text()
    assert "<code>docs/site/</code>" in results_page
    assert "<code>build/site/</code>" in results_page
    assert (tmp_path / "assets/site.css").is_file()
    assert (tmp_path / "assets/site.js").is_file()
    example = json.loads((tmp_path / "data/example-trajectory.json").read_text())
    assert example["record"]["transcript"] == load_example(REPO_ROOT)["record"]["transcript"]
    assert {"example-handle-h1", "example-handle-h2", "example-handle-h3"} <= set(parsed.ids)
    assert 'id="tool-search"' not in page.read_text()
    first_build = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    build_site(REPO_ROOT, tmp_path)
    assert first_build == {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }


def test_tool_descriptions_and_nested_schemas_are_escaped():
    payload = '<script>alert("example")</script>'
    tool = {
        "name": "example",
        "status": "core",
        "profile": "readonly",
        "availability": "default",
        "purpose": payload,
        "source": "https://example.com/source",
        "native_spec": {
            "type": "function",
            "function": {
                "name": "example",
                "description": payload,
                "parameters": {
                    "type": "object",
                    "required": ["select"],
                    "properties": {
                        "select": {
                            "type": "array",
                            "description": payload,
                            "items": {
                                "type": "object",
                                "properties": {"value": {"type": "string", "description": payload}},
                            },
                        }
                    },
                },
            },
        },
    }
    rendered = render_tool(tool)
    parsed = PageLinks()
    parsed.feed(rendered)
    assert parsed.scripts == []
    assert "&lt;script&gt;" in rendered
    assert "Inspect parameter schema" in rendered
    assert 'class="presence required">Required' in rendered


def test_example_preserves_the_archived_record_and_handle_previews():
    example = load_example(REPO_ROOT)
    run_file = (
        REPO_ROOT / "results/cypherbench-company/full/runs" / example["run"]["run_id"] / "run.jsonl"
    )
    with run_file.open() as source:
        original = next(
            record
            for line in source
            if (record := json.loads(line))["qid"] == example["record"]["qid"]
        )
    assert example["record"] == original
    assert original["matches_answer_json"] is True
    assert original["rows"] == [["Novo Nordisk"]]
    handles = {
        step["result"]["handle"]: step["result"]
        for step in original["transcript"]
        if "handle" in step["result"]
    }
    assert handles["h1"]["preview"] == ["Novo Nordisk (Germany)"]
    assert handles["h2"]["preview"] == ["Novo Nordisk"]
    assert handles["h3"]["preview"] == [{"name": "Novo Nordisk"}]
    assert handles["h3"]["entity_variables"] == []
    assert "reasoning_content" not in original
