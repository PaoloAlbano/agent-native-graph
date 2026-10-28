"""Question-scoped deadlines and ownership of cancellable asynchronous requests."""

import asyncio
import math
import time
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar

_DEADLINE = ContextVar("llm_question_deadline", default=None)
_REQUEST_GROUP = ContextVar("llm_question_requests", default=None)


class TaskTimeoutError(TimeoutError):
    """The question's elapsed-time allowance expired, including retry waits."""


class Deadline:
    """A monotonic deadline; None preserves the runner's unlimited default."""

    def __init__(self, seconds=None):
        if seconds is not None and (
            isinstance(seconds, bool)
            or not isinstance(seconds, int | float)
            or not math.isfinite(seconds)
            or seconds <= 0
        ):
            raise ValueError("Task timeout must be positive and finite")
        self.expires = None if seconds is None else time.monotonic() + seconds

    def remaining(self):
        if self.expires is None:
            return None
        remaining = self.expires - time.monotonic()
        if remaining <= 0:
            raise TaskTimeoutError("Question deadline exceeded")
        return remaining


def current_deadline():
    return _DEADLINE.get()


def ensure_question_open():
    """Reject late role work before it starts HTTP or writes to a closed call log."""
    group = _REQUEST_GROUP.get()
    if group is not None and group["closed"]:
        raise asyncio.CancelledError("Question request scope is closed")


async def gather_and_settle(awaitables):
    """Keep gather's results/errors but drain cancelled siblings and queued work."""
    tasks = [asyncio.create_task(item) for item in awaitables]
    try:
        return await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done() and not task.cancelling():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@contextmanager
def deadline_scope(deadline):
    """Propagate one elapsed-time deadline across all roles, retries and fallbacks."""
    token = _DEADLINE.set(deadline)
    try:
        yield
    finally:
        _DEADLINE.reset(token)


@asynccontextmanager
async def question_requests():
    """Cancel and await active sibling requests before saving a question's ledger.

    Reference batching uses gather, which can leave siblings running when one
    branch fails. Track only tasks performing LLM calls, not unrelated questions.
    """
    group = {"tasks": set(), "closed": False}
    token = _REQUEST_GROUP.set(group)
    try:
        yield
    finally:
        group["closed"] = True
        pending = [
            task
            for task in group["tasks"]
            if task is not asyncio.current_task() and not task.done()
        ]
        for task in pending:
            if not task.cancelling():
                task.cancel()
        try:
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        finally:
            _REQUEST_GROUP.reset(token)


@asynccontextmanager
async def active_request():
    """Own this request task and interrupt HTTP or retry waits at the deadline."""
    group = _REQUEST_GROUP.get()
    task = asyncio.current_task()
    ensure_question_open()
    if group is not None:
        group["tasks"].add(task)
    deadline = current_deadline()
    try:
        async with asyncio.timeout(deadline.remaining() if deadline else None):
            yield
    except TimeoutError:
        if deadline is not None:
            deadline.remaining()
        raise
    finally:
        if group is not None:
            group["tasks"].discard(task)
