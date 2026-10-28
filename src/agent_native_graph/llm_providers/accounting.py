"""Passive, request-boundary accounting; no budgets, retries or prompt changes."""

import math
import time
from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps
from threading import Lock
from uuid import uuid4

_ACCOUNTING = ContextVar("llm_request_accounting", default=None)
_CALL = ContextVar("llm_logical_call", default=None)
_ROLE = ContextVar("llm_role", default="agent")


def _numbers(mapping):
    if not isinstance(mapping, dict):
        return {}
    return {
        k: v
        for k, v in mapping.items()
        if type(v) in (int, float) and (type(v) is int or math.isfinite(v)) and v >= 0
    }


def _usage(data):
    """Keep token numbers only; absence is unknown, never an inferred zero."""
    raw = data.get("usage") if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        return None
    result = {
        k: raw[k]
        for k in ("prompt_tokens", "completion_tokens", "total_tokens")
        if k in _numbers(raw)
    }
    for key in ("prompt_tokens_details", "completion_tokens_details"):
        details = _numbers(raw.get(key))
        if details:
            result[key] = details
    return result or None


class RequestAccounting:
    """One question's thread-safe ledger, shared by async roles via ContextVar.

    A snapshot may contain pending work after async cancellation: blocking HTTP
    in a worker thread is not cancelled by cancelling its awaiting coroutine.
    Never describe such a snapshot as complete cost accounting.
    """

    def __init__(self):
        self._lock = Lock()
        self._calls = []
        self._attempts = []

    def start_call(self, model):
        event = {
            "id": uuid4().hex,
            "model": model,
            "role": _ROLE.get(),
            "status": "pending",
            "error_type": None,
            "elapsed_s": None,
        }
        with self._lock:
            self._calls.append(event)
        return event

    def update(self, event, **values):
        with self._lock:
            event.update(values)

    def start_attempt(self, call, kind):
        with self._lock:
            retry = any(a["call_id"] == call["id"] and a["kind"] == kind for a in self._attempts)
            event = {
                "call_id": call["id"],
                "role": call["role"],
                "kind": kind,
                "index": len(self._attempts) + 1,
                "is_retry": retry,
                "status": "pending",
                "http_status": None,
                "error_type": None,
                "finish_reason": None,
                "completion_observed": False,
                "usage": None,
                "elapsed_s": None,
            }
            self._attempts.append(event)
        return event

    def snapshot(self, *, call_id=None):
        """Return an independent JSON-safe ledger and observed-only aggregates."""
        with self._lock:
            calls = deepcopy([c for c in self._calls if call_id is None or c["id"] == call_id])
            attempts = deepcopy(
                [a for a in self._attempts if call_id is None or a["call_id"] == call_id]
            )
        usage, fields, details = Counter(), Counter(), Counter()
        for attempt in attempts:
            raw = attempt["usage"] or {}
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                if key in raw:
                    usage[key] += raw[key]
                    fields[key] += 1
            for section in ("prompt_tokens_details", "completion_tokens_details"):
                for key, value in raw.get(section, {}).items():
                    details[f"{section}.{key}"] += value
        pending = sum(a["status"] == "pending" for a in attempts)
        return {
            "schema_version": 1,
            "calls": calls,
            "attempts": attempts,
            "summary": {
                "logical_calls": len(calls),
                "failed_logical_calls": sum(c["status"] == "error" for c in calls),
                "pending_logical_calls": sum(c["status"] == "pending" for c in calls),
                "http_attempts": len(attempts),
                "pending_http_attempts": pending,
                "failed_http_attempts": sum(a["status"] == "error" for a in attempts),
                "http_retry_attempts": sum(a["is_retry"] for a in attempts),
                "low_effort_http_attempts": sum(
                    a["kind"] == "low_effort_fallback" for a in attempts
                ),
                "observed_completion_responses": sum(a["completion_observed"] for a in attempts),
                "http_status_counts": dict(
                    Counter(str(a["http_status"]) for a in attempts if a["http_status"] is not None)
                ),
                "finish_reasons": dict(
                    Counter(a["finish_reason"] for a in attempts if a["finish_reason"] is not None)
                ),
                "attempts_with_usage": sum(a["usage"] is not None for a in attempts),
                "attempts_without_usage": sum(
                    a["usage"] is None and a["status"] != "pending" for a in attempts
                ),
                "observed_usage_totals": dict(usage),
                "usage_field_coverage": dict(fields),
                "observed_token_details_totals": dict(details),
                "http_elapsed_s": sum(a["elapsed_s"] or 0 for a in attempts),
                "logical_call_elapsed_s": sum(c["elapsed_s"] or 0 for c in calls),
                "requests_settled": not pending and all(c["status"] != "pending" for c in calls),
                "roles": dict(Counter(c["role"] for c in calls)),
            },
        }


