import json
from pathlib import Path

from agent_native_graph.research.archive_result import (
    _archive_root,
    _failure_record,
    _refresh_index,
    _suite,
    _summary,
)


def test_suite_names_standard_benchmark_splits() -> None:
    assert _suite(347) == "full"
    assert _suite(100) == "first100"
    assert _suite(20) == "n20"


def test_diagnostic_runs_default_to_local_archive() -> None:
    assert _archive_root(Path("results"), 347) == Path("results")
    assert _archive_root(Path("results"), 100) == Path(".local-results")
    assert _archive_root(Path("custom"), 20) == Path("custom")


def test_index_contains_only_full_runs_and_does_not_write_leaderboard(tmp_path: Path) -> None:
    for suite, limit in (("full", 347), ("n20", 20)):
        run_dir = tmp_path / suite / "runs" / suite
        run_dir.mkdir(parents=True)
        (run_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "run_id": suite,
                    "suite": suite,
                    "model": "example-model",
                    "temperature": 0,
                    "reasoning": "none",
                    "limit": limit,
                }
            )
        )
        (run_dir / "summary.json").write_text(
            json.dumps(
                {
                    "accuracy": 0.5,
                    "executable_rate": 1.0,
                    "avg_tool_calls": 2.0,
                    "avg_llm_calls": 2.0,
                }
            )
        )

    _refresh_index(tmp_path)

    index = json.loads((tmp_path / "index.json").read_text())
    assert [record["run_id"] for record in index] == ["full"]
    assert not (tmp_path / "leaderboard.md").exists()


def test_failure_record_exposes_category_for_jsonl_analysis() -> None:
    row = {
        "qid": "q1",
        "matches_answer_json": False,
        "failure_class": "backend_timeout",
    }

    failure = _failure_record(row)

    assert failure["failure_category"] == "backend_timeout"


def test_summary_counts_failure_classes_and_total() -> None:
    rows = [
        {
            "ok": True,
            "matches_answer_json": False,
            "tool_call_count": 2,
            "tool_error_count": 0,
            "llm_call_count": 2,
            "failure_class": "semantic_mismatch",
            "llm_call_metrics": [],
            "transcript": [],
        },
        {
            "ok": False,
            "matches_answer_json": False,
            "tool_call_count": 1,
            "tool_error_count": 1,
            "llm_call_count": 1,
            "failure_class": "backend_timeout",
            "llm_call_metrics": [],
            "transcript": [],
        },
    ]

    summary = _summary(rows, "run")

    assert summary["failure_classes"] == {
        "backend_timeout": 1,
        "semantic_mismatch": 1,
    }
    assert summary["failure_total"] == 2


def test_summary_counts_nested_llm_usage_tokens() -> None:
    rows = [
        {
            "ok": True,
            "matches_answer_json": True,
            "tool_call_count": 1,
            "tool_error_count": 0,
            "llm_call_count": 1,
            "llm_call_metrics": [
                {
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 4,
                        "total_tokens": 14,
                    }
                }
            ],
            "transcript": [],
        },
    ]

    summary = _summary(rows, "run")

    assert summary["llm_prompt_tokens"] == 10
    assert summary["llm_completion_tokens"] == 4
    assert summary["llm_total_tokens"] == 14
