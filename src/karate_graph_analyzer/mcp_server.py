"""
Proper MCP Server for Karate Feature Graph Analyzer using FastMCP.
"""

import logging
from typing import Any, Dict, List, Optional
from fastmcp import FastMCP

from karate_graph_analyzer.mcp_interface.mcp_tool import KarateGraphAnalyzerTool

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastMCP
mcp = FastMCP("Karate-Graph-Analyzer")

# Initialize Implementation Tool
# We use a global instance to persist state across tool calls if needed
# (FastMCP handles lifecycle, but we want the registry to be consistent)
analyzer_tool = KarateGraphAnalyzerTool()

@mcp.tool()
def register_project(
    name: str,
    root_path: str,
    feature_file_patterns: Optional[List[str]] = None,
    parser_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Register a new Karate project for analysis.
    
    Args:
        name: Unique name for the project.
        root_path: Absolute path to project root.
        feature_file_patterns: Optional list of glob patterns (default: ["**/*.feature"]).
        parser_config: Optional configuration for the parser.
    """
    return analyzer_tool.register_project(name, root_path, feature_file_patterns, parser_config)

@mcp.tool()
def list_projects() -> List[Dict[str, Any]]:
    """List all registered projects and their analysis status."""
    return analyzer_tool.list_projects()

@mcp.tool()
def analyze_project(project_name: str) -> Dict[str, Any]:
    """
    Analyze a registered project to build its dependency graph.
    
    Args:
        project_name: Name of the registered project.
    """
    return analyzer_tool.analyze_project(project_name)

@mcp.tool()
def bulk_analyze() -> Dict[str, Any]:
    """Analyze all registered projects at once."""
    return analyzer_tool.bulk_analyze()

@mcp.tool()
def query_dependencies(component_id: str, transitive: bool = True) -> Dict[str, Any]:
    """
    Find all components that the specified component depends on.
    
    Args:
        component_id: ID of the component (e.g., file path or scenario tag).
        transitive: Whether to include indirect dependencies (default: True).
    """
    return analyzer_tool.query_dependencies(component_id, transitive)

@mcp.tool()
def impact_analysis(component_id: str) -> Dict[str, Any]:
    """
    Identify all test cases and workflows affected by a change in this component.
    
    Args:
        component_id: ID of the component being changed.
    """
    return analyzer_tool.impact_analysis(component_id)

@mcp.tool()
def search_api(
    project_name: str,
    method: Optional[str] = None,
    path: Optional[str] = None,
    domain: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search for API endpoints in an analyzed project.
    
    Args:
        project_name: Name of the analyzed project.
        method: HTTP method (GET, POST, etc).
        path: Path pattern to search for.
        domain: Domain name to filter by.
    """
    return analyzer_tool.search_api(project_name, method, path, domain)

@mcp.tool()
def search_workflow(
    project_name: str,
    path: Optional[str] = None,
    scenario_tag: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search for workflows or specific scenarios.
    
    Args:
        project_name: Name of the analyzed project.
        path: Workflow file path pattern.
        scenario_tag: Scenario tag (e.g., '@AddPayment').
    """
    return analyzer_tool.search_workflow(project_name, path, scenario_tag)

@mcp.tool()
def search_test_case(
    project_name: str,
    jira_tag: Optional[str] = None,
    name_pattern: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search for test cases by Jira ID or name.
    
    Args:
        project_name: Name of the analyzed project.
        jira_tag: Jira tag (e.g., '@JiraId-123').
        name_pattern: Pattern in test case name.
    """
    return analyzer_tool.search_test_case(project_name, jira_tag, name_pattern)

@mcp.tool()
def get_project_health(project_name: str) -> Dict[str, Any]:
    """
    Get an architectural health report (cycles, orphans, complexity).
    
    Args:
        project_name: Name of the analyzed project.
    """
    return analyzer_tool.get_project_health(project_name)

@mcp.tool()
def visualize_project(project_name: str, output_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Generate an interactive HTML visualization for a project.
    
    Args:
        project_name: Name of the analyzed project.
        output_path: Optional custom path to save the HTML file.
    """
    return analyzer_tool.visualize_project(project_name, output_path)

@mcp.tool()
def merge_projects(project_names: List[str], new_project_name: str = "Merged_Project") -> Dict[str, Any]:
    """
    Merge multiple projects into one global dependency graph.
    
    Args:
        project_names: List of project names to merge.
        new_project_name: Name for the merged project.
    """
    return analyzer_tool.merge_projects(project_names, new_project_name)

@mcp.tool()
def export_graph(project_name: str, format: str = "json") -> Dict[str, Any]:
    """
    Export the dependency graph to a file format.
    
    Args:
        project_name: Name of the project.
        format: Export format ('json' or 'graphml').
    """
    return analyzer_tool.export_graph(project_name, format)

if __name__ == "__main__":
    # Start the server using stdio
    mcp.run()
