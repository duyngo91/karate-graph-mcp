import os, sys
sys.path.append(os.path.abspath("src"))

from collections import Counter
from karate_graph_analyzer.models import Project
from karate_graph_analyzer.graph.graph_builder import GraphBuilder

project = Project(
    name="karate-core-verify",
    root_path=r"E:\Project\auto\karate-fw\karate-core",
    feature_file_patterns=["src/test/java/**/*.feature", "src/main/resources/**/*.feature"]
)
builder = GraphBuilder()
graph = builder.build_from_project(project)

# --- Node breakdown ---
type_counts = Counter(n.type.value for n in graph.nodes.values())
print("=== Node Breakdown ===")
for t, c in sorted(type_counts.items()):
    print(f"  {t}: {c}")

print()
print("=== All API nodes ===")
for nid, n in graph.nodes.items():
    if n.type.value == "API":
        method = n.metadata.additional_data.get("http_method", "?")
        print(f"  [{method:8}] {n.name}")

print()
print("=== COMMON nodes ===")
for nid, n in graph.nodes.items():
    if n.type.value == "COMMON":
        fp = n.metadata.file_path or "NULL (orphan!)"
        print(f"  {n.name}")
        print(f"    file_path = {fp}")

print()
print("=== Orphan nodes (no incoming edges, not TEST_CASE) ===")
g = builder.nx_builder.graph
orphans = []
for nid in g.nodes:
    nd = g.nodes[nid]
    node_type = nd.get("type")
    if g.in_degree(nid) == 0 and node_type and node_type.value != "TEST_CASE":
        orphans.append((node_type.value, nd.get("name", nid)))

if orphans:
    for t, name in sorted(orphans):
        print(f"  [{t}] {name}")
else:
    print("  None! Clean graph.")

print()
print(f"Total nodes: {len(graph.nodes)}")
print(f"Total edges: {len(graph.edges)}")
