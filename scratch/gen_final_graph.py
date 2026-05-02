
import os
import sys
import logging
import webbrowser

# Add src to path
sys.path.append(os.path.abspath("src"))

from karate_graph_analyzer.models import Project, ParserConfig
from karate_graph_analyzer.graph.graph_builder import GraphBuilder
from karate_graph_analyzer.visualization.graph_visualizer import GraphVisualizer
from karate_graph_analyzer.parser.config_parser import KarateConfigParser

# Setup logging
logging.basicConfig(level=logging.INFO)

PROJECT_ROOT = r"E:\Project\auto\karate-fw\karate-core"

def generate_and_open_graph():
    # 0. Auto-detect variables from karate-config*.js
    print("\n--- Auto-detecting Karate config variables ---")
    config_parser = KarateConfigParser(PROJECT_ROOT)
    variable_patterns = config_parser.parse_all_configs()
    print(f"Detected {len(variable_patterns)} variable(s):")
    for k, v in sorted(variable_patterns.items()):
        print(f"  {k} = {v}")

    parser_config = ParserConfig(
        variable_patterns=variable_patterns,
        # ApiExtractor uses base_url_mapping to resolve `url <varName>` statements
        base_url_mapping={**ParserConfig().base_url_mapping, **variable_patterns},
    )

    project = Project(
        name="karate-core-final-verify",
        root_path=PROJECT_ROOT,
        feature_file_patterns=["src/test/java/**/*.feature", "src/main/resources/**/*.feature"],
        parser_config=parser_config,
    )
    
    # 1. Build Graph
    print("\n--- Building Graph ---")
    builder = GraphBuilder()
    graph = builder.build_from_project(project)
    
    # 2. Print breakdown
    from collections import Counter
    type_counts = Counter(n.type.value for n in graph.nodes.values())
    print("\n=== Node Breakdown ===")
    for t, c in sorted(type_counts.items()):
        print(f"  {t}: {c}")

    print("\n=== All API nodes ===")
    for nid, n in graph.nodes.items():
        if n.type.value == "API":
            method = n.metadata.additional_data.get("http_method", "?")
            print(f"  [{method:8}] {n.name}")

    # Orphan check
    import networkx as nx
    g = builder.nx_builder.graph
    orphans = [(g.nodes[nid].get("type").value, g.nodes[nid].get("name", nid))
               for nid in g.nodes
               if g.in_degree(nid) == 0
               and g.nodes[nid].get("type")
               and g.nodes[nid].get("type").value != "TEST_CASE"]
    print(f"\n=== Orphan nodes: {len(orphans)} ===")
    for t, name in sorted(orphans):
        print(f"  [{t}] {name}")

    # 3. Visualize
    print("\n--- Generating Visualization ---")
    visualizer = GraphVisualizer(graph)
    output_path = os.path.abspath("karate_core_final_python_gen.html")
    final_path = visualizer.render(output_path=output_path)
    
    print(f"\nGraph generated at: {final_path}")
    print(f"Total nodes: {len(graph.nodes)} | Total edges: {len(graph.edges)}")
    
    # 4. Open in browser
    webbrowser.open(f"file:///{final_path}")

if __name__ == "__main__":
    generate_and_open_graph()
