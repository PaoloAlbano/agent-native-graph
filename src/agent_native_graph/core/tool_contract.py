"""Stable ANA tool contract metadata generated from decorated tools."""

from dataclasses import dataclass

from agent_native_graph.core.enums import ToolProfile, ToolStatus
from agent_native_graph.core.tooling import registered_tools
from agent_native_graph.tools import load_tool_modules

load_tool_modules()


@dataclass(frozen=True)
class ToolContract:
    name: str
    status: ToolStatus
    profile: ToolProfile
    purpose: str
    when_to_use: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "status": self.status.value,
            "profile": self.profile.value,
            "purpose": self.purpose,
            "when_to_use": self.when_to_use,
        }


def get_tool_contract(status: ToolStatus | str | None = None) -> list[dict[str, str]]:
    """Return the public tool catalog from the decorator registry.

    This intentionally has no static fallback list: tool metadata lives next to
    the executable tool function, and this module is only a read model for CLI,
    API, and documentation surfaces.
    """
    normalized_status = ToolStatus(status) if isinstance(status, str) else status
    contracts = [
        ToolContract(
            name=definition.name,
            status=definition.status,
            profile=definition.profile,
            purpose=definition.purpose,
            when_to_use=definition.when_to_use,
        )
        for definition in registered_tools().values()
    ]
    if normalized_status is not None:
        contracts = [contract for contract in contracts if contract.status == normalized_status]
    return [contract.to_dict() for contract in sorted(contracts, key=lambda item: item.name)]
