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
def delete_project(name: str) -> Dict[str, Any]:
    """
    Delete a project from the registry and in-memory cache.
    
    Args:
        name: Name of the project to delete.
    """
    return analyzer_tool.delete_project(name)

@mcp.tool()
def clear_all_projects() -> Dict[str, Any]:
    """
    Clear all registered projects from the registry and in-memory cache.
    Useful for resetting the analyzer state.
    """
    return analyzer_tool.clear_all_projects()

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
def get_api_stats(
    project_name: str,
    keyword: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get API statistics for an analyzed project.
    
    Args:
        project_name: Name of the analyzed project.
        keyword: Optional keyword to filter APIs (e.g. 't24').
    """
    return analyzer_tool.get_api_stats(project_name, keyword)

@mcp.tool()
def get_page_stats(
    project_name: str,
    domain: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get Page statistics for an analyzed project.
    
    Args:
        project_name: Name of the analyzed project.
        domain: Optional business domain to filter pages (e.g. 'Authentication').
    """
    return analyzer_tool.get_page_stats(project_name, domain)

@mcp.tool()
def search_workflow(
    project_name: str,
    path: Optional[str] = None,
    scenario_tag: Optional[str] = None,
    keyword: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search for workflows or specific scenarios.
    
    Args:
        project_name: Name of the analyzed project.
        path: Workflow file path pattern.
        scenario_tag: Scenario tag (e.g., '@AddPayment').
        keyword: Keyword for full-text search.
    """
    return analyzer_tool.search_workflow(project_name, path, scenario_tag, keyword)

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
def get_failure_hotspots(project_name: str) -> Dict[str, Any]:
    """
    Identify components (APIs, Workflows) that contribute most to test failures.
    Returns a sorted list of hotspots based on failure impact score.
    
    Args:
        project_name: Name of the analyzed project.
    """
    return analyzer_tool.get_failure_hotspots(project_name)

@mcp.tool()
def record_fix(project_name: str, node_id: str, error_message: str, solution: str, description: str) -> Dict[str, Any]:
    """
    Record a successful fix for a component and error pattern.
    This helps the AI 'learn' how to fix similar issues in the future.
    
    Args:
        project_name: Name of the analyzed project.
        node_id: ID of the component that was fixed.
        error_message: The error message that occurred.
        solution: The code change or steps taken to fix it.
        description: Brief explanation of the fix.
    """
    return analyzer_tool.record_fix(project_name, node_id, error_message, solution, description)

@mcp.tool()
def get_fix_suggestions(project_name: str, node_id: str, error_message: str) -> Dict[str, Any]:
    """
    Get historical fix suggestions for a component and error pattern.
    
    Args:
        project_name: Name of the analyzed project.
        node_id: ID of the failing component.
        error_message: Current error message.
    """
    return analyzer_tool.get_fix_suggestions(project_name, node_id, error_message)

@mcp.tool()
def get_subgraph(node_id: str, radius: int = 2) -> Dict[str, Any]:
    """
    Extract a local subgraph for AI context.
    Provides a concise view of a node and its neighbors.
    
    Args:
        node_id: ID of the target node.
        radius: Number of hops to include (default: 2).
    """
    return analyzer_tool.get_subgraph(node_id, radius)

@mcp.tool()
def query_node_by_metadata(key: str, value: str) -> Dict[str, Any]:
    """
    Search nodes by metadata attributes across all projects.
    Useful for finding all nodes in a specific 'feature' or 'category'.
    
    Args:
        key: Metadata key to search in (e.g., 'feature', 'category').
        value: Value to match.
    """
    return analyzer_tool.query_node_by_metadata(key, value)

@mcp.tool()
def get_impact_radius(node_id: str, depth: int = 2) -> Dict[str, Any]:
    """
    Analyze impact within a specific radius for AI reasoning.
    Identifies components that depend on the specified node.
    
    Args:
        node_id: ID of the component being changed.
        depth: Search depth (default: 2).
    """
    return analyzer_tool.get_impact_radius(node_id, depth)

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

@mcp.tool()
def render_execution_report(
    project_name: str, 
    report_path: str, 
    output_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate an execution report visualization (Living Graph) with Pass/Fail/Not Run status.
    
    Args:
        project_name: Name of the analyzed project.
        report_path: Path to the Karate execution report (JSON format).
        output_path: Optional custom path to save the HTML file.
    """
    return analyzer_tool.render_execution_report(project_name, report_path, output_path)

@mcp.tool()
def compare_projects(
    base_project_name: str, 
    new_project_name: str, 
    output_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Compare two projects and generate a diff visualization report (Added/Removed/Modified).
    
    Args:
        base_project_name: Name of the base (old) project.
        new_project_name: Name of the new project to compare.
        output_path: Optional custom path to save the HTML file.
    """
    return analyzer_tool.compare_projects(base_project_name, new_project_name, output_path)

if __name__ == "__main__":
    # Start the server using stdio
    mcp.run()