def summarize_ledgers(ledgers):
    """Aggregate new ledgers without pretending legacy missing telemetry is zero."""
    observed = [ledger for ledger in ledgers if isinstance(ledger, dict)]
    if not observed:
        return None
    scalars, mappings = Counter(), {}
    for ledger in observed:
        for key, value in ledger["summary"].items():
            if type(value) in (int, float):
                scalars[key] += value
            elif isinstance(value, dict):
                mappings.setdefault(key, Counter()).update(value)
    return {
        "schema_version": 1,
        "instrumented_items": len(observed),
        "uninstrumented_items": len(ledgers) - len(observed),
        "requests_settled": all(ledger["summary"]["requests_settled"] for ledger in observed),
        **dict(scalars),
        **{key: dict(value) for key, value in mappings.items()},
    }


@contextmanager
def account_requests(accounting=None, *, role=None):
    """Scope observations without changing behavior; asyncio.to_thread copies context."""
    ledger = accounting if accounting is not None else RequestAccounting()
    token = _ACCOUNTING.set(ledger)
    role_token = _ROLE.set(role) if role is not None else None
    try:
        yield ledger
    finally:
        if role_token is not None:
            _ROLE.reset(role_token)
        _ACCOUNTING.reset(token)


@contextmanager
def request_role(role):
    """Label a reference agent while preserving the question's existing ledger."""
    token = _ROLE.set(role)
    try:
        yield
    finally:
        _ROLE.reset(token)


def tracked_chat(method):
    """Observe logical calls, including calls that fail before returning metadata."""

    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with _logical_call(self._model) as (ledger, call):
            message = method(self, *args, **kwargs)
        message["__chat_meta"]["request_accounting"] = ledger.snapshot(call_id=call["id"])
        return message

    return wrapped


def tracked_async_chat(method):
    """Observe async calls through cancellation, after client cleanup has finished."""

    @wraps(method)
    async def wrapped(self, *args, **kwargs):
        with _logical_call(self._model) as (ledger, call):
            message = await method(self, *args, **kwargs)
        message["__chat_meta"]["request_accounting"] = ledger.snapshot(call_id=call["id"])
        return message

    return wrapped


@contextmanager
def _logical_call(model):
    ledger = _ACCOUNTING.get() or RequestAccounting()
    call = ledger.start_call(model)
    started = time.perf_counter()
    token = _CALL.set((ledger, call))
    try:
        yield ledger, call
        ledger.update(call, status="ok")
    except BaseException as exc:
        ledger.update(call, status="error", error_type=type(exc).__name__)
        raise
    finally:
        ledger.update(call, elapsed_s=time.perf_counter() - started)
        _CALL.reset(token)


@contextmanager
def _http_attempt(kind):
    context = _CALL.get()
    if context is None:
        raise RuntimeError("post_chat must run inside a tracked provider call")
    ledger, call = context
    attempt = ledger.start_attempt(call, kind)
    started = time.perf_counter()
    try:
        yield ledger, attempt
    except BaseException as exc:
        ledger.update(attempt, status="error", error_type=type(exc).__name__)
        raise
    finally:
        ledger.update(attempt, elapsed_s=time.perf_counter() - started)


def _record_response(ledger, attempt, response):
    ledger.update(attempt, http_status=response.status_code)
    response.raise_for_status()
    data = response.json()
    choices = data.get("choices") if isinstance(data, dict) else None
    choice = choices[0] if isinstance(choices, list) and choices else None
    reason = choice.get("finish_reason") if isinstance(choice, dict) else None
    ledger.update(
        attempt,
        status="ok",
        usage=_usage(data),
        completion_observed=isinstance(choice, dict) and isinstance(choice.get("message"), dict),
        finish_reason=reason if isinstance(reason, str) else None,
    )
    return data


def post_chat(client, url, *, headers, payload, kind):
    """Observe synchronous POSTs without storing credentials or prompt content."""
    with _http_attempt(kind) as (ledger, attempt):
        return _record_response(ledger, attempt, client.post(url, headers=headers, json=payload))


async def post_chat_async(client, url, *, headers, payload, kind):
    """Observe cancellable HTTP POSTs through the same request ledger."""
    with _http_attempt(kind) as (ledger, attempt):
        response = await client.post(url, headers=headers, json=payload)
        return _record_response(ledger, attempt, response)
