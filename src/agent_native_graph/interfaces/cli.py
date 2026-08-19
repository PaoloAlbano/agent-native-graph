"""Command-line entrypoint for the Agent-Native Graph wrapper."""

import argparse
import sys


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "benchmark-neo4j":
        from agent_native_graph.runner import run_neo4j_tools_benchmark

        sys.argv = [sys.argv[0], *sys.argv[2:]]
        run_neo4j_tools_benchmark()
        return

    parser = argparse.ArgumentParser(prog="agent-native-graph")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("tools", help="Print the ANA v0 tool contract as JSON.")
    subparsers.add_parser("serve", help="Run the experimental HTTP service with uvicorn.")
    subparsers.add_parser("serve-mcp", help="Run the experimental MCP service.")
    subparsers.add_parser(
        "benchmark-neo4j",
        help="Run the current CypherBench/Neo4j ANA tool benchmark runner.",
    )
    args = parser.parse_args()

    if args.command == "tools":
        import json

        from agent_native_graph.core.tool_contract import get_tool_contract

        print(json.dumps({"version": "ana-v0", "tools": get_tool_contract()}, indent=2))
        return

    if args.command == "serve":
        try:
            import uvicorn
        except ImportError as exc:
            raise SystemExit(
                "Install service dependencies with `uv sync --extra service`."
            ) from exc
        uvicorn.run("agent_native_graph.interfaces.service:app", host="0.0.0.0", port=8080)
        return

    if args.command == "serve-mcp":
        from agent_native_graph.interfaces.mcp import create_mcp_server

        create_mcp_server().run()
        return

    parser.print_help()


if __name__ == "__main__":
    main()
