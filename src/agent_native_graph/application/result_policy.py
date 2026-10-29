"""Opt-in research result bounds; completeness always names its limited scope."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

_observations = ContextVar("ana_result_observations", default=None)
_candidate = ContextVar("ana_candidate_result", default=False)


@dataclass(frozen=True)
class BoundedResults:
    """Versioned research bounds, independent of model profiles and public tools."""

    name: str = "bounded-v1"
    preview_rows: int = 20
    max_rows: int = 100000


def result_policy(name):
    """Absence preserves historical behavior; unknown versions fail closed."""
    if name is None:
        return None
    if name != "bounded-v1":
        raise ValueError("Unknown result policy")
    return BoundedResults()


def completeness(policy, *, scope, available, collected, preview, complete, error=None):
    """Describe query/handle coverage, never completeness of the whole graph."""
    return {
        "policy": policy.name,
        "scope": scope,
        "status": "error" if error else ("complete" if complete else "partial"),
        "available_count": available,
        "collected_count": collected,
        "preview_count": preview,
        "preview_truncated": collected > preview,
        "complete": complete and error is None,
        "upstream_completeness": "unknown" if scope == "stored_handle" else "not_claimed",
        "error": error,
    }


@contextmanager
def observe_results():
    """Own observations per question, including inherited asynchronous role tasks."""
    entries = []
    token = _observations.set(entries)
    try:
        yield entries
    finally:
        _observations.reset(token)


def record_observation(value):
    """Append to the owning question only; setup/probes outside it are not captured."""
    entries = _observations.get()
    if entries is not None:
        entries.append(value)


class CandidatePreviewGraph:
    """Mark controller executions only; verification/introspection keep their own limits."""

    def __init__(self, graph):
        self.graph = graph

    def __getattr__(self, name):
        return getattr(self.graph, name)

    async def run_query(self, *args, **kwargs):
        token = _candidate.set(True)
        try:
            return await self.graph.run_query(*args, **kwargs)
        finally:
            _candidate.reset(token)


def candidate_result():
    """Tell graph adapters whether this read is a controller candidate or introspection."""
    return _candidate.get()


def collect_handle(backend, action, page, policy):
    """Collect a model-finalized stored handle for scoring, never choose an earlier one.

    A second fetch is bounded and starts at zero, including when the model asked
    for a later page. Tool limits upstream are not repaired by this operation.
    """
    backend.last_fetch = None

    def validate(value):
        rows = value.get("rows")
        total, offset, count = (value.get(k) for k in ("total_count", "offset", "returned_count"))
        if (
            not isinstance(rows, list)
            or any(type(n) is not int or n < 0 for n in (total, offset, count))
            or count != len(rows)
            or offset > total
            or offset + count > total
        ):
            raise ValueError("invalid_fetch_coverage")
        if total > policy.max_rows:
            raise ValueError("result_row_limit")
        end = offset + count
        if value.get("next_offset") != (end if end < total else None):
            raise ValueError("invalid_fetch_pagination")
        if value.get("truncated") is not (end < total):
            raise ValueError("invalid_fetch_pagination")
        return total, offset, count

    total, offset, count = validate(page)
    final = page
    if offset != 0 or count != total:
        if not (action.get("args") or {}).get("from"):
            raise ValueError("missing_final_handle")
        args = {**action["args"], "offset": 0, "limit": max(total, 1)}
        try:
            final = backend.call("fetch", args)
            new_total, offset, count = validate(final)
            if (
                new_total != total
                or offset != 0
                or count != total
                or final.get("columns") != page.get("columns")
            ):
                raise ValueError("incomplete_final_handle")
        except Exception:
            backend.last_fetch = None
            raise
    backend.last_fetch = final["rows"]
    metadata = completeness(
        policy,
        scope="stored_handle",
        available=total,
        collected=total,
        preview=min(total, policy.preview_rows),
        complete=True,
    )
    return {**final, "result_completeness": metadata, "evaluation_collection": final is not page}
