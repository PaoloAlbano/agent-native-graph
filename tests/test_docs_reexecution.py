import hashlib
import json
from pathlib import Path

import pytest

from agent_native_graph.research.docs_comparison import profile
from agent_native_graph.research.docs_reexecution import load_evaluation
from agent_native_graph.research.docs_results import read_runs
from agent_native_graph.research_common import result_matches_answer


@pytest.fixture
def evidence(tmp_path):
    config = {
        "execution_evaluation": "evaluation",
        "commit": "commit",
        "repository": "repo",
        "qid_file": "qids",
    }
    pinned = {"qids": [str(i) for i in range(100)], "qid_sha256": "qid-hash"}
    records = [
        {"qid": qid, "expected": [[1]], "rows": [[1]], "ok": True, "matches_answer_json": True}
        for qid in pinned["qids"]
    ]
    run = {
        "manifest": {"run_id": "ana", "run_sha256": "run-hash", "graph_sha256": "graph-hash"},
        "records": records,
    }
    folder = tmp_path / "evaluation"
    folder.mkdir()
    payload = "".join(json.dumps(r) + "\n" for r in records).encode()
    (folder / "gold.jsonl").write_bytes(payload)
    (folder / "baseline.jsonl").write_bytes(payload)
    entry = {
        "file": "baseline.jsonl",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "correct": 100,
    }
    report = {
        "status": "complete",
        "snapshot_before": {"hash": "a"},
        "snapshot_after": {"hash": "a"},
        "source": config,
        "qid_sha256": "qid-hash",
        "graph_sha256": "graph-hash",
        "ana": {"ana": {"run_sha256": "run-hash"}},
        "gold": entry,
        "baselines": {"baseline": entry},
    }
    (folder / "manifest.json").write_text(json.dumps(report))
    return tmp_path, config, pinned, [run]


def test_complete_evidence_is_loaded(evidence):
    report = load_evaluation(*evidence)
    assert len(report["baselines"]["baseline"]["records"]) == 100


def test_new_run_does_not_invalidate_historical_evaluation(evidence):
    root, config, pinned, runs = evidence
    new = {
        **runs[0],
        "manifest": {**runs[0]["manifest"], "run_id": "new-run", "run_sha256": "new-hash"},
    }
    report = load_evaluation(root, config, pinned, [*runs, new])
    assert "new-run" not in report["ana"]


@pytest.mark.parametrize("temperature,reasoning", [(0, "medium"), (1, "none")])
def test_extended_evaluation_checks_new_profile_provenance(evidence, temperature, reasoning):
    root, config, pinned, runs = evidence
    run_id = f"new-temp{temperature}-{reasoning}"
    new = {
        **runs[0],
        "manifest": {
            **runs[0]["manifest"],
            "run_id": run_id,
            "run_sha256": "new-hash",
            "temperature": temperature,
            "reasoning": reasoning,
        },
    }
    path = root / "evaluation/manifest.json"
    saved = json.loads(path.read_text())
    saved["ana"][run_id] = {"run_sha256": "new-hash"}
    path.write_text(json.dumps(saved))
    report = load_evaluation(root, config, pinned, [*runs, new])
    assert report["ana"][run_id]["run_sha256"] == "new-hash"

    saved["ana"][run_id]["run_sha256"] = "different-run"
    path.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match="ANA provenance mismatch"):
        load_evaluation(root, config, pinned, [*runs, new])


@pytest.mark.parametrize("change", ["status", "snapshot", "source", "qid", "graph"])
def test_rejects_invalid_provenance(evidence, change):
    path = evidence[0] / "evaluation/manifest.json"
    report = json.loads(path.read_text())
    if change == "status":
        report["status"] = "running"
    elif change == "snapshot":
        report["snapshot_after"] = {}
    elif change == "source":
        report["source"]["commit"] = "other"
    elif change == "qid":
        report["qid_sha256"] = "other"
    else:
        report["graph_sha256"] = "other"
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError):
        load_evaluation(*evidence)


def test_rejects_modified_result_file(evidence):
    (evidence[0] / "evaluation/baseline.jsonl").write_text("{}\n")
    with pytest.raises(ValueError, match="checksum"):
        load_evaluation(*evidence)


def test_rejects_wrong_verdict_even_with_updated_checksum(evidence):
    folder = evidence[0] / "evaluation"
    payload = (
        (folder / "baseline.jsonl").read_text().replace('"rows": [[1]]', '"rows": [[2]]').encode()
    )
    (folder / "baseline.jsonl").write_bytes(payload)
    report = json.loads((folder / "manifest.json").read_text())
    report["baselines"]["baseline"]["sha256"] = hashlib.sha256(payload).hexdigest()
    (folder / "manifest.json").write_text(json.dumps(report))
    with pytest.raises(ValueError, match="verdict"):
        load_evaluation(*evidence)


def test_selected_evaluation_covers_qwen_matrix_and_its_pinned_baselines():
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / "docs/site/comparison-source.json").read_text())
    pinned = json.loads((root / config["qid_file"]).read_text())
    runs = read_runs(root)
    report = load_evaluation(root, config, pinned, runs)
    assert report is not None
    assert set(report["ana"]) <= {run["manifest"]["run_id"] for run in runs}
    # Future contributions may legitimately await their own baseline evaluation.
    covered = [run for run in runs if run["manifest"]["run_id"] in report["ana"]]
    qwen_profiles = {
        profile(run["manifest"])[1:]
        for run in covered
        if run["manifest"]["model"] == "Qwen/Qwen3.5-27B"
    }
    assert {(0, "none"), (0, "medium"), (1, "none"), (1, "medium")} <= qwen_profiles
    pairs = {
        (profile(entry["config"], True), Path(path).name)
        for path, entry in report["baselines"].items()
    }
    assert pairs >= {
        (profile(run["manifest"]), mode) for run in covered for mode in ("single", "agentic")
    }
    qids = set(pinned["qids"])
    for run in covered:
        rows = [r for r in run["records"] if r["qid"] in qids]
        assert len(rows) == 100
        expected_correct = sum(
            bool(r["ok"]) and result_matches_answer(r["rows"], r["expected"]) for r in rows
        )
        saved = report["ana"][run["manifest"]["run_id"]]
        assert saved["total"] == 100 and saved["correct"] == expected_correct
    assert all(entry["total"] == 100 for entry in report["baselines"].values())
