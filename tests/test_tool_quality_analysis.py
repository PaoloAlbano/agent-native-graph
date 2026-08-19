from analyze_tool_quality import _suspicious_tools, _tool_metrics


def test_tool_metrics_counts_call_level_signals() -> None:
    rows = [
        {
            "matches_answer_json": False,
            "transcript": [
                {
                    "action": {"tool": "pattern_query"},
                    "result": {"matched_count": 0, "truncated": True},
                },
                {
                    "action": {"tool": "entity_set_operation"},
                    "result": {"matched_count": 1200, "truncated": False},
                },
                {
                    "action": {"tool": "fetch"},
                    "result": {"rows": [], "truncated": False},
                },
            ],
        },
        {
            "matches_answer_json": True,
            "transcript": [
                {
                    "action": {"tool": "pattern_query"},
                    "result": {"matched_count": 3, "truncated": False},
                },
                {
                    "action": {"tool": "fetch"},
                    "result": {"rows": [["ok"]], "truncated": False},
                },
            ],
        },
    ]

    metrics = _tool_metrics(rows)

    assert metrics["pattern_query"]["calls"] == 2
    assert metrics["pattern_query"]["tasks"] == 2
    assert metrics["pattern_query"]["zero"] == 1
    assert metrics["pattern_query"]["truncated"] == 1
    assert metrics["entity_set_operation"]["broad"] == 1
    assert metrics["fetch"]["last"] == 2
    assert metrics["fetch"]["wrong_last"] == 1


def test_fetch_is_not_flagged_as_suspicious_only_because_it_is_final() -> None:
    metrics = {
        "fetch": {
            "tasks": 20,
            "correct_tasks": 8,
            "errors": 0,
            "zero": 0,
            "broad": 0,
            "truncated": 0,
            "wrong_last": 12,
        },
        "node_scan": {
            "tasks": 20,
            "correct_tasks": 2,
            "errors": 0,
            "zero": 0,
            "broad": 0,
            "truncated": 20,
            "wrong_last": 0,
        },
    }

    suspicious = dict(_suspicious_tools(metrics))

    assert "fetch" not in suspicious
    assert "node_scan" in suspicious
