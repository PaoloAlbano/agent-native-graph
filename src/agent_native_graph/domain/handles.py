"""Server-side handle models used by ANA graph tools."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Handle:
    """Represents intermediate graph state kept server-side between tool calls."""

    id: str
    rows: list[dict[str, Any]]
    focus: str | None = None
    kind: str = "rows"
    columns: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
