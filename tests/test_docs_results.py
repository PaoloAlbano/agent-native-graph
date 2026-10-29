import hashlib
import json
from pathlib import Path

import pytest

from agent_native_graph.research.docs_results import (
    ARCHIVE,
    evidence_summary,
    publish_results,
    read_runs,
)

ROOT = Path(__file__).resolve().parents[1]


def archive(root, run_id="test-run", question="Question", size=347):
    folder = root / ARCHIVE / run_id
    folder.mkdir(parents=True)
    records = [
        {
            "qid": f"q-{i}",
            "nl_question": question,
            "gold_cypher": "RETURN 1",
            "expected": [[1]],
            "rows": [[1]],
            "ok": True,
            "matches_answer_json": True,
            "llm_call_count": 2,
            "tool_call_count": 2,
            "transcript": [
                {"action": {"tool": "fetch", "args": {"from": "h1"}}, "result": {"rows": [[1]]}}
            ],
        }
        for i in range(size)
    ]
    payload = "".join(json.dumps(r) + "\n" for r in records).encode()
    (folder / "run.jsonl").write_bytes(payload)
    manifest = {
        "run_id": run_id,
        "run_sha256": hashlib.sha256(payload).hexdigest(),
        "category": "company",
        "suite": "full",
        "model": "test-model",
        "created_at": "2026-10-26",
        "temperature": 0,
        "reasoning": "none",
        "source_file": "/private/local/path.jsonl",
    }
    summary = {
        "run_id": run_id,
        "total": size,
        "ok": size,
        "matches": size,
        "accuracy": 1,
        "avg_llm_calls": 2,
        "avg_tool_calls": 2,
    }
    (folder / "manifest.json").write_text(json.dumps(manifest))
    (folder / "summary.json").write_text(json.dumps(summary))
    return folder, records


def test_publish_preserves_records_and_sources_and_escapes_html(tmp_path):
    folder, records = archive(tmp_path, question="<script>alert(1)</script>")
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["model"] = '<script>alert("model")</script>'
    manifest_path.write_text(json.dumps(manifest))
    sources = tmp_path / "docs/site"
    sources.mkdir(parents=True)
    (sources / "results.template.html").write_text(
        (ROOT / "docs/site/results.template.html").read_text()
    )
    (sources / "run-explorer.html").write_text((ROOT / "docs/site/run-explorer.html").read_text())
    before = {p: p.read_bytes() for p in folder.iterdir()}
    output = tmp_path / "site"
    page = publish_results(tmp_path, output, "https://example.com/repo")
    index = json.loads((output / "data/results/index.json").read_text())
    published = index["runs"][0]
    assert "source_file" not in published["config"]
    assert "questions" not in published
    run_index = json.loads((output / published["question_index"]).read_text())
    assert len(run_index["questions"]) == 347
    q = next(q for q in run_index["questions"] if q["qid"] == records[0]["qid"])
    assert json.loads((output / q["detail"]).read_text()) == records[0]
    assert "transcript" not in q  # Large traces are lazy-loaded, not in the index.
    assert '<script>alert("model")</script>' not in page
    assert "&lt;script&gt;" in page
    assert "Temperature 0" in page
    assert "Reasoning none" in page
    assert '<div class="metric-guide"><h3>How to read these numbers</h3>' in page
    assert '<details class="metric-guide"' not in page
    run_page = (output / published["page"]).read_text()
    assert 'placeholder="Filter by QID"' in run_page
    assert 'class="question-table"' in run_page
    assert "<script" not in page
    assert 'class="question-table"' not in page
    assert 'class="explorer-layout"' not in page
    assert before == {p: p.read_bytes() for p in folder.iterdir()}
    assert "The evidence at a glance" in page
    assert "1 complete runs" in page
    assert "@@EVIDENCE_SUMMARY@@" not in page
    assert "The evidence at a glance" not in run_page


def test_evidence_summary_retains_repeats_and_escapes_model_names():
    runs = [
        {"manifest": {"model": "<model>"}, "summary": {"accuracy": score}}
        for score in (0.6, 0.7, 0.65)
    ]
    html = evidence_summary(runs)
    assert "3 complete runs" in html
    assert "<td>3</td><td>60.0% &ndash; 70.0%</td>" in html
    assert "&lt;model&gt;" in html and "<model>" not in html
    assert "neither confidence intervals nor averages" in html
    assert "shared-preflight diagnostics" in html


def test_standard_run_config_is_validated(tmp_path):
    folder, _ = archive(tmp_path)
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.update(
        concurrency=3,
        max_tokens=16000,
        max_steps=12,
        tool_mode="native",
        tool_choice="auto",
        configuration_sha256="frozen-config",
    )
    payload = json.dumps(
        {
            k: manifest[k]
            for k in (
                "model",
                "temperature",
                "reasoning",
                "concurrency",
                "max_tokens",
                "max_steps",
                "tool_mode",
                "tool_choice",
                "configuration_sha256",
            )
        }
    ).encode()
    (folder / "run-config.json").write_bytes(payload)
    manifest["run_config_sha256"] = hashlib.sha256(payload).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    assert len(read_runs(tmp_path)) == 1
    (folder / "run-config.json").write_text("{}")
    with pytest.raises(ValueError, match="configuration checksum"):
        read_runs(tmp_path)


