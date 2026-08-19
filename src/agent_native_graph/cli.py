"""Compatibility shim for the CLI entrypoint."""

from agent_native_graph.interfaces.cli import main

__all__ = ["main"]


if __name__ == "__main__":
    main()
