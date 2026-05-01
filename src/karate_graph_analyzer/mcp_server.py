"""
MCP Server for Karate Feature Graph Analyzer.

This module provides an MCP server interface that can be used by AI agents
to analyze Karate feature files and generate dependency graphs.
"""

import json
import logging
import sys
from typing import Any, Dict, List

from karate_graph_analyzer.mcp_interface.mcp_tool import KarateGraphAnalyzerTool

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MCPServer:
    """MCP Server for Karate Graph Analyzer."""

    def __init__(self):
        """Initialize MCP server."""
        self.tool = KarateGraphAnalyzerTool()
        logger.info("MCP Server initialized")

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP request.

        Args:
            request: MCP request dictionary with 'method' and 'params'

        Returns:
            MCP response dictionary
        """
        method = request.get("method")
        params = request.get("params", {})

        logger.info(f"Handling request: {method}")

        try:
            # Route to appropriate method
            if method == "register_project":
                return self.tool.register_project(**params)

            elif method == "list_projects":
                return {"success": True, "projects": self.tool.list_projects()}

            elif method == "analyze_project":
                return self.tool.analyze_project(**params)

            elif method == "query_dependencies":
                return self.tool.query_dependencies(**params)

            elif method == "impact_analysis":
                return self.tool.impact_analysis(**params)

            elif method == "get_node_details":
                return self.tool.get_node_details(**params)

            elif method == "find_common_components":
                return self.tool.find_common_components(**params)

            elif method == "export_graph":
                return self.tool.export_graph(**params)

            elif method == "import_graph":
                return self.tool.import_graph(**params)
            
            # Search and Query methods
            elif method == "search_api":
                return self.tool.search_api(**params)
            
            elif method == "search_workflow":
                return self.tool.search_workflow(**params)
            
            elif method == "search_page":
                return self.tool.search_page(**params)
            
            elif method == "search_test_case":
                return self.tool.search_test_case(**params)
            
            elif method == "get_usage_stats":
                return self.tool.get_usage_stats(**params)
            
            elif method == "get_most_used_components":
                return self.tool.get_most_used_components(**params)
            
            elif method == "find_unused_components":
                return self.tool.find_unused_components(**params)

            else:
                return {
                    "success": False,
                    "error": {
                        "code": "6002",
                        "category": "MCP_ERROR",
                        "message": f"Unknown method: {method}"
                    }
                }

        except Exception as e:
            logger.error(f"Error handling request: {e}", exc_info=True)
            return {
                "success": False,
                "error": {
                    "code": "6003",
                    "category": "INTERNAL_ERROR",
                    "message": str(e)
                }
            }

    def run(self):
        """Run MCP server (stdio mode)."""
        logger.info("MCP Server starting in stdio mode")

        try:
            while True:
                # Read request from stdin
                line = sys.stdin.readline()
                if not line:
                    break

                try:
                    request = json.loads(line.strip())
                    response = self.handle_request(request)

                    # Write response to stdout
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()

                except json.JSONDecodeError as e:
                    error_response = {
                        "success": False,
                        "error": {
                            "code": "6001",
                            "category": "MCP_ERROR",
                            "message": f"Invalid JSON: {e}"
                        }
                    }
                    sys.stdout.write(json.dumps(error_response) + "\n")
                    sys.stdout.flush()

        except KeyboardInterrupt:
            logger.info("MCP Server stopped by user")
        except Exception as e:
            logger.error(f"MCP Server error: {e}", exc_info=True)
        finally:
            logger.info("MCP Server shutting down")


def main():
    """Main entry point for MCP server."""
    server = MCPServer()
    server.run()


if __name__ == "__main__":
    main()
