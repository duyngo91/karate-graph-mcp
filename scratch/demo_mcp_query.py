import sys
import os
from pathlib import Path

# Add src to sys.path to import local modules
sys.path.append(str(Path("src").absolute()))

from karate_graph_analyzer.graph.graph_builder import GraphBuilder
from karate_graph_analyzer.analyzer.dependency_analyzer import DependencyAnalyzer
from karate_graph_analyzer.models import NodeType, Project

def demo_query():
    project_root = "e:/Project/auto/karate-fw/karate-core"
    
    print(f"--- Step 1: Scanning Project ---")
    builder = GraphBuilder()
    project = Project(
        name="karate-core",
        root_path=project_root,
        feature_file_patterns=["src/test/java/**/*.feature"]
    )
    graph = builder.build_from_project(project)
    analyzer = DependencyAnalyzer(graph)
    
    # Example 1: Search by API URL
    target_api_path = "/api/v2/payment"
    print(f"\n--- Step 2: Searching for API by URL: {target_api_path} ---")
    
    found_api_nodes = []
    for node in graph.nodes.values():
        if node.type == NodeType.API:
            if node.metadata.additional_data.get("path_template") == target_api_path:
                found_api_nodes.append(node)
    
    for api_node in found_api_nodes:
        print(f"FOUND API: {api_node.name} (ID: {api_node.id})")
        print(f" Defined in: {api_node.metadata.file_path}:{api_node.metadata.line_number}")
        
        # Impact Analysis
        impact = analyzer.impact_analysis(api_node.id)
        print(f" Usage found in {len(impact.affected_test_cases)} Test Cases:")
        for tc in impact.affected_test_cases:
            # Get full node data from graph using ID
            full_node = graph.nodes[tc.node_id]
            print(f"  - [{full_node.metadata.jira_tags[0] if full_node.metadata.jira_tags else 'N/A'}] {full_node.name}")
            print(f"    Path: {full_node.metadata.file_path}")

    # Example 2: Search for most used components
    print(f"\n--- Step 3: Most Used Components (Reusability) ---")
    usage_stats = []
    for node_id, node in graph.nodes.items():
        if node.type in [NodeType.API, NodeType.ACTION]:
            in_degree = analyzer._nx_graph.in_degree(node_id)
            if in_degree > 0:
                usage_stats.append((node, in_degree))
    
    # Sort by usage
    usage_stats.sort(key=lambda x: x[1], reverse=True)
    for node, count in usage_stats[:3]:
        print(f" - {node.name} ({node.type.value}): Used by {count} test cases")

if __name__ == "__main__":
    demo_query()
