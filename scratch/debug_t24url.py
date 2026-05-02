"""
Debug script to trace WHY t24Url domain is missing from graph.
"""
import sys
sys.path.insert(0, r'e:\Project\auto\karate_graph\src')

from karate_graph_analyzer.parser.config_parser import KarateConfigParser
from karate_graph_analyzer.models import ParserConfig
from karate_graph_analyzer.parser.extractors.api_extractor import ApiExtractor
from karate_graph_analyzer.models import Dependency, DependencyType

# Setup config
root = r'e:\Project\auto\karate-fw\karate-core'
config_parser = KarateConfigParser(root)
auto_config = config_parser.get_base_url_mapping()
reverse_config = config_parser.global_reverse_mapping

print("=== REVERSE MAPPING ===")
for k, v in reverse_config.items():
    if 't24' in k.lower() or 't24' in v.lower():
        print(f"  '{k}' -> '{v}'")

parser_config = ParserConfig(
    base_url_mapping=auto_config,
    variable_patterns=auto_config,
    global_reverse_mapping=reverse_config,
)

extractor = ApiExtractor(parser_config)

print("\n=== STEP 1: Test 'url t24Url' extraction ===")
deps = extractor.extract("url t24Url", 4)
for d in deps:
    print(f"  Target: {d.target}, Params: {d.parameters}")

print("\n=== STEP 2: Test 'path /api/v2/payment' extraction ===")
deps2 = extractor.extract("path '/api/v2/payment'", 8)
for d in deps2:
    print(f"  Target: {d.target}, Params: {d.parameters}")

print("\n=== STEP 3: Test normalize_logical_url('https://t24.com') ===")
result = extractor.normalize_logical_url('https://t24.com')
print(f"  Result: {result}")

print("\n=== STEP 4: Simulate ApiContextTracker ===")
from karate_graph_analyzer.parser.api_context_tracker import ApiContextTracker
from karate_graph_analyzer.models import Scenario, Step

tracker = ApiContextTracker(extractor)

# Simulate background: url t24Url
bg_deps = extractor.extract("url t24Url", 4)
for d in bg_deps:
    print(f"  BG dep: type={d.type}, target={d.target}")

# Simulate scenario
class FakeScenario:
    name = "test"
    tags = []

sc = FakeScenario()
for d in bg_deps:
    tracker.process_dependency(d, sc, "POST")

path_deps = extractor.extract("path '/api/v2/payment'", 8)
for d in path_deps:
    print(f"  PATH dep: type={d.type}, target={d.target}")
    tracker.process_dependency(d, sc, "POST")

# Emit method
method_dep = Dependency(type=DependencyType.API, target="METHOD_MARKER", line_number=10, parameters={"http_method": "POST"})
tracker.process_dependency(method_dep, sc, "POST")

print("\n=== STEP 5: Finalized API deps ===")
final = tracker.finalize(10, sc, "POST")
for d in final:
    print(f"  FINAL: target={d.target}, params={d.parameters}")

print("\n=== STEP 6: Test parse_api_hierarchy on final targets ===")
from karate_graph_analyzer.graph.core.dependency_linker import DependencyLinker
from karate_graph_analyzer.graph.core.networkx_builder import NetworkXBuilder
from karate_graph_analyzer.utils.path_classifier import PathClassifier

linker = DependencyLinker(NetworkXBuilder(), PathClassifier())

# Create a mock context
from karate_graph_analyzer.models import Project
from karate_graph_analyzer.core.context import AnalysisContext
project = Project(name="karate-core", root_path=root, parser_config=parser_config)
linker.context = AnalysisContext(project)

for d in final:
    print(f"\n  Parsing hierarchy for: '{d.target}'")
    segs = linker.parse_api_hierarchy(d.target)
    print(f"  Segments: {segs}")
