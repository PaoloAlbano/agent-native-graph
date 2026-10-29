"""Integrity evidence must fail closed on mutation, incomplete coverage and tampering."""

import json
from copy import deepcopy

import pytest

from agent_native_graph.application.run_config import file_hash
from agent_native_graph.research.graph_integrity import (
    GraphBlock,
    GraphIntegrityError,
    validate_integrity,
)


@pytest.fixture
def block(tmp_path):
    out, config, graph = (
        tmp_path / name for name in ("run.jsonl", "run.config.json", "graph.json")
    )
    config.write_text('{"model":"test"}')
    graph.write_text("{}")
    out.write_text('{"qid":"a"}\n{"qid":"b"}\n')
    before = {"nodes": {"count": 2, "sha256": "a" * 64}, "edges": {"count": 1, "sha256": "b" * 64}}
    instance = GraphBlock(
        out,
        config,
        graph,
        {"database": "benchmark", "snapshot": before, "graph_sha256": file_hash(graph)},
        ["a", "b"],
    )
    instance.start()
    return instance, before


def test_verified_report_binds_exact_bytes_and_config_and_never_overwrites(block):
    instance, before = block
    report = instance.finish(before)
    assert report["status"] == "verified"
    assert (
        validate_integrity(instance.path, instance.output, configuration=instance.configuration)
        == report
    )
    with pytest.raises(FileExistsError):
        instance.start()
    assert "benchmark" in instance.path.read_text()
    assert str(instance.output.parent) not in instance.path.read_text()


@pytest.mark.parametrize("mutation", ["nodes", "edges", "graph_file", "configuration"])
def test_changed_content_is_invalid_even_when_the_run_has_all_questions(block, mutation):
    instance, before = block
    after = deepcopy(before)
    if mutation in ("nodes", "edges"):
        # Counts alone are insufficient: change properties/endpoints without changing size.
        after[mutation]["sha256"] = "c" * 64
    else:
        (instance.graph if mutation == "graph_file" else instance.configuration).write_text(
            '{"changed":true}'
        )
    assert instance.finish(after)["status"] == "invalid"
    with pytest.raises(GraphIntegrityError):
        validate_integrity(instance.path, instance.output)


@pytest.mark.parametrize("qids", [[], ["a"], ["a", "a"], ["a", "foreign"]])
def test_missing_duplicate_or_foreign_qids_are_not_publishable(block, qids):
    instance, before = block
    instance.output.write_text("".join(json.dumps({"qid": qid}) + "\n" for qid in qids))
    assert instance.finish(before)["status"] == "incomplete"


def test_interruption_and_failed_postcheck_are_not_equivalent_to_success(block):
    instance, _ = block
    with pytest.raises(GraphIntegrityError):
        validate_integrity(instance.path, instance.output)
    report = instance.finish(None, run_failed=True, postcheck_error="TimeoutError")
    assert report["status"] == "incomplete"
    assert {"postcheck_failed", "run_failed"} <= set(report["issues"])


@pytest.mark.parametrize("target", ["run", "configuration", "report"])
def test_tampered_evidence_is_rejected(block, target):
    instance, before = block
    instance.finish(before)
    if target == "run":
        instance.output.write_text('{"qid":"b"}\n{"qid":"a"}\n')
    elif target == "configuration":
        instance.configuration.write_text("{}")
    else:
        report = json.loads(instance.path.read_text())
        report["after"]["edges"]["sha256"] = "d" * 64
        instance.path.write_text(json.dumps(report))
    with pytest.raises(GraphIntegrityError):
        validate_integrity(instance.path, instance.output, configuration=instance.configuration)


def test_before_fingerprint_cannot_be_modified_through_the_preflight_object(block):
    instance, before = block
    before["nodes"]["count"] += 1
    assert instance.finish(before)["status"] == "invalid"


def test_missing_output_never_produces_a_verified_report(block):
    instance, before = block
    instance.output.unlink()
    report = instance.finish(before)
    assert report["status"] == "incomplete" and "evidence_read_failed" in report["issues"]


def test_baseline_archiver_preserves_verified_sidecar_and_refuses_invalid_blocks(tmp_path):
    from agent_native_graph.research.archive_reference_baseline import archive

    out, graph, tasks, metadata_path = (
        tmp_path / name for name in ("run.jsonl", "graph.json", "tasks.jsonl", "run.meta.json")
    )
    out.write_text(
        "".join(
            json.dumps(
                {
                    "qid": q,
                    "approach": "multigraphrag_single_retrieval",
                    "ok": True,
                    "matches_answer_json": True,
                }
            )
            + "\n"
            for q in ("a", "b")
        )
    )
    graph.write_text("{}")
    tasks.write_text('{"qid":"a"}\n{"qid":"b"}\n')
    metadata = {
        "verify_graph_block": True,
        "source_repo": "multigraphrag",
        "tasks_sha256": file_hash(tasks),
        "graph_sha256": file_hash(graph),
        "approach": "multigraphrag_single_retrieval",
        "mode": "single_retrieval",
        "model": "test/model",
        "temperature": 0,
        "reasoning": "none",
        "limit": 2,
        "suite": "n2",
        "call_logs": [],
    }
    metadata_path.write_text(json.dumps(metadata))
    before = {"nodes": {"count": 1, "sha256": "a" * 64}, "edges": {"count": 0, "sha256": "b" * 64}}
    block = GraphBlock(
        out,
        metadata_path,
        graph,
        {"database": "benchmark", "snapshot": before, "graph_sha256": file_hash(graph)},
        ["a", "b"],
    )
    block.start()
    block.finish(before)
    destination = archive(out, tmp_path / "archives", tasks, graph)
    assert (destination / "graph-integrity.json").read_bytes() == block.path.read_bytes()
    validate_integrity(destination / "graph-integrity.json", destination / "run.jsonl")
    report = json.loads(block.path.read_text())
    report["status"] = "invalid"
    block.path.write_text(json.dumps(report))
    with pytest.raises(GraphIntegrityError):
        archive(out, tmp_path / "refused", tasks, graph)
    assert not (tmp_path / "refused").exists()
