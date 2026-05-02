import json
import logging
import os
from pprint import pprint

from karate_graph_analyzer.mcp_interface.mcp_tool import KarateGraphAnalyzerTool

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def demo_ai_agent():
    print("=== Karate Graph AI Agent Demo ===")
    tool = KarateGraphAnalyzerTool()
    
    project_name = "karate-core-demo"
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../karate-fw/karate-core"))
    
    print(f"\n1. Analyzing project: {project_root}")
    res = tool.register_project(project_name, project_root)
    if not res.get("success") and res.get("error", {}).get("code") != 3001:
        print(f"Failed to register project: {res}")
        return
        
    res = tool.analyze_project(project_name)
    if not res.get("success"):
        print(f"Failed to analyze project: {res}")
        return
    print(f"Graph analyzed successfully. Found {res['statistics']['total_nodes']} nodes.")
    
    # Feature 1: Keyword Search
    print("\n2. AI Agent received a User Story: 'Update the Promo Code feature'")
    print("   AI is searching the graph for the keyword 'promo'...")
    search_res = tool.search_workflow(project_name, keyword="promo")
    if search_res.get("success") and search_res["count"] > 0:
        print(f"   Found {search_res['count']} workflows/scenarios matching 'promo':")
        for w in search_res["results"]:
            print(f"     - [{w['type']}] {w['name']}")
    else:
        print("   No workflows found for keyword 'promo'.")
        # Let's try another keyword
        print("   Let's try 'payment' instead...")
        search_res = tool.search_workflow(project_name, keyword="payment")
        if search_res.get("success"):
            print(f"   Found {search_res['count']} workflows/scenarios matching 'payment':")
            for w in search_res["results"][:3]: # limit output
                print(f"     - [{w['type']}] {w['name']}")
                
    # Feature 2: Locator Parsing & Impact Analysis
    print("\n3. Developer updated UI Locator 'btn-submit' in 'locators/common.json'.")
    print("   AI is extracting the graph to find the exact locator node...")
    
    graph = tool.analyzers[project_name].graph
    locator_nodes = [n for n in graph.nodes.values() if n.type.value == "LOCATOR"]
    
    print(f"   Found {len(locator_nodes)} LOCATOR files.")
    for ln in locator_nodes:
        selectors = ln.metadata.additional_data.get('selectors', [])
        print(f"     - {ln.name} has {len(selectors)} selectors parsed.")
        
    print("\n4. AI predicts impact of changing this locator:")
    if locator_nodes:
        target_locator = locator_nodes[0].id
        print(f"   Running impact analysis for {target_locator}...")
        impact = tool.impact_analysis(target_locator)
        if impact.get("success"):
            print(f"   Impacted Test Cases: {impact['total_count']}")
            for tc in impact.get('affected_test_cases', []):
                print(f"     -> {tc['name']} ({tc['node_id']})")
    
    print("\n=== Demo Complete ===")

if __name__ == "__main__":
    demo_ai_agent()
