"""
Graph builder implementation.

Constructs dependency graphs from parsed feature files.
Supports Dependency Injection for parser (testability).
Refactored using Facade, Builder and Strategy patterns.
"""

import logging
import os
import glob
import networkx as nx
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from karate_graph_analyzer.models import (
    DependencyGraph,
    DependencyType,
    Edge,
    Node,
    NodeMetadata,
    NodeType,
    Project,
    Scenario,
    ParseError,
)

from karate_graph_analyzer.graph.core.nx_builder import NetworkXBuilder
from karate_graph_analyzer.graph.core.path_classifier import PathClassifier
from karate_graph_analyzer.graph.core.dependency_linker import DependencyLinker
from karate_graph_analyzer.graph.core.incremental_updater import IncrementalUpdater

if TYPE_CHECKING:
    from karate_graph_analyzer.cache.cache_manager import CacheManager
    from karate_graph_analyzer.parser.feature_parser import FeatureFileParser

logger = logging.getLogger(__name__)


class GraphBuilder:
    """Facade for constructing dependency graphs.
    
    Coordinates specialized components to build and update graphs.
    """

    def __init__(self, parser: Optional["FeatureFileParser"] = None) -> None:
        """Initialize graph builder with specialized components."""
        self.nx_builder = NetworkXBuilder()
        self.path_classifier = PathClassifier()
        self.dependency_linker = DependencyLinker(self.nx_builder)
        self.incremental_updater = IncrementalUpdater(
            self.nx_builder, self.path_classifier, self.dependency_linker
        )
        self._injected_parser = parser

    @property
    def graph(self):
        """Proxy for the underlying NetworkX graph."""
        return self.nx_builder.graph

    @graph.setter
    def graph(self, value):
        self.nx_builder.graph = value

    # --- Proxy methods for backward compatibility and internal use ---

    def _generate_node_id(self, node_type: NodeType) -> str:
        return self.nx_builder._generate_node_id(node_type)

    def add_test_case(self, scenario: Scenario, metadata: NodeMetadata) -> str:
        return self.nx_builder.add_test_case(scenario, metadata)

    def add_workflow_node(self, name: str, metadata: NodeMetadata) -> str:
        return self.nx_builder.add_workflow_node(name, metadata)

    def add_api_node(self, endpoint: str, metadata: NodeMetadata) -> str:
        return self.nx_builder.add_api_node(endpoint, metadata)

    def add_api_group_node(self, group_name: str, metadata: NodeMetadata) -> str:
        return self.nx_builder.add_api_group_node(group_name, metadata)

    def add_page_node(self, page_path: str, metadata: NodeMetadata) -> str:
        return self.nx_builder.add_page_node(page_path, metadata)

    def add_database_node(self, operation: str, metadata: NodeMetadata) -> str:
        return self.nx_builder.add_database_node(operation, metadata)

    def add_locator_node(self, locator_path: str, metadata: NodeMetadata) -> str:
        return self.nx_builder.add_locator_node(locator_path, metadata)

    def add_scenario_node(self, scenario_tag: str, workflow_path: str, metadata: NodeMetadata) -> str:
        return self.nx_builder.add_scenario_node(scenario_tag, workflow_path, metadata)

    def add_action_node(self, action_tag: str, page_path: str, metadata: NodeMetadata) -> str:
        return self.nx_builder.add_action_node(action_tag, page_path, metadata)

    def add_dependency(self, from_node: str, to_node: str, dep_type: DependencyType) -> str:
        return self.nx_builder.add_dependency(from_node, to_node, dep_type)

    def detect_cycles(self) -> List[List[str]]:
        return self.nx_builder.detect_cycles()

    def _classify_scenario_by_path(self, file_path: str, config=None) -> NodeType:
        return self.path_classifier.classify_scenario_by_path(file_path, config)

    def _build_scenario_display_name(self, scenario: Scenario, node_type: NodeType) -> str:
        return self.path_classifier.build_scenario_display_name(scenario, node_type)

    def _detect_feature_from_path(self, file_path: str) -> str:
        return self.path_classifier.detect_feature_from_path(file_path)

    def _create_api_hierarchy(self, endpoint: str, metadata: NodeMetadata, node_map: Dict) -> str:
        return self.dependency_linker.create_api_hierarchy(endpoint, metadata, node_map)

    def _get_or_create_dependency_node(self, dep, project_name: str, node_map: Dict) -> str:
        return self.dependency_linker.get_or_create_dependency_node(dep, project_name, node_map)

    # --- Core Orchestration Logic ---

    def build_from_project(self, project: Project) -> DependencyGraph:
        """Build complete graph for a project using 2-pass strategy."""
        self.nx_builder.graph = nx.DiGraph()
        self.nx_builder._node_counter = {}
        parser = self._injected_parser or self._create_default_parser(project)
        
        feature_files = self._get_feature_files(project)
        common_api_deps_map: Dict[Tuple[str, str], List] = {}
        file_asts: List[FeatureAST] = []
        
        # Pass 1: Index all COMMON scenarios (API definitions)
        self._index_common_scenarios(feature_files, parser, project, common_api_deps_map, file_asts)

        # Pass 2: Build nodes and edges
        dependency_node_map: Dict[Tuple, str] = {}
        self._build_nodes_and_edges(file_asts, parser, project, common_api_deps_map, dependency_node_map)

        return self._create_final_graph(project.name)

    def build_from_asts(self, project: Project, file_asts: List) -> DependencyGraph:
        """Build a graph from pre-parsed ASTs using the same 2-pass strategy."""
        self.nx_builder.graph = nx.DiGraph()
        self.nx_builder._node_counter = {}
        parser = self._injected_parser or self._create_default_parser(project)

        common_api_deps_map: Dict[Tuple[str, str], List] = {}
        for ast in file_asts:
            norm_path = os.path.normpath(ast.file_path).replace("\\", "/")
            for scenario in ast.scenarios:
                if self.path_classifier.classify_scenario_by_path(
                    scenario.file_path, project.parser_config
                ) == NodeType.COMMON:
                    deps = parser.extract_dependencies_with_background(scenario, ast.background_steps)
                    api_deps = [d for d in deps if d.type == DependencyType.API]
                    for dep in api_deps:
                        dep.parameters["file_path"] = scenario.file_path

                    keys = [(norm_path, tag) for tag in scenario.tags] or [(norm_path, "")]
                    for key in keys:
                        common_api_deps_map[key] = api_deps

        dependency_node_map: Dict[Tuple, str] = {}
        self._build_nodes_and_edges(file_asts, parser, project, common_api_deps_map, dependency_node_map)
        return self._create_final_graph(project.name)

    def _create_default_parser(self, project: Project):
        from karate_graph_analyzer.parser.feature_parser import FeatureFileParser
        return FeatureFileParser(config=project.parser_config)

    def _get_feature_files(self, project: Project) -> List[str]:
        feature_files = []
        for pattern in project.feature_file_patterns:
            full_pattern = os.path.join(project.root_path, pattern)
            feature_files.extend(glob.glob(full_pattern, recursive=True))
        return sorted(set(feature_files))

    def _index_common_scenarios(self, files, parser, project, common_map, ast_list):
        for path in files:
            try:
                ast = parser.parse_file(path)
                ast_list.append(ast)
                norm_path = os.path.normpath(path).replace("\\", "/")
                
                for scenario in ast.scenarios:
                    if self.path_classifier.classify_scenario_by_path(scenario.file_path, project.parser_config) == NodeType.COMMON:
                        deps = parser.extract_dependencies_with_background(scenario, ast.background_steps)
                        api_deps = [d for d in deps if d.type == DependencyType.API]
                        for d in api_deps: d.parameters["file_path"] = scenario.file_path
                        
                        keys = [(norm_path, tag) for tag in scenario.tags] or [(norm_path, "")]
                        for k in keys: common_map[k] = api_deps
            except Exception as e:
                logger.error(f"Error indexing {path}: {e}")

    def _build_nodes_and_edges(self, ast_list, parser, project, common_map, node_map):
        for ast in ast_list:
            try:
                for scenario in ast.scenarios:
                    node_type = self.path_classifier.classify_scenario_by_path(scenario.file_path, project.parser_config)
                    if node_type == NodeType.COMMON: continue
                    
                    metadata = NodeMetadata(
                        file_path=scenario.file_path, line_number=scenario.line_number,
                        jira_tags=scenario.jira_tags, project_name=project.name,
                        additional_data={"scenario_type": scenario.type.value, "tags": scenario.tags},
                    )

                    # Handle different node types
                    if node_type == NodeType.TEST_CASE:
                        node_id = self.nx_builder.add_test_case(scenario, metadata)
                    elif node_type == NodeType.WORKFLOW:
                        display_name = self.path_classifier.build_scenario_display_name(scenario, node_type)
                        node_id = self.nx_builder.add_workflow_node(display_name, metadata)
                    elif node_type == NodeType.API:
                        # Register descriptive name for API files
                        deps = parser.extract_dependencies_with_background(scenario, ast.background_steps)
                        for d in [d for d in deps if d.type == DependencyType.API]:
                            d.parameters.update({"scenario_name": scenario.name, "scenario_tags": scenario.tags})
                            self.dependency_linker.get_or_create_dependency_node(d, project.name, node_map)
                        continue
                    elif node_type == NodeType.PAGE:
                        node_id = self._handle_page_and_action(scenario, metadata, node_map)
                    else:
                        node_id = self.nx_builder.add_test_case(scenario, metadata)
                    
                    # Process and link dependencies
                    self._link_scenario_dependencies(scenario, ast, parser, project, node_id, common_map, node_map)
            except Exception as e:
                logger.error(f"Error building graph for {ast.file_path}: {e}", exc_info=True)

    def _handle_page_and_action(self, scenario, metadata, node_map) -> str:
        rel_path = self.dependency_linker.normalize_path(scenario.file_path)
        file_key = (NodeType.PAGE, rel_path)
        
        if file_key in node_map:
            file_node_id = node_map[file_key]
        else:
            file_node_id = self.nx_builder.add_page_node(rel_path, metadata)
            node_map[file_key] = file_node_id
        
        action_tag = self.path_classifier.build_scenario_display_name(scenario, NodeType.PAGE)
        key_tag = action_tag if action_tag.startswith('@') else f"@{action_tag}"
        action_key = (NodeType.ACTION, f"{rel_path}#{key_tag}")
        
        if action_key in node_map:
            node_id = node_map[action_key]
        else:
            node_id = self.nx_builder.add_action_node(action_tag, rel_path, metadata)
            node_map[action_key] = node_id
        
        if not self.nx_builder.graph.has_edge(file_node_id, node_id):
            self.nx_builder.add_dependency(file_node_id, node_id, DependencyType.PAGE)
        return node_id

    def _link_scenario_dependencies(self, scenario, ast, parser, project, node_id, common_map, node_map):
        deps = parser.extract_dependencies_with_background(scenario, ast.background_steps)
        for dep in deps:
            if dep.type == DependencyType.COMMON:
                tag = dep.parameters.get("scenario_tag", "")
                if tag and not tag.startswith("@"): tag = "@" + tag
                
                target_norm = dep.target.replace("\\", "/")
                api_deps = next((common_map[k] for k in common_map if k[0].endswith(target_norm) and k[1] == tag), None)

                common_dep_id = self.dependency_linker.get_or_create_dependency_node(dep, project.name, node_map)
                self.nx_builder.add_dependency(node_id, common_dep_id, dep.type, line_number=dep.line_number)
                
                if api_deps:
                    for api_dep in api_deps:
                        dep_id = self.dependency_linker.get_or_create_dependency_node(api_dep, project.name, node_map)
                        self.nx_builder.add_dependency(node_id, dep_id, api_dep.type, line_number=dep.line_number)
            else:
                dep_id = self.dependency_linker.get_or_create_dependency_node(dep, project.name, node_map)
                self.nx_builder.add_dependency(node_id, dep_id, dep.type, line_number=dep.line_number)

    def _create_final_graph(self, project_name: str) -> DependencyGraph:
        cycles = self.nx_builder.detect_cycles()
        nodes_dict = {
            nid: Node(id=nd["id"], type=nd["type"], name=nd["name"],
                     metadata=NodeMetadata(**{k: v for k, v in nd["metadata"].items() if k != "project_name"}, 
                                        project_name=nd["metadata"].get("project_name", project_name)))
            for nid, nd in self.nx_builder.graph.nodes(data=True)
        }
        edges_dict = {
            ed["id"]: Edge(
                id=ed["id"], 
                from_node=ed["from_node"], 
                to_node=ed["to_node"], 
                type=ed["type"],
                line_number=ed.get("line_number")
            )
            for _, _, ed in self.nx_builder.graph.edges(data=True)
        }
        return DependencyGraph(project_name=project_name, nodes=nodes_dict, edges=edges_dict, cycles=cycles)

    def update_from_project(self, project: Project, existing_graph: DependencyGraph, cache_manager: "CacheManager") -> DependencyGraph:
        """Proxy to IncrementalUpdater."""
        if self._injected_parser is not None:
            parser = self._injected_parser
        else:
            from karate_graph_analyzer.parser.feature_parser import FeatureFileParser
            parser = FeatureFileParser(config=project.parser_config)
            
        return self.incremental_updater.update_from_project(
            project, existing_graph, cache_manager, parser
        )
