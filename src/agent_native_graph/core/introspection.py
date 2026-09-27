"""Abstract schema introspection contract for graph backends."""

from abc import ABC, abstractmethod
from typing import Any


class GraphSchemaIntrospector(ABC):
    """Base class for backend-specific schema discovery."""

    @abstractmethod
    def introspect_schema(self) -> dict[str, Any]:
        """Return ANA-compatible graph schema metadata."""
