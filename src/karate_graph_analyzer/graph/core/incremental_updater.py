"""
Incremental Updater.

Handles incremental updates to the dependency graph by only re-parsing
changed or new files.
"""

import os
import glob
import logging
import networkx as nx
from typing import TYPE_CHECKING, Dict, List

from karate_graph_analyzer.models import (
    DependencyGraph,
    DependencyType,
    Node,
    Edge,
    NodeMetadata,
    NodeType,
    ParseError,
)

if TYPE_CHECKING:
    from karate_graph_analyzer.cache.cache_manager import CacheManager
    from karate_graph_analyzer.models import Project

logger = logging.getLogger(__name__)


class IncrementalUpdater:
    """Handles incremental graph updates."""

    def __init__(self, nx_builder, path_classifier, dependency_linker) -> None:
        """Initialize with helper instances."""
        self.nx_builder = nx_builder
        self.path_classifier = path_classifier
        self.dependency_linker = dependency_linker

    def update_from_project(
        self, 
        project: "Project", 
        existing_graph: DependencyGraph,
        cache_manager: "CacheManager",
        parser
    ) -> DependencyGraph:
        """Incrementally update graph for changed files in a project."""
        feature_files = []
        for pattern in project.feature_file_patterns:
            full_pattern = os.path.join(project.root_path, pattern)
            matched_files = glob.glob(full_pattern, recursive=True)
            feature_files.extend(matched_files)
        
        feature_files = sorted(set(feature_files))
        
        changed_files = []
        for file_path in feature_files:
            cached_ast = cache_manager.get(file_path)
            if cached_ast is None:
                changed_files.append(file_path)
        
        if not changed_files:
            logger.info(f"No file changes detected for project '{project.name}'")
            return existing_graph
        
        logger.info(f"Detected {len(changed_files)} changed files in project '{project.name}'")
        
        # Reset graph and counters
        self.nx_builder.graph = nx.DiGraph()
        self.nx_builder._node_counter = {}
        
        # Restore existing nodes and edges
        for node_id, node in existing_graph.nodes.items():
            parts = node_id.split('_')
            if len(parts) == 2:
                prefix = parts[0]
                try:
                    counter = int(parts[1])
                    if prefix not in self.nx_builder._node_counter:
                        self.nx_builder._node_counter[prefix] = 0
                    self.nx_builder._node_counter[prefix] = max(self.nx_builder._node_counter[prefix], counter)
                except ValueError:
                    pass
            
            node_data = {
                "id": node.id,
                "type": node.type,
                "name": node.name,
                "metadata": {
                    "file_path": node.metadata.file_path,
                    "line_number": node.metadata.line_number,
                    "jira_tags": node.metadata.jira_tags,
                    "project_name": node.metadata.project_name,
                    "additional_data": node.metadata.additional_data,
                },
            }
            self.nx_builder.graph.add_node(node_id, **node_data)
        
        for edge_id, edge in existing_graph.edges.items():
            edge_data = {
                "id": edge.id,
                "from_node": edge.from_node,
                "to_node": edge.to_node,
                "type": edge.type,
            }
            self.nx_builder.graph.add_edge(edge.from_node, edge.to_node, **edge_data)
        
        dependency_node_map: Dict[tuple, str] = {}
        for node_id, node in existing_graph.nodes.items():
            if node.type != NodeType.TEST_CASE:
                node_key = (node.type, node.name)
                dependency_node_map[node_key] = node_id
        
        # Remove nodes from changed files
        nodes_to_remove = []
        for node_id, node_data in self.nx_builder.graph.nodes(data=True):
            file_path = node_data.get("metadata", {}).get("file_path")
            if file_path in changed_files:
                nodes_to_remove.append(node_id)
        
        for node_id in nodes_to_remove:
            node_data = self.nx_builder.graph.nodes[node_id]
            node_key = (node_data["type"], node_data["name"])
            if node_key in dependency_node_map:
                del dependency_node_map[node_key]
            self.nx_builder.graph.remove_node(node_id)
        
        logger.info(f"Removed {len(nodes_to_remove)} nodes from changed files")
        
        # Remove orphaned dependency nodes
        orphaned_nodes = [
            node_id for node_id, node_data in self.nx_builder.graph.nodes(data=True)
            if node_data["type"] != NodeType.TEST_CASE and self.nx_builder.graph.in_degree(node_id) == 0
        ]
        
        for node_id in orphaned_nodes:
            node_data = self.nx_builder.graph.nodes[node_id]
            node_key = (node_data["type"], node_data["name"])
            if node_key in dependency_node_map:
                del dependency_node_map[node_key]
            self.nx_builder.graph.remove_node(node_id)
        
        if orphaned_nodes:
            logger.info(f"Removed {len(orphaned_nodes)} orphaned dependency nodes")
        
        # Re-parse changed files
        for file_path in changed_files:
            try:
                ast = parser.parse_file(file_path)
                cache_manager.put(file_path, ast)
                
                # Classify file
                file_node_type = self.path_classifier.classify_scenario_by_path(file_path, project.parser_config)
                
                if file_node_type == NodeType.COMMON:
                    # For COMMON files, we don't add nodes, but we should ideally update the API map.
                    # For now, we skip adding nodes for scenarios in COMMON files.
                    continue
                
                for scenario in ast.scenarios:
                    scenario_node_type = self.path_classifier.classify_scenario_by_path(
                        scenario.file_path, project.parser_config
                    )
                    
                    if scenario_node_type == NodeType.COMMON:
                        continue
                        
                    test_case_metadata = NodeMetadata(
                        file_path=scenario.file_path,
                        line_number=scenario.line_number,
                        jira_tags=scenario.jira_tags,
                        project_name=project.name,
                        additional_data={
                            "scenario_type": scenario.type.value,
                            "tags": scenario.tags,
                        },
                    )
                    
                    test_case_id = self.nx_builder.add_test_case(scenario, test_case_metadata)
                    
                    dependencies = parser.extract_dependencies_with_background(
                        scenario, ast.background_steps, validate_paths=False
                    )
                    
                    for dep in dependencies:
                        if dep.type == DependencyType.COMMON:
                            # In incremental mode, we don't have the full common_api_deps_map.
                            # Fallback: link to the workflow node if it exists, or skip.
                            # For robustness, we'll try to get it as a workflow node.
                            try:
                                dep_node_id = self.dependency_linker.get_or_create_dependency_node(
                                    dep, project.name, dependency_node_map
                                )
                                self.nx_builder.add_dependency(test_case_id, dep_node_id, dep.type)
                            except Exception as e:
                                logger.warning(f"Could not link COMMON dependency in incremental mode: {e}")
                        else:
                            dep_node_id = self.dependency_linker.get_or_create_dependency_node(
                                dep, project.name, dependency_node_map
                            )
                            self.nx_builder.add_dependency(test_case_id, dep_node_id, dep.type)
            
            except ParseError as e:
                logger.error(f"Failed to parse {file_path}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error processing {file_path}: {e}")
        
        cycles = self.nx_builder.detect_cycles()
        
        # Build final DependencyGraph object
        nodes_dict = {}
        for node_id in self.nx_builder.graph.nodes():
            node_data = self.nx_builder.graph.nodes[node_id]
            nodes_dict[node_id] = Node(
                id=node_data["id"],
                type=node_data["type"],
                name=node_data["name"],
                metadata=NodeMetadata(
                    file_path=node_data["metadata"].get("file_path"),
                    line_number=node_data["metadata"].get("line_number"),
                    jira_tags=node_data["metadata"].get("jira_tags", []),
                    project_name=node_data["metadata"].get("project_name", project.name),
                    additional_data=node_data["metadata"].get("additional_data", {}),
                ),
            )
        
        edges_dict = {}
        for from_node, to_node in self.nx_builder.graph.edges():
            edge_data = self.nx_builder.graph.edges[from_node, to_node]
            edge_id = edge_data["id"]
            edges_dict[edge_id] = Edge(
                id=edge_id,
                from_node=edge_data["from_node"],
                to_node=edge_data["to_node"],
                type=edge_data["type"],
            )
        
        return DependencyGraph(
            project_name=project.name,
            nodes=nodes_dict,
            edges=edges_dict,
            cycles=cycles,
        )
