import sys
import os
from pathlib import Path

# Add src to sys.path to import local modules
sys.path.append(str(Path("src").absolute()))

from karate_graph_analyzer.graph.graph_builder import GraphBuilder
from karate_graph_analyzer.analyzer.dependency_analyzer import DependencyAnalyzer
from karate_graph_analyzer.models import NodeType, Project

def demo_expert_analysis():
    project_root = "e:/Project/auto/karate-fw/karate-core"
    
    print(f"--- Step 1: Scanning Project and Initializing Expert ---")
    builder = GraphBuilder()
    project = Project(
        name="karate-core",
        root_path=project_root,
        feature_file_patterns=["src/test/java/**/*.feature"]
    )
    graph = builder.build_from_project(project)
    analyzer = DependencyAnalyzer(graph)
    expert = analyzer.expert
    
    print(f"\n--- Step 2: Project Health Report ---")
    health = expert.get_health_summary()
    print(f"Overall Health Score: {health['health_score']}/100")
    print(f" - Orphan Components: {health['orphan_count']}")
    print(f" - Redundant APIs: {health['redundant_api_count']}")
    print(f" - Circular Dependencies: {health['cycle_count']}")
    
    print(f"\n--- Step 3: Top 3 Most Complex Test Cases ---")
    for item in health['top_complex_test_cases'][:3]:
        print(f" - {item['name']} (Score: {item['score']})")
    
    print(f"\n--- Step 4: Redundant API Detection ---")
    duplicates = expert.find_redundant_apis()
    if not duplicates:
        print("No redundant APIs found.")
    for key, nodes in duplicates.items():
        print(f"Potential Duplicate: {key}")
        for node in nodes:
            print(f"  - {node.metadata.file_path}:{node.metadata.line_number} (ID: {node.id})")

    print(f"\n--- Step 5: Unused (Orphan) Components ---")
    orphans = expert.find_orphans()
    # Filter to show only some
    api_orphans = [n for n in orphans if n.type == NodeType.API]
    print(f"Found {len(api_orphans)} unused APIs.")
    for node in api_orphans[:5]:
        print(f" - Unused API: {node.name} ({node.metadata.file_path})")

if __name__ == "__main__":
    demo_expert_analysis()
