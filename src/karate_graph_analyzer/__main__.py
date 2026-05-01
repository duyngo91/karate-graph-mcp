"""
Entry point for Karate Graph Analyzer MCP server.

Run with: python -m karate_graph_analyzer
"""

import argparse
import sys
from pathlib import Path

from karate_graph_analyzer.logging_config import setup_logging_from_config
from karate_graph_analyzer.mcp_interface.mcp_tool import KarateGraphAnalyzerTool


def main() -> int:
    """Main entry point for the MCP server."""
    parser = argparse.ArgumentParser(
        description="Karate Feature Graph Analyzer MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start server with default settings
  python -m karate_graph_analyzer

  # Start with custom storage path
  python -m karate_graph_analyzer --storage /path/to/projects.json

  # Enable debug logging
  python -m karate_graph_analyzer --log-level DEBUG

  # Use development logging configuration
  python -m karate_graph_analyzer --log-config development
        """,
    )

    parser.add_argument(
        "--storage",
        type=str,
        default=".karate_projects.json",
        help="Path to project registry storage file (default: .karate_projects.json)",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Logging level (default: INFO)",
    )

    parser.add_argument(
        "--log-config",
        type=str,
        choices=["development", "production", "testing"],
        help="Use predefined logging configuration",
    )

    parser.add_argument(
        "--log-file",
        type=str,
        help="Log file path (if not specified, logs to console only)",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )

    args = parser.parse_args()

    # Set up logging
    if args.log_config:
        setup_logging_from_config(args.log_config)
    else:
        from karate_graph_analyzer.logging_config import setup_logging

        setup_logging(level=args.log_level, log_file=args.log_file)

    # Initialize MCP tool
    print(f"Initializing Karate Graph Analyzer MCP Server...")
    print(f"Storage path: {args.storage}")
    print(f"Log level: {args.log_level}")

    tool = KarateGraphAnalyzerTool(storage_path=args.storage)

    # Load existing projects
    projects = tool.list_projects()
    print(f"Loaded {len(projects)} registered projects")

    print("\nMCP Server ready!")
    print("Available functions:")
    print("  - register_project")
    print("  - list_projects")
    print("  - analyze_project")
    print("  - query_dependencies")
    print("  - impact_analysis")
    print("  - get_node_details")
    print("  - find_common_components")
    print("  - export_graph")
    print("  - import_graph")

    print("\nPress Ctrl+C to exit")

    try:
        # Keep server running
        import time

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
