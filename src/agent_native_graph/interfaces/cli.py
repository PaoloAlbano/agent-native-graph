"""Command-line entrypoint for the Agent-Native Graph wrapper."""

import argparse
import importlib
import sys

RESEARCH_COMMANDS = {
    "build-docs": "build_docs",
    "prepare-company-tasks": "prepare_cypherbench",
    "load-company": "load_simplekg_neo4j",
    "export-schema": "export_schema_prompt",
    "run-gold": "run_gold_neo4j",
    "evaluate-run": "evaluate_run",
    "archive-result": "archive_result",
    "baseline-run": "run_reference_baseline",
    "baseline-archive": "archive_reference_baseline",
    "compare-results": "compare_company_results",
    "audit-execution": "audit_execution_accuracy",
    "audit-failures": "audit_failures",
    "audit-score-cap": "audit_score_cap",
    "compare-replicates": "compare_replicates",
    "analyze-tool-quality": "analyze_tool_quality",
}


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in RESEARCH_COMMANDS:
        module_name = RESEARCH_COMMANDS[sys.argv[1]]
        sys.argv = [f"{sys.argv[0]} {sys.argv[1]}", *sys.argv[2:]]
        importlib.import_module(f"agent_native_graph.research.{module_name}").main()
        return

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
    for command in RESEARCH_COMMANDS:
        subparsers.add_parser(command, help=f"Run the {command} research workflow.")
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
