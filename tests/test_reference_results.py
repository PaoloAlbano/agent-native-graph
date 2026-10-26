import hashlib
import json
from pathlib import Path

import pytest

from agent_native_graph.research.archive_reference_baseline import DEFAULT_ARCHIVE_ROOT, archive
from agent_native_graph.research.compare_company_results import _output_paths, compare


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_reference_archive_defaults_to_ignored_local_results() -> None:
    assert DEFAULT_ARCHIVE_ROOT == Path(
        ".local-results/baselines/multigraphrag/cypherbench-company"
    )


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    tasks = tmp_path / "tasks.jsonl"
    graph = tmp_path / "graph.json"
    run = tmp_path / "direct.jsonl"
    _write_jsonl(tasks, [{"qid": "q1"}, {"qid": "q2"}])
    graph.write_text("{}", encoding="utf-8")
    _write_jsonl(
        run,
        [
            {
                "qid": "q1",
                "approach": "multigraphrag_direct",
                "expected": [["Alice"]],
                "rows": [["Alice"]],
                "matches_answer_json": True,
                "ok": True,
                "llm_call_count": 2,
                "elapsed_s": 1.0,
                "error": None,
            },
            {
                "qid": "q2",
                "approach": "multigraphrag_direct",
                "expected": [["Bob"]],
                "rows": [],
                "matches_answer_json": False,
                "ok": True,
                "llm_call_count": 3,
                "elapsed_s": 2.0,
                "error": None,
            },
        ],
    )
    run.with_suffix(".meta.json").write_text(
        json.dumps(
            {
                "approach": "multigraphrag_direct",
                "mode": "direct",
                "benchmark": "cypherbench-company",
                "suite": "n2",
                "split": "test",
                "source_repo": "reference",
                "source_commit": "123abc",
                "model": "test/model",
                "temperature": 0.0,
                "reasoning": "none",
                "max_tokens": 16000,
                "concurrency": 1,
                "limit": 2,
                "scoring": "ana_exact_answer_json_on_replayed_cypher",
                "tasks_sha256": _digest(tasks),
                "graph_sha256": _digest(graph),
                "max_score_rows": 10000,
                "call_logs": [],
            }
        ),
        encoding="utf-8",
    )
    return run, tasks, graph


def test_archive_rejects_incomplete_reference_run(tmp_path: Path) -> None:
    run, tasks, graph = _fixture(tmp_path)
    lines = run.read_text(encoding="utf-8").splitlines()
    run.write_text(lines[0] + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Incomplete run"):
        archive(run, tmp_path / "results", tasks, graph)


def test_comparison_paths_keep_dots_in_model_name(tmp_path: Path) -> None:
    base = tmp_path / "qwen3.5-temp0-n20"
    assert _output_paths(base) == (
        base.parent / f"{base.name}.json",
        base.parent / f"{base.name}.md",
    )
    assert _output_paths(base.with_name("comparison.json")) == (
        base.with_name("comparison.json"),
        base.with_name("comparison.md"),
    )


def test_archive_and_compare_require_matching_qids_and_profiles(tmp_path: Path) -> None:
    run, tasks, graph = _fixture(tmp_path)
    direct = archive(run, tmp_path / "baselines", tasks, graph)
    summary = json.loads((direct / "summary.json").read_text(encoding="utf-8"))
    assert summary["correct"] == 1
    assert summary["average_llm_calls"] == 2.5

    ana = tmp_path / "ana"
    agentic = tmp_path / "agentic"
    for target, approach in ((ana, "agent_tools_neo4j"), (agentic, "multigraphrag_agentic")):
        target.mkdir()
        rows = [json.loads(line) for line in (direct / "run.jsonl").read_text().splitlines()]
        for row in rows:
            row["approach"] = approach
        if target == agentic:
            rows[1]["rows"] = [["Bob"]]
            rows[1]["matches_answer_json"] = True
        _write_jsonl(target / "run.jsonl", rows)
        (target / "manifest.json").write_text(
            json.dumps(
                {
                    "run_id": target.name,
                    "approach": approach,
                    "run_sha256": _digest(target / "run.jsonl"),
                    "model": "test/model",
                    "temperature": 0.0,
                    "reasoning": "none",
                    "max_tokens": 16000,
                    "limit": 2,
                    "suite": "n2",
                    "tasks_sha256": _digest(tasks),
                    "graph_sha256": _digest(graph),
                }
            ),
            encoding="utf-8",
        )

    result = compare(ana, direct, agentic)
    assert result["runs"]["ANA"]["correct"] == 1
    assert result["paired"]["Multi-Agent GraphRAG"]["baseline_only"] == 1

    gold_validation = tmp_path / "gold.jsonl"
    _write_jsonl(
        gold_validation,
        [
            {"qid": "q1", "matches_answer_json": True},
            {"qid": "q2", "matches_answer_json": False},
            {"qid": "q3", "matches_answer_json": True},
        ],
    )
    result = compare(ana, direct, agentic, gold_validation)
    assert result["gold_reproducible"]["total"] == 1
    assert result["gold_reproducible"]["excluded_qids"] == ["q2"]
    assert result["runs"]["ANA"]["gold_reproducible_correct"] == 1

    _write_jsonl(gold_validation, [{"qid": "q1", "matches_answer_json": True}])
    with pytest.raises(ValueError, match="do not cover"):
        compare(ana, direct, agentic, gold_validation)

    manifest_path = agentic / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["temperature"] = 1.0
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="profiles differ"):
        compare(ana, direct, agentic)
