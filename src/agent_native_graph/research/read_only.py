"""Bounded Neo4j read execution shared by live baselines and saved-query scoring."""

import math
import time

from neo4j import READ_ACCESS, Query

from agent_native_graph.research_common import normalize_answer_rows


def _validate(database, cypher, timeout, max_rows):
    if not isinstance(cypher, str) or not cypher.strip():
        raise ValueError("missing_generated_cypher")
    if not isinstance(database, str) or not database.strip():
        raise ValueError("missing_database")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("invalid_query_timeout")
    if type(max_rows) is not int or max_rows < 1:
        raise ValueError("invalid_row_limit")


def _result():
    return {"ok": False, "rows": [], "columns": [], "error": None, "failure_class": None}


def _error(result, exc):
    result.update(ok=False, rows=[], error=f"{type(exc).__name__}: {exc}")
    result["failure_class"] = getattr(exc, "code", None) or (
        str(exc) if isinstance(exc, ValueError) else type(exc).__name__
    )


def execute_read_only(driver, database, cypher, timeout, max_rows=100000, *, parameters=None):
    """Reject non-read plans, stream bounded rows in a transaction, always rollback."""
    started, result = time.perf_counter(), _result()
    try:
        _validate(database, cypher, timeout, max_rows)
        with driver.session(database=database, default_access_mode=READ_ACCESS) as session:
            plan = session.run(
                Query("EXPLAIN " + cypher, timeout=timeout),
                **({"parameters": parameters} if parameters is not None else {}),
            ).consume()
            if plan.query_type != "r":
                raise ValueError("non_read_query_rejected")
            with session.begin_transaction(timeout=timeout) as tx:
                try:
                    cursor = tx.run(
                        cypher, **({"parameters": parameters} if parameters is not None else {})
                    )
                    result["columns"] = list(cursor.keys())
                    rows = []
                    for record in cursor:
                        if len(rows) >= max_rows:
                            raise ValueError("result_row_limit")
                        rows.append(list(record.values()))
                    result.update(ok=True, rows=normalize_answer_rows(rows))
                finally:
                    tx.rollback()
    except Exception as exc:
        _error(result, exc)
    result["elapsed_s"] = time.perf_counter() - started
    return result


async def execute_read_only_async(
    driver, database, cypher, timeout, max_rows=100000, *, parameters=None
):
    """Async equivalent; cancellation propagates after the transaction rollback."""
    started, result = time.perf_counter(), _result()
    try:
        _validate(database, cypher, timeout, max_rows)
        async with driver.session(database=database, default_access_mode=READ_ACCESS) as session:
            cursor = await session.run(
                Query("EXPLAIN " + cypher, timeout=timeout), parameters=parameters or {}
            )
            if (await cursor.consume()).query_type != "r":
                raise ValueError("non_read_query_rejected")
            async with await session.begin_transaction(timeout=timeout) as tx:
                try:
                    cursor = await tx.run(cypher, parameters=parameters or {})
                    result["columns"] = list(cursor.keys())
                    rows = []
                    async for record in cursor:
                        if len(rows) >= max_rows:
                            raise ValueError("result_row_limit")
                        rows.append(list(record.values()))
                    result.update(ok=True, rows=normalize_answer_rows(rows))
                finally:
                    await tx.rollback()
    except Exception as exc:
        _error(result, exc)
    result["elapsed_s"] = time.perf_counter() - started
    return result
