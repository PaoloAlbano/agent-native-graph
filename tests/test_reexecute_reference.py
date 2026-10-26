from types import SimpleNamespace
from unittest.mock import MagicMock

from agent_native_graph.research.reexecute_reference import execute_read_only, fingerprint
from agent_native_graph.research_common import result_matches_answer


def driver_fixture(query_type="r", values=None):
    driver = MagicMock()
    session = driver.session.return_value.__enter__.return_value
    session.run.return_value.consume.return_value = SimpleNamespace(query_type=query_type)
    tx = session.begin_transaction.return_value.__enter__.return_value
    tx.run.return_value.keys.return_value = ["value"]
    tx.run.return_value.__iter__.return_value = iter(
        [SimpleNamespace(values=lambda value=value: [value]) for value in (values or [])]
    )
    return driver, session, tx


def test_read_uses_real_timeout_and_rolls_back():
    driver, session, tx = driver_fixture(values=[1, 2])
    result = execute_read_only(driver, "neo4j", "RETURN 1", 30)
    assert result["ok"] and result["rows"] == [[1], [2]]
    assert session.run.call_args.args[0].timeout == 30
    session.begin_transaction.assert_called_once_with(timeout=30)
    tx.rollback.assert_called_once()
    tx.commit.assert_not_called()


def test_write_query_never_executes():
    driver, session, tx = driver_fixture(query_type="rw")
    result = execute_read_only(driver, "neo4j", "CREATE (n) RETURN n", 30)
    assert result["failure_class"] == "non_read_query_rejected"
    session.begin_transaction.assert_not_called()
    tx.run.assert_not_called()


def test_row_limit_does_not_score_partial_results():
    driver, _, tx = driver_fixture(values=[1, 2])
    result = execute_read_only(driver, "neo4j", "RETURN 1", 30, max_rows=1)
    assert not result["ok"] and result["rows"] == []
    assert result["failure_class"] == "result_row_limit"
    tx.rollback.assert_called_once()


def test_error_is_structured_and_rollback_happens():
    driver, _, tx = driver_fixture()
    tx.run.side_effect = RuntimeError("test failure")
    result = execute_read_only(driver, "neo4j", "RETURN 1", 30)
    assert result["failure_class"] == "RuntimeError"
    assert not result["ok"]
    tx.rollback.assert_called_once()


def test_missing_query_does_not_open_session():
    driver = MagicMock()
    assert (
        execute_read_only(driver, "neo4j", None, 30)["failure_class"] == "missing_generated_cypher"
    )
    driver.session.assert_not_called()


def test_snapshot_preserves_content_and_multiplicity_not_order():
    assert fingerprint([{"x": 1}, {"x": 2}]) == fingerprint([{"x": 2}, {"x": 1}])
    assert fingerprint([{"x": 1}]) != fingerprint([{"x": 2}])
    assert fingerprint([{"x": 1}]) != fingerprint([{"x": 1}, {"x": 1}])


def test_exact_scoring_ignores_row_order_not_columns_or_duplicates():
    assert result_matches_answer([[1], [2]], [[2], [1]])
    assert not result_matches_answer([[1, 2]], [[2, 1]])
    assert not result_matches_answer([[1]], [[1], [1]])
