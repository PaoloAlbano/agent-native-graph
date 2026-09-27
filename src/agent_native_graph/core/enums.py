"""Core enums shared by ANA metadata, services, and tool registration."""

from enum import StrEnum


class ToolStatus(StrEnum):
    CORE = "core"
    EXPERIMENTAL = "experimental"


class ToolProfile(StrEnum):
    READONLY = "readonly"
    READWRITE = "readwrite"
