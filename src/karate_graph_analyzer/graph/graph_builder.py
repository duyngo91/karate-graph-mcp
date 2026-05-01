"""
Graph builder implementation.

Constructs dependency graphs from parsed feature files.
Supports Dependency Injection for parser (testability).
Refactored using Facade, Builder and Strategy patterns.
"""

import logging
import os
import glob
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
        # Use injected parser or create default
        if self._injected_parser is not None:
            parser = self._injected_parser
        else:
            from karate_graph_analyzer.parser.feature_parser import FeatureFileParser
            parser = FeatureFileParser(config=project.parser_config)
        
        dependency_node_map: Dict[Tuple, str] = {}
        common_api_deps_map: Dict[Tuple[str, str], List] = {}
        file_asts = []
        
        feature_files = []
        for pattern in project.feature_file_patterns:
            full_pattern = os.path.join(project.root_path, pattern)
            matched_files = glob.glob(full_pattern, recursive=True)
            feature_files.extend(matched_files)
        
        feature_files = sorted(set(feature_files))

        # Pass 1: Index all COMMON scenarios (API definitions)
        for file_path in feature_files:
            try:
                ast = parser.parse_file(file_path)
                file_asts.append(ast)
                norm_path = os.path.normpath(file_path).replace("\\", "/")
                
                for scenario in ast.scenarios:
                    scenario_node_type = self.path_classifier.classify_scenario_by_path(
                        scenario.file_path, project.parser_config
                    )
                    if scenario_node_type == NodeType.COMMON:
                        dependencies = parser.extract_dependencies_with_background(
                            scenario, ast.background_steps, validate_paths=False
                        )
                        api_deps = [d for d in dependencies if d.type == DependencyType.API]
                        for d in api_deps:
                            if "file_path" not in d.parameters:
                                d.parameters["file_path"] = scenario.file_path
                        for tag in scenario.tags:
                            common_api_deps_map[(norm_path, tag)] = api_deps
                        if not scenario.tags:
                            common_api_deps_map[(norm_path, "")] = api_deps
            except Exception as e:
                logger.error(f"Error in Pass 1 for {file_path}: {e}")

        # Pass 2: Build nodes and edges
        for ast in file_asts:
            try:
                for scenario in ast.scenarios:
                    scenario_node_type = self.path_classifier.classify_scenario_by_path(
                        scenario.file_path, project.parser_config
                    )
                    
                    if scenario_node_type == NodeType.COMMON:
                        continue
                    
                    display_name = self.path_classifier.build_scenario_display_name(scenario, scenario_node_type)
                    scenario_metadata = NodeMetadata(
                        file_path=scenario.file_path,
                        line_number=scenario.line_number,
                        jira_tags=scenario.jira_tags,
                        project_name=project.name,
                        additional_data={"scenario_type": scenario.type.value, "tags": scenario.tags},
                    )

                    rel_path = self.dependency_linker.normalize_path(scenario.file_path)

                    if scenario_node_type == NodeType.TEST_CASE:
                        node_id = self.nx_builder.add_test_case(scenario, scenario_metadata)
                    elif scenario_node_type == NodeType.WORKFLOW:
                        node_id = self.nx_builder.add_workflow_node(display_name, scenario_metadata)
                    elif scenario_node_type == NodeType.API:
                        # For API definition files, we want to register the descriptive name
                        # so that when test cases call them, they use this nice name.
                        
                        # Find the API dependency in this scenario to get the endpoint
                        dependencies = parser.extract_dependencies_with_background(
                            scenario, ast.background_steps, validate_paths=False
                        )
                        
                        for dep in dependencies:
                            if dep.type == DependencyType.API:
                                # Enrich dependency with current scenario info
                                dep.parameters["scenario_name"] = scenario.name
                                dep.parameters["scenario_tags"] = scenario.tags
                                
                                # This will create the hierarchy with the descriptive name
                                self.dependency_linker.get_or_create_dependency_node(
                                    dep, project.name, dependency_node_map
                                )
                                # Note: We don't need to link it here, 
                                # it's just to ensure the node exists in node_map with the right name.

                    elif scenario_node_type == NodeType.PAGE:
                        file_key = (NodeType.PAGE, rel_path)
                        if file_key in dependency_node_map:
                            file_node_id = dependency_node_map[file_key]
                        else:
                            file_node_id = self.nx_builder.add_page_node(rel_path, scenario_metadata)
                            dependency_node_map[file_key] = file_node_id
                        
                        action_tag = display_name
                        key_tag = action_tag if action_tag.startswith('@') else f"@{action_tag}"
                        action_key = (NodeType.ACTION, f"{rel_path}#{key_tag}")
                        if action_key in dependency_node_map:
                            node_id = dependency_node_map[action_key]
                        else:
                            node_id = self.nx_builder.add_action_node(action_tag, rel_path, scenario_metadata)
                            dependency_node_map[action_key] = node_id
                        
                        if not self.nx_builder.graph.has_edge(file_node_id, node_id):
                            self.nx_builder.add_dependency(file_node_id, node_id, DependencyType.PAGE)
                    else:
                        node_id = self.nx_builder.add_test_case(scenario, scenario_metadata)
                    
                    dependencies = parser.extract_dependencies_with_background(
                        scenario, ast.background_steps, validate_paths=False
                    )
                    
                    for dep in dependencies:
                        if dep.type == DependencyType.COMMON:
                            tag = dep.parameters.get("scenario_tag", "")
                            if tag and not tag.startswith("@"):
                                tag = "@" + tag
                            
                            target_norm = dep.target.replace("\\", "/")
                            api_deps = None
                            for map_path, map_tag in common_api_deps_map.keys():
                                if map_path.endswith(target_norm) and map_tag == tag:
                                    api_deps = common_api_deps_map.get((map_path, map_tag))
                                    break
                            
                            if api_deps:
                                for api_dep in api_deps:
                                    dep_node_id = self.dependency_linker.get_or_create_dependency_node(
                                        api_dep, project.name, dependency_node_map
                                    )
                                    self.nx_builder.add_dependency(node_id, dep_node_id, api_dep.type)
                        else:
                            dep_node_id = self.dependency_linker.get_or_create_dependency_node(
                                dep, project.name, dependency_node_map
                            )
                            self.nx_builder.add_dependency(node_id, dep_node_id, dep.type)
            except Exception as e:
                logger.error(f"Error in Pass 2: {e}", exc_info=True)

        cycles = self.nx_builder.detect_cycles()
        
        nodes_dict = {}
        for node_id in self.nx_builder.graph.nodes():
            nd = self.nx_builder.graph.nodes[node_id]
            nodes_dict[node_id] = Node(
                id=nd["id"], type=nd["type"], name=nd["name"],
                metadata=NodeMetadata(
                    file_path=nd["metadata"].get("file_path"),
                    line_number=nd["metadata"].get("line_number"),
                    jira_tags=nd["metadata"].get("jira_tags", []),
                    project_name=nd["metadata"].get("project_name", project.name),
                    additional_data=nd["metadata"].get("additional_data", {}),
                ),
            )
        
        edges_dict = {}
        for u, v in self.nx_builder.graph.edges():
            ed = self.nx_builder.graph.edges[u, v]
            edges_dict[ed["id"]] = Edge(
                id=ed["id"], from_node=ed["from_node"], to_node=ed["to_node"], type=ed["type"]
            )
        
        return DependencyGraph(
            project_name=project.name, nodes=nodes_dict, edges=edges_dict, cycles=cycles
        )

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
