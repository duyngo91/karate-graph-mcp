import json
from pathlib import Path

def analyze_impact():
    json_path = Path(r"E:\Project\auto\karate_graph\output\karate_core_scan_graph.json")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    nodes = {n['id']: n for n in data['nodes']}
    edges = data['edges']
    
    # Find v1 API nodes
    v1_api_ids = []
    for node_id, node in nodes.items():
        if node['type'] == 'API' and '/v1/' in node['name']:
            v1_api_ids.append(node_id)
    
    print(f"Found {len(v1_api_ids)} v1 API nodes.")
    
    # Map of target_node -> list of source_nodes
    incoming = {}
    for edge in edges:
        to_node = edge['to_node']
        from_node = edge['from_node']
        if to_node not in incoming:
            incoming[to_node] = []
        incoming[to_node].append(from_node)
    
    def find_affected_test_cases(target_id, visited=None):
        if visited is None:
            visited = set()
        
        if target_id in visited:
            return set()
        visited.add(target_id)
        
        affected_tcs = set()
        sources = incoming.get(target_id, [])
        for src_id in sources:
            src_node = nodes.get(src_id)
            if not src_node:
                continue
            if src_node['type'] == 'TEST_CASE':
                affected_tcs.add(src_node['name'])
            # Continue searching upstream
            affected_tcs.update(find_affected_test_cases(src_id, visited))
        
        return affected_tcs

    all_affected = set()
    for api_id in v1_api_ids:
        all_affected.update(find_affected_test_cases(api_id))
    
    print("\nTotal affected Test Cases:", len(all_affected))
    for tc in sorted(all_affected):
        print(f"- {tc}")

if __name__ == "__main__":
    analyze_impact()
