import json

def count_t24_apis(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    t24_apis = []
    for node in data.get('nodes', []):
        if node.get('type') == 'API':
            # Check if t24 is in domain or path
            meta = node.get('metadata', {})
            domain = meta.get('domain', '').lower()
            path = meta.get('path', '').lower()
            
            if 't24' in domain or 't24' in path:
                t24_apis.append({
                    'method': meta.get('method'),
                    'domain': meta.get('domain'),
                    'path': meta.get('path')
                })
    
    print(f"Total T24 APIs: {len(t24_apis)}")
    for api in t24_apis:
        print(f"  - {api['method']} {api['domain']}{api['path']}")

if __name__ == "__main__":
    count_t24_apis(r"e:\Project\auto\karate_graph\output\MultiScan_karate-core_graph.json")
