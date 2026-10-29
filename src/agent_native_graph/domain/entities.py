"""Internal entity references; never serialized as graph properties or tool IDs."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EntityReference:
    """A backend-owned identity whose validity is limited to one workflow."""

    owner: str
    key: str


class EntityPayload(dict):
    """Ordinary public node JSON with an out-of-band, non-JSON reference."""

    reference: EntityReference


_reference_factory: ContextVar[Callable[[Any], EntityReference] | None] = ContextVar(
    "ana_entity_reference_factory", default=None
)


@contextmanager
def entity_references(factory: Callable[[Any], EntityReference]) -> Iterator[None]:
    """Scope node decoding to the backend executing this call, including threads."""
    token = _reference_factory.set(factory)
    try:
        yield
    finally:
        _reference_factory.reset(token)


def attach_reference(payload: dict, node: Any) -> dict:
    """Leave legacy payloads unchanged; attach references only in an explicit scope."""
    factory = _reference_factory.get()
    if factory is None:
        return payload
    result = EntityPayload(payload)
    result.reference = factory(node)
    return result


def entity_identity(value: dict) -> Any:
    """Use opaque references when available, preserving historical property IDs otherwise."""
    if isinstance(value, EntityPayload):
        return value.reference
    return value["properties"]["id"]
