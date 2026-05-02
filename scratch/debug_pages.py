from karate_graph_analyzer.mcp_interface.mcp_tool import KarateGraphAnalyzerTool
import json

def debug_pages():
    tool = KarateGraphAnalyzerTool()
    tool.register_project("karate-core", r"e:\Project\auto\karate-fw\karate-core")
    graph = tool.analyze_project("karate-core")
    
    from karate_graph_analyzer.models import NodeType
    graph_data = tool.graphs["karate-core"]
    
    print("\n--- PAGE NODES DEBUG ---")
    for node in graph_data.nodes.values():
        if node.type == NodeType.PAGE:
            print(f"ID: {node.id}")
            print(f"Name: {node.name}")
            print(f"File: {node.metadata.file_path}")
            print(f"Feature (Biz Domain): {node.metadata.additional_data.get('feature')}")
            print("-" * 20)

if __name__ == "__main__":
    debug_pages()
