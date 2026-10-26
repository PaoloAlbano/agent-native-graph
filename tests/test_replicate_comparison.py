import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from agent_native_graph.research.compare_replicates import compare


def _run(path: Path, outcomes: dict[str, bool], *, model: str = "model") -> Path:
    path.mkdir()
    run_file = path / "run.jsonl"
    run_file.write_text(
        "".join(
            json.dumps({"qid": qid, "matches_answer_json": correct}) + "\n"
            for qid, correct in outcomes.items()
        ),
        encoding="utf-8",
    )
    (path / "manifest.json").write_text(
        json.dumps(
            {
                "run_sha256": hashlib.sha256(run_file.read_bytes()).hexdigest(),
                "approach": "agent_tools_neo4j",
                "model": model,
                "temperature": 0,
                "reasoning": "none",
                "max_tokens": 16000,
                "concurrency": 5,
                "limit": len(outcomes),
                "tasks_sha256": "tasks",
                "graph_sha256": "graph",
            }
        ),
        encoding="utf-8",
    )
    return path


def test_replicate_comparison_tracks_outcome_changes(tmp_path: Path) -> None:
    first = _run(tmp_path / "first", {"a": True, "b": False, "c": True})
    second = _run(tmp_path / "second", {"a": True, "b": True, "c": False})
    result = compare(first, second)
    assert result["first_correct"] == result["second_correct"] == 2
    assert result["fixed_qids"] == ["b"]
    assert result["regressed_qids"] == ["c"]
    assert result["answer_outcome_disagreement"] == 2


def test_replicate_comparison_rejects_different_model(tmp_path: Path) -> None:
    first = _run(tmp_path / "first", {"a": True})
    second = _run(tmp_path / "second", {"a": True}, model="other")
    with pytest.raises(ValueError, match="profile"):
        compare(first, second)


def test_replicate_comparison_rejects_concurrency_difference(tmp_path: Path) -> None:
    first = _run(tmp_path / "first", {"a": True})
    second = _run(tmp_path / "second", {"a": True})
    manifest_path = second / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["concurrency"] = 2
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="concurrency"):
        compare(first, second)
    assert not compare(first, second, allow_concurrency_diff=True)["same_concurrency"]
