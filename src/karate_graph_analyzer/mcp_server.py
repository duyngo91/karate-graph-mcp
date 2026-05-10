"""
Proper MCP Server for Karate Feature Graph Analyzer using FastMCP.
"""

import argparse
import logging
import sys
from typing import Any, Dict, List, Optional
from fastmcp import FastMCP

from karate_graph_analyzer import __version__
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
def mcp_health() -> Dict[str, Any]:
    """Health probe for MCP connectivity and server state."""
    return {
        "success": True,
        "server": "Karate-Graph-Analyzer",
        "version": __version__,
        "registered_projects": len(analyzer_tool.registry.list()),
        "analyzed_projects": len(analyzer_tool.graphs),
    }


@mcp.tool()
def mcp_version() -> Dict[str, Any]:
    """Return server and package version metadata."""
    return {
        "success": True,
        "server": "Karate-Graph-Analyzer",
        "version": __version__,
    }

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
def analyze_project(project_name: str, include_structural_nodes: bool = False) -> Dict[str, Any]:
    """
    Analyze a registered project to build its dependency graph.
    
    Args:
        project_name: Name of the registered project.
        include_structural_nodes: Whether to include folder/file structural nodes (default: False).
    """
    return analyzer_tool.analyze_project(project_name, include_structural_nodes)

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
def search_java_usage(
    project_name: str,
    query: str,
    include_methods: bool = True,
) -> Dict[str, Any]:
    """
    Search Java class/method usage and the test cases that call them.

    Args:
        project_name: Name of the analyzed project.
        query: Java class or method keyword/pattern.
        include_methods: Include JAVA_METHOD nodes in results.
    """
    return analyzer_tool.search_java_usage(project_name, query, include_methods)

@mcp.tool()
def search_js_usage(
    project_name: str,
    query: str = "",
    include_functions: bool = True,
) -> Dict[str, Any]:
    """
    Search JavaScript file/function usage and the test cases that call them.

    Args:
        project_name: Name of the analyzed project.
        query: JavaScript file/function keyword or path.
        include_functions: Include JS_FUNCTION nodes in results.
    """
    return analyzer_tool.search_js_usage(project_name, query, include_functions)

