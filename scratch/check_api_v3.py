from karate_graph_analyzer.mcp_interface.mcp_tool import KarateGraphAnalyzerTool
import os

def check_impact():
    tool = KarateGraphAnalyzerTool()
    project_name = 'karate-core'
    project_root = os.path.abspath('E:/Project/auto/karate-fw/karate-core')

    # Register ignoring existing error
    res = tool.register_project(project_name, project_root)
    
    # Analyze
    tool.analyze_project(project_name)

    # Find the API node for payment
    search_res = tool.search_api(project_name, path='payment')
    if search_res.get('success') and search_res['count'] > 0:
        for api in search_res['results']:
            method = api.get('metadata', {}).get('http_method', 'N/A')
            path = api.get('metadata', {}).get('full_url', api['name'])
            print(f"Found API: {method} {path}")
            print(f"  -> Node ID: {api['id']}")
            
            # Run impact analysis
            impact = tool.impact_analysis(api['id'])
            if impact.get('success'):
                print(f"  -> If we change this API to v3, it will impact {impact['total_count']} test cases:")
                for tc in impact.get('affected_test_cases', []):
                    path_str = " -> ".join(tc['dependency_path'])
                    print(f"       - {tc['name']} (Path: {path_str})")

if __name__ == "__main__":
    check_impact()
