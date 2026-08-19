"""Compatibility shim for the HTTP service interface."""

from agent_native_graph.interfaces.service import ToolCallRequest, app, create_app

__all__ = ["ToolCallRequest", "app", "create_app"]
