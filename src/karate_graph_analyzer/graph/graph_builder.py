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
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Any, Set
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
    ComponentCategory,
    FlowType
)

from karate_graph_analyzer.graph.core.nx_builder import NetworkXBuilder
from karate_graph_analyzer.graph.core.path_classifier import PathClassifier
from karate_graph_analyzer.graph.core.dependency_linker import DependencyLinker
from karate_graph_analyzer.graph.core.incremental_updater import IncrementalUpdater
from karate_graph_analyzer.graph.structural_builder import StructuralBuilder
from karate_graph_analyzer.parser.extractors.call_read_extractor import CallReadExtractor
from karate_graph_analyzer.parser.extractors.javascript_structure_extractor import JavaScriptStructureExtractor
from karate_graph_analyzer.utils.path_resolver import PathResolver
from karate_graph_analyzer.utils.scan_filters import is_excluded_path
from karate_graph_analyzer.core.context import AnalysisContext

if TYPE_CHECKING:
    from karate_graph_analyzer.cache.cache_manager import CacheManager
    from karate_graph_analyzer.parser.feature_parser import FeatureFileParser

logger = logging.getLogger(__name__)


class GraphBuilder:
    """Facade for constructing dependency graphs."""

    def __init__(
        self,
        parser: Optional["FeatureFileParser"] = None,
        config: Optional[ParserConfig] = None,
        include_structural_nodes: bool = False,
    ) -> None:
        self.nx_builder = NetworkXBuilder()
        # Default context if no project yet
        self.context: Optional[AnalysisContext] = None
        self.config = config or (parser.config if parser else ParserConfig())
        self.include_structural_nodes = include_structural_nodes
        self.path_classifier = PathClassifier()
        self.structural_builder = (
            StructuralBuilder(self.nx_builder) if include_structural_nodes else None
        )
        self.dependency_linker = DependencyLinker(
            self.nx_builder,
            path_classifier=self.path_classifier,
            structural_builder=self.structural_builder,
        )
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

    def _initialize_context(self, project: Project, clear_graph: bool = True):
        """Shared initialization logic for building graphs."""
        if clear_graph:
            self.nx_builder.graph = nx.DiGraph()
        self.context = AnalysisContext(project)
        self.config = self.context.config
        
        # Inject context into dependent components
        self.path_classifier.context = self.context
        self.dependency_linker.context = self.context
        self.dependency_linker.path_classifier = self.path_classifier
        self.dependency_linker.structural_builder = self.structural_builder
        
        return self._injected_parser or self._create_default_parser(project)

    def build_from_project(self, project: Project) -> DependencyGraph:
        """Build complete graph for a project using 2-pass strategy."""
        parser = self._initialize_context(project)
        # Build structural layer first when explicitly requested.
        if self.structural_builder:
            self.structural_builder.build_structure(project)
        
        feature_files = self._get_feature_files(project)

        if self._should_use_streaming_scan(project, len(feature_files)):
            logger.info(
                "Using streaming scan for project '%s' with %d feature files",
                project.name,
                len(feature_files),
            )
            return self._build_from_feature_files_streaming(project, parser, feature_files)

        ast_list, ignored_files = self._parse_feature_files(parser, project, feature_files)
        self._set_ignored_files(ignored_files)

        return self.build_from_asts(project, ast_list, clear_graph=False)

    def build_from_asts(self, project: Project, ast_list: List[FeatureAST], clear_graph: bool = True) -> DependencyGraph:
        """Build a graph from pre-parsed ASTs using the same 2-pass strategy."""
        parser = self._initialize_context(project, clear_graph=clear_graph)

        # Pass 1: Extract API definitions from COMMON components
        common_api_map: Dict[Tuple[str, str], List] = {}
        for ast in ast_list:
            self._collect_common_api_map(ast, parser, project, common_api_map)

        # Pass 2: Build reusable JavaScript structure before linking features.
        # This lets feature dependencies point at both the JS file and callable export.
        node_map: Dict[Tuple, str] = {}
        self._process_javascript_files(project, node_map)
        for ast in ast_list:
            self._process_ast_nodes(ast, parser, project, common_api_map, node_map)

        return self._create_final_graph(project.name, project.root_path)

    def _parse_feature_files(
        self,
        parser,
        project: Project,
        feature_files: List[str],
    ) -> Tuple[List[FeatureAST], Set[str]]:
        ast_list: List[FeatureAST] = []
        ignored_files: Set[str] = set()
        total = len(feature_files)
        log_every = self._scan_log_every(project)

        for index, path in enumerate(feature_files, start=1):
            self._log_scan_progress("Parsing feature files", project.name, index, total, log_every)
            logger.debug("Processing feature file: %s", path)
            try:
                ast = parser.parse_file(path)
                if not ast.scenarios:
                    logger.warning("File skipped (no scenarios found): %s", path)
                    ignored_files.add(PathResolver.normalize_path(path))
                else:
                    logger.debug("Successfully parsed: %s (%d scenarios)", path, len(ast.scenarios))
                    ast_list.append(ast)
            except Exception as exc:
                logger.error("Failed to parse %s: %s", path, exc)
                ignored_files.add(PathResolver.normalize_path(path))

        logger.info(
            "Parsed %d/%d feature files for project '%s' (%d skipped)",
            len(ast_list),
            total,
            project.name,
            len(ignored_files),
        )
        return ast_list, ignored_files

    def _build_from_feature_files_streaming(
        self,
        project: Project,
        parser,
        feature_files: List[str],
    ) -> DependencyGraph:
        ignored_files: Set[str] = set()
        common_api_map: Dict[Tuple[str, str], List] = {}
        total = len(feature_files)
        log_every = self._scan_log_every(project)

        for index, path in enumerate(feature_files, start=1):
            self._log_scan_progress("Indexing reusable feature APIs", project.name, index, total, log_every)
            if not self._is_common_candidate_path(path, project):
                continue
            try:
                ast = parser.parse_file(path)
                if not ast.scenarios:
                    ignored_files.add(PathResolver.normalize_path(path))
                    continue
                self._collect_common_api_map(ast, parser, project, common_api_map)
            except Exception as exc:
                logger.error("Failed to parse reusable feature %s: %s", path, exc)
                ignored_files.add(PathResolver.normalize_path(path))

        self._set_ignored_files(ignored_files)
        node_map: Dict[Tuple, str] = {}
        self._process_javascript_files(project, node_map)

        processed_count = 0
        for index, path in enumerate(feature_files, start=1):
            self._log_scan_progress("Building graph from feature files", project.name, index, total, log_every)
            norm_path = PathResolver.normalize_path(path)
            if norm_path in ignored_files:
                continue
            try:
                ast = parser.parse_file(path)
                if not ast.scenarios:
                    ignored_files.add(norm_path)
                    continue
                self._process_ast_nodes(ast, parser, project, common_api_map, node_map)
                processed_count += 1
            except Exception as exc:
                logger.error("Failed to process feature %s: %s", path, exc)
                ignored_files.add(norm_path)

        self._set_ignored_files(ignored_files)
        logger.info(
            "Streaming scan processed %d/%d feature files for project '%s' (%d skipped)",
            processed_count,
            total,
            project.name,
            len(ignored_files),
        )
        return self._create_final_graph(project.name, project.root_path)

    def _collect_common_api_map(
        self,
        ast: FeatureAST,
        parser,
        project: Project,
        common_api_map: Dict[Tuple[str, str], List],
    ) -> None:
        norm_path = PathResolver.normalize_path(ast.file_path)
        for scenario in ast.scenarios:
            if self.path_classifier.classify_scenario_by_path(scenario.file_path, project.parser_config) != NodeType.COMMON:
                continue

            deps = parser.extract_dependencies_with_background(scenario, ast.background_steps)
            api_deps = [d for d in deps if d.type == DependencyType.API]
            for dep in api_deps:
                dep.parameters["file_path"] = scenario.file_path

            keys = [(norm_path, tag) for tag in scenario.tags] or [(norm_path, "")]
            for key in keys:
                common_api_map[key] = api_deps

    def _should_use_streaming_scan(self, project: Project, feature_count: int) -> bool:
        config = project.parser_config
        if getattr(config, "large_project_streaming_scan", False):
            return True
        threshold = getattr(config, "large_project_streaming_threshold", 0) or 0
        return threshold > 0 and feature_count >= threshold

    def _is_common_candidate_path(self, path: str, project: Project) -> bool:
        return self.path_classifier.classify_scenario_by_path(path, project.parser_config) == NodeType.COMMON

    def _set_ignored_files(self, ignored_files: Set[str]) -> None:
        self._ignored_files = ignored_files
        self.dependency_linker.ignored_files = ignored_files

    def _scan_log_every(self, project: Project) -> int:
        return max(1, int(getattr(project.parser_config, "scan_log_every", 1000) or 1000))

    def _log_scan_progress(
        self,
        label: str,
        project_name: str,
        index: int,
        total: int,
        log_every: int,
    ) -> None:
        if total == 0:
            return
        if index == 1 or index == total or index % log_every == 0:
            logger.info("%s for project '%s': %d/%d", label, project_name, index, total)

    def _process_ast_nodes(self, ast: FeatureAST, parser, project, common_map, node_map):
        for scenario in ast.scenarios:
            try:
                node_type = self.path_classifier.classify_scenario_by_path(scenario.file_path, project.parser_config)
                # We process all types now to ensure orphan common/page files are visible
                
                context = PathContext(scenario.file_path, project.root_path, project.parser_config)
                
                # Resolve category and flow
                category = self.path_classifier.classify_component_category(scenario.file_path)
                flow = self.path_classifier.resolve_flow(node_type)

                metadata = NodeMetadata(
                    file_path=scenario.file_path, line_number=scenario.line_number,
                    jira_tags=scenario.jira_tags, project_name=project.name,
                    category=category,
                    flow=flow,
                    additional_data={
                        "scenario_type": scenario.type.value,
                        "tags": scenario.tags,
                        "display_jira_prefix": False,
                    },
                )

                if node_type == NodeType.API:
                    # APIs in non-common files register their info in pass 2
                    deps = parser.extract_dependencies_with_background(scenario, ast.background_steps)
                    for d in [d for d in deps if d.type == DependencyType.API]:
                        d.parameters.update({"scenario_name": scenario.name, "scenario_tags": scenario.tags})
                        self.dependency_linker.get_or_create_dependency_node(d, project.name, node_map, context=context)
                    continue
                
                # Add business domain classification (Prioritize Tags, fallback to path)
                if self.path_classifier and scenario.file_path:
                    feature = self.path_classifier.detect_business_domain(scenario.file_path, scenario.tags)
                    metadata.additional_data['feature'] = feature
                
                # Create main node
                node_id = self._create_typed_node(node_type, scenario, metadata, node_map)
                
                # Link dependencies
                self._link_dependencies(scenario, ast, parser, project, node_id, common_map, node_map, context)
                self._link_implicit_karate_config(project, node_id, node_map)
            except Exception as e:
                logger.error(f"Error processing scenario {scenario.name} in {ast.file_path}: {e}", exc_info=True)

    def _create_typed_node(self, node_type: NodeType, scenario: Scenario, metadata: NodeMetadata, node_map: Dict) -> str:
        if node_type == NodeType.PAGE:
            return self._handle_page_and_action(scenario, metadata, node_map)
        
        # For WORKFLOW, COMMON, DATABASE, and DATA, we also want to support subnodes if tags are present
        # to ensure consistency with 'call read' dependencies
        if node_type in [NodeType.WORKFLOW, NodeType.COMMON, NodeType.DATABASE, NodeType.DATA]:
            rel_path = PathResolver.normalize_path(scenario.file_path)
            create_func = self._builder_for_node_type(node_type)

            # Create/get the file node
            file_node_id = self.dependency_linker._get_or_create_node(
                node_type, rel_path, metadata, node_map, create_func
            )
            
            # Use primary tag for subnode identity
            primary_tag = self._get_primary_tag(scenario)
            
            if primary_tag:
                display_name = self.path_classifier.build_scenario_display_name(scenario, node_type)
                
                return self.dependency_linker._handle_tag_subnode(
                    file_node_id, node_type, rel_path, primary_tag, metadata, node_map, 
                    self._dependency_type_for_node_type(node_type), display_name=display_name
                )
            
            # Fallback to file node if no tags
            if self.structural_builder:
                self.structural_builder.link_to_functional_node(scenario.file_path, file_node_id)
            return file_node_id
            
        node_id = self.nx_builder.add_test_case(scenario, metadata)
        if self.structural_builder:
            self.structural_builder.link_to_functional_node(scenario.file_path, node_id)
        return node_id

    def _builder_for_node_type(self, node_type: NodeType):
        return {
            NodeType.WORKFLOW: self.nx_builder.add_workflow_node,
            NodeType.COMMON: self.nx_builder.add_common_node,
            NodeType.DATABASE: self.nx_builder.add_database_node,
            NodeType.DATA: self.nx_builder.add_data_node,
        }.get(node_type, self.nx_builder.add_test_case)

    def _dependency_type_for_node_type(self, node_type: NodeType) -> DependencyType:
        return {
            NodeType.COMMON: DependencyType.COMMON,
            NodeType.DATABASE: DependencyType.DATABASE,
            NodeType.DATA: DependencyType.DATA,
            NodeType.PAGE: DependencyType.PAGE,
        }.get(node_type, DependencyType.WORKFLOW)

    def _get_primary_tag(self, scenario: Scenario) -> str:
        if self.context and self.context.tag_manager:
            return self.context.tag_manager.get_primary_tag(scenario.tags)
        return ""

    def _handle_page_and_action(self, scenario: Scenario, metadata: NodeMetadata, node_map: Dict) -> str:
        rel_path = PathResolver.normalize_path(scenario.file_path)
        file_node_id = self.dependency_linker._get_or_create_node(
            NodeType.PAGE, rel_path, metadata, node_map, self.nx_builder.add_page_node
        )
        
        # Identity tag
        primary_tag = self._get_primary_tag(scenario)
        
        # Display name
        display_name = self.path_classifier.build_scenario_display_name(scenario, NodeType.PAGE)
        
        # If no primary tag, use the display name as a fallback tag (legacy behavior)
        tag_to_use = primary_tag or display_name
        
        res_id = self.dependency_linker._handle_tag_subnode(
            file_node_id, NodeType.PAGE, rel_path, tag_to_use, metadata, node_map,
            self._dependency_type_for_node_type(NodeType.PAGE),
            display_name=display_name
        )
        if self.structural_builder:
            self.structural_builder.link_to_functional_node(scenario.file_path, res_id)
        return res_id

    def _link_dependencies(self, scenario, ast, parser, project, node_id, common_map, node_map, context):
        deps = parser.extract_dependencies_with_background(scenario, ast.background_steps)
        for dep in deps:
            if dep.type == DependencyType.COMMON:
                self._link_common_dependency(node_id, dep, project.name, common_map, node_map, context)
            else:
                dep_id = self.dependency_linker.get_or_create_dependency_node(dep, project.name, node_map, context=context)
                if dep_id:
                    self.nx_builder.add_dependency(node_id, dep_id, dep.type, line_number=dep.line_number)
                    if dep.type == DependencyType.JAVASCRIPT:
                        self._link_javascript_callable(node_id, dep_id, dep.line_number, dep.parameters.get("function_name"))

    def _link_common_dependency(self, node_id, dep, project_name, common_map, node_map, context):
        tag = dep.parameters.get("scenario_tag", "")
        if tag and not tag.startswith("@"): tag = "@" + tag
        
        target_norm = PathResolver.normalize_path(dep.target)
        api_deps = next((common_map[k] for k in common_map if k[0].endswith(target_norm) and k[1] == tag), None)

        common_dep_id = self.dependency_linker.get_or_create_dependency_node(dep, project_name, node_map, context=context)
        if common_dep_id:
            self.nx_builder.add_dependency(node_id, common_dep_id, dep.type, line_number=dep.line_number)
            
            if api_deps:
                for api_dep in api_deps:
                    dep_id = self.dependency_linker.get_or_create_dependency_node(api_dep, project_name, node_map, context=context)
                    if dep_id:
                        self.nx_builder.add_dependency(node_id, dep_id, api_dep.type, line_number=dep.line_number)

    def _get_feature_files(self, project: Project) -> List[str]:
        files = []
        for pattern in project.feature_file_patterns:
            for match in self._iter_project_matches(project, pattern):
                files.append(match)
        return sorted(set(files))

    def _process_javascript_files(self, project: Project, node_map: Dict[Tuple, str]) -> None:
        extractor = JavaScriptStructureExtractor()
        structures = {}
        for script_path in self._get_javascript_files(project):
            norm_path = PathResolver.normalize_path(script_path)
            if norm_path in getattr(self, "_ignored_files", set()):
                continue

            metadata = self._build_javascript_metadata(project, script_path, norm_path, line_number=1)
            script_id = self.dependency_linker._get_or_create_node(
                NodeType.JAVASCRIPT,
                norm_path,
                metadata,
                node_map,
                self.nx_builder.add_javascript_node,
            )
            if self.structural_builder:
                self.structural_builder.link_to_functional_node(script_path, script_id)

            try:
                structure = extractor.parse_file(script_path)
            except OSError as exc:
                logger.warning(f"Failed to parse JavaScript file {script_path}: {exc}")
                continue
            structures[script_path] = structure

            for function in structure.functions:
                function_identity = f"{norm_path}#{function.name}:{function.line_number}"
                function_metadata = self._build_javascript_metadata(
                    project,
                    script_path,
                    norm_path,
                    line_number=function.line_number,
                    additional_data={
                        "script_path": norm_path,
                        "function_name": function.name,
                        "function_kind": function.kind,
                    },
                )
                function_id = self.dependency_linker._get_or_create_node(
                    NodeType.JS_FUNCTION,
                    function_identity,
                    function_metadata,
                    node_map,
                    self.nx_builder.add_js_function_node,
                )
                self.nx_builder.add_dependency(script_id, function_id, DependencyType.CONTAINS)

            default_function_id = self._resolve_default_js_function_id(norm_path, structure.functions, node_map)
            if default_function_id and script_id in self.nx_builder.graph.nodes:
                self.nx_builder.graph.nodes[script_id]["metadata"]["additional_data"][
                    "default_function_node_id"
                ] = default_function_id

        dependency_extractor = CallReadExtractor(project.parser_config)
        for script_path in structures:
            norm_path = PathResolver.normalize_path(script_path)
            script_id = node_map.get((NodeType.JAVASCRIPT, norm_path))
            if not script_id:
                continue
            context = PathContext(script_path, project.root_path, project.parser_config)
            for dep in self._extract_javascript_dependencies(script_path, dependency_extractor):
                dep.parameters["source_language"] = "javascript"
                dep_id = self.dependency_linker.get_or_create_dependency_node(
                    dep,
                    project.name,
                    node_map,
                    context=context,
                )
                if dep_id:
                    self.nx_builder.add_dependency(script_id, dep_id, dep.type, line_number=dep.line_number)
                    if dep.type == DependencyType.JAVASCRIPT:
                        self._link_javascript_callable(script_id, dep_id, dep.line_number)

    def _get_javascript_files(self, project: Project) -> List[str]:
        files = []
        patterns = getattr(project.parser_config, "javascript_file_patterns", ["**/*.js"]) or []
        for pattern in patterns:
            for match in self._iter_project_matches(project, pattern):
                files.append(match)
        return sorted(set(files))

    def _iter_project_matches(self, project: Project, pattern: str):
        full_pattern = os.path.join(project.root_path, pattern)
        for match in glob.iglob(full_pattern, recursive=True):
            if not is_excluded_path(match, project.parser_config):
                yield match

    def _build_javascript_metadata(
        self,
        project: Project,
        script_path: str,
        norm_path: str,
        line_number: int,
        additional_data: Optional[Dict[str, Any]] = None,
    ) -> NodeMetadata:
        category = self.path_classifier.classify_component_category(script_path)
        flow = self.path_classifier.resolve_flow(NodeType.JAVASCRIPT)
        data = {
            "file_path": norm_path,
            "feature": self.path_classifier.detect_business_domain(script_path),
        }
        if additional_data:
            data.update(additional_data)
        return NodeMetadata(
            file_path=script_path,
            line_number=line_number,
            jira_tags=[],
            project_name=project.name,
            category=category,
            flow=flow,
            additional_data=data,
        )

    def _extract_javascript_dependencies(
        self,
        script_path: str,
        dependency_extractor: CallReadExtractor,
    ) -> List[Any]:
        dependencies = []
        try:
            with open(script_path, "r", encoding="utf-8") as handle:
                lines = handle.readlines()
        except UnicodeDecodeError:
            with open(script_path, "r", encoding="utf-8", errors="ignore") as handle:
                lines = handle.readlines()
        except OSError as exc:
            logger.warning(f"Failed to read JavaScript dependencies from {script_path}: {exc}")
            return dependencies

        for line_number, line in enumerate(lines, start=1):
            if dependency_extractor.can_extract(line):
                dependencies.extend(dependency_extractor.extract(line, line_number))
        return dependencies

    def _resolve_default_js_function_id(
        self,
        norm_path: str,
        functions: List[Any],
        node_map: Dict[Tuple, str],
    ) -> Optional[str]:
        if not functions:
            return None

        candidates = sorted(
            functions,
            key=lambda f: (
                0 if f.kind == "module_exports_function" else 1,
                0 if f.name == "fn" else 1,
                0 if len(functions) == 1 else 1,
                f.line_number,
            ),
        )
        selected = candidates[0]
        identity = f"{norm_path}#{selected.name}:{selected.line_number}"
        return node_map.get((NodeType.JS_FUNCTION, identity))

    def _link_javascript_callable(
        self,
        from_node_id: str,
        script_node_id: str,
        line_number: Optional[int],
        function_name: Optional[str] = None,
    ) -> None:
        script_node = self.nx_builder.graph.nodes.get(script_node_id)
        if not script_node:
            return
        function_id = None
        if function_name:
            for candidate_id in self.nx_builder.graph.successors(script_node_id):
                candidate = self.nx_builder.graph.nodes.get(candidate_id)
                if candidate and candidate.get("type") == NodeType.JS_FUNCTION and candidate.get("name") == function_name:
                    function_id = candidate_id
                    break
        if not function_id:
            function_id = script_node.get("metadata", {}).get("additional_data", {}).get("default_function_node_id")
        if function_id and function_id in self.nx_builder.graph.nodes:
            self.nx_builder.add_dependency(from_node_id, function_id, DependencyType.JAVASCRIPT, line_number=line_number)

    def _link_implicit_karate_config(self, project: Project, from_node_id: str, node_map: Dict[Tuple, str]) -> None:
        config_paths = [
            os.path.join(project.root_path, "karate-config.js"),
            os.path.join(project.root_path, "src", "test", "java", "karate-config.js"),
            os.path.join(project.root_path, "src", "test", "resources", "karate-config.js"),
        ]
        for config_path in config_paths:
            if not os.path.exists(config_path):
                continue
            norm_path = PathResolver.normalize_path(config_path)
            script_id = node_map.get((NodeType.JAVASCRIPT, norm_path))
            if script_id:
                self.nx_builder.add_dependency(from_node_id, script_id, DependencyType.JAVASCRIPT)
                self._link_javascript_callable(from_node_id, script_id, line_number=None)
            return

    def _create_default_parser(self, project: Project):
        from karate_graph_analyzer.parser.feature_parser import FeatureFileParser
        return FeatureFileParser(config=project.parser_config)

    def _create_final_graph(self, project_name: str, project_root: str = None) -> DependencyGraph:
        cycles = self._detect_cycles_for_final_graph()
        nodes_dict = {}
        for nid, nd in self.nx_builder.graph.nodes(data=True):
            if "metadata" not in nd:
                logger.warning(f"Skipping node missing metadata: {nid}")
                continue
            # Extract metadata and preserve category/flow
            metadata_dict = nd["metadata"].copy()
            p_name = metadata_dict.pop("project_name", project_name)
            
            # Ensure category and flow are preserved during reconstruction
            category = metadata_dict.pop("category", ComponentCategory.UNKNOWN)
            flow = metadata_dict.pop("flow", FlowType.UNKNOWN)
            
            meta = NodeMetadata(
                **{k: v for k, v in metadata_dict.items() if k in NodeMetadata.__dataclass_fields__},
                project_name=p_name,
                category=category,
                flow=flow
            )
            
            if nd["type"] == NodeType.LOCATOR.value and project_root and meta.file_path:
                self._enrich_locator_metadata(meta, project_root)

            nodes_dict[nid] = Node(id=nd["id"], type=nd["type"], name=nd["name"], metadata=meta, tags=nd.get("tags", []))
            
        edges_dict = {}
        for _, _, ed in self.nx_builder.graph.edges(data=True):
            if ed["from_node"] in nodes_dict and ed["to_node"] in nodes_dict:
                edges_dict[ed["id"]] = Edge(
                    id=ed["id"], 
                    from_node=ed["from_node"], 
                    to_node=ed["to_node"], 
                    type=ed["type"], 
                    line_number=ed.get("line_number")
                )
        return DependencyGraph(
            project_name=project_name, 
            nodes=nodes_dict, 
            edges=edges_dict, 
            cycles=cycles,
            config=self.config,
            include_structural_nodes=self.include_structural_nodes
        )

    def _detect_cycles_for_final_graph(self) -> List[List[str]]:
        if not getattr(self.config, "cycle_detection_enabled", True):
            self.nx_builder.graph.graph["cycles"] = []
            return []

        node_limit = getattr(self.config, "cycle_detection_node_limit", 20000) or 0
        node_count = self.nx_builder.graph.number_of_nodes()
        if node_limit > 0 and node_count > node_limit:
            logger.warning(
                "Skipping full cycle detection for large graph (%d nodes > limit %d)",
                node_count,
                node_limit,
            )
            self.nx_builder.graph.graph["cycles"] = []
            return []

        return self.nx_builder.detect_cycles()

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