@mcp.tool()
def search_error_pattern(
    project_name: str,
    pattern: str,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Search failed nodes by error text, fingerprint, or failed-step pattern.

    Args:
        project_name: Name of the analyzed project.
        pattern: Error/fingerprint text pattern.
        limit: Maximum number of matched nodes to return.
    """
    return analyzer_tool.search_error_pattern(project_name, pattern, limit)

@mcp.tool()
def search_reusable_function(
    project_name: str,
    query: str,
    language: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Search Java/JavaScript source for reusable helper functions before adding new code.

    Args:
        project_name: Name of the analyzed project.
        query: Function intent or keyword, e.g. "random string" or "uuid".
        language: Optional language filter: "java", "javascript", "js", or "all".
        limit: Maximum number of candidates to return.
    """
    return analyzer_tool.search_reusable_function(project_name, query, language, limit)

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
def top_hotspots(project_name: str, limit: int = 10) -> Dict[str, Any]:
    """
    Preset query: top failure hotspots for a project.

    Args:
        project_name: Name of the analyzed project.
        limit: Maximum number of hotspots to return.
    """
    return analyzer_tool.top_hotspots(project_name, limit)

@mcp.tool()
def unused_components(project_name: str, limit: int = 10) -> Dict[str, Any]:
    """
    Preset query: unused components flattened across types.

    Args:
        project_name: Name of the analyzed project.
        limit: Maximum number of unused components to return.
    """
    return analyzer_tool.unused_components(project_name, limit)

@mcp.tool()
def common_usage_map(project_name: str, limit: int = 50) -> Dict[str, Any]:
    """
    Return reusable components sorted by how many test cases use them.

    Args:
        project_name: Name of the analyzed project.
        limit: Maximum number of reusable components to return.
    """
    return analyzer_tool.common_usage_map(project_name, limit)

@mcp.tool()
def javascript_structure_map(project_name: str, limit: int = 100) -> Dict[str, Any]:
    """
    Return JavaScript files, exported/helper functions, dependencies, and test usage.

    Args:
        project_name: Name of the analyzed project.
        limit: Maximum number of JavaScript files to return.
    """
    return analyzer_tool.javascript_structure_map(project_name, limit)

@mcp.tool()
def similar_common_components(project_name: str, limit: int = 50) -> Dict[str, Any]:
    """
    Find common/scenario/action components that share the same dependency shape.

    Args:
        project_name: Name of the analyzed project.
        limit: Maximum number of duplicate-like groups to return.
    """
    return analyzer_tool.similar_common_components(project_name, limit)

@mcp.tool()
def change_impact_preview(
    project_name: str,
    changed_paths: List[str],
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Preset query: preview impacted test cases from changed files/components.

    Args:
        project_name: Name of the analyzed project.
        changed_paths: Changed file paths or path keywords.
        limit: Maximum impacted test cases to return.
    """
    return analyzer_tool.change_impact_preview(project_name, changed_paths, limit)

@mcp.tool()
def test_selection_suggestion(
    project_name: str,
    changed_paths: List[str],
    limit: int = 30,
) -> Dict[str, Any]:
    """
    Preset query: suggest smallest high-signal test subset to rerun after change.

    Args:
        project_name: Name of the analyzed project.
        changed_paths: Changed file paths or path keywords.
        limit: Maximum suggested test cases to return.
    """
    return analyzer_tool.test_selection_suggestion(project_name, changed_paths, limit)

@mcp.tool()
def feature_intent_index(
    project_name: str,
    query: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Build/search scenario intent summaries from feature files.

    Args:
        project_name: Name of the registered project.
        query: Optional keyword filter for scenario intent.
        limit: Maximum scenario summaries to return.
    """
    return analyzer_tool.feature_intent_index(project_name, query, limit)

@mcp.tool()
def variable_data_flow_trace(
    project_name: str,
    feature_path: Optional[str] = None,
    scenario_tag: Optional[str] = None,
    scenario_name: Optional[str] = None,
    node_id: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Trace variables in feature scenarios from definition/source to usage.

    Args:
        project_name: Name of the registered project.
        feature_path: Optional feature path or path fragment.
        scenario_tag: Optional scenario tag such as @TC-103.
        scenario_name: Optional scenario name fragment.
        node_id: Optional graph node id.
        limit: Maximum traces to return.
    """
    return analyzer_tool.variable_data_flow_trace(
        project_name, feature_path, scenario_tag, scenario_name, node_id, limit
    )

@mcp.tool()
def assertion_map(
    project_name: str,
    query: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Index status/match/assert steps across feature files.

    Args:
        project_name: Name of the registered project.
        query: Optional assertion keyword filter.
        limit: Maximum assertions to return.
    """
    return analyzer_tool.assertion_map(project_name, query, limit)

@mcp.tool()
def call_read_deep_context(
    project_name: str,
    feature_path: Optional[str] = None,
    scenario_tag: Optional[str] = None,
    scenario_name: Optional[str] = None,
    node_id: Optional[str] = None,
    max_depth: int = 2,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Return nested call/read context for selected feature scenarios.

    Args:
        project_name: Name of the registered project.
        feature_path: Optional feature path or path fragment.
        scenario_tag: Optional scenario tag such as @TC-103.
        scenario_name: Optional scenario name fragment.
        node_id: Optional graph node id.
        max_depth: Nested call/read depth.
        limit: Maximum contexts to return.
    """
    return analyzer_tool.call_read_deep_context(
        project_name, feature_path, scenario_tag, scenario_name, node_id, max_depth, limit
    )

@mcp.tool()
def ai_feature_context_pack(
    project_name: str,
    feature_path: Optional[str] = None,
    scenario_tag: Optional[str] = None,
    scenario_name: Optional[str] = None,
    node_id: Optional[str] = None,
    max_call_depth: int = 2,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Build AI-ready feature context: intent, variables, assertions, call/read chain, graph context.

    Args:
        project_name: Name of the registered project.
        feature_path: Optional feature path or path fragment.
        scenario_tag: Optional scenario tag such as @TC-103.
        scenario_name: Optional scenario name fragment.
        node_id: Optional graph node id.
        max_call_depth: Nested call/read depth.
        limit: Maximum packs to return.
    """
    return analyzer_tool.ai_feature_context_pack(
        project_name, feature_path, scenario_tag, scenario_name, node_id, max_call_depth, limit
    )

@mcp.tool()
def feature_behavior_map(
    project_name: str,
    feature_path: Optional[str] = None,
    scenario_tag: Optional[str] = None,
    scenario_name: Optional[str] = None,
    node_id: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Build scenario behavior maps for AI: preconditions, actions, expectations.

    Args:
        project_name: Name of the registered project.
        feature_path: Optional feature path or path fragment.
        scenario_tag: Optional scenario tag such as @TC-103.
        scenario_name: Optional scenario name fragment.
        node_id: Optional graph node id.
        limit: Maximum scenarios to return.
    """
    return analyzer_tool.feature_behavior_map(
        project_name, feature_path, scenario_tag, scenario_name, node_id, limit
    )

@mcp.tool()
def scenario_similarity_map(
    project_name: str,
    query: Optional[str] = None,
    limit: int = 50,
    top_k: int = 3,
) -> Dict[str, Any]:
    """
    Find similar scenarios based on intent keywords for AI reuse and suggestion.

    Args:
        project_name: Name of the registered project.
        query: Optional keyword filter for anchor scenarios.
        limit: Maximum anchor scenarios to return.
        top_k: Maximum similar scenarios per anchor.
    """
    return analyzer_tool.scenario_similarity_map(project_name, query, limit, top_k)

@mcp.tool()
def feature_reuse_advisor(
    project_name: str,
    min_group_size: int = 2,
    min_flow_length: int = 3,
    limit: int = 50,
    include_low_signal: bool = False,
) -> Dict[str, Any]:
    """
    Find duplicate feature steps/flows and return AI-safe refactor suggestions.

    Args:
        project_name: Name of the registered project.
        min_group_size: Minimum duplicate locations.
        min_flow_length: Minimum duplicate flow length.
        limit: Maximum groups to return.
        include_low_signal: Include generic Karate grammar steps such as status/method/url.
    """
    return analyzer_tool.feature_reuse_advisor(
        project_name,
        min_group_size,
        min_flow_length,
        limit,
        include_low_signal,
    )

@mcp.tool()
def db_query_index(
    project_name: str,
    query: Optional[str] = None,
    limit: int = 100,
    include_components: bool = True,
    link_status: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build/search DB query and DB component index.

    Args:
        project_name: Name of the registered project.
        query: Optional DB keyword filter.
        limit: Maximum items to return.
        include_components: Include DB feature/executor components besides raw SQL nodes.
        link_status: Optional comma-separated filter: linked, orphan, component, demo, or default.
    """
    return analyzer_tool.db_query_index(project_name, query, limit, include_components, link_status)

@mcp.tool()
def search_db_usage(
    project_name: str,
    query: str,
    limit: int = 100,
    link_status: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Search DB usage by table/query/operation/host/path keywords.

    Args:
        project_name: Name of the registered project.
        query: DB keyword, table name, operation, host, or path.
        limit: Maximum results to return.
        link_status: Optional comma-separated filter: linked, orphan, component, demo, or default.
    """
    return analyzer_tool.search_db_usage(project_name, query, limit, link_status)

@mcp.tool()
def db_data_flow_trace(
    project_name: str,
    feature_path: Optional[str] = None,
    scenario_tag: Optional[str] = None,
    scenario_name: Optional[str] = None,
    node_id: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Trace DB-related variable/call/assertion flow in selected scenarios.

    Args:
        project_name: Name of the registered project.
        feature_path: Optional feature path or path fragment.
        scenario_tag: Optional scenario tag such as @VerifyOrderStatus.
        scenario_name: Optional scenario name fragment.
        node_id: Optional graph node id.
        limit: Maximum traces to return.
    """
    return analyzer_tool.db_data_flow_trace(
        project_name, feature_path, scenario_tag, scenario_name, node_id, limit
    )

@mcp.tool()
def db_assertion_map(
    project_name: str,
    query: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Index DB-related assertions across feature files.

    Args:
        project_name: Name of the registered project.
        query: Optional DB assertion keyword filter.
        limit: Maximum assertions to return.
    """
    return analyzer_tool.db_assertion_map(project_name, query, limit)

@mcp.tool()
def db_impact_preview(
    project_name: str,
    changed_entities: List[str],
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Preview impacted tests from changed DB entities.

    Args:
        project_name: Name of the registered project.
        changed_entities: Changed tables, schema names, DB hosts, or DB feature paths.
        limit: Maximum impacted test cases to return.
    """
    return analyzer_tool.db_impact_preview(project_name, changed_entities, limit)

@mcp.tool()
def flaky_risk(project_name: str, limit: int = 10) -> Dict[str, Any]:
    """
    Preset query: test cases with mixed pass/fail history (flaky risk).

    Args:
        project_name: Name of the analyzed project.
        limit: Maximum number of test cases to return.
    """
    return analyzer_tool.flaky_risk(project_name, limit)

@mcp.tool()
def prioritize_fix_queue(project_name: str, limit: int = 10) -> Dict[str, Any]:
    """
    Preset query: rank failures/components to fix first by impact and risk.

    Args:
        project_name: Name of the analyzed project.
        limit: Maximum number of ranked items to return.
    """
    return analyzer_tool.prioritize_fix_queue(project_name, limit)

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
def auto_fix_hint_pack(
    project_name: str,
    node_id: str,
    error_message: str,
    max_historical: int = 3,
) -> Dict[str, Any]:
    """
    Build a step-by-step auto-fix checklist from smart + historical suggestions.

    Args:
        project_name: Name of the analyzed project.
        node_id: ID of the failing component.
        error_message: Current error message.
        max_historical: Maximum historical patterns to include.
    """
    return analyzer_tool.auto_fix_hint_pack(
        project_name, node_id, error_message, max_historical
    )

@mcp.tool()
def get_failure_history(project_name: str, node_id: str) -> Dict[str, Any]:
    """
    Return execution history, flaky score, and failure fingerprint trend for a node.

    Args:
        project_name: Name of the analyzed project.
        node_id: ID of the failing or flaky node.
    """
    return analyzer_tool.get_failure_history(project_name, node_id)

@mcp.tool()
def get_failure_debug_context(
    project_name: str,
    node_id: str,
    error_message: Optional[str] = None,
    radius: int = 2,
    max_historical: int = 3,
) -> Dict[str, Any]:
    """
    Build an AI-ready debug pack: failure fingerprint, run history, local dependency graph,
    related hotspots, source snippet, and fix checklist.

    Args:
        project_name: Name of the analyzed project.
        node_id: ID of the failing node.
        error_message: Optional current error message override.
        radius: Dependency context radius around the node.
        max_historical: Maximum historical fix hints to include.
    """
    return analyzer_tool.get_failure_debug_context(
        project_name,
        node_id,
        error_message,
        radius,
        max_historical,
    )

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
def global_search(query: str) -> Dict[str, Any]:
    """
    Search across all nodes in all projects using a global keyword.
    
    Args:
        query: Search query across all fields.
    """
    return analyzer_tool.global_search(query)

@mcp.tool()
def find_path(source_id: str, target_id: str) -> Dict[str, Any]:
    """
    Find all simple paths between two nodes to analyze traceability.
    
    Args:
        source_id: Source node ID.
        target_id: Target node ID.
    """
    return analyzer_tool.find_path(source_id, target_id)

@mcp.tool()
def get_component_importance(project_name: str) -> Dict[str, Any]:
    """
    Get nodes sorted by their architectural importance (huyết mạch).
    
    Args:
        project_name: Name of the analyzed project.
    """
    return analyzer_tool.get_component_importance(project_name)

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
def process_reports_folder(
    project_name: str, 
    directory_path: str, 
    output_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Scan a directory for Karate JSON reports, apply them, and generate a visualization.
    Returns an AI-distilled summary of failures.
    
    Args:
        project_name: Name of the analyzed project.
        directory_path: Path to the directory containing Karate JSON reports.
        output_path: Optional custom path to save the HTML file.
    """
    return analyzer_tool.process_reports_folder(project_name, directory_path, output_path)

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


def main() -> int:
    """Run Karate Graph Analyzer as a FastMCP stdio server."""
    parser = argparse.ArgumentParser(description="Karate Graph Analyzer MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio"],
        default="stdio",
        help="Server transport (default: stdio)",
    )
    parser.parse_args()
    mcp.run()
    return 0

if __name__ == "__main__":
    sys.exit(main())
