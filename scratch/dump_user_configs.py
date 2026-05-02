import sys
import os
sys.path.append(r'e:\Project\auto\karate_graph\src')

from karate_graph_analyzer.parser.config_parser import KarateConfigParser

root = r'e:\Project\auto\karate-fw\karate-core'
parser = KarateConfigParser(root)
mapping = parser.get_base_url_mapping()
print("Variables:")
for k, v in mapping.items():
    print(f"  {k} = {v}")
print("\nReverse Mapping:")
for k, v in parser.global_reverse_mapping.items():
    print(f"  {k} -> {v}")
