"""App-owned workflow sessions, independent of graph engine and HTTP transport."""

import logging
import math
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from agent_native_graph.core.backend import AgentGraphBackend
from agent_native_graph.core.handle_store import HandleStore

BackendFactory = Callable[[HandleStore], AgentGraphBackend]
logger = logging.getLogger(__name__)


class SessionNotFound(ValueError):
    pass


class SessionCapacityError(RuntimeError):
    pass


@dataclass(frozen=True)
class SessionConfig:
    max_sessions: int = 128
    idle_timeout_s: float = 1800

    def __post_init__(self) -> None:
        if type(self.max_sessions) is not int or self.max_sessions < 1:
            raise ValueError("max_sessions must be a positive integer")
        if (
            isinstance(self.idle_timeout_s, bool)
            or not isinstance(self.idle_timeout_s, int | float)
            or not math.isfinite(self.idle_timeout_s)
            or self.idle_timeout_s <= 0
        ):
            raise ValueError("idle_timeout_s must be finite and positive")


@dataclass
class _Session:
    backend: AgentGraphBackend
    store: HandleStore
    last_used: float
    owner_id: str | None = None
    active: int = 0
    closed: bool = False
    lock: Any = field(default_factory=threading.Lock)

    def close(self) -> None:
        with self.lock:
            if self.closed:
                return
            self.closed = True
            try:
                self.backend.close()
            finally:
                self.store.clear()


class BackendSessions:
    """Own backend instances, serialize each workflow and drain them on shutdown.

    Factories must use the supplied store; its namespace prevents local handle
    names from resolving in another session. The transport supplies a trusted
    owner ID after authentication; the registry checks it alongside the workflow
    token. Tokens alone are not authentication. Idle expiry is checked on requests, not by a background
    reaper. State is process-local and unsuitable for uncoordinated workers.
    """

    def __init__(
        self,
        factory: BackendFactory,
        config: SessionConfig | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._factory = factory
        self.config = config or SessionConfig()
        self._clock = clock
        self._sessions: dict[str, _Session] = {}
        self._lock = threading.Lock()
        self._idle = threading.Condition(self._lock)
        self._creating = 0
        self._closed = False

    def _expire_idle(self) -> None:
        expired = []
        with self._lock:
            now = self._clock()
            for token, entry in list(self._sessions.items()):
                if entry.active == 0 and now - entry.last_used >= self.config.idle_timeout_s:
                    expired.append(self._sessions.pop(token))
        for entry in expired:
            try:
                entry.close()
            except Exception:
                logger.warning("Failed to close an expired workflow backend")

    def create(self, *, owner_id: str | None = None) -> str:
        """Reserve capacity, create one owned backend and return an opaque capability."""
        self._expire_idle()
        with self._lock:
            if self._closed:
                raise RuntimeError("Session manager is closed")
            if len(self._sessions) + self._creating >= self.config.max_sessions:
                raise SessionCapacityError("Session capacity reached")
            self._creating += 1
        store = HandleStore.isolated()
        try:
            backend = self._factory(store)
        except BaseException:
            with self._lock:
                self._creating -= 1
                self._idle.notify_all()
            store.clear()
            raise
        entry = _Session(backend, store, self._clock(), owner_id=owner_id)
        with self._lock:
            closed = self._closed
            if not closed:
                token = secrets.token_urlsafe(32)
                self._sessions[token] = entry
                self._creating -= 1
                self._idle.notify_all()
        if closed:
            try:
                entry.close()
            finally:
                with self._lock:
                    self._creating -= 1
                    self._idle.notify_all()
            raise RuntimeError("Session manager is closed")
        return token

    def call(
        self, token: str, tool: str, args: dict[str, Any], *, owner_id: str | None = None
    ) -> dict[str, Any]:
        """Reserve a live session, protecting it from expiry while queued or executing."""
        self._expire_idle()
        with self._lock:
            entry = self._sessions.get(token)
            if entry is None or self._closed or entry.owner_id != owner_id:
                raise SessionNotFound("Unknown or expired session")
            entry.active += 1
        try:
            with entry.lock:
                if entry.closed:
                    raise SessionNotFound("Unknown or expired session")
                return entry.backend.call(tool, args)
        finally:
            with self._lock:
                entry.active -= 1
                entry.last_used = self._clock()

    def delete(self, token: str, *, owner_id: str | None = None) -> None:
        """Forget a session and wait for its current operation before releasing it."""
        self._expire_idle()
        with self._lock:
            entry = self._sessions.get(token)
            if entry is None or entry.owner_id != owner_id:
                raise SessionNotFound("Unknown or expired session")
            del self._sessions[token]
        entry.close()

    def close(self) -> None:
        """Reject new sessions and attempt cleanup of every backend, even after errors."""
        with self._lock:
            self._closed = True
            while self._creating:
                self._idle.wait()
            entries = list(self._sessions.values())
            self._sessions.clear()
        errors = []
        for entry in entries:
            try:
                entry.close()
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise ExceptionGroup("Failed to close workflow backends", errors)
