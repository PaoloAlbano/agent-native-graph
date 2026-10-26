import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from agent_native_graph.research.audit_execution_accuracy import audit
from agent_native_graph.research.execution_equivalence import execution_equivalent


def test_unordered_rows_and_column_permutation() -> None:
    assert execution_equivalent([[1, "A"], [2, "B"]], [["B", 2], ["A", 1]], order_matters=False)


def test_ordered_rows_are_not_permuted() -> None:
    assert not execution_equivalent([[2], [1]], [[1], [2]], order_matters=True)


def test_duplicate_rows_matter() -> None:
    assert not execution_equivalent([[1], [1]], [[1], [2]], order_matters=False)


def test_list_cell_order_does_not_matter() -> None:
    assert execution_equivalent([[["B", "A"]]], [[["A", "B"]]], order_matters=False)


def test_audit_uses_gold_order_and_checks_task_pairing(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    gold.write_text(
        json.dumps(
            {
                "qid": "one",
                "query": "RETURN n ORDER BY n",
                "rows": [[1], [2]],
                "expected": [[1], [2]],
                "ok": True,
                "matches_answer_json": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    run = tmp_path / "run"
    run.mkdir()
    row = {
        "qid": "one",
        "gold_cypher": "RETURN n ORDER BY n",
        "rows": [[2], [1]],
        "expected": [[1], [2]],
        "ok": True,
        "matches_answer_json": True,
        "nl_question": "List in order",
    }
    run_file = run / "run.jsonl"
    run_file.write_text(json.dumps(row) + "\n", encoding="utf-8")
    (run / "manifest.json").write_text(
        json.dumps(
            {
                "run_sha256": hashlib.sha256(run_file.read_bytes()).hexdigest(),
                "model": "test",
                "approach": "agent_tools_neo4j",
            }
        ),
        encoding="utf-8",
    )
    result = audit(gold, [run])
    assert result["runs"][0]["exact_correct"] == 1
    assert result["runs"][0]["execution_equivalent_correct"] == 0
    row["gold_cypher"] = "RETURN n"
    run_file.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        audit(gold, [run])
