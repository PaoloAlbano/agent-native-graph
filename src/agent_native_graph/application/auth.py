"""Small static API-key policy for a controlled demo, independent of transport/engine."""

import hashlib
import hmac
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from agent_native_graph.core.enums import ToolProfile


class AuthenticationError(ValueError):
    """The supplied bearer credential is missing or unknown."""


class AuthNotConfigured(RuntimeError):
    """No clients have been configured; data endpoints must remain closed."""


@dataclass(frozen=True)
class Principal:
    subject: str
    profile: ToolProfile = ToolProfile.READONLY

    def permits(self, profile: ToolProfile | str) -> bool:
        """A read-write grant includes read tools, never the reverse."""
        return self.profile == ToolProfile.READWRITE or ToolProfile(profile) == ToolProfile.READONLY


@dataclass(frozen=True)
class ApiKeyClient:
    subject: str
    api_key: str = field(repr=False)
    profile: ToolProfile = ToolProfile.READONLY

    def __post_init__(self) -> None:
        if not isinstance(self.subject, str) or not self.subject.strip():
            raise ValueError("Client id must be a nonempty string")
        if not isinstance(self.api_key, str) or len(self.api_key) < 32:
            raise ValueError("Client API keys must contain at least 32 characters")
        if self.api_key != self.api_key.strip() or any(c.isspace() for c in self.api_key):
            raise ValueError("Client API keys must not contain whitespace")
        object.__setattr__(self, "profile", ToolProfile(self.profile))


class ApiKeyAuth:
    """Snapshot a server-owned client file; never accept permission grants from requests."""

    def __init__(self, clients: tuple[ApiKeyClient, ...] = ()) -> None:
        self._clients = tuple(clients)
        if len({c.subject for c in self._clients}) != len(self._clients):
            raise ValueError("Client ids must be unique")
        if len({c.api_key for c in self._clients}) != len(self._clients):
            raise ValueError("Client API keys must be unique")

    @classmethod
    def from_env(cls) -> "ApiKeyAuth":
        """Load ANA_AUTH_FILE once; an unset file configures no authenticated clients."""
        path = os.getenv("ANA_AUTH_FILE")
        if not path:
            return cls()
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if set(data) != {"clients"} or not isinstance(data["clients"], list):
                raise ValueError
            clients = []
            for item in data["clients"]:
                if not isinstance(item, dict) or set(item) - {"id", "api_key", "profile"}:
                    raise ValueError
                clients.append(
                    ApiKeyClient(item["id"], item["api_key"], item.get("profile", "readonly"))
                )
            return cls(tuple(clients))
        except (OSError, ValueError, KeyError, TypeError):
            raise ValueError("Invalid ANA_AUTH_FILE; check client ids, keys and profiles") from None

    def authenticate(self, authorization: str | None) -> Principal:
        """Validate a bearer key without including credentials in errors or reprs."""
        if not self._clients:
            raise AuthNotConfigured("Server authentication is not configured")
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise AuthenticationError("Invalid or missing bearer credential")
        supplied = hashlib.sha256(token.encode()).digest()
        matched = None
        for client in self._clients:
            expected = hashlib.sha256(client.api_key.encode()).digest()
            if hmac.compare_digest(supplied, expected):
                matched = client
        if matched is None:
            raise AuthenticationError("Invalid or missing bearer credential")
        return Principal(matched.subject, matched.profile)