def test_checksum_mismatch_is_rejected(tmp_path):
    folder, _ = archive(tmp_path)
    with (folder / "run.jsonl").open("a") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="Checksum"):
        read_runs(tmp_path)


def test_summary_mismatch_is_rejected(tmp_path):
    folder, _ = archive(tmp_path)
    path = folder / "summary.json"
    summary = json.loads(path.read_text())
    summary["matches"] -= 1
    path.write_text(json.dumps(summary))
    with pytest.raises(ValueError, match="Summary matches"):
        read_runs(tmp_path)


def test_incomplete_runs_are_rejected(tmp_path):
    archive(tmp_path, size=100)
    with pytest.raises(ValueError, match="347 unique"):
        read_runs(tmp_path)


def test_duplicate_qids_are_rejected_even_with_a_valid_checksum(tmp_path):
    folder, records = archive(tmp_path)
    records[-1] = records[0]
    payload = "".join(json.dumps(r) + "\n" for r in records).encode()
    (folder / "run.jsonl").write_bytes(payload)
    path = folder / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["run_sha256"] = hashlib.sha256(payload).hexdigest()
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="347 unique"):
        read_runs(tmp_path)


def test_different_questions_cannot_be_compared(tmp_path):
    archive(tmp_path, "run-a")
    archive(tmp_path, "run-b", question="Different question")
    with pytest.raises(ValueError, match="Question/gold mismatch"):
        read_runs(tmp_path)


def test_actual_archive_summary_and_qids_are_consistent():
    runs = read_runs(ROOT)
    assert len(runs) >= 4
    assert all(len(r["records"]) == 347 for r in runs)


def test_actual_standard_archives_preserve_provenance_and_failure_subsets():
    from agent_native_graph.application.run_config import validate_results
    from agent_native_graph.research.archive_result import _failure_record, _summary

    runs = read_runs(ROOT)
    indexed = json.loads((ROOT / "results/cypherbench-company/index.json").read_text())
    assert {r["manifest"]["run_id"] for r in runs} == {r["run_id"] for r in indexed}
    for run in runs:
        folder = ROOT / ARCHIVE / run["manifest"]["run_id"]
        if not (folder / "run-config.json").exists():
            continue  # Historical provenance must not be reconstructed retroactively.
        config = json.loads((folder / "run-config.json").read_text())
        validate_results(run["records"], config)
        assert "inputs" not in config and "runtime_identity" not in config
        assert config["max_tokens"] == 16000 and config["tool_choice"] == "auto"
        assert config["tool_mode"] == "native" and config["limit"] == 347
        assert run["summary"] == json.loads(json.dumps(_summary(run["records"], folder.name)))
        failures = [
            json.loads(line) for line in (folder / "failures.jsonl").read_text().splitlines()
        ]
        assert failures == [
            _failure_record(row) for row in run["records"] if not row["matches_answer_json"]
        ]


def test_qwen_archive_contains_all_four_requested_profiles():
    profiles = {
        (run["manifest"]["temperature"], run["manifest"]["reasoning"])
        for run in read_runs(ROOT)
        if run["manifest"]["model"] == "Qwen/Qwen3.5-27B"
    }
    assert {(0, "none"), (0, "medium"), (1, "none"), (1, "medium")} <= profiles


def test_model_pages_group_runs_and_link_to_the_question_explorer(tmp_path):
    archive(tmp_path, "run-a")
    archive(tmp_path, "run-b")
    folder, _ = archive(tmp_path, "run-c")
    path = folder / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["model"] = "another/model"
    path.write_text(json.dumps(manifest))
    sources = tmp_path / "docs/site"
    sources.mkdir(parents=True)
    (sources / "results.template.html").write_text(
        (ROOT / "docs/site/results.template.html").read_text()
    )
    (sources / "run-explorer.html").write_text((ROOT / "docs/site/run-explorer.html").read_text())
    output = tmp_path / "site"
    overview = publish_results(tmp_path, output, "https://example.com/repo")
    pages = list(output.glob("model-*.html"))
    assert len(pages) == 2
    entries = json.loads((output / "data/results/index.json").read_text())["runs"]
    assert len(list(output.glob("run-*.html"))) == 3
    for page in pages:
        html = page.read_text()
        assert page.name in overview
        assert "@@" not in html
        assert 'href="results.html"' in html
        assert "<script" not in html
        assert 'id="question-list"' not in html
        for entry in entries:
            model = entry["config"]["model"]
            belongs = f"<h1>{model}</h1>" in html
            assert (entry["page"] in html) == belongs
    for entry in entries:
        run_html = (output / entry["page"]).read_text()
        assert f'data-run-index="{entry["question_index"]}"' in run_html
        assert 'id="question-list"' in run_html
        assert "assets/results.js" in run_html
        assert entry["page"] in overview
