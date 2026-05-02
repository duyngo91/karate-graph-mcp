import json
import os

json_path = r'E:\Project\auto\karate_graph\output\MultiScan_karate-core_graph.json'

if not os.path.exists(json_path):
    print(f"Error: {json_path} not found")
    exit(1)

with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

test_cases = [node for node in data.get('nodes', []) if node.get('type') == 'TEST_CASE']
names = sorted([tc.get('name', 'Unnamed') for tc in test_cases])

print(f"Total Test Cases: {len(names)}")
for i, name in enumerate(names, 1):
    print(f"{i}. {name}")
