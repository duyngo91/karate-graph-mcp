"""
Graph builder implementation.

Constructs dependency graphs from parsed feature files.
Supports Dependency Injection for parser (testability).
Refactored using Facade, Builder and Strategy patterns.
"""

import json
import logging
import os
import glob
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Any
import networkx as nx

from karate_graph_analyzer.models import (
    DependencyGraph,
    DependencyType,
    Edge,
    Node,
    NodeMetadata,
    NodeType,
    PathContext,
    ParserConfig,
    Project,
    Scenario,
    FeatureAST,
)

from karate_graph_analyzer.graph.core.nx_builder import NetworkXBuilder
from karate_graph_analyzer.graph.core.path_classifier import PathClassifier
from karate_graph_analyzer.graph.core.dependency_linker import DependencyLinker
from karate_graph_analyzer.graph.core.incremental_updater import IncrementalUpdater
from karate_graph_analyzer.utils.path_resolver import PathResolver

if TYPE_CHECKING:
    from karate_graph_analyzer.cache.cache_manager import CacheManager
    from karate_graph_analyzer.parser.feature_parser import FeatureFileParser

logger = logging.getLogger(__name__)


class GraphBuilder:
    """Facade for constructing dependency graphs."""

    def __init__(self, parser: Optional["FeatureFileParser"] = None, config: Optional[ParserConfig] = None) -> None:
        self.nx_builder = NetworkXBuilder()
        self.config = config or (parser.config if parser else ParserConfig())
        self.path_classifier = PathClassifier()
        self.dependency_linker = DependencyLinker(self.nx_builder, config=self.config)
        self.incremental_updater = IncrementalUpdater(self.nx_builder, self.path_classifier, self.dependency_linker)
        self._injected_parser = parser

    @property
    def graph(self): return self.nx_builder.graph

    @graph.setter
    def graph(self, value): self.nx_builder.graph = value

    # Proxy methods for backward compatibility with tests
    def add_test_case(self, scenario: Scenario, metadata: NodeMetadata) -> str:
        return self.nx_builder.add_test_case(scenario, metadata)

    def add_workflow_node(self, name: str, metadata: NodeMetadata) -> str:
        return self.nx_builder.add_workflow_node(name, metadata)

    def add_common_node(self, name: str, metadata: NodeMetadata) -> str:
        return self.nx_builder.add_common_node(name, metadata)

    def add_api_node(self, endpoint: str, metadata: NodeMetadata) -> str:
        return self.nx_builder.add_api_node(endpoint, metadata)

    def add_page_node(self, name: str, metadata: NodeMetadata) -> str:
        return self.nx_builder.add_page_node(name, metadata)

    def add_database_node(self, operation: str, metadata: NodeMetadata) -> str:
        return self.nx_builder.add_database_node(operation, metadata)

    def add_dependency(self, from_node: str, to_node: str, dep_type: DependencyType, line_number: int = None) -> str:
        return self.nx_builder.add_dependency(from_node, to_node, dep_type, line_number)

    def detect_cycles(self) -> List[List[str]]:
        return self.nx_builder.detect_cycles()

    def build_from_project(self, project: Project) -> DependencyGraph:
        """Build complete graph for a project using 2-pass strategy."""
        self.nx_builder.graph = nx.DiGraph()
        parser = self._injected_parser or self._create_default_parser(project)
        
        # Sync config with components
        self.config = project.parser_config
        self.dependency_linker.config = self.config
        
        feature_files = self._get_feature_files(project)
        ast_list: List[FeatureAST] = []
        
        # Pass 1: Parse and Filter ignored components
        ignored_files = set()
        for path in feature_files:
            try:
                ast = parser.parse_file(path)
                if not ast.scenarios:
                    logger.warning(f"File skipped (no scenarios found): {path}")
                    ignored_files.add(PathResolver.normalize_path(path))
                else:
                    logger.info(f"Successfully parsed: {path} ({len(ast.scenarios)} scenarios)")
                    ast_list.append(ast)
            except Exception as e:
                logger.error(f"Failed to parse {path}: {str(e)}")
                ignored_files.add(PathResolver.normalize_path(path))

        # Store ignored files in a way build_from_asts can access
        self._ignored_files = ignored_files
        self.dependency_linker.ignored_files = ignored_files

        return self.build_from_asts(project, ast_list)

    def build_from_asts(self, project: Project, ast_list: List[FeatureAST]) -> DependencyGraph:
        """Build a graph from pre-parsed ASTs using the same 2-pass strategy."""
        self.nx_builder.graph = nx.DiGraph()
        
        # Sync config with components
        self.config = project.parser_config
        self.dependency_linker.config = self.config
        
        parser = self._injected_parser or self._create_default_parser(project)

        # Pass 1: Extract API definitions from COMMON components
        common_api_map: Dict[Tuple[str, str], List] = {}
        for ast in ast_list:
            norm_path = PathResolver.normalize_path(ast.file_path)
            for scenario in ast.scenarios:
                if self.path_classifier.classify_scenario_by_path(scenario.file_path, project.parser_config) == NodeType.COMMON:
                    deps = parser.extract_dependencies_with_background(scenario, ast.background_steps)
                    api_deps = [d for d in deps if d.type == DependencyType.API]
                    for d in api_deps: d.parameters["file_path"] = scenario.file_path
                    
                    keys = [(norm_path, tag) for tag in scenario.tags] or [(norm_path, "")]
                    for k in keys: common_api_map[k] = api_deps

        # Pass 2: Build all nodes and link dependencies
        node_map: Dict[Tuple, str] = {}
        for ast in ast_list:
            self._process_ast_nodes(ast, parser, project, common_api_map, node_map)

        return self._create_final_graph(project.name, project.root_path)

    def _process_ast_nodes(self, ast: FeatureAST, parser, project, common_map, node_map):
        for scenario in ast.scenarios:
            try:
                node_type = self.path_classifier.classify_scenario_by_path(scenario.file_path, project.parser_config)
                # We process all types now to ensure orphan common/page files are visible
                
                context = PathContext(scenario.file_path, project.root_path, project.parser_config)
                
                metadata = NodeMetadata(
                    file_path=scenario.file_path, line_number=scenario.line_number,
                    jira_tags=scenario.jira_tags, project_name=project.name,
                    additional_data={"scenario_type": scenario.type.value, "tags": scenario.tags},
                )

                if node_type == NodeType.API:
                    # APIs in non-common files register their info in pass 2
                    deps = parser.extract_dependencies_with_background(scenario, ast.background_steps)
                    for d in [d for d in deps if d.type == DependencyType.API]:
                        d.parameters.update({"scenario_name": scenario.name, "scenario_tags": scenario.tags})
                        self.dependency_linker.get_or_create_dependency_node(d, project.name, node_map, context=context)
                    continue
                
                # Create main node
                node_id = self._create_typed_node(node_type, scenario, metadata, node_map)
                
                # Link dependencies
                self._link_dependencies(scenario, ast, parser, project, node_id, common_map, node_map, context)
            except Exception as e:
                logger.error(f"Error processing scenario {scenario.name} in {ast.file_path}: {e}", exc_info=True)

    def _create_typed_node(self, node_type: NodeType, scenario: Scenario, metadata: NodeMetadata, node_map: Dict) -> str:
        if node_type == NodeType.PAGE:
            return self._handle_page_and_action(scenario, metadata, node_map)
        
        if node_type == NodeType.WORKFLOW or node_type == NodeType.COMMON:
            name = self.path_classifier.build_scenario_display_name(scenario, node_type)
            if node_type == NodeType.WORKFLOW:
                return self.nx_builder.add_workflow_node(name, metadata)
            else:
                return self.nx_builder.add_common_node(name, metadata)
            
        return self.nx_builder.add_test_case(scenario, metadata)

    def _handle_page_and_action(self, scenario, metadata, node_map) -> str:
        rel_path = PathResolver.normalize_path(scenario.file_path)
        file_node_id = self.dependency_linker._get_or_create_node(
            NodeType.PAGE, rel_path, metadata, node_map, self.nx_builder.add_page_node
        )
        
        action_tag = self.path_classifier.build_scenario_display_name(scenario, NodeType.PAGE)
        return self.dependency_linker._handle_tag_subnode(
            file_node_id, NodeType.PAGE, rel_path, action_tag, metadata, node_map, DependencyType.PAGE
        )

    def _link_dependencies(self, scenario, ast, parser, project, node_id, common_map, node_map, context):
        deps = parser.extract_dependencies_with_background(scenario, ast.background_steps)
        for dep in deps:
            if dep.type == DependencyType.COMMON:
                self._link_common_dependency(node_id, dep, project.name, common_map, node_map)
            else:
                dep_id = self.dependency_linker.get_or_create_dependency_node(dep, project.name, node_map, context=context)
                if dep_id:
                    self.nx_builder.add_dependency(node_id, dep_id, dep.type, line_number=dep.line_number)

    def _link_common_dependency(self, node_id, dep, project_name, common_map, node_map):
        tag = dep.parameters.get("scenario_tag", "")
        if tag and not tag.startswith("@"): tag = "@" + tag
        
        target_norm = PathResolver.normalize_path(dep.target)
        api_deps = next((common_map[k] for k in common_map if k[0].endswith(target_norm) and k[1] == tag), None)

        common_dep_id = self.dependency_linker.get_or_create_dependency_node(dep, project_name, node_map)
        if common_dep_id:
            self.nx_builder.add_dependency(node_id, common_dep_id, dep.type, line_number=dep.line_number)
            
            if api_deps:
                for api_dep in api_deps:
                    dep_id = self.dependency_linker.get_or_create_dependency_node(api_dep, project_name, node_map)
                    if dep_id:
                        self.nx_builder.add_dependency(node_id, dep_id, api_dep.type, line_number=dep.line_number)

    def _get_feature_files(self, project: Project) -> List[str]:
        from pathlib import Path
        files = []
        exclude_dirs = {"target", "build", "node_modules", ".git"}
        for p in project.feature_file_patterns:
            matches = glob.glob(os.path.join(project.root_path, p), recursive=True)
            for m in matches:
                path_parts = [p.lower() for p in Path(m).parts]
                if not any(ex in path_parts for ex in exclude_dirs):
                    files.append(m)
        return sorted(set(files))

    def _create_default_parser(self, project: Project):
        from karate_graph_analyzer.parser.feature_parser import FeatureFileParser
        return FeatureFileParser(config=project.parser_config)

    def _create_final_graph(self, project_name: str, project_root: str = None) -> DependencyGraph:
        cycles = self.nx_builder.detect_cycles()
        nodes_dict = {}
        for nid, nd in self.nx_builder.graph.nodes(data=True):
            meta = NodeMetadata(**{k: v for k, v in nd["metadata"].items() if k != "project_name"}, 
                                project_name=nd["metadata"].get("project_name", project_name))
            
            if nd["type"] == NodeType.LOCATOR.value and project_root and meta.file_path:
                self._enrich_locator_metadata(meta, project_root)

            nodes_dict[nid] = Node(id=nd["id"], type=nd["type"], name=nd["name"], metadata=meta, tags=nd.get("tags", []))
            
        edges_dict = {
            ed["id"]: Edge(id=ed["id"], from_node=ed["from_node"], to_node=ed["to_node"], type=ed["type"], line_number=ed.get("line_number"))
            for _, _, ed in self.nx_builder.graph.edges(data=True)
        }
        return DependencyGraph(project_name=project_name, nodes=nodes_dict, edges=edges_dict, cycles=cycles)

    def _enrich_locator_metadata(self, meta: NodeMetadata, project_root: str):
        try:
            full_path = os.path.join(project_root, meta.file_path)
            if not os.path.exists(full_path):
                for p in ['src/test/java', 'src/test/resources', 'src/main/resources']:
                    cand = os.path.join(project_root, p, meta.file_path)
                    if os.path.exists(cand): full_path = cand; break
            
            if os.path.exists(full_path) and full_path.endswith('.json'):
                with open(full_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict): meta.additional_data['selectors'] = list(data.keys())
        except Exception as e: logger.warning(f"Failed to parse locator {meta.file_path}: {e}")

    def update_from_project(self, project: Project, graph: DependencyGraph, cache: "CacheManager") -> DependencyGraph:
        parser = self._injected_parser or self._create_default_parser(project)
        return self.incremental_updater.update_from_project(project, graph, cache, parser)
