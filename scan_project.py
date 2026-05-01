"""
Karate Project Scanner

Scan a Karate project and generate dependency graph visualization.

Usage:
    python scan_project.py <project_root> [output_name]

Examples:
    python scan_project.py E:/Project/auto/karate-fw/karate-core
    python scan_project.py E:/Project/auto/karate-fw/karate-core my-project
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from karate_graph_analyzer.models import Project, ParserConfig
from karate_graph_analyzer.graph.graph_builder import GraphBuilder
from karate_graph_analyzer.visualization.graph_visualizer import GraphVisualizer
from karate_graph_analyzer.parser.config_parser import auto_detect_config


def scan_project(project_root: str, output_name: str = None):
    """Scan a Karate project and generate graph.
    
    Args:
        project_root: Root directory of the Karate project
        output_name: Optional output file name (default: project directory name)
    """
    print("="*80)
    print("KARATE PROJECT SCANNER")
    print("="*80)
    
    # Validate project root
    project_path = Path(project_root)
    if not project_path.exists():
        print(f"\n❌ ERROR: Project root not found: {project_root}")
        return 1
    
    # Determine project name and output name
    project_name = project_path.name
    if output_name is None:
        output_name = project_name
    
    print(f"\n📁 Project: {project_name}")
    print(f"📂 Root: {project_root}")
    
    # Auto-detect config from karate-config*.js files
    print(f"\n🔍 Auto-detecting configuration...")
    auto_config = auto_detect_config(str(project_path))
    
    if auto_config:
        print(f"✅ Found {len(auto_config)} environment variables")
        # Show first 5 variables
        for i, (key, value) in enumerate(sorted(auto_config.items())):
            if i >= 5:
                print(f"   ... and {len(auto_config) - 5} more")
                break
            display_value = value if len(value) <= 50 else value[:47] + "..."
            print(f"   • {key}: {display_value}")
    else:
        print("⚠️  No config variables found")
    
    # Parser configuration with auto-detected variables
    parser_config = ParserConfig(
        base_url_mapping=auto_config,
        variable_patterns=auto_config,  # Also use for call read() variable resolution
    )
    
    # Create project — exclude target/ and build/ directories (Maven/Gradle compiled copies)
    project = Project(
        name=project_name,
        root_path=str(project_path),
        feature_file_patterns=[
            "src/**/*.feature",  # Source files only
        ],
        parser_config=parser_config
    )
    
    print(f"\n🔍 Scanning for feature files...")
    
    # Build graph
    print(f"⚙️  Building dependency graph...")
    builder = GraphBuilder()
    
    try:
        graph = builder.build_from_project(project)
        
        print(f"\n✅ Graph built successfully!")
        print(f"   📊 Nodes: {len(graph.nodes)}")
        print(f"   🔗 Edges: {len(graph.edges)}")
        print(f"   🔄 Cycles: {len(graph.cycles)}")
        
        # Node type breakdown
        print(f"\n📈 Node Types:")
        node_counts = {}
        for node in graph.nodes.values():
            node_type = node.type.value
            node_counts[node_type] = node_counts.get(node_type, 0) + 1
        
        for node_type, count in sorted(node_counts.items()):
            print(f"   • {node_type}: {count}")
        
        # --- NEW: Architectural Health Analysis ---
        from karate_graph_analyzer.analyzer.dependency_analyzer import DependencyAnalyzer
        analyzer = DependencyAnalyzer(graph)
        expert = analyzer.expert
        
        print("\n" + "🩺" + " PROJECT HEALTH REPORT")
        print("-" * 30)
        health = expert.get_health_summary()
        print(f"   ❤️  Health Score: {health['health_score']:.1f}/100")
        print(f"   🗑️  Orphan Components: {health['orphan_count']}")
        print(f"   👯 Redundant APIs: {health['redundant_api_count']}")
        print(f"   🌀 Cycles: {health['cycle_count']}")
        
        print(f"\n   🔥 Top 3 Complex Test Cases:")
        for item in health['top_complex_test_cases'][:3]:
            print(f"      • {item['name']} (Score: {item['score']})")

        # --- End Analysis ---

        # Create visualization
        print(f"\n🎨 Creating visualization...")
        output_dir = Path(__file__).parent / "output"
        output_dir.mkdir(exist_ok=True)
        
        output_file = output_dir / f"{output_name}_graph.html"
        
        visualizer = GraphVisualizer(graph)
        result_path = visualizer.render(
            output_path=str(output_file),
            height="900px",
            width="100%",
            physics_enabled=True
        )
        
        print(f"✅ Visualization: {result_path}")
        
        # Export graph to JSON
        json_file = output_dir / f"{output_name}_graph.json"
        print(f"💾 Exporting to JSON...")
        
        import json
        from datetime import datetime
        
        # Convert graph to JSON
        nodes_list = []
        for node in graph.nodes.values():
            nodes_list.append({
                "id": node.id,
                "type": node.type.value,
                "name": node.name,
                "metadata": {
                    "file_path": node.metadata.file_path,
                    "line_number": node.metadata.line_number,
                    "jira_tags": node.metadata.jira_tags,
                    "project_name": node.metadata.project_name,
                    "additional_data": node.metadata.additional_data,
                }
            })
        
        edges_list = []
        for edge in graph.edges.values():
            edges_list.append({
                "id": edge.id,
                "from_node": edge.from_node,
                "to_node": edge.to_node,
                "type": edge.type.value,
                "line_number": edge.line_number,
            })
        
        export_data = {
            "project_name": graph.project_name,
            "timestamp": datetime.now().isoformat(),
            "nodes": nodes_list,
            "edges": edges_list,
            "cycles": graph.cycles,
        }
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ JSON export: {json_file}")
        
        # Summary
        print(f"\n{'='*80}")
        print("SCAN COMPLETE")
        print(f"{'='*80}")
        print(f"\n📊 Summary:")
        print(f"   • Project: {project_name}")
        print(f"   • Nodes: {len(graph.nodes)}")
        print(f"   • Edges: {len(graph.edges)}")
        print(f"   • Cycles: {len(graph.cycles)}")
        print(f"\n📁 Output:")
        print(f"   • HTML: {output_file}")
        print(f"   • JSON: {json_file}")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python scan_project.py <project_root> [output_name]")
        print("\nExamples:")
        print("  python scan_project.py E:/Project/auto/karate-fw/karate-core")
        print("  python scan_project.py E:/Project/auto/karate-fw/karate-core my-project")
        return 1
    
    project_root = sys.argv[1]
    output_name = sys.argv[2] if len(sys.argv) > 2 else None
    
    return scan_project(project_root, output_name)


if __name__ == "__main__":
    sys.exit(main())
