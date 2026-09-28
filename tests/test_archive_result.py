from archive_result import _failure_record, _suite, _summary


def test_suite_names_standard_benchmark_splits() -> None:
    assert _suite(347) == "full"
    assert _suite(100) == "first100"
    assert _suite(20) == "n20"


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
